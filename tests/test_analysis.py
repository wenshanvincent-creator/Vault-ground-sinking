import math
import unittest
from datetime import date, timedelta

from vault.analysis import aggregate, analyze, distance
from vault.models import Device, Settings


def sample_records(device="A", sign=1, count=35, displacement=True):
    records = []
    for i in range(count):
        day = date(2026, 9, 1) + timedelta(days=i)
        angle = sign * i * 0.001
        records.append({"name": device, "message_type": "Heartbeat", "event_time": day.isoformat() + "T12:00:00",
                        "angle_x": angle, "angle_y": 0, "temperature": 25,
                        "x_displacement": 10000 * math.tan(math.radians(angle)) if displacement else None,
                        "y_displacement": 0 if displacement else None, "x_y_displacement": None})
    return records


def warehouse(devices, settings=None):
    return {"id": "test", "name": "测试仓库", "settings": (settings or Settings()).model_dump(),
            "devices": [d.model_dump() for d in devices], "layout": None, "imports": []}


class AnalysisTests(unittest.TestCase):
    def test_euclidean_distance_preserves_missing_and_zero(self):
        self.assertEqual(distance(3, 4), 5)
        self.assertEqual(distance(-3, -4), 5)
        self.assertEqual(distance(0, 0), 0)
        self.assertIsNone(distance(None, 4))

    def test_alarm_bursts_do_not_bias_heartbeat_statistics(self):
        rows = sample_records(count=1)
        rows.extend([{**rows[0], "message_type": "Alarm", "angle_x": 10} for _ in range(50)])
        self.assertEqual(aggregate(rows)[0]["ax"], 0)
        self.assertEqual(aggregate(rows)[0]["count"], 1)

    def test_persistent_trend_and_fixed_reference(self):
        rows = sample_records()
        result = analyze(warehouse([Device(id="A")]), rows)
        device = result["devices"][0]
        self.assertTrue(device["persistent"])
        self.assertAlmostEqual(device["slope_x_week"], 0.007)
        self.assertEqual(device["reference_start"], "2026-09-01")
        self.assertAlmostEqual(device["reference"]["ax"], 0.003)
        self.assertEqual(result["counts"]["reference_changes"], 1)

    def test_missing_displacement_does_not_block_tilt(self):
        result = analyze(warehouse([Device(id="A")]), sample_records(displacement=False))
        self.assertTrue(result["devices"][0]["persistent"])
        self.assertIsNone(result["devices"][0]["current"]["distance"])

    def test_automatic_reference_avoids_initial_missing_displacement(self):
        rows = sample_records()
        for row in rows[:15]:
            row["x_displacement"] = None
            row["y_displacement"] = None
        result = analyze(warehouse([Device(id="A")]), rows)
        device = result["devices"][0]
        self.assertIsNotNone(device["reference"]["distance"])
        self.assertGreater(device["reference_start"], "2026-09-01")
        explicit = Settings(reference_start="2026-09-01")
        fixed = analyze(warehouse([Device(id="A")], explicit), rows)
        self.assertEqual(fixed["devices"][0]["reference_start"], "2026-09-01")
        self.assertIsNone(fixed["devices"][0]["reference"]["distance"])

    def test_sparse_period_does_not_become_a_healthy_result(self):
        rows = sample_records()
        rows = rows[:28] + rows[-1:]
        result = analyze(warehouse([Device(id="A")]), rows)
        self.assertEqual(result["devices"][0]["quality"], "当前周期数据不足")
        self.assertFalse(result["devices"][0]["persistent"])

    def test_regions_are_evidence_and_require_axis_confirmation_for_direction(self):
        devices = [Device(id="A", group="区域", x=.2, y=.5), Device(id="B", group="区域", x=.8, y=.5)]
        rows = sample_records() + sample_records("B", sign=-1)
        result = analyze(warehouse(devices), rows)
        self.assertEqual(len(result["regions"]), 1)
        self.assertIsNone(result["regions"][0]["inward_fraction"])
        self.assertFalse(result["regions"][0]["direction_supported"])
        for d in devices:
            d.axis_confirmed = True
        confirmed = analyze(warehouse(devices), rows)
        self.assertTrue(confirmed["regions"][0]["direction_supported"])

    def test_future_records_do_not_change_saved_cutoff_evaluation(self):
        rows = sample_records()
        w = warehouse([Device(id="A")])
        before = analyze(w, rows[:28], cutoff="2026-09-28")
        after = analyze(w, rows, cutoff="2026-09-28")
        self.assertEqual(before, after)

    def test_unconfigured_thresholds_remain_unknown(self):
        result = analyze(warehouse([Device(id="A")]), sample_records())
        self.assertIsNone(result["devices"][0]["angle_attention"])
        self.assertIsNone(result["devices"][0]["distance_attention"])
        self.assertRaises(ValueError, analyze, warehouse([Device(id="A")]), sample_records(), cutoff="2027-01-01")

    def test_history_matrix_keeps_a_fully_missing_month(self):
        rows = sample_records(count=10)
        rows.append({**rows[-1], "event_time": "2026-11-01T12:00:00"})
        result = analyze(warehouse([Device(id="A")]), rows)
        self.assertEqual(result["history_months"], ["2026-09", "2026-10", "2026-11"])
        self.assertNotIn("2026-10", [m["date"] for m in result["devices"][0]["monthly_matrix"]])


if __name__ == "__main__":
    unittest.main()
