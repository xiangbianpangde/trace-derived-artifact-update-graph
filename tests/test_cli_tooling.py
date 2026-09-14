import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from daug.ledger import Ledger, compute_sha256
from daug.normalizer import Normalizer
from daug.graph import GraphBuilder
from daug.retriever import CandidateRetriever
from daug.verifier import StalenessVerifier
from daug.patcher import PatchProposer, HashConflictError
from daug.cli import cmd_check, cmd_patch_apply, cmd_hook_install, cmd_hook_uninstall

BASE_DIR = Path(__file__).resolve().parent.parent

class TestCLITooling(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_tooling.sqlite")
        self.repo_copy = Path(self.temp_dir) / "demo-repo"
        shutil.copytree(BASE_DIR / "fixtures/demo-repo", self.repo_copy)

        self.ledger = Ledger(self.db_path)
        self.ledger.init_db()
        self.ledger.register_repository("demo-auth-repo", str(self.repo_copy))

        for root, _, files in os.walk(self.repo_copy):
            for f in files:
                p = Path(root) / f
                rel = str(p.relative_to(self.repo_copy))
                kind = "documentation" if rel.endswith(".md") else "source_code"
                aid = self.ledger.register_artifact("demo-auth-repo", rel, artifact_kind=kind)
                with open(p, "rb") as fp:
                    h = compute_sha256(fp.read())
                self.ledger.record_artifact_version(aid, h, size_bytes=p.stat().st_size)

        normalizer = Normalizer()
        organic_trace = BASE_DIR / "fixtures/traces/organic-interface-change.jsonl"
        self.ledger.register_trace_run("trace-demo-interface-001", "task-rename", "demo-auth-repo", "2026-09-14T01:00:00Z")
        for ev in normalizer.read_jsonl(str(organic_trace)):
            self.ledger.append_tool_event(normalizer.validate_and_normalize_event(ev))

        self.ledger.record_change_event(
            change_id="change-test-001",
            source_artifact_id="artifact-src-auth-user_context-ts",
            change_type="interface",
            scope="file"
        )
        builder = GraphBuilder(self.ledger)
        builder.build_snapshot("graph-test-v1")

    def tearDown(self):
        self.ledger.close()
        shutil.rmtree(self.temp_dir)

    def test_patch_apply_with_cas_verification(self):
        retriever = CandidateRetriever(self.ledger)
        cand_set = retriever.rank_candidates("change-test-001", graph_version="graph-test-v1")

        verifier = StalenessVerifier(self.ledger, repo_root_override=self.repo_copy)
        verifs = verifier.verify_candidate_set(cand_set["candidate_set_id"])

        auth_design_verif = next(v for v in verifs if "auth_design.md" in v["canonical_uri"])
        self.assertEqual(auth_design_verif["status"], "STALE")

        patcher = PatchProposer(self.ledger, repo_root_override=self.repo_copy)
        proposal = patcher.propose_patch(auth_design_verif["verification_id"])
        self.assertIsNotNone(proposal)
        patch_id = proposal["patch_id"]

        # Target file before patch
        target_path = self.repo_copy / "docs/auth_design.md"
        before_text = target_path.read_text(encoding="utf-8")
        self.assertIn("user_id", before_text)

        # Apply patch
        receipt = patcher.apply_patch(patch_id)
        self.assertEqual(receipt["readback_status"], "pass")
        self.assertEqual(receipt["before_hash"], proposal["expected_target_hash"])
        self.assertNotEqual(receipt["after_hash"], receipt["before_hash"])

        # Target file after patch
        after_text = target_path.read_text(encoding="utf-8")
        self.assertNotIn("user_id", after_text)
        self.assertIn("subject_id", after_text)

        # Verify ledger records
        cursor = self.ledger.conn.cursor()
        attempt = cursor.execute("SELECT * FROM attempt WHERE patch_id=?", (patch_id,)).fetchone()
        self.assertIsNotNone(attempt)
        self.assertEqual(attempt["status"], "applied")

        app_rec = cursor.execute("SELECT * FROM application_receipt WHERE attempt_id=?", (attempt["attempt_id"],)).fetchone()
        self.assertIsNotNone(app_rec)
        self.assertEqual(app_rec["readback_status"], "pass")
        self.assertEqual(app_rec["after_hash"], receipt["after_hash"])

    def test_patch_apply_blocked_on_hash_drift(self):
        retriever = CandidateRetriever(self.ledger)
        cand_set = retriever.rank_candidates("change-test-001", graph_version="graph-test-v1")

        verifier = StalenessVerifier(self.ledger, repo_root_override=self.repo_copy)
        verifs = verifier.verify_candidate_set(cand_set["candidate_set_id"])
        auth_design_verif = next(v for v in verifs if "auth_design.md" in v["canonical_uri"])

        patcher = PatchProposer(self.ledger, repo_root_override=self.repo_copy)
        proposal = patcher.propose_patch(auth_design_verif["verification_id"])
        patch_id = proposal["patch_id"]

        # Simulate out-of-band edit to target file (drifts hash)
        target_path = self.repo_copy / "docs/auth_design.md"
        target_path.write_text(target_path.read_text(encoding="utf-8") + "\n# Unrelated manual edit", encoding="utf-8")

        # Attempt to apply patch: must raise HashConflictError
        with self.assertRaises(HashConflictError):
            patcher.apply_patch(patch_id)

        # Confirm attempt was NOT applied
        cursor = self.ledger.conn.cursor()
        attempt = cursor.execute("SELECT * FROM attempt WHERE patch_id=?", (patch_id,)).fetchone()
        self.assertIsNone(attempt)

    def test_cli_check_command(self):
        class Args:
            files = ["src/auth/user_context.ts"]
            files_opt = None
            staged = False
            uncommitted = False
            db = self.db_path
            repo_root = str(self.repo_copy)
            json = True
            fail_on_stale = False
            propose = True

        import io
        from contextlib import redirect_stdout
        f = io.StringIO()
        with redirect_stdout(f):
            ret = cmd_check(Args())
        self.assertEqual(ret, 0)
        output = json.loads(f.getvalue())
        self.assertEqual(output["total_files"], 1)
        self.assertGreater(output["total_stale"], 0)

        # Check that auth_design.md was flagged stale
        inspection = output["inspections"][0]
        stale_targets = [c["target_uri"] for c in inspection["candidates"] if c["status"] == "STALE"]
        self.assertIn("docs/auth_design.md", stale_targets)

    def test_git_hook_install_and_uninstall(self):
        # Create a fake git repo directory structure
        fake_git_dir = self.repo_copy / ".git"
        fake_git_dir.mkdir(parents=True, exist_ok=True)

        class InstallArgs:
            repo = str(self.repo_copy)
            type = "pre-commit"
            strict = True

        ret = cmd_hook_install(InstallArgs())
        self.assertEqual(ret, 0)

        hook_file = fake_git_dir / "hooks" / "pre-commit"
        self.assertTrue(hook_file.exists())
        self.assertTrue(os.access(hook_file, os.X_OK))

        content = hook_file.read_text(encoding="utf-8")
        self.assertIn("DAUG HOOK BEGIN", content)
        self.assertIn("daug check --staged --fail-on-stale", content)

        # Test uninstall
        class UninstallArgs:
            repo = str(self.repo_copy)
            type = "pre-commit"

        ret_un = cmd_hook_uninstall(UninstallArgs())
        self.assertEqual(ret_un, 0)
        if hook_file.exists():
            self.assertNotIn("DAUG HOOK BEGIN", hook_file.read_text(encoding="utf-8"))
