"""One-command verification. Negative-suite FAIL/ERROR is expected and checked."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from goldencheck.__main__ import run_suite


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    out = ROOT / "reports" / stamp
    out.mkdir(parents=True)
    tests = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                           cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    (out / "unittest.log").write_text(tests.stdout + tests.stderr, encoding="utf-8")
    match = re.search(r"Ran (\d+) tests", tests.stderr)
    checks = {"unit_tests": {"status": "PASS" if tests.returncode == 0 else "FAIL", "count": int(match[1]) if match else None}}
    for name, file in (("demo", "demo_suite.json"), ("scope", "scope_suite.json"), ("negative", "negative_suite.json")):
        report = run_suite(ROOT / "examples" / file, out / name)
        expected = {"numeric-mismatch": "FAIL", "length-mismatch": "FAIL", "missing-output": "ERROR"} if name == "negative" else None
        good = {c["id"]: c["status"] for c in report["cases"]} == expected if expected else report["status"] == "PASS"
        checks[name] = {"status": "PASS" if good else "FAIL", "suite_status": report["status"], "summary": report["summary"]}
    summary = {"status": "PASS" if all(c["status"] == "PASS" for c in checks.values()) else "FAIL",
               "checks": checks, "note": "Negative suite intentionally contains FAIL and ERROR. No hardware access performed."}
    (out / "verification_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Reports: {out}")
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
