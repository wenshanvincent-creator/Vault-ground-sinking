import io
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import openpyxl
from fastapi.testclient import TestClient

from vault import storage
from vault.app import app


def trend_excel(begin=0, end=35):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Result"
    sheet.append(["name", "message_type", "angle_x", "angle_y", "event_time", "x_displacement", "y_displacement"])
    for i in range(begin, end):
        angle = min(i, 34) * .001
        sheet.append(["A", "Heartbeat", angle, 0, (date(2026, 9, 1) + timedelta(days=i)).isoformat() + " 12:00:00", angle * 100, 0])
    stream = io.BytesIO()
    workbook.save(stream)
    workbook.close()
    return stream.getvalue()


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = storage.DATA
        storage.DATA = Path(self.temp.name)
        self.context = TestClient(app)
        self.client = self.context.__enter__()
        self.key = self.client.post("/api/warehouses", json={"name": "流程验证"}).json()["id"]
        self.base = f"/api/warehouses/{self.key}"
        self.client.post(self.base + "/import", files={"file": ("trend.xlsx", trend_excel())}).raise_for_status()

    def tearDown(self):
        self.context.__exit__(None, None, None)
        storage.DATA = self.original
        self.temp.cleanup()

    def report(self, cutoff=None):
        response = self.client.post(self.base + "/reports", json={"cycle": "week", "cutoff": cutoff})
        response.raise_for_status()
        return response.json()

    def issues(self):
        return self.client.get(self.base + "/issues").json()

    def test_repeat_reports_no_duplicate_and_no_automatic_closure(self):
        first = self.report()
        self.report()
        self.assertEqual(len(self.issues()), 2)
        issue = next(i for i in self.issues() if i["kind"] == "persistent")
        self.assertEqual(len(issue["events"]), 2)
        updated = self.client.put(self.base + f"/issues/{issue['id']}", json={
            "version": issue["version"], "status": "resolved", "author": "测试管理员", "note": "测试处理记录"})
        self.assertEqual(updated.status_code, 200)
        recurring = self.report()
        resolved = next(i for i in recurring["tracking"] if i["id"] == issue["id"])
        self.assertTrue(resolved["recheck_needed"])
        self.assertEqual(resolved["status"], "resolved")
        self.client.post(self.base + "/import", files={"file": ("next.xlsx", trend_excel(35, 42))}).raise_for_status()
        next_report = self.report()
        tracked = next(i for i in next_report["tracking"] if i["id"] == issue["id"])
        self.assertEqual(tracked["status"], "resolved")
        self.assertEqual(tracked["latest_assessment"]["outcome"], "not_triggered")
        # Backfilled older reports must not replace the current assessment.
        settings = self.client.get(self.base).json()["settings"]
        settings["trend_deg_week"] = .00001
        self.client.put(self.base + "/settings", json=settings).raise_for_status()
        self.report("2026-10-05")
        current = next(i for i in self.issues() if i["id"] == issue["id"])
        self.assertEqual(current["latest_assessment"]["cutoff"], "2026-10-12")
        self.assertEqual(self.client.get(f"/api/reports/{first['id']}").json(), first)

    def test_site_history_is_separate_from_causes_and_frozen_in_reports(self):
        old = self.report()
        event = {"event_on": "2026-09-15", "event_type": "load", "location": "A点", "members": ["A"],
                 "description": "测试载荷调整", "recorded_by": "测试记录人", "certainty": "confirmed"}
        self.assertEqual(self.client.post(self.base + "/site-events", json=event).status_code, 422)
        event["source"] = "测试操作记录"
        saved = self.client.post(self.base + "/site-events", json=event)
        self.assertEqual(saved.status_code, 200)
        event["members"] = ["别的仓库设备"]
        self.assertEqual(self.client.post(self.base + "/site-events", json=event).status_code, 400)
        new = self.report()
        self.assertTrue(any(e["kind"] == "site_event" for e in new["archive_events"]))
        self.assertEqual(new["counts"], old["counts"])
        self.assertEqual(self.client.get(f"/api/reports/{old['id']}").json(), old)

    def test_confirmation_requires_evidence_and_changes_invalidate_it(self):
        devices = self.client.get(self.base).json()["devices"]
        devices[0]["evidence"] = {"axis": {"status": "confirmed"}}
        self.assertEqual(self.client.put(self.base + "/devices", json=devices).status_code, 422)
        devices[0]["evidence"]["axis"].update(source="测试照片方向标记", confirmed_on="2026-10-01", confirmed_by="验证人员")
        result = self.client.put(self.base + "/devices", json=devices)
        self.assertTrue(result.json()["devices"][0]["axis_confirmed"])
        snapshot = self.report()
        devices = result.json()["devices"]
        devices[0]["rotation_deg"] = 90
        result = self.client.put(self.base + "/devices", json=devices)
        self.assertFalse(result.json()["devices"][0]["axis_confirmed"])
        self.assertEqual(result.json()["devices"][0]["evidence"]["axis"]["status"], "unknown")
        self.assertGreaterEqual(len(result.json()["archive_events"]), 2)
        self.assertTrue(self.client.get(f"/api/reports/{snapshot['id']}").json()["devices"][0]["axis_confirmed"])
        devices = result.json()["devices"]
        devices[0].update(x=.2, y=.3)
        devices[0]["evidence"]["position"] = {"status": "confirmed", "source": "测试定位依据", "confirmed_on": "2026-10-01", "confirmed_by": "检查人"}
        self.client.put(self.base + "/devices", json=devices).raise_for_status()
        devices[0].update(x=None, y=None)
        cleared = self.client.put(self.base + "/devices", json=devices)
        self.assertEqual(cleared.status_code, 200)
        self.assertEqual(cleared.json()["devices"][0]["evidence"]["position"]["status"], "unknown")

    def test_profile_reference_confirmation_does_not_survive_changed_baseline(self):
        settings = self.client.get(self.base).json()["settings"]
        settings["reference_start"] = "2026-09-01"
        self.client.put(self.base + "/settings", json=settings).raise_for_status()
        profile = {"evidence": {"reference": {"status": "confirmed", "source": "测试起点", "confirmed_on": "2026-10-01", "confirmed_by": "检查人"}}}
        self.client.put(self.base + "/profile", json=profile).raise_for_status()
        settings["reference_start"] = "2026-09-02"
        result = self.client.put(self.base + "/settings", json=settings)
        self.assertEqual(result.json()["profile"]["evidence"]["reference"]["status"], "unknown")

    def test_inspection_attachment_snapshot_and_simulation_isolation(self):
        before = self.report()
        issue = self.issues()[0]
        payload = {"checked_on": "2026-10-06", "inspector": "测试检查人", "location": "A点", "observation": "测试观察",
                   "cause": "测试原因", "conclusion": "confirmed"}
        path = self.base + f"/issues/{issue['id']}/inspections"
        self.assertEqual(self.client.post(path, json=payload).status_code, 422)
        payload["basis"] = "测试仪器复测记录"
        created = self.client.post(path, json=payload).json()
        event = next(e for e in reversed(created["events"]) if e["kind"] == "inspection")
        upload_path = self.base + f"/issues/{issue['id']}/events/{event['id']}/attachments"
        uploaded = self.client.post(upload_path, files={"file": ("measurement.csv", b"point,height_mm\nA,1\n")})
        self.assertEqual(uploaded.status_code, 200)
        attachment = next(e for e in uploaded.json()["events"] if e["id"] == event["id"])["attachments"][0]
        download = self.client.get(self.base + f"/issues/{issue['id']}/attachments/{attachment['id']}")
        self.assertEqual(download.content, b"point,height_mm\nA,1\n")
        demo = self.client.post(self.base + "/simulation").json()
        self.assertTrue(demo["is_demo"])
        self.assertEqual(self.client.post(self.base + "/simulation").json()["id"], demo["id"])
        after = self.report()
        self.assertTrue(all(not i["is_demo"] for i in after["tracking"]))
        target = next(i for i in after["tracking"] if i["id"] == issue["id"])
        self.assertTrue(any(e["attachments"] for e in target["events"]))
        self.assertEqual(self.client.get(f"/api/reports/{before['id']}").json(), before)
        pdf = self.client.get(f"/api/reports/{after['id']}/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF"))

    def test_cross_warehouse_links_and_lost_updates_are_rejected(self):
        report = self.report()
        issue = self.issues()[0]
        other = self.client.post("/api/warehouses", json={"name": "另一仓库"}).json()["id"]
        self.assertEqual(self.client.post(f"/api/warehouses/{other}/issues", json={"report_id": report["id"], "device_id": "A", "reason": "测试"}).status_code, 404)
        change = {"version": issue["version"], "status": "observing", "note": "继续复看", "author": "管理员"}
        self.assertEqual(self.client.put(self.base + f"/issues/{issue['id']}", json=change).status_code, 200)
        self.assertEqual(self.client.put(self.base + f"/issues/{issue['id']}", json=change).status_code, 409)
        self.assertEqual(self.client.put(f"/api/warehouses/{other}/issues/{issue['id']}", json=change).status_code, 404)
        handling = next(e for e in self.issues()[0]["events"] if e["kind"] == "handling")
        self.assertEqual(self.client.post(self.base + f"/issues/{issue['id']}/events/{handling['id']}/attachments", files={"file": ("x.txt", b"test")}).status_code, 400)

    def test_sparse_followup_is_unknown_and_not_recovery(self):
        self.report()
        self.client.post(self.base + "/import", files={"file": ("sparse.xlsx", trend_excel(48, 49))}).raise_for_status()
        followup = self.report()
        self.assertTrue(all(i["latest_assessment"]["outcome"] == "unavailable" for i in followup["tracking"]))
        self.assertTrue(all(i["status"] == "pending" for i in followup["tracking"]))

    def test_long_installation_basis_can_paginate_in_pdf(self):
        profile = {"ground_reference": "测量说明" * 700, "evidence": {"ground_reference": {
            "status": "confirmed", "source": "测量依据" * 450, "confirmed_on": "2026-10-01", "confirmed_by": "检查人"}}}
        self.client.put(self.base + "/profile", json=profile).raise_for_status()
        report = self.report()
        pdf = self.client.get(f"/api/reports/{report['id']}/pdf")
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
