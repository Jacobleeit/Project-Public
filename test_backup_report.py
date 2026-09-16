"""Run with: python -m unittest -v"""

import contextlib
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest

import backup_report as br


class BackupReportTests(unittest.TestCase):
    def setUp(self):
        self.now = br.parse_time("2026-09-16T12:00:00Z")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def job(self, status, stamp, name="server", message=""):
        return br.Job(name, status, br.parse_time(stamp), message)

    def csv_file(self, text, name="input.csv"):
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    def report(self, jobs, inventory=None):
        return br.build_report(jobs, inventory or {}, self.now, 24, inventory is not None)

    def test_latest_failure_is_critical_despite_recent_success(self):
        jobs = [self.job("success", "2026-09-16T10:00:00Z"), self.job("failed", "2026-09-16T11:00:00Z")]
        self.assertEqual(self.report(jobs)["objects"][0]["health"], "CRITICAL")

    def test_successful_retry_restores_health_and_keeps_failure_history(self):
        jobs = [self.job("success", "2026-09-16T11:00:00Z"), self.job("failed", "2026-09-16T10:00:00Z")]
        result = self.report(jobs)
        self.assertEqual(result["objects"][0]["health"], "OK")
        self.assertEqual(len(result["failed_jobs"]), 1)

    def test_exact_age_boundary_and_one_second_over(self):
        exact = self.report([self.job("success", "2026-09-15T12:00:00Z")])
        over = self.report([self.job("success", "2026-09-15T11:59:59Z")])
        self.assertEqual(exact["objects"][0]["health"], "OK")
        self.assertEqual(over["objects"][0]["health"], "CRITICAL")

    def test_inventory_detects_absent_object_and_weekly_override(self):
        result = self.report([self.job("success", "2026-09-13T12:00:00Z", "weekly")],
                             {"weekly": 168, "absent": 24})
        by_name = {row["object_name"]: row for row in result["objects"]}
        self.assertEqual(by_name["weekly"]["health"], "OK")
        self.assertEqual(by_name["absent"]["health"], "CRITICAL")
        self.assertEqual(by_name["absent"]["latest_status"], "no_history")

    def test_warning_running_and_cancelled(self):
        for status, expected in (("warning", "WARNING"), ("running", "WARNING"), ("cancelled", "CRITICAL")):
            with self.subTest(status=status):
                jobs = [self.job("success", "2026-09-16T10:00:00Z"), self.job(status, "2026-09-16T11:00:00Z")]
                self.assertEqual(self.report(jobs)["objects"][0]["health"], expected)
        self.assertEqual(self.report([self.job("warning", "2026-09-16T10:00:00Z")])["objects"][0]["health"], "CRITICAL")

    def test_timezone_offsets_are_normalized_and_naive_time_rejected(self):
        self.assertEqual(br.parse_time("2026-09-16T08:00:00-04:00"), self.now)
        with self.assertRaises(br.InputError):
            br.parse_time("2026-09-16T12:00:00")

    def test_bad_csv_unknown_status_future_and_duplicate_records_rejected(self):
        invalid = [
            "object_name,status\nserver,success\n",
            "object_name,status,timestamp\nserver,success\n",
            "object_name,status,timestamp\nserver,success,2026-09-16T10:00:00Z,extra\n",
            "object_name,status,timestamp\nserver,succeeded,2026-09-16T10:00:00Z\n",
            "object_name,status,timestamp\nserver,success,2026-09-17T10:00:00Z\n",
            "object_name,status,timestamp\n,success,2026-09-16T10:00:00Z\n",
            "object_name,status,timestamp\nserver,success,2026-09-16T10:00:00Z\nserver,failed,2026-09-16T10:00:00Z\n",
        ]
        for content in invalid:
            with self.subTest(content=content), self.assertRaises(br.InputError):
                br.load_jobs(self.csv_file(content), self.now)

    def test_nonfinite_and_nonpositive_thresholds_rejected(self):
        for value in ("NaN", "inf", "-1", "0", "bad"):
            with self.subTest(value=value), self.assertRaises(br.InputError):
                br.positive_hours(value)

    def test_duplicate_inventory_rejected(self):
        path = self.csv_file("object_name,max_age_hours\nserver,24\nserver,48\n")
        with self.assertRaises(br.InputError):
            br.load_inventory(path, 24)

    def test_html_escapes_untrusted_values(self):
        result = self.report([self.job("failed", "2026-09-16T10:00:00Z", "<script>alert(1)</script>", "<img src=x onerror=alert(1)>")])
        rendered = br.render_html(result)
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("<img", rendered)
        self.assertIn("&lt;script&gt;", rendered)

    def test_csv_neutralizes_formulas_and_preserves_quoted_message(self):
        result = self.report([self.job("failed", "2026-09-16T10:00:00Z", "=1+1", '@SUM(1,2)\nnext line')])
        row = next(csv.DictReader(io.StringIO(br.render_csv(result))))
        self.assertEqual(row["object_name"], "'=1+1")
        self.assertEqual(row["latest_message"], "'@SUM(1,2)\nnext line")

    def test_empty_history_requires_inventory(self):
        with self.assertRaises(br.InputError):
            self.report([])
        self.assertEqual(self.report([], {"server": 24})["summary"]["critical"], 1)

    def test_input_files_cannot_be_overwritten(self):
        path = self.csv_file("original input", "backup_summary.csv")
        report = self.report([self.job("success", "2026-09-16T10:00:00Z")])
        with self.assertRaises(br.InputError):
            br.write_reports(report, self.root, [path])
        self.assertEqual(path.read_text(), "original input")

    def test_demo_cli_outputs_and_monitoring_exit_code(self):
        with contextlib.redirect_stdout(io.StringIO()):
            result = br.main(["--demo", "--output-dir", str(self.root), "--fail-on-alert"])
        self.assertEqual(result, 1)
        report = json.loads((self.root / "backup_report.json").read_text())
        self.assertEqual(report["summary"], {"objects": 8, "jobs_in_export": 11, "ok": 3, "warning": 2, "critical": 3})
        self.assertTrue((self.root / "backup_report.html").is_file())
        with (self.root / "backup_summary.csv").open(encoding="utf-8", newline="") as handle:
            self.assertEqual(len(list(csv.DictReader(handle))), 8)

    def test_cli_invalid_data_exits_two_without_reports(self):
        path = self.csv_file("bad header\n")
        target = self.root / "out"
        with contextlib.redirect_stderr(io.StringIO()):
            result = br.main(["--input", str(path), "--output-dir", str(target)])
        self.assertEqual(result, 2)
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
