import os
import unittest
from pathlib import Path

from daug.ablation import AblationStudy

BASE_DIR = Path(__file__).resolve().parent.parent

class TestAblationStudy(unittest.TestCase):
    def setUp(self):
        self.demo_db = str(BASE_DIR / "demo.sqlite")
        self.gap_db = str(BASE_DIR / "gap-demo.sqlite")
        self.study = AblationStudy(self.demo_db, self.gap_db)

    def test_ablation_rq1_trace_incremental_value(self):
        """RQ1: Trajectory signals significantly outperform no-trace baseline."""
        full_res = self.study.evaluate_method("DAUG_Full")
        no_trace_res = self.study.evaluate_method("DAUG_No_Trace")
        self.assertGreater(full_res["mrr"], no_trace_res["mrr"])
        self.assertGreaterEqual(full_res["doc_recall"], no_trace_res["doc_recall"])

    def test_ablation_rq2_direction_and_change_type(self):
        """RQ2: Directionality prevents spurious reverse updates and improves negative control pass."""
        full_res = self.study.evaluate_method("DAUG_Full")
        no_dir_res = self.study.evaluate_method("DAUG_No_Direction")
        self.assertGreater(full_res["mrr"], no_dir_res["mrr"])
        self.assertGreater(full_res["negative_control_pass"], no_dir_res["negative_control_pass"])

    def test_ablation_ast_blindness_on_non_code(self):
        """AST import analysis fails completely on non-code documentation."""
        ast_res = self.study.evaluate_method("AST_Import_Only")
        self.assertEqual(ast_res["doc_recall"], 0.0)
        self.assertEqual(ast_res["mrr"], 0.0)

    def test_ablation_full_model_safety(self):
        """Full model achieves high MRR and 100% negative control safety."""
        full_res = self.study.evaluate_method("DAUG_Full")
        self.assertGreaterEqual(full_res["mrr"], 0.9)
        self.assertEqual(full_res["negative_control_pass"], 1.0)
        self.assertEqual(full_res["doc_recall"], 1.0)

if __name__ == "__main__":
    unittest.main()
