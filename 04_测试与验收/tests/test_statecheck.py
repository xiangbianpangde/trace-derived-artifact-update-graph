import unittest
from pathlib import Path

from daug.statecheck import (
    StateClaimScanner,
    StateTruthExtractor,
    parse_frontmatter,
    parse_status_table,
)

BASE_DIR = Path(__file__).resolve().parent.parent

STATUS_LEDGER = """---
schema: gap-plan/v1
revision: 104
current_stage_id: stage-2
---

| ID | 阶段 | 交付与验收 | 状态 | 更新 |
|---|---|---|---|---|
| `WU-0012` | 第二阶段 | detectors | verified | 2026-09-14T08:37:50Z |
| `WU-0013` | 第二阶段 | compiler | active | 2026-09-15T08:46:00Z |
"""

HANDOFF_STALE = """# HANDOFF

- 当前协调以 `plan/STATUS.md` revision 74、`WU-0013`（active）为准。
- 当前活跃工作单元：**WU-0013**，状态为 `active`。

## 状态

- Plan revision: 60
"""


class TestStatecheck(unittest.TestCase):
    def test_parse_frontmatter(self):
        fields = parse_frontmatter(STATUS_LEDGER)
        self.assertEqual(fields.get("revision"), "104")
        self.assertEqual(fields.get("current_stage_id"), "stage-2")

    def test_parse_status_table(self):
        items = parse_status_table(STATUS_LEDGER)
        self.assertEqual(items.get("WU-0012"), "verified")
        self.assertEqual(items.get("WU-0013"), "active")

    def test_parse_status_table_survives_column_reorder(self):
        reordered = """| 状态 | ID | 备注 |
|---|---|---|
| review | `WU-0007` | x |
"""
        items = parse_status_table(reordered)
        self.assertEqual(items.get("WU-0007"), "review")

    def test_status_claim_mismatch_detected(self):
        known = {"WU-0013": "active"}
        stale_doc = "- `WU-0013` is under review pending audit.\n"
        findings = StateClaimScanner.scan_work_item_status_claims(stale_doc, known)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["kind"], "work_item_status_mismatch")
        self.assertEqual(findings[0]["claimed"], "review")
        self.assertEqual(findings[0]["actual"], "active")

    def test_matching_status_not_flagged(self):
        known = {"WU-0013": "active"}
        ok_doc = "- `WU-0013` is active.\n"
        findings = StateClaimScanner.scan_work_item_status_claims(ok_doc, known)
        self.assertEqual(findings, [])

    def test_bare_mention_not_treated_as_claim(self):
        """Naming a work item without a status word must not be flagged."""
        known = {"WU-0013": "active"}
        findings = StateClaimScanner.scan_work_item_status_claims(
            "见 `WU-0013` 的实现说明。\n", known
        )
        self.assertEqual(findings, [])

    def test_numeric_revision_claim_detected(self):
        findings = StateClaimScanner.scan_numeric_claims(HANDOFF_STALE, revision_truth=104)
        claimed = {f["claimed"] for f in findings}
        self.assertIn(74, claimed)
        self.assertIn(60, claimed)
        for f in findings:
            self.assertEqual(f["actual"], 104)

    def test_numeric_claim_matching_not_flagged(self):
        findings = StateClaimScanner.scan_numeric_claims("Plan revision: 104\n", revision_truth=104)
        self.assertEqual(findings, [])

    def test_line_limit_excludes_history(self):
        body = "\n" * 5 + "Plan revision: 12\n"
        findings = StateClaimScanner.scan_numeric_claims(body, revision_truth=104, line_limit=3)
        self.assertEqual(findings, [])

    def test_abstains_when_no_truth_available(self):
        """Without a readable ledger the scanner must abstain, not guess."""
        findings = StateClaimScanner.scan_numeric_claims("Plan revision: 1\n", revision_truth=None)
        self.assertEqual(findings, [])

    def test_extractor_reports_unavailable_for_missing_file(self):
        truth = StateTruthExtractor.from_status_ledger(BASE_DIR, "plan/DOES_NOT_EXIST.md")
        self.assertFalse(truth["available"])
        self.assertIsNone(truth["revision"])

    def test_real_gap_handoff_drift_if_present(self):
        """
        Real-world regression: GAP's HANDOFF.md historically asserted a stale
        plan revision. Skipped when that repository is not present on this
        machine so the suite stays portable.
        """
        gap_repo = Path("/Users/xbpd/Projects/GAP Context Pager skills")
        if not (gap_repo / "plan" / "STATUS.md").is_file():
            self.skipTest("GAP repository not present")

        truth = StateTruthExtractor.from_status_ledger(gap_repo, "plan/STATUS.md")
        self.assertTrue(truth["available"])
        self.assertIsInstance(truth["revision"], int)
        # The status table must yield real work items.
        self.assertTrue(len(truth["work_items"]) > 0)


if __name__ == "__main__":
    unittest.main()
