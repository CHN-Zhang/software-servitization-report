"""Post-hoc sensitivity analysis: replay schema deviations as upstream does.

Keep strict results untouched. Do not silently normalize object IDs to strings.
"""
import copy
import json

from experiment import ConservativeMerger
from real_model_study import OUT, Replay
from small_study import DATA, ORIGINAL, make_units, score_outputs, summarize


def main():
    cases = {c["id"]: c for c in json.loads(DATA.read_text(encoding="utf-8"))["cases"] if c["split"] == "test"}
    records, errors = [], []
    responses = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((OUT / "responses").glob("*.json"))]
    for response in responses:
        case = cases[response["case_id"]]
        reverse = response["reverse"]
        harness = Replay(response.get("content", ""))
        parsed = harness._safe_parse_json(harness.response)
        try:
            units = make_units(case, reverse)
            baseline = ORIGINAL(harness, copy.deepcopy(units))
            improved, _ = ConservativeMerger().merge(copy.deepcopy(units), parsed or {})
            for method, output in [("original", baseline), ("conservative", improved)]:
                records.append(score_outputs(case, reverse, method, output))
        except (TypeError, AttributeError, KeyError) as exc:
            errors.append({"case_id": case["id"], "reverse": reverse, "error_type": type(exc).__name__})
    summaries = {m: summarize([r for r in records if r["method"] == m]) for m in ["original", "conservative"]}
    payload = {"analysis": "POST-HOC sensitivity replay, not predeclared strict primary analysis",
               "response_count": len(responses), "evaluated": len(records)//2,
               "errors": errors, "summary": summaries, "runs": records}
    (OUT / "all_response_sensitivity.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 全部返回的补充回放", "", "这是发现格式偏差后新增的敏感性分析，不能替换预先约定的严格结果。没有重新调用模型，没有修改原型，没有把对象列表转换成ID列表。",
             "原代码对非字符串unique_items会跳过；若没有任何保留ID则回退为全保留。这里按它的实际行为执行。", "",
             f"回放 {len(records)//2}/{len(responses)} 次返回，执行异常 {len(errors)}。", "",
             "| 方法 | 合并精确率 | 合并召回率 | 不可合并样例误合并率 | 标注事实保留 | 来源覆盖 | 字符减少 |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for m in ["original", "conservative"]:
        cells = ["—" if summaries[m][k] is None else f"{summaries[m][k]:.1%}" for k in ["merge_precision", "merge_recall", "unsafe_merge_rate", "fact_retention", "source_retention", "char_reduction"]]
        lines.append("| " + m + " | " + " | ".join(cells) + " |")
    lines += ["", "保守原型仍在scope类样例上出现误合并。全部数据回放减少了严格筛选带来的分母偏差，但不能解决合成样例、未独立复核标注和事后分析的局限。"]
    (OUT / "全部返回补充回放.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Sensitivity replay: {len(records)//2}/{len(responses)}, errors={len(errors)}")


if __name__ == "__main__":
    main()
