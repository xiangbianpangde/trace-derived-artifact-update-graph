import json
import threading
import time
import unittest
import urllib.request
from http.server import HTTPServer
from pathlib import Path

from daug.server import DaugReviewHandler
BASE_DIR = Path(__file__).resolve().parent.parent

class TestReviewServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = 8991
        cls.repo_root = BASE_DIR
        cls.db_path = BASE_DIR / "demo.sqlite"

        handler = lambda *args, **kwargs: DaugReviewHandler(
            *args, repo_root=cls.repo_root, db_path=cls.db_path, **kwargs
        )
        cls.httpd = HTTPServer(("127.0.0.1", cls.port), handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def test_get_index_html(self):
        url = f"http://127.0.0.1:{self.port}/"
        req = urllib.request.urlopen(url)
        self.assertEqual(req.status, 200)
        html = req.read().decode("utf-8")
        self.assertIn("DAUG Review Workbench", html)
        self.assertIn("P2 Assisted Deployment", html)

    def test_api_status(self):
        url = f"http://127.0.0.1:{self.port}/api/status"
        req = urllib.request.urlopen(url)
        self.assertEqual(req.status, 200)
        data = json.loads(req.read().decode("utf-8"))
        self.assertEqual(data["status"], "running")

    def test_api_check(self):
        url = f"http://127.0.0.1:{self.port}/api/check"
        req = urllib.request.urlopen(url)
        self.assertEqual(req.status, 200)
        data = json.loads(req.read().decode("utf-8"))
        self.assertIn("inspections", data)

    def test_verify_candidate_missing_file_does_not_crash(self):
        """
        Regression: a candidate whose target artifact is absent from disk must
        return UNCERTAIN. The verifier previously referenced canonical_uri before
        assigning it on that path, raising UnboundLocalError and taking down the
        review server's /api/check endpoint.
        """
        import sqlite3
        import tempfile

        from daug.ledger import Ledger
        from daug.verifier import StalenessVerifier

        with tempfile.TemporaryDirectory() as tmp:
            empty_repo = Path(tmp) / "repo"
            empty_repo.mkdir()
            db_path = Path(tmp) / "ledger.sqlite"

            ledger = Ledger(str(db_path))
            ledger.init_db()
            ledger.register_repository("missing-file-repo", str(empty_repo))
            aid = ledger.register_artifact("missing-file-repo", "docs/absent.md")
            ledger.record_change_event("chg-missing", aid, "interface")

            ledger.conn.execute(
                "INSERT INTO graph_snapshot (graph_version, built_until, feature_version, "
                "config_digest, input_digest, graph_digest, status, created_at) "
                "VALUES ('g1','2026-09-15T00:00:00Z','f1','c','i','d','published','2026-09-15T00:00:00Z')"
            )
            ledger.conn.execute(
                "INSERT INTO candidate_set VALUES ('cs1','chg-missing','g1','v1','cfg',1,'d','2026-09-15T00:00:00Z')"
            )
            ledger.conn.execute(
                "INSERT INTO update_candidate VALUES ('cand1','cs1',?,1,0.9,'f','e','rule')",
                (aid,)
            )

            verifier = StalenessVerifier(ledger, repo_root_override=empty_repo)
            result = verifier.verify_candidate("cand1")

            self.assertEqual(result["status"], "UNCERTAIN")
            self.assertEqual(result["canonical_uri"], "docs/absent.md")
            self.assertIsNotNone(result["abstention_reason"])

if __name__ == "__main__":
    unittest.main()
