"""Collect a fresh real-model run. Key is read from environment, never saved."""
import argparse
import ast
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from string import Template
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="results/real_model_new")
    parser.add_argument("--model", default="qwen3.6-flash")
    args = parser.parse_args()
    key = os.environ.get("DASHSCOPE_API_KEY")
    if not key:
        raise SystemExit("Set DASHSCOPE_API_KEY locally before collecting; do not put it in project files.")
    base = os.environ.get("DASHSCOPE_BASE_URL", "https://cn-beijing.maas.qianwenaiapi.com/compatible-mode/v1").rstrip("/")
    target = (ROOT / args.output).resolve()
    if target.exists():
        raise SystemExit("Output directory exists; select a fresh directory to preserve old results.")
    (target / "responses").mkdir(parents=True)
    data_bytes = (ROOT / "data/pilot_pairs.json").read_bytes()
    cases = [c for c in json.loads(data_bytes)["cases"] if c["split"] == "test"]
    source = (ROOT.parent / "Mandol/src/mandol/auto_builder/hierarchical_prompts.py").read_text(encoding="utf-8")
    cls = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == "HierarchicalPromptManager")
    assignment = next(n for n in cls.body if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == "L1_DEDUPLICATION_PROMPT" for t in n.targets))
    prompt = Template(ast.literal_eval(assignment.value))
    settings = {"model": args.model, "temperature": 0.1, "max_tokens": 1000,
                "enable_thinking": False, "stream": False}
    manifest = {"base_url": base, "settings": settings, "requests": len(cases) * 2,
                "dataset_sha256": hashlib.sha256(data_bytes).hexdigest(),
                "prompt_sha256": hashlib.sha256(prompt.template.encode()).hexdigest(),
                "started_at": datetime.now(timezone.utc).isoformat(), "concurrency": 4}
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def collect(job):
        case, reverse = job
        units = list(reversed(case["units"])) if reverse else case["units"]
        text = prompt.safe_substitute(summaries=json.dumps([
            {"id": u["uid"], "content": u["text"][:500]} for u in units], ensure_ascii=False, indent=2))
        record = {"case_id": case["id"], "reverse": reverse, "requested_model": args.model,
                  "started_at": datetime.now(timezone.utc).isoformat(),
                  "prompt_sha256": hashlib.sha256(text.encode()).hexdigest()}
        started = time.monotonic()
        request = urllib.request.Request(base + "/chat/completions",
                  data=json.dumps({**settings, "messages": [{"role": "user", "content": text}]}).encode(),
                  headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                body = json.load(response)
                choice = body.get("choices", [{}])[0]
                record.update(status=response.status, model=body.get("model"), response_id=body.get("id"),
                              finish_reason=choice.get("finish_reason"), content=choice.get("message", {}).get("content", ""),
                              usage=body.get("usage", {}))
        except urllib.error.HTTPError as exc:
            record.update(status=exc.code, error_type="HTTPError")
        except Exception as exc:
            record.update(status="network_error", error_type=type(exc).__name__)
        record["elapsed_ms"] = round((time.monotonic() - started) * 1000)
        filename = case["id"] + ("_reverse.json" if reverse else "_forward.json")
        (target / "responses" / filename).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return record["status"]

    with ThreadPoolExecutor(max_workers=4) as pool:
        statuses = list(pool.map(collect, [(c, r) for c in cases for r in [False, True]]))
    manifest.update(finished_at=datetime.now(timezone.utc).isoformat(), http_success=sum(s == 200 for s in statuses))
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Collected {len(statuses)} calls in {target}; HTTP success={manifest['http_success']}")


if __name__ == "__main__":
    main()
