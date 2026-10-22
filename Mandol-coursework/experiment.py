"""Week 8/9 controlled experiment. Standard library only; no real LLM calls."""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / "Mandol/src/mandol/auto_builder/hierarchical_builder.py"


@dataclass
class Summary:
    session_id: str
    summary_type: str
    content: str
    unit_uid: str
    source_unit_uids: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_structured: bool = False


def load_original_method():
    """Compile the original method's AST, rather than rewriting its logic.

    Only collaborators (LLM, prompt manager and JSON parser) are replaced.
    Importing the whole package would require its ML/storage dependency stack.
    """
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef)
               and n.name == "HierarchicalAutoBuilder")
    method = copy.deepcopy(next(n for n in cls.body if isinstance(n, ast.FunctionDef)
                                and n.name == "deduplicate_l1"))
    module = ast.Module(body=[method], type_ignores=[])
    namespace = {
        "List": List, "Optional": __import__("typing").Optional,
        "Dict": Dict, "L1ExtractionResult": Summary,
        "json": json, "logger": logging.getLogger("controlled_baseline"),
    }
    exec(compile(module, str(SOURCE), "exec"), namespace)
    return namespace["deduplicate_l1"]


class FixedPromptManager:
    @staticmethod
    def get_deduplication_prompt(summaries, custom_prompt=None):
        return summaries


class BaselineHarness:
    def __init__(self, response):
        self.config = SimpleNamespace(enable_deduplication=True)
        self.prompt_manager = FixedPromptManager()
        self.response = response
        self.prompts = []
        self._build_stats = {"dedup_merged": 0}

    def _ensure_llm_client(self):
        pass

    def _call_llm_with_retry(self, **kwargs):
        self.prompts.append(kwargs["prompt"])
        return json.dumps(self.response, ensure_ascii=False)

    def _safe_parse_json(self, text):
        return json.loads(text)


def atoms(text):
    # Conservative literal check, not a semantic equivalence detector.
    return {re.sub(r"\s+", "", part) for part in re.split(r"[;；。\n]+", text)
            if re.sub(r"\s+", "", part)}


@dataclass
class MergePlan:
    members: List[str]
    representative: str
    source_uids: List[str]
    reason: str


class ConservativeMerger:
    """Prototype: validate proposals; merge only literal equality/containment.

    Out of scope: free paraphrase, structured JSON, persisted graph mutation.
    Unknown or overlapping group IDs make the entire proposal a no-op.
    Unmentioned input records are always preserved.
    """
    def merge(self, summaries, response):
        records = {r.unit_uid: r for r in summaries}
        groups = [g.get("merged_from", []) for g in response.get("merged_items", [])]
        mentioned = []
        for group in groups:
            if len(group) < 2 or any(not isinstance(uid, str) for uid in group):
                return list(summaries), []
            mentioned.extend(group)
        if len(set(mentioned)) != len(mentioned) or any(uid not in records for uid in mentioned):
            return list(summaries), []

        plans = []
        replacements = {}
        removed = set()
        for group in groups:
            members = [records[uid] for uid in group]
            user = members[0].metadata.get("user_id")
            if (not user or any(r.metadata.get("user_id") != user for r in members)
                    or len({r.summary_type for r in members}) != 1
                    or any(r.is_structured for r in members)):
                continue
            # The chosen existing text must literally cover every input's clauses.
            representative = max(members, key=lambda r: (len(atoms(r.content)), len(r.content)))
            cover = atoms(representative.content)
            if not cover or any(not atoms(r.content) or not atoms(r.content) <= cover for r in members):
                continue
            sources = sorted({uid for r in members for uid in r.source_unit_uids})
            metadata = dict(representative.metadata)
            metadata.update({
                "merged_from": sorted(group),
                "source_session_ids": sorted({r.session_id for r in members}),
                "merge_method": "literal_clause_coverage_v1",
            })
            replacements[representative.unit_uid] = replace(
                representative, source_unit_uids=sources, metadata=metadata)
            removed.update(set(group) - {representative.unit_uid})
            plans.append(MergePlan(sorted(group), representative.unit_uid, sources,
                                   "代表文本覆盖组内全部字面事实，且主体和摘要类型一致"))
        output = [replacements.get(r.unit_uid, r) for r in summaries if r.unit_uid not in removed]
        return output, plans


def unit(uid, text, user="u1", kind="knowledge", structured=False):
    return Summary("session_" + uid, kind, text, uid, ["raw_" + uid],
                   {"user_id": user}, structured)


def cases():
    def pair(name, category, a, b, expected, **kwargs):
        return {"name": name, "category": category,
                "units": [unit("a", a), unit("b", b, **kwargs)],
                "proposal": {"unique_items": [], "merged_items": [{"merged_from": ["a", "b"]}]},
                "expected_uids": expected}
    items = [
        pair("完全重复", "可合并", "用户偏好清淡饮食", "用户偏好清淡饮食", ["a"]),
        pair("空格差异", "可合并", "用户预算 3000 元", "用户预算3000元", ["a"]),
        pair("补充返回日期", "可合并", "周五去上海", "周五去上海；周日返回", ["b"]),
        pair("补充行程约束", "可合并", "周五去上海；不接受夜航", "周五去上海", ["a"]),
        pair("语义近似但字面不同", "保守保留", "用户喜欢清淡饮食", "用户口味偏清淡", ["a", "b"]),
        pair("否定冲突", "保守保留", "用户喜欢辣", "用户不喜欢辣", ["a", "b"]),
        pair("数字冲突", "保守保留", "预算300元", "预算3000元", ["a", "b"]),
        pair("时间更新", "保守保留", "去年住北京", "现在住上海", ["a", "b"]),
        pair("不同用户", "保守保留", "喜欢清淡饮食", "喜欢清淡饮食", ["a", "b"], user="u2"),
        pair("不同摘要类型", "保守保留", "周五去上海", "周五去上海", ["a", "b"], kind="episodic"),
        pair("结构化内容", "保守保留", '{"预算":300}', '{"预算":300}', ["a", "b"], structured=True),
        pair("500字符后不同", "保守保留", "共同背景" * 130 + "；预算300元", "共同背景" * 130 + "；预算3000元", ["a", "b"]),
    ]
    items.append({"name": "模型漏列输入", "category": "异常建议", "units": [unit("a", "用户喜欢跑步"), unit("b", "用户喜欢阅读")],
                  "proposal": {"unique_items": ["a"], "merged_items": []}, "expected_uids": ["a", "b"]})
    items.append({"name": "模型返回未知ID", "category": "异常建议", "units": [unit("a", "用户喜欢跑步"), unit("b", "用户喜欢阅读")],
                  "proposal": {"unique_items": [], "merged_items": [{"merged_from": ["missing", "a"]}]}, "expected_uids": ["a", "b"]})
    items.append({"name": "组内重复ID", "category": "异常建议", "units": [unit("a", "用户喜欢跑步"), unit("b", "用户喜欢阅读")],
                  "proposal": {"unique_items": ["b"], "merged_items": [{"merged_from": ["a", "a"]}]}, "expected_uids": ["a", "b"]})
    return items


def measure(inputs, outputs):
    expected_sources = {uid for r in inputs for uid in r.source_unit_uids}
    sources = {uid for r in outputs for uid in r.source_unit_uids}
    expected_atoms = set().union(*(atoms(r.content) for r in inputs))
    output_atoms = set().union(*(atoms(r.content) for r in outputs)) if outputs else set()
    return {
        "output_count": len(outputs),
        "source_coverage": len(sources & expected_sources) / len(expected_sources),
        "literal_clause_coverage": len(output_atoms & expected_atoms) / len(expected_atoms),
        "text_chars": sum(len(r.content) for r in outputs),
    }


def main():
    original = load_original_method()
    merger = ConservativeMerger()
    results = []
    for case in cases():
        inputs = case["units"]
        snapshot = copy.deepcopy(inputs)
        harness = BaselineHarness(case["proposal"])
        baseline = original(harness, copy.deepcopy(inputs))
        improved, plans = merger.merge(inputs, case["proposal"])
        assert [r.unit_uid for r in improved] == case["expected_uids"], case["name"]
        assert inputs == snapshot, "原型不应修改输入对象"
        assert measure(inputs, improved)["source_coverage"] == 1.0
        assert measure(inputs, improved)["literal_clause_coverage"] == 1.0
        results.append({
            "name": case["name"], "category": case["category"],
            "input": [vars(r) for r in inputs], "fixed_response": case["proposal"],
            "baseline_output": [vars(r) for r in baseline],
            "prototype_output": [vars(r) for r in improved],
            "merge_plans": [vars(p) for p in plans],
            "baseline_metrics": measure(inputs, baseline),
            "prototype_metrics": measure(inputs, improved),
            "baseline_prompt_item_lengths": [[len(item["content"]) for item in json.loads(prompt)]
                                              for prompt in harness.prompts],
        })
    result_dir = ROOT / "results"
    result_dir.mkdir(exist_ok=True)
    payload = {
        "mode": "controlled fixed-response experiment; not real LLM evaluation",
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "case_count": len(results), "results": results,
    }
    (result_dir / "controlled_results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 受控实验结果", "", "固定模型返回值，仅检查后处理逻辑，不代表真实模型准确率。", "",
             "字面事实覆盖仅按分号、句号和换行切分后匹配，不是语义保真指标。", "",
             "| 样例 | 原方法条数 | 原方法来源覆盖 | 原方法字面事实覆盖 | 原型条数 | 原型来源覆盖 | 原型字面事实覆盖 |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for r in results:
        a, b = r["baseline_metrics"], r["prototype_metrics"]
        lines.append(f'| {r["name"]} | {a["output_count"]} | {a["source_coverage"]:.0%} | {a["literal_clause_coverage"]:.0%} | {b["output_count"]} | {b["source_coverage"]:.0%} | {b["literal_clause_coverage"]:.0%} |')
    (result_dir / "实验结果.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Completed {len(results)} controlled cases; assertions passed.")
    print("Results: " + str(result_dir))


if __name__ == "__main__":
    main()
