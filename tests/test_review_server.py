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

if __name__ == "__main__":
    unittest.main()
