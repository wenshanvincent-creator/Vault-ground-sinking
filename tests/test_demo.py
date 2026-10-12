import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from vault import storage
from vault.app import app


class PublicDemoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = storage.DATA
        storage.DATA = Path(self.temp.name)
        self.context = TestClient(app)
        self.client = self.context.__enter__()

    def tearDown(self):
        self.context.__exit__(None, None, None)
        storage.DATA = self.original
        self.temp.cleanup()

    def test_clean_install_can_run_without_any_private_source(self):
        response = self.client.post("/api/demo")
        self.assertEqual(response.status_code, 200)
        warehouse = response.json()
        self.assertIn("合成数据", warehouse["name"])
        self.assertTrue(all(d["id"].startswith("DEMO-") for d in warehouse["devices"]))
        self.assertEqual(self.client.get(warehouse["layout_url"]).status_code, 200)
        report = self.client.post(f"/api/warehouses/{warehouse['id']}/reports", json={"cycle": "month"})
        self.assertEqual(report.status_code, 200)
        self.assertGreater(report.json()["counts"]["persistent"], 0)
        self.assertEqual(self.client.post("/api/demo").json()["id"], warehouse["id"])

    def test_synthetic_checks_bypass_private_manifest(self):
        (storage.DATA / "private-demo.json").write_text(json.dumps({"name": "私有仓库", "excel": "unavailable", "layout": "unavailable", "devices": []}), encoding="utf-8")
        self.assertEqual(self.client.post("/api/demo").status_code, 400)
        generated = self.client.post("/api/demo?synthetic=true")
        self.assertEqual(generated.status_code, 200)
        self.assertIn("合成数据", generated.json()["name"])


if __name__ == "__main__":
    unittest.main()
