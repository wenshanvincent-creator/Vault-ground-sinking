import io
import tempfile
import unittest
from pathlib import Path

import openpyxl
from fastapi.testclient import TestClient

from vault import storage
from vault.app import app


def excel(angle=.1, missing_sheet=False, event_time="2026-10-01 12:00:00"):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Other" if missing_sheet else "Result"
    sheet.append(["name", "message_type", "angle_x", "angle_y", "event_time", "x_displacement", "y_displacement"])
    sheet.append(["TEST-A", "Heartbeat", angle, 0, event_time, 3, 4])
    stream = io.BytesIO()
    workbook.save(stream)
    workbook.close()
    return stream.getvalue()


class ImportApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = storage.DATA
        storage.DATA = Path(self.temp.name)
        self.context = TestClient(app)
        self.client = self.context.__enter__()
        self.key = self.client.post("/api/warehouses", json={"name": "测试"}).json()["id"]

    def tearDown(self):
        self.context.__exit__(None, None, None)
        storage.DATA = self.original
        self.temp.cleanup()

    def upload(self, payload):
        return self.client.post(f"/api/warehouses/{self.key}/import", files={"file": ("source.xlsx", payload)})

    def test_duplicate_import_and_conflict_rollback(self):
        source = excel()
        self.assertEqual(self.upload(source).json()["added"], 1)
        repeated = self.upload(source).json()
        self.assertEqual(repeated["added"], 0)
        self.assertEqual(repeated["duplicates"], 1)
        self.assertEqual(self.upload(excel(angle=.2)).status_code, 400)
        self.assertEqual(len(storage.get_records(self.key)), 1)
        self.assertEqual(storage.get_records(self.key)[0]["angle_x"], .1)

    def test_wrong_schema_is_reported_without_partial_import(self):
        self.assertEqual(self.upload(excel(missing_sheet=True)).status_code, 400)
        self.assertEqual(len(storage.get_records(self.key)), 0)

    def test_snapshot_is_immutable_and_pdf_uses_same_result(self):
        self.upload(excel())
        generated = self.client.post(f"/api/warehouses/{self.key}/reports", json={"cycle": "week"})
        self.assertEqual(generated.status_code, 200)
        report = generated.json()
        settings = storage.get_warehouse(self.key)["settings"]
        settings["angle_change_deg"] = .2
        self.assertEqual(self.client.put(f"/api/warehouses/{self.key}/settings", json=settings).status_code, 200)
        metadata = storage.get_warehouse(self.key)["devices"]
        metadata[0].update(x=.2, y=.3, group="新点组")
        self.assertEqual(self.client.put(f"/api/warehouses/{self.key}/devices", json=metadata).status_code, 200)
        self.assertEqual(self.client.get(f"/api/reports/{report['id']}").json(), report)
        pdf = self.client.get(f"/api/reports/{report['id']}/pdf")
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        self.assertEqual(report["devices"][0]["current"]["distance"], 5)

    def test_threshold_requires_basis_and_unknown_device_cannot_be_injected(self):
        settings = storage.get_warehouse(self.key)["settings"]
        settings["distance_limit_mm"] = 15
        self.assertEqual(self.client.put(f"/api/warehouses/{self.key}/settings", json=settings).status_code, 400)
        self.upload(excel())
        self.assertEqual(self.client.put(f"/api/warehouses/{self.key}/devices", json=[{"id": "evil"}]).status_code, 400)

    def test_two_warehouses_do_not_share_record_identity(self):
        self.upload(excel())
        second = self.client.post("/api/warehouses", json={"name": "另一仓库"}).json()["id"]
        result = self.client.post(f"/api/warehouses/{second}/import", files={"file": ("source.xlsx", excel())})
        self.assertEqual(result.json()["added"], 1)
        self.assertEqual(len(storage.get_records(self.key)), 1)
        self.assertEqual(len(storage.get_records(second)), 1)

    def test_subsecond_events_are_not_collapsed_as_duplicates(self):
        first = self.upload(excel(event_time="2026-10-01 12:00:00.100000"))
        second = self.upload(excel(angle=.2, event_time="2026-10-01 12:00:00.200000"))
        self.assertEqual(first.json()["added"], 1)
        self.assertEqual(second.json()["added"], 1)
        self.assertEqual(len(storage.get_records(self.key)), 2)


if __name__ == "__main__":
    unittest.main()
