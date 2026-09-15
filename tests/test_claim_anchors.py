import os
import shutil
import tempfile
import unittest
from pathlib import Path

from daug.anchor import AnchorParser, DiffSymbolExtractor
from daug.ledger import Ledger
from daug.patcher import PatchProposer
from daug.verifier import StalenessVerifier

class TestClaimAnchors(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.db_path = self.temp_dir / "anchor_test.sqlite"
        self.repo_root = self.temp_dir / "repo"
        self.repo_root.mkdir()

        self.ledger = Ledger(str(self.db_path))
        self.ledger.init_db()
        self.ledger.register_repository("anchor-repo", str(self.repo_root))

    def tearDown(self):
        self.ledger.close()
        shutil.rmtree(self.temp_dir)

    def test_markdown_section_anchors(self):
        md_content = (
            "# Main Title\n\n"
            "Introduction text.\n\n"
            "## Authentication Spec\n\n"
            "The auth interface defines:\n"
            "- `tenant_id`: The organization identifier.\n"
            "- `auth_token`: The bearer credentials.\n\n"
            "## Storage Spec\n\n"
            "Uses postgres.\n"
        )
        anchors = AnchorParser.find_anchors_for_token(md_content, "auth_token", "docs/auth.md")
        self.assertEqual(len(anchors), 1)
        anchor = anchors[0]
        self.assertEqual(anchor.anchor_type, "section")
        self.assertIn("Authentication Spec", anchor.context)
        self.assertIn("section:## Authentication Spec", anchor.locator)
        self.assertIn("line:9", anchor.locator)
        self.assertEqual(anchor.line_start, 9)

    def test_json_schema_pointer_anchors(self):
        schema_content = (
            '{\n'
            '  "type": "object",\n'
            '  "properties": {\n'
            '    "session_id": {"type": "string"},\n'
            '    "org_id": {"type": "string"}\n'
            '  }\n'
            '}\n'
        )
        anchors = AnchorParser.find_anchors_for_token(schema_content, "org_id", "schemas/user.schema.json")
        self.assertEqual(len(anchors), 1)
        anchor = anchors[0]
        self.assertEqual(anchor.anchor_type, "json_pointer")
        self.assertIn("/properties/org_id", anchor.locator)
        self.assertEqual(anchor.line_start, 5)

    def test_code_symbol_anchors(self):
        ts_code = (
            "export interface SessionConfig {\n"
            "  ttl_seconds: number;\n"
            "  refresh_token: string;\n"
            "}\n"
        )
        anchors = AnchorParser.find_anchors_for_token(ts_code, "refresh_token", "src/session.ts")
        self.assertEqual(len(anchors), 1)
        anchor = anchors[0]
        self.assertEqual(anchor.anchor_type, "symbol")
        self.assertIn("SessionConfig", anchor.context)
        self.assertIn("symbol:interface SessionConfig", anchor.locator)
        self.assertEqual(anchor.line_start, 3)

    def test_diff_symbol_renames_extraction(self):
        diff = (
            "--- a/src/auth.ts\n"
            "+++ b/src/auth.ts\n"
            "@@ -10,3 +10,3 @@\n"
            "-export interface AuthContext {\n"
            "-  auth_token: string;\n"
            "-}\n"
            "+export interface AuthContext {\n"
            "+  session_token: string;\n"
            "+}\n"
        )
        renames = DiffSymbolExtractor.extract_renames_from_diff(diff)
        self.assertIn("auth_token", renames)
        self.assertEqual(renames["auth_token"], "session_token")

    def test_dynamic_patch_generation_with_anchors(self):
        # Create target doc
        doc_file = self.repo_root / "docs/tokens.md"
        doc_file.parent.mkdir(parents=True, exist_ok=True)
        with open(doc_file, "w") as f:
            f.write(
                "# Tokens\n\n"
                "## Protocol\n\n"
                "Clients must send `auth_token` in headers.\n"
            )

        aid = self.ledger.register_artifact("anchor-repo", "docs/tokens.md")
        self.ledger.record_change_event("chg-tok-01", aid, "interface")

        # Create dummy graph snapshot for foreign key constraint
        self.ledger.conn.execute(
            """
            INSERT INTO graph_snapshot (graph_version, built_until, feature_version, config_digest, input_digest, graph_digest, status, created_at)
            VALUES ('v1', '2026-09-14T00:00:00Z', 'f1', 'cfg', 'inp', 'snap-dummy', 'published', '2026-09-14T00:00:00Z')
            """
        )

        cand_set_id = "candset-anchor"
        self.ledger.conn.execute(
            "INSERT INTO candidate_set VALUES (?, 'chg-tok-01', 'v1', 'v1', 'cfg', 1, 'd', '2026-09-14T00:00:00Z')",
            (cand_set_id,)
        )
        cand_id = "cand-anchor-1"
        self.ledger.conn.execute(
            "INSERT INTO update_candidate VALUES (?, ?, ?, 1, 0.9, 'f', 'e', 'rule')",
            (cand_id, cand_set_id, aid)
        )

        diff = (
            "--- a/src/auth.ts\n"
            "+++ b/src/auth.ts\n"
            "@@ -1,2 +1,2 @@\n"
            "-const auth_token = getHeader();\n"
            "+const session_token = getHeader();\n"
        )

        verifier = StalenessVerifier(self.ledger, repo_root_override=self.repo_root)
        verif_res = verifier.verify_candidate(cand_id, diff_text=diff)

        self.assertEqual(verif_res["status"], "STALE")
        self.assertTrue(len(verif_res["spans"]) > 0)
        self.assertIn("section:## Protocol", verif_res["spans"][0]["locator"])

        # Propose patch using dynamically discovered renames
        patcher = PatchProposer(self.ledger, repo_root_override=self.repo_root)
        patch = patcher.propose_patch(verif_res["verification_id"])
        self.assertIsNotNone(patch)
        self.assertIn("-Clients must send `auth_token` in headers.", patch["diff"])
        self.assertIn("+Clients must send `session_token` in headers.", patch["diff"])

if __name__ == "__main__":
    unittest.main()
