"""Checks for evaluation semantics, leakage and a known prototype failure."""
import copy
import json
import unittest

from small_study import DATA, run_method, summarize


class StudyChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads(DATA.read_text(encoding="utf-8"))["cases"]

    def test_annotations_do_not_drive_decision(self):
        case = next(c for c in self.cases if c["id"] == "contains_03")
        changed = copy.deepcopy(case)
        changed["mergeable"] = not changed["mergeable"]
        for method in ["keep_all", "exact", "original_postprocess", "conservative"]:
            a = run_method(case, False, method, 0.5)
            b = run_method(changed, False, method, 0.5)
            self.assertEqual(a["output"], b["output"])

    def test_hand_calculated_first_item_loss(self):
        case = next(c for c in self.cases if c["id"] == "contains_03")
        a = run_method(case, False, "original_postprocess", 0.3)
        b = run_method(case, True, "original_postprocess", 0.3)
        self.assertEqual(a["fact_retention"], 0.5)
        self.assertEqual(b["fact_retention"], 1.0)
        self.assertEqual(a["source_retention"], 0.5)

    def test_scope_failure_is_not_hidden(self):
        case = next(c for c in self.cases if c["id"] == "scope_03")
        result = run_method(case, False, "conservative", 0.5)
        self.assertFalse(result["mergeable"])
        self.assertTrue(result["merged"])
        self.assertEqual(result["fact_retention"], 0.5)

    def test_abstention_precision_undefined(self):
        rows = [run_method(c, False, "keep_all", 0.5) for c in self.cases]
        self.assertIsNone(summarize(rows)["merge_precision"])
        self.assertEqual(summarize(rows)["merge_recall"], 0.0)


if __name__ == "__main__":
    unittest.main()
