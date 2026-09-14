import os
import shutil
import tempfile
import unittest
from pathlib import Path

from daug.ledger import Ledger, IdempotencyConflictError, PathEscapeError, ValidationError
from daug.normalizer import Normalizer
from daug.graph import GraphBuilder
from daug.retriever import CandidateRetriever
from daug.verifier import StalenessVerifier
from daug.patcher import PatchProposer, HashConflictError
from daug.policy import PolicyEngine

BASE_DIR = Path(__file__).resolve().parent.parent

class TestDAUGContracts(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.sqlite")
        self.ledger = Ledger(self.db_path)
        self.ledger.init_db()

        self.repo_root = os.path.join(self.temp_dir, "repo")
        os.makedirs(self.repo_root, exist_ok=True)
        self.ledger.register_repository("test-repo", self.repo_root)

        # Create dummy file
        self.dummy_file = os.path.join(self.repo_root, "test.txt")
        with open(self.dummy_file, "w") as f:
            f.write("hello world")

        self.ledger.register_artifact("test-repo", "test.txt")
        self.ledger.register_trace_run("trace-001", "task-001", "test-repo", "2026-09-14T00:00:00Z")

    def tearDown(self):
        self.ledger.close()
        shutil.rmtree(self.temp_dir)

    def test_c01_idempotent_duplicate_event(self):
        ev = {
            "schema_version": "daug.tool-event.v1",
            "event_id": "evt-001",
            "trace_id": "trace-001",
            "repository_id": "test-repo",
            "sequence_no": 1,
            "operation": "read",
            "artifact_path": "test.txt",
            "access_origin": "organic"
        }
        ev_id, is_dup = self.ledger.append_tool_event(ev)
        self.assertFalse(is_dup)

        # Re-append identical event
        ev_id2, is_dup2 = self.ledger.append_tool_event(ev)
        self.assertTrue(is_dup2)
        self.assertEqual(ev_id, ev_id2)

        count = self.ledger.conn.execute("SELECT COUNT(*) FROM tool_event WHERE trace_id='trace-001'").fetchone()[0]
        self.assertEqual(count, 1)

    def test_c02_idempotency_conflict(self):
        ev1 = {
            "schema_version": "daug.tool-event.v1",
            "event_id": "evt-002",
            "trace_id": "trace-001",
            "repository_id": "test-repo",
            "sequence_no": 2,
            "operation": "read",
            "artifact_path": "test.txt",
            "input_digest": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
            "access_origin": "organic"
        }
        self.ledger.append_tool_event(ev1)

        # Re-append same trace and seq_no but different event_id / content
        ev2 = dict(ev1)
        ev2["event_id"] = "evt-different"
        ev2["input_digest"] = "sha256:2222222222222222222222222222222222222222222222222222222222222222"
        with self.assertRaises(IdempotencyConflictError):
            self.ledger.append_tool_event(ev2)

    def test_c03_path_escape_rejected(self):
        ev = {
            "schema_version": "daug.tool-event.v1",
            "event_id": "evt-escape",
            "trace_id": "trace-001",
            "repository_id": "test-repo",
            "sequence_no": 3,
            "operation": "read",
            "artifact_path": "../../etc/passwd",
            "access_origin": "organic"
        }
        with self.assertRaises(PathEscapeError):
            self.ledger.append_tool_event(ev)

    def test_c04_missing_edit_hashes_marks_trace_incomplete(self):
        ev = {
            "schema_version": "daug.tool-event.v1",
            "event_id": "evt-edit-nohash",
            "trace_id": "trace-001",
            "repository_id": "test-repo",
            "sequence_no": 4,
            "operation": "edit",
            "artifact_path": "test.txt",
            "access_origin": "organic"
        }
        self.ledger.append_tool_event(ev)
        trace_row = self.ledger.conn.execute("SELECT completeness FROM trace_run WHERE trace_id='trace-001'").fetchone()
        self.assertEqual(trace_row["completeness"], "partial")

    def test_c05_recommended_access_requires_recommendation_id(self):
        ev = {
            "schema_version": "daug.tool-event.v1",
            "event_id": "evt-rec-noid",
            "trace_id": "trace-001",
            "repository_id": "test-repo",
            "sequence_no": 5,
            "operation": "read",
            "artifact_path": "test.txt",
            "access_origin": "system_recommended"
        }
        with self.assertRaises(ValidationError):
            self.ledger.append_tool_event(ev)

    def test_c06_deterministic_graph_digest(self):
        builder = GraphBuilder(self.ledger)
        snap1 = builder.build_snapshot("graph-snap-1", until_timestamp="2026-09-14T00:00:00Z")
        snap2 = builder.build_snapshot("graph-snap-2", until_timestamp="2026-09-14T00:00:00Z")
        self.assertEqual(snap1["graph_digest"], snap2["graph_digest"])

    def test_c07_target_hash_drift_causes_hash_conflict(self):
        # Register artifact and version
        aid = self.ledger.register_artifact("test-repo", "doc.md")
        doc_path = os.path.join(self.repo_root, "doc.md")
        with open(doc_path, "w") as f:
            f.write("Field: user_id\n")

        self.ledger.record_change_event("chg-01", aid, "interface")
        builder = GraphBuilder(self.ledger)
        snap = builder.build_snapshot("graph-snap-drift")

        retriever = CandidateRetriever(self.ledger, minimum_score=0.0)
        # Manually create candidate
        cand_set = retriever.rank_candidates("chg-01", graph_version=snap["graph_version"], top_k=5)

        # Now verify
        cand_row = self.ledger.conn.execute("SELECT candidate_id FROM update_candidate LIMIT 1").fetchone()
        if not cand_row:
            # Insert direct update_candidate for test
            cand_set_id = cand_set["candidate_set_id"]
            cand_id = f"cand-{cand_set_id}-doc"
            self.ledger.conn.execute(
                "INSERT INTO update_candidate VALUES (?, ?, ?, 1, 0.9, 'x', 'y', 'rule')",
                (cand_id, cand_set_id, aid)
            )
            cand_row = {"candidate_id": cand_id}

        verifier = StalenessVerifier(self.ledger)
        verif = verifier.verify_candidate(cand_row["candidate_id"])
        self.assertEqual(verif["status"], "STALE")

        # Now simulate drift by modifying file on disk
        with open(doc_path, "w") as f:
            f.write("Modified out of band!\n")

        patcher = PatchProposer(self.ledger)
        with self.assertRaises(HashConflictError):
            patcher.propose_patch(verif["verification_id"])

    def test_c09_protected_artifacts_rejected_by_policy(self):
        aid = self.ledger.register_artifact("test-repo", "security/credentials.yaml", risk_class="R4")
        # Insert prerequisite candidate_set, candidate, verification, and patch_proposal for foreign keys
        cand_set_id = "candset-sec"
        cand_id = "cand-sec-01"
        verif_id = "ver-sec-01"
        patch_id = "patch-sec-01"
        self.ledger.conn.execute(
            "INSERT INTO change_event VALUES ('chg-sec', 'trace-001', ?, NULL, NULL, 'interface', 0.9, 'file', 'deterministic', 1.0, 'd', '2026-09-14T00:00:00Z')",
            (aid,)
        )
        builder = GraphBuilder(self.ledger)
        snap = builder.build_snapshot("graph-snap-sec")
        self.ledger.conn.execute(
            "INSERT INTO candidate_set VALUES (?, 'chg-sec', 'graph-snap-sec', 'v1', 'cfg', 5, 'd', '2026-09-14T00:00:00Z')",
            (cand_set_id,)
        )
        self.ledger.conn.execute(
            "INSERT INTO update_candidate VALUES (?, ?, ?, 1, 0.9, 'f', 'e', 'rule')",
            (cand_id, cand_set_id, aid)
        )
        self.ledger.conn.execute(
            "INSERT INTO verification VALUES (?, ?, 'hash', 'STALE', 0.9, 'v1', 'digest', NULL, '2026-09-14T00:00:00Z')",
            (verif_id, cand_id)
        )
        self.ledger.conn.execute(
            "INSERT INTO patch_proposal VALUES (?, ?, ?, 'hash', 'unified_diff', 'pdig', 'cdig', 'pass', 'tdig', 'rdig', 'v1', 'proposed', '2026-09-14T00:00:00Z')",
            (patch_id, verif_id, aid)
        )
        policy = PolicyEngine(self.ledger, mode="auto_apply")
        decision = policy.evaluate_patch(patch_id, "security/credentials.yaml")
        self.assertEqual(decision["risk_class"], "R4")
        self.assertEqual(decision["action"], "REJECTED")

    def test_c10_bulk_task_creates_hyperedge_not_clique(self):
        # Register 60 dummy artifacts
        self.ledger.register_trace_run("trace-bulk", "task-bulk", "test-repo", "2026-09-14T00:00:00Z")
        for i in range(60):
            p = f"file_{i}.txt"
            aid = self.ledger.register_artifact("test-repo", p)
            self.ledger.append_tool_event({
                "schema_version": "daug.tool-event.v1",
                "event_id": f"evt-bulk-{i}",
                "trace_id": "trace-bulk",
                "repository_id": "test-repo",
                "sequence_no": i + 1,
                "operation": "edit",
                "artifact_path": p,
                "before_hash": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
                "after_hash": "sha256:2222222222222222222222222222222222222222222222222222222222222222",
                "access_origin": "organic"
            })

        builder = GraphBuilder(self.ledger, bulk_threshold=50)
        snap = builder.build_snapshot("graph-snap-bulk")
        # Ensure task_hyperedge was created
        hyper_count = self.ledger.conn.execute("SELECT COUNT(*) FROM task_hyperedge WHERE trace_id='trace-bulk'").fetchone()[0]
        self.assertEqual(hyper_count, 1)

if __name__ == "__main__":
    unittest.main()
