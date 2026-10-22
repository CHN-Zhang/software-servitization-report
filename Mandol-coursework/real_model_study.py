"""Evaluate archived real model responses with original parser/postprocessing.

Collection uses the original prompt. No API key is stored here or in outputs.
"""
import ast
import copy
import hashlib
import json
from pathlib import Path

from experiment import BaselineHarness, ConservativeMerger, SOURCE
from small_study import DATA, ORIGINAL, make_units, score_outputs, summarize, interval

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results/real_model"


def original_parser():
    cls = next(n for n in ast.parse(SOURCE.read_text(encoding="utf-8")).body
               if isinstance(n, ast.ClassDef) and n.name == "HierarchicalAutoBuilder")
    method = copy.deepcopy(next(n for n in cls.body if isinstance(n, ast.FunctionDef)
                                and n.name == "_safe_parse_json"))
    namespace = {"json": json, "Optional": __import__("typing").Optional,
                 "Dict": __import__("typing").Dict, "Any": __import__("typing").Any}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace["_safe_parse_json"]


class Replay(BaselineHarness):
    _safe_parse_json = original_parser()

    def _call_llm_with_retry(self, **kwargs):
        return self.response


def main():
    cases = {c["id"]: c for c in json.loads(DATA.read_text(encoding="utf-8"))["cases"] if c["split"] == "test"}
    responses = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((OUT / "responses").glob("*.json"))]
    if len(responses) != len(cases) * 2:
        raise RuntimeError("Incomplete collection; do not silently evaluate partial results")
    records, failures = [], []
    seen = set()
    for response in responses:
        identity = (response["case_id"], response["reverse"])
        assert identity not in seen
        seen.add(identity)
        case = cases[response["case_id"]]
        reverse = response["reverse"]
        harness = Replay(response.get("content", ""))
        parsed = harness._safe_parse_json(harness.response)
        if (response.get("status") != 200 or response.get("finish_reason") != "stop"
                or not isinstance(parsed, dict)
                or not isinstance(parsed.get("merged_items"), list)
                or not isinstance(parsed.get("unique_items"), list)):
            failures.append({"case_id": case["id"], "reverse": reverse,
                             "status": response.get("status"), "finish_reason": response.get("finish_reason")})
            continue
        # Do not let malformed merge groups silently change the denominator.
        if any(not isinstance(g, dict) or not isinstance(g.get("merged_from"), list)
               or any(not isinstance(uid, str) for uid in g["merged_from"])
               for g in parsed["merged_items"]) or any(not isinstance(uid, str) for uid in parsed["unique_items"]):
            failures.append({"case_id": case["id"], "reverse": reverse, "status": "invalid_schema"})
            continue
        units = make_units(case, reverse)
        baseline = ORIGINAL(harness, copy.deepcopy(units))
        improved, plans = ConservativeMerger().merge(copy.deepcopy(units), parsed)
        for method, output in [("original", baseline), ("conservative", improved)]:
            record = score_outputs(case, reverse, method, output)
            record["case_id"] = case["id"]
            records.append(record)
    if not records:
        raise RuntimeError("No valid responses")
    summaries = {}
    for method in ["original", "conservative"]:
        rows = [r for r in records if r["method"] == method]
        summaries[method] = summarize(rows)
        summaries[method]["exploratory_pair_bootstrap_95ci"] = {
            key: interval(rows, key) for key in ["fact_retention", "unsafe_merge_rate"]}
    usage = {key: sum(r.get("usage", {}).get(key, 0) for r in responses)
             for key in ["prompt_tokens", "completion_tokens", "total_tokens"]}
    result = {
        "scope": "real model proposals, isolated original parser and postprocessing; not full Mandol runtime",
        "dataset_sha256": hashlib.sha256(DATA.read_bytes()).hexdigest(),
        "annotation_status": "AI-authored provisional synthetic gold; human review pending",
        "collection_count": len(responses), "valid_response_count": len(records) // 2,
        "failed_responses": failures, "usage": usage,
        "model_names": sorted({r.get("model", "") for r in responses}),
        "summary": summaries, "runs": records,
    }
    (OUT / "evaluated.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 真实模型小规模评测", "", "使用 qwen3.6-flash、原项目L1去重提示词。每组同一份真实返回值分别交给原后处理与保守原型。",
             "32组评测样例，各交换输入顺序一次，共64次调用。不是64条独立样例，没有重复采样稳定性结论。", "",
             f"有效返回 {len(records)//2}/{len(responses)}；失败 {len(failures)}。以下质量指标按有效返回计算，失败单独列出，不算成成功保留。", "",
             "| 方法 | 合并精确率 | 合并召回率 | 不可合并样例误合并率 | 标注事实保留 | 来源覆盖 | 文本字符减少 |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for method, label in [("original", "真实返回＋原后处理"), ("conservative", "同一返回＋保守原型")]:
        s = summaries[method]
        cells = ["—" if s[k] is None else f"{s[k]:.1%}" for k in ["merge_precision", "merge_recall", "unsafe_merge_rate", "fact_retention", "source_retention", "char_reduction"]]
        lines.append("| " + label + " | " + " | ".join(cells) + " |")
    lines += ["", "## 原型的误合并记录", ""]
    bad = [r for r in records if r["method"] == "conservative" and r["merged"] and not r["mergeable"]]
    lines += [f'- {r["case_id"]}，reverse={r["reverse"]}，事实保留 {r["fact_retention"]:.0%}。' for r in bad] or ["本轮未观察到；不代表不会发生。"]
    lines += ["", "## 范围和限制", "", "样例为人工合成、AI初始标注，未经独立人工复核；与离线规则评测使用同一评测集，规则没有根据本轮结果调整。",
              "模型只看原提示词中的ID和文本前500字符，不接触标签或事实ID；后处理还可以读取原对象的主体等元数据。",
              "事实指标适用于当前选择已有原文的输出。模型生成的result字段没有作为新的摘要写入，因为原方法本身没有采用该字段。",
              "来源覆盖只检查ID，不验证逐事实证据。字符减少不代表内存或总存储减少。未评测L2、持久化及下游问答。",
              "模型别名可能随平台更新；保留了平台返回的model、响应ID、参数、时间和原始回答内容，无法保证远端权重永久固定。",
              "没有保存密钥和模型思考内容。接口耗时与token用量保存在响应文件中，不对小样本网络时延作性能结论。",
              f"本轮接口计量总用量：{usage['total_tokens']} tokens；未计算金额。"]
    (OUT / "真实模型评测结果.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Evaluated {len(records)//2}/{len(responses)} responses; failures={len(failures)}")


if __name__ == "__main__":
    main()
