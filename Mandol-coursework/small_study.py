"""Offline pilot: frozen synthetic annotations, dev/test split, paired order runs.

No model or annotations are used by the candidate generator. All strategies
return existing texts, allowing fact IDs to be scored through annotated UID.
This is NOT an end-to-end Mandol or real-LLM evaluation.
"""
from __future__ import annotations

import copy
import hashlib
import json
import random
import re
from dataclasses import asdict
from pathlib import Path

from experiment import BaselineHarness, ConservativeMerger, Summary, load_original_method

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data/pilot_pairs.json"
OUT = ROOT / "results/pilot"


def build_dataset():
    """Author provisional gold separately from evaluated decision functions."""
    rows = []
    def add(category, a, b, mergeable, facts_a, facts_b, user_b="u1"):
        index = sum(r["category"] == category for r in rows)
        pair_id = f"{category}_{index + 1:02}"
        rows.append({
            "id": pair_id, "category": category,
            "split": "dev" if index < 2 else "test",
            "mergeable": mergeable,
            "units": [
                {"uid": "a", "text": a, "user": "u1", "fact_ids": facts_a},
                {"uid": "b", "text": b, "user": user_b, "fact_ids": facts_b},
            ],
        })
    exact = ["用户喜欢跑步", "用户通常周六休息", "项目在周一发布", "午饭预算50元", "用户不喝咖啡", "会议地点在南京"]
    for t in exact:
        add("exact", t, t, True, ["f1"], ["f1"])
    contains = [
        ("周五去上海", "周日返回"), ("购买蓝色衬衫", "尺码为M"),
        ("会议在周一", "地点在杭州"), ("用户喜欢徒步", "每周末参加"),
        ("报销截止周三", "需要纸质发票"), ("项目使用Python", "版本为3.12"),
    ]
    for a, extra in contains:
        add("contains", a, a + "；" + extra, True, ["f1"], ["f1", "f2"])
    paraphrases = [
        ("用户喜欢清淡饮食", "用户的饮食口味偏清淡"),
        ("用户每周跑步三次", "用户一周进行三次跑步锻炼"),
        ("用户不喝含糖饮料", "用户避免饮用含糖饮品"),
        ("用户周六不用上班", "用户星期六休息"),
        ("用户的预算上限为500元", "用户最多愿意花500元"),
        ("会议地点是北京", "会议在北京举行"),
    ]
    for a, b in paraphrases:
        add("paraphrase", a, b, True, ["f1"], ["f1"])
    for name in ["咖啡", "辣椒", "牛奶", "花生", "海鲜", "香菜"]:
        add("negation", f"用户喜欢{name}", f"用户不喜欢{name}", False, ["f1"], ["f2"])
    for a, b in [(300, 3000), (20, 200), (15, 50), (500, 5000), (80, 800), (100, 1000)]:
        add("number", f"本次预算为{a}元", f"本次预算为{b}元", False, ["f1"], ["f2"])
    for a, b in [("北京", "上海"), ("南京", "杭州"), ("武汉", "成都"), ("深圳", "广州"), ("苏州", "无锡"), ("青岛", "济南")]:
        add("time", f"用户去年住{a}", f"用户现在住{b}", False, ["f1"], ["f2"])
    for t in exact:
        add("subject", t, t, False, ["u1_f1"], ["u2_f1"], user_b="u2")
    # Deliberate challenge to the prototype's punctuation-based containment.
    # A condition/exception changes meaning, even when clauses overlap literally.
    scopes = [
        ("用户周五出发", "如果没有加班；用户周五出发"),
        ("用户参加会议", "只有收到邀请；用户参加会议"),
        ("用户取消出行", "如果下雨；用户取消出行"),
        ("用户购买机票", "如果报销获批；用户购买机票"),
        ("用户接受加班", "仅限紧急情况；用户接受加班"),
        ("用户在家办公", "如果设备可用；用户在家办公"),
    ]
    for a, b in scopes:
        add("scope", a, b, False, ["unconditional"], ["conditional"])
    return {
        "annotation_status": "AI-authored provisional synthetic gold; no independent human review",
        "annotation_policy": "Only equivalent propositions or genuine factual containment may merge; preserve conditions, subject, numbers and temporal versions.",
        "design": "8 strata x 6 pairs; first 2 per stratum dev, remaining 4 test; synthetic/template-dependent",
        "cases": rows,
    }


def normalized(text):
    return re.sub(r"\s+", "", text)


def similarity(a, b):
    # Character-set Jaccard intentionally serves as a simple lexical baseline.
    x, y = set(normalized(a)), set(normalized(b))
    return len(x & y) / len(x | y) if x | y else 0.0


def candidate_response(units, threshold):
    a, b = units
    compatible = a.metadata["user_id"] == b.metadata["user_id"]
    if compatible and similarity(a.content, b.content) >= threshold:
        return {"unique_items": [], "merged_items": [{"merged_from": [a.unit_uid, b.unit_uid]}]}
    return {"unique_items": [u.unit_uid for u in units], "merged_items": []}


def make_units(case, reverse):
    units = [Summary("session_" + u["uid"], "knowledge", u["text"], u["uid"],
                     ["raw_" + u["uid"]], {"user_id": u["user"]}) for u in case["units"]]
    return list(reversed(units)) if reverse else units


ORIGINAL = load_original_method()


def run_method(case, reverse, method, threshold):
    units = make_units(case, reverse)
    if method == "keep_all":
        output = units
    elif method == "exact":
        a, b = units
        if a.metadata["user_id"] == b.metadata["user_id"] and normalized(a.content) == normalized(b.content):
            # This baseline deliberately keeps provenance, so provenance gain
            # is not confused with a universally weak exact-match baseline.
            representative = copy.deepcopy(a)
            representative.source_unit_uids = sorted({s for u in units for s in u.source_unit_uids})
            output = [representative]
        else:
            output = units
    elif method == "original_postprocess":
        harness = BaselineHarness(candidate_response(units, threshold))
        output = ORIGINAL(harness, units)
    elif method == "conservative":
        output, _ = ConservativeMerger().merge(units, candidate_response(units, threshold))
    else:
        raise ValueError(method)

    return score_outputs(case, reverse, method, output)


def score_outputs(case, reverse, method, output):
    units = make_units(case, reverse)
    gold = {u["uid"]: u for u in case["units"]}
    all_facts = {f for u in gold.values() for f in u["fact_ids"]}
    retained = {f for u in output for f in gold[u.unit_uid]["fact_ids"]}
    merged = len(output) == 1
    char_in = sum(len(u.content) for u in units)
    char_out = sum(len(u.content) for u in output)
    return {
        "case_id": case["id"], "category": case["category"], "reverse": reverse,
        "method": method, "mergeable": case["mergeable"], "merged": merged,
        "fact_retention": len(retained) / len(all_facts),
        "source_retention": len({s for u in output for s in u.source_unit_uids}) / 2,
        "char_reduction": 1 - char_out / char_in,
        "output": [asdict(u) for u in output],
    }


def summarize(records):
    tp = sum(r["merged"] and r["mergeable"] for r in records)
    fp = sum(r["merged"] and not r["mergeable"] for r in records)
    fn = sum(not r["merged"] and r["mergeable"] for r in records)
    negatives = sum(not r["mergeable"] for r in records)
    return {
        "merge_precision": tp / (tp + fp) if tp + fp else None,
        "merge_recall": tp / (tp + fn),
        "merge_f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0,
        "unsafe_merge_rate": fp / negatives,
        "fact_retention": sum(r["fact_retention"] for r in records) / len(records),
        "source_retention": sum(r["source_retention"] for r in records) / len(records),
        "char_reduction": sum(r["char_reduction"] for r in records) / len(records),
        "true_positive": tp, "false_positive": fp, "false_negative": fn,
    }


def interval(records, metric):
    # Resample pairs, keeping both orderings together. Does not resolve shared
    # template dependence across pairs; these are exploratory intervals only.
    groups = {}
    for r in records:
        groups.setdefault(r["case_id"], []).append(r)
    groups = list(groups.values())
    rng = random.Random(20261023)
    values = []
    for _ in range(2000):
        sample = [r for _ in groups for r in rng.choice(groups)]
        values.append(summarize(sample)[metric])
    values.sort()
    return [values[49], values[1949]]


def main():
    if not DATA.exists():
        raise SystemExit("Dataset missing. Create/review data/pilot_pairs.json before evaluation.")
    raw = DATA.read_bytes()
    dataset = json.loads(raw)
    dev = [c for c in dataset["cases"] if c["split"] == "dev"]
    test = [c for c in dataset["cases"] if c["split"] == "test"]
    methods = ["keep_all", "exact", "original_postprocess", "conservative"]
    assert len(dev) == 16 and len(test) == 32
    assert not ({c["id"] for c in dev} & {c["id"] for c in test})
    # Select one shared candidate threshold using baseline dev F1 only.
    tuning = []
    for threshold in [0.3, 0.5, 0.7, 0.9]:
        score = summarize([run_method(c, rev, "original_postprocess", threshold)
                           for c in dev for rev in [False, True]])
        tuning.append({"threshold": threshold, **score})
    chosen = max(tuning, key=lambda x: (x["merge_f1"], x["threshold"]))["threshold"]
    records = [run_method(c, rev, method, chosen)
               for c in test for rev in [False, True] for method in methods]
    aggregates = {}
    for method in methods:
        rows = [r for r in records if r["method"] == method]
        summary = summarize(rows)
        summary["exploratory_pair_bootstrap_95ci"] = {
            key: interval(rows, key) for key in ["fact_retention", "unsafe_merge_rate"]}
        changed = 0
        for case in test:
            pair = [r for r in rows if r["case_id"] == case["id"]]
            # Ignore representative ID for equivalent texts; compare factual
            # coverage, merge action and provenance rather than string order.
            if any(pair[0][key] != pair[1][key] for key in ["fact_retention", "source_retention", "merged"]):
                changed += 1
        summary["order_sensitive_pairs"] = changed
        aggregates[method] = summary
    OUT.mkdir(parents=True, exist_ok=True)
    result = {
        "scope": "offline synthetic pilot; original postprocessing isolated via AST; no real LLM or full Mandol runtime",
        "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "experiment_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "prototype_sha256": hashlib.sha256((ROOT / "experiment.py").read_bytes()).hexdigest(),
        "upstream_source_sha256": hashlib.sha256((ROOT.parent / "Mandol/src/mandol/auto_builder/hierarchical_builder.py").read_bytes()).hexdigest(),
        "annotation_status": dataset["annotation_status"],
        "dev_pairs": len(dev), "test_pairs": len(test), "orders_per_pair": 2,
        "threshold": chosen, "dev_tuning": tuning,
        "summary": aggregates, "runs": records,
    }
    (OUT / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    labels = {"keep_all": "全部保留", "exact": "精确去重并汇总来源", "original_postprocess": "字面候选＋原后处理", "conservative": "相同候选＋保守原型"}
    lines = ["# 小规模离线评测结果", "", "16 组开发样例、32 组评测样例，每组正反两种顺序。没有真实模型调用。",
             "人工合成、AI 初始标注，尚未经独立人工复核；不是隐藏测试集或外部基准。", "",
             f"开发集选择的共享字符集合 Jaccard 阈值：{chosen}。", "",
             "| 方法 | 合并精确率 | 合并召回率 | 不可合并样例误合并率 | 标注事实保留 | 来源覆盖 | 文本字符减少 |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for method in methods:
        s = aggregates[method]
        cells = ["—" if s[k] is None else f"{s[k]:.1%}" for k in ["merge_precision", "merge_recall", "unsafe_merge_rate", "fact_retention", "source_retention", "char_reduction"]]
        lines.append("| " + labels[method] + " | " + " | ".join(cells) + " |")
    lines += ["", "## 顺序敏感性", "", "以下统计交换两条输入后，事实保留、来源覆盖或是否合并发生变化的样例数（共32组）。", ""]
    for method in methods:
        lines.append(f'- {labels[method]}：{aggregates[method]["order_sensitive_pairs"]} 组。')
    lines += ["", "## 保守原型的失败样例", ""]
    for r in records:
        if r["method"] == "conservative" and not r["reverse"] and r["merged"] and not r["mergeable"]:
            lines.append(f'- {r["case_id"]}：合并了带条件与无条件陈述，事实保留为 {r["fact_retention"]:.0%}。')
    lines += ["", "## 解释范围", "", "事实指标根据预先标注的事实ID和实际保留的原文对象计算。所有方法只选择已有文本，没有评价自由生成摘要。",
              "字符减少不包括来源元数据、向量、图或 L0，不等于总存储/内存减少。",
              "results.json 保存逐次输出、开发集选择过程和按样例重采样2000次的探索性区间。共享模板会削弱独立性，区间不能当作总体保证。",
              "两种输入顺序不是两条独立样例。没有报告真实模型准确率、下游问答效果或完整系统性能。"]
    (OUT / "评测结果.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Finished: dev={len(dev)}, test={len(test)}, threshold={chosen}; {len(records)} method-runs.")


if __name__ == "__main__":
    import sys
    if "--init-data" in sys.argv:
        if DATA.exists():
            raise SystemExit("Refusing to overwrite existing annotations.")
        DATA.parent.mkdir(parents=True, exist_ok=True)
        DATA.write_text(json.dumps(build_dataset(), ensure_ascii=False, indent=2), encoding="utf-8")
        print("Created provisional annotations; review before treating as gold.")
    else:
        main()
