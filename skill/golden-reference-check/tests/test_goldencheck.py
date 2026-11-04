import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from goldencheck.core import compare, load_data, read_json, run_case
from goldencheck.models import dft, envelope, fir, statistics
from goldencheck.__main__ import collect_metrics, run_suite


class ComparisonTests(unittest.TestCase):
    def test_tolerance_boundary_and_relative(self):
        self.assertEqual(compare([10, 0], [11, 0.1], atol=0.1, rtol=0.1)["status"], "PASS")
        self.assertEqual(compare([0], [0.10001], atol=0.1)["status"], "FAIL")

    def test_structure_not_silently_zipped(self):
        for expected, actual in (([1, 2], [1]), ({"x": 1}, {"x": 1, "extra": 2}), ([1], {"0": 1}), (True, 1)):
            self.assertEqual(compare(expected, actual)["status"], "FAIL")

    def test_nonfinite_and_empty_cannot_pass(self):
        for x in (math.nan, math.inf, -math.inf):
            self.assertEqual(compare([x], [x])["status"], "FAIL")
        with self.assertRaises(ValueError):
            compare([], [])

    def test_override_exact_pointer_and_typo(self):
        self.assertEqual(compare({"a/b": [1]}, {"a/b": [1.5]}, overrides={"/a~1b/0": {"atol": 0.5}})["status"], "PASS")
        with self.assertRaises(ValueError):
            compare([1], [1], overrides={"/typo": {"atol": 1}})

    def test_invalid_tolerance_rejected(self):
        for tolerance in (-1, math.inf, True):
            with self.assertRaises(ValueError):
                compare(1, 1, atol=tolerance)
        with self.assertRaises(ValueError):
            compare([1], [1], overrides={"": {"atol": 1}})
        with self.assertRaises(ValueError):
            compare([1], [1], max_details=-1)

    def test_rmse_and_detail_cap(self):
        result = compare([0, 0], [3, 4], max_details=1)
        self.assertAlmostEqual(result["rmse"], math.sqrt(12.5))
        self.assertEqual(result["mismatches"], 2)
        self.assertTrue(result["details_truncated"])


class ReferenceTests(unittest.TestCase):
    def test_statistics_dc_and_impulse_fir(self):
        self.assertEqual(statistics([2, 2, 2])["rms"], 2)
        self.assertEqual(fir([1, 0, 0, 0], [1, 2, 3]), [1, 2, 3, 0])

    def test_envelope_covers_once_and_ties(self):
        result = envelope([5, 5, -1, 2, -1], 2)
        self.assertEqual([(x["first"], x["last"]) for x in result], [(0, 1), (2, 4)])
        self.assertEqual(result[0]["max_index"], 0)
        self.assertEqual(result[1]["min_index"], 2)
        self.assertEqual(len(envelope([1, 2], 20)), 2)

    def test_dft_known_impulse_dc_and_hann(self):
        self.assertEqual(compare([[1, 0]]*8, dft([1]+[0]*7), atol=1e-12)["status"], "PASS")
        result = dft([2]*8)
        self.assertAlmostEqual(result[0][0], 16)
        self.assertTrue(all(abs(x)+abs(y) < 1e-12 for x, y in result[1:]))
        self.assertAlmostEqual(dft([1]*8, window="hann")[0][0], 4)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        (self.base / "in.json").write_text("[1, 2, 3]", encoding="utf-8")

    def case(self, observed):
        return {"id": "test", "input": {"path": "in.json"}, "reference": {"model": "identity"}, "observed": observed}

    def test_csv_bom_metadata_and_bad_values(self):
        path = self.base / "x.csv"
        path.write_text("# source,recorded\nx,y\n1,3\n2,4\n", encoding="utf-8-sig")
        data, source = load_data({"path": "x.csv", "column": "y"}, self.base)
        self.assertEqual(data, [3, 4])
        self.assertEqual(len(source["sha256"]), 64)
        with self.assertRaises(ValueError):
            load_data({"path": "x.csv", "column": "missing"}, self.base)
        path.write_text("x\nNaN\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            load_data({"path": "x.csv", "column": "x"}, self.base)

    def test_json_duplicate_and_nonfinite(self):
        for content in ('{"x":1,"x":2}', '[NaN]'):
            (self.base / "bad.json").write_text(content, encoding="utf-8")
            with self.assertRaises(ValueError):
                read_json(self.base / "bad.json")

    def test_metrics_import_and_json_selector(self):
        path = self.base / "metrics.json"
        path.write_text(json.dumps({"scope": "fixture-only", "metrics": [
            {"name": "lut", "value": 123, "unit": "LUT"},
            {"name": "latency", "value": None, "unit": "cycles"}]}), encoding="utf-8")
        rows = collect_metrics([{"path": "metrics.json"}], self.base)
        self.assertEqual([r["status"] for r in rows], ["PROVIDED", "UNAVAILABLE"])
        self.assertEqual(len(rows[0]["source_sha256"]), 64)
        value, _ = load_data({"path": "metrics.json", "keys": ["metrics", 0, "value"]}, self.base)
        self.assertEqual(value, 123)

    def test_custom_reference_from_importable_module(self):
        (self.base / "independent_custom_reference.py").write_text(
            "def gain(data, factor):\n    return [x*factor for x in data]\n", encoding="utf-8")
        (self.base / "actual.json").write_text("[2, 4, 6]", encoding="utf-8")
        case = self.case({"path": "actual.json"})
        case["reference"] = {"model": "independent_custom_reference:gain", "params": {"factor": 2}}
        with patch.object(sys, "path", [str(self.base)] + sys.path):
            result = run_case(case, self.base)
        sys.modules.pop("independent_custom_reference", None)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(len(result["reference"]["sha256"]), 64)

    def test_command_failure_missing_and_timeout(self):
        for code, timeout in (("raise SystemExit(9)", 5), ("pass", 5), ("import time;time.sleep(3)", 0.05)):
            c = self.case({"mode": "command", "argv": ["{python}", "-c", code], "timeout_seconds": timeout})
            self.assertEqual(run_case(c, self.base)["status"], "ERROR")

    def test_suite_artifacts_html_escape_and_no_overwrite(self):
        config = self.base / "suite.json"
        config.write_text(json.dumps({"schema_version": 1, "name": "<script>alert(1)</script>",
                                     "cases": [self.case({"path": "in.json"})]}), encoding="utf-8")
        out = self.base / "report"
        r = run_suite(config, out)
        self.assertEqual(r["status"], "PASS")
        self.assertTrue((out / r["cases"][0]["actual_artifact"]["path"]).exists())
        self.assertNotIn("<script>", (out / "report.html").read_text(encoding="utf-8"))
        self.assertEqual(r["metrics"][0]["status"], "UNAVAILABLE")
        with self.assertRaises(FileExistsError):
            run_suite(config, out)

    def test_cli_exit_statuses(self):
        for name, observed, expected_code in (("pass", "in.json", 0), ("fail", "wrong.json", 1), ("error", "absent.json", 2)):
            (self.base / "wrong.json").write_text("[9]", encoding="utf-8")
            config = self.base / f"{name}.json"
            config.write_text(json.dumps({"schema_version": 1, "name": name, "cases": [self.case({"path": observed})]}), encoding="utf-8")
            result = subprocess.run([sys.executable, "-m", "goldencheck", str(config), "--out", str(self.base / name)], capture_output=True)
            self.assertEqual(result.returncode, expected_code, result.stderr)


if __name__ == "__main__":
    unittest.main()
