"""Component wiring checks using upstream AST and controlled collaborators.

No real LLM, embedding, SemanticGraph or persistence is executed.
Only the MemoryUnit import inside the write adapter is replaced by a recorder.
"""
import ast
import copy
from dataclasses import dataclass, field
from datetime import datetime
import logging
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from typing import Any, Dict, List, Optional
import unittest

from experiment import ConservativeMerger

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / "Mandol/src/mandol/auto_builder/hierarchical_builder.py"


def load_components():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    wanted = {"L1ExtractionResult", "L2AggregationResult"}
    nodes = [copy.deepcopy(n) for n in tree.body if isinstance(n, ast.ClassDef) and n.name in wanted]
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "HierarchicalAutoBuilder")
    methods = {"extract_l1_from_l0_units", "_aggregate_l2_default_style", "add_to_semantic_system"}
    for n in cls.body:
        if isinstance(n, ast.FunctionDef) and n.name in methods:
            method = copy.deepcopy(n)
            # Replace only transport object construction; preserve source write logic.
            method.body = [s for s in method.body if not isinstance(s, ast.ImportFrom)]
            nodes.append(method)
    module = ModuleType("_mandol_feasibility_components")
    sys.modules[module.__name__] = module
    ns = module.__dict__
    ns.update(dataclass=dataclass, field=field, datetime=datetime,
              logger=logging.getLogger("feasibility"),
              MemoryUnit=lambda **kwargs: SimpleNamespace(**kwargs),
              GraphWriteRequest=lambda **kwargs: SimpleNamespace(**kwargs))
    exec("from typing import *", ns)
    ns["L1SummaryType"] = SimpleNamespace(STRUCTURED=SimpleNamespace(value="structured"))
    ns["ExtractionStyle"] = SimpleNamespace(LOCOMO=SimpleNamespace(value="locomo"),
                                           LONGMEMEVAL=SimpleNamespace(value="longmemeval"))
    ns["dispatch_graph_write_requests"] = lambda **kwargs: kwargs["semantic_system"].extend(kwargs["requests"])
    executable = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)] + nodes, type_ignores=[])
    ast.fix_missing_locations(executable)
    exec(compile(executable, str(SOURCE), "exec"), ns)
    return ns


NS = load_components()


class Harness:
    def __init__(self):
        self.config = SimpleNamespace(extraction_style="default", enable_chunking=False,
                                      l1_max_tokens=500, l1_temperature=.3,
                                      l2_max_tokens=1000, l2_temperature=.3,
                                      l1_space_name="hierarchical_memory:L1_Summary",
                                      l2_space_name="hierarchical_memory:L2_Insight")
        self.prompt_manager = SimpleNamespace(get_l1_prompt=lambda **kwargs: kwargs,
                                              get_l2_prompt=lambda **kwargs: kwargs)
        self._build_stats = {"l1_summaries_generated": 0, "l0_units_processed": 0,
                             "l2_insights_generated": 0}
        self.semantic_system = []
        self.calls = []
        self.reply = "用户周五去上海"

    def _ensure_llm_client(self):
        pass

    def _merge_l0_content(self, units):
        return "\n".join(u.raw_data["text_content"] for u in units)

    def _call_llm_with_retry(self, **kwargs):
        self.calls.append(kwargs)
        return self.reply


def generated(session, text):
    harness = Harness()
    harness.reply = text
    unit = SimpleNamespace(uid="raw_" + session,
                           raw_data={"text_content": text}, metadata={"user_id": "user_1"})
    return NS["extract_l1_from_l0_units"](harness, [unit], session_id=session,
             session_date="2026-10-29", participants=["user_1", "assistant"],
             summary_types=["knowledge"])[0]


class FeasibilityChecks(unittest.TestCase):
    def setUp(self):
        self.items = [generated("s1", "周五去上海"), generated("s2", "周五去上海；周日返回")]
        self.proposal = {"merged_items": [{"merged_from": [r.unit_uid for r in self.items]}]}

    def test_actual_l1_metadata_does_not_pass_prototype_owner_gate(self):
        self.assertTrue(all("user_id" not in r.metadata for r in self.items))
        output, plans = ConservativeMerger().merge(self.items, self.proposal)
        self.assertEqual(len(output), 2)
        self.assertEqual(plans, [])

    def owned_items(self):
        items = copy.deepcopy(self.items)
        # Proposed adapter: verified scope must be supplied from the caller.
        # This is an explicit fixture assumption, not an implemented owner resolver.
        for item in items:
            item.metadata["user_id"] = "user_1"
        return items

    def test_original_dataclass_and_provenance_compatible(self):
        items = self.owned_items()
        before = copy.deepcopy(items)
        output, plans = ConservativeMerger().merge(items, self.proposal)
        self.assertEqual(len(output), 1)
        self.assertIsInstance(output[0], NS["L1ExtractionResult"])
        self.assertEqual(output[0].content, "周五去上海；周日返回")
        self.assertEqual(output[0].source_unit_uids, ["raw_s1", "raw_s2"])
        self.assertEqual(items, before)

    def test_l2_receives_kept_content_and_valid_representative(self):
        output, _ = ConservativeMerger().merge(self.owned_items(), self.proposal)
        harness = Harness()
        harness.reply = "用于连接检查的固定L2文本"
        l2 = NS["_aggregate_l2_default_style"](harness, output, "sample_1", None)
        self.assertEqual(l2.source_l1_uids, [output[0].unit_uid])
        self.assertIn("周日返回", harness.calls[0]["prompt"]["summaries"])

    def test_write_adapter_transmits_merged_sources(self):
        output, _ = ConservativeMerger().merge(self.owned_items(), self.proposal)
        harness = Harness()
        result = NS["add_to_semantic_system"](harness, output, rebuild_index=False)
        self.assertEqual(result["l1_added"], 1)
        request = harness.semantic_system[0]
        self.assertEqual(request.unit.metadata["source_unit_uids"], ["raw_s1", "raw_s2"])
        self.assertEqual(request.explicit_content_for_embedding, output[0].content)
        self.assertEqual(request.unit.metadata["source_session_ids"], ["s1", "s2"])

    def test_different_owners_and_structured_outputs_are_not_merged(self):
        items = self.owned_items()
        items[1].metadata["user_id"] = "user_2"
        self.assertEqual(len(ConservativeMerger().merge(items, self.proposal)[0]), 2)
        items = self.owned_items()
        items[1].is_structured = True
        self.assertEqual(len(ConservativeMerger().merge(items, self.proposal)[0]), 2)


if __name__ == "__main__":
    unittest.main()
