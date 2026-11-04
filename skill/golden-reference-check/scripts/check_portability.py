"""Run from an independent temp directory, with no parent-project modules copied."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix="goldencheck_portable_") as td:
        isolated = Path(td) / "standalone"
        isolated.mkdir()
        for name in ("goldencheck", "examples", "tests", "scripts"):
            shutil.copytree(ROOT / name, isolated / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        result = subprocess.run([sys.executable, "-I", "scripts/verify_all.py"], cwd=isolated,
                                capture_output=True, text=True, encoding="utf-8", errors="replace")
        reports = sorted((isolated / "reports").glob("*/verification_summary.json"))
        summary = json.loads(reports[-1].read_text(encoding="utf-8")) if reports else None
        good = result.returncode == 0 and summary and summary["status"] == "PASS"
        # Copy the standalone verification results before the temp directory is removed.
        dest = ROOT / "reports" / ("portability_" + reports[-1].parent.name if reports else "portability_failed")
        if reports:
            shutil.copytree(reports[-1].parent, dest)
        else:
            dest.mkdir(parents=True, exist_ok=True)
        (dest / "portability.json").write_text(json.dumps({
            "status": "PASS" if good else "FAIL", "method": "Copied only goldencheck, examples, tests and scripts to a fresh temp directory; invoked isolated Python (-I). No parent project modules or UI libraries copied.",
            "command_returncode": result.returncode, "verification": summary,
            "temp_directory_removed_after_run": True}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        (dest / "portability.log").write_text(result.stdout+result.stderr, encoding="utf-8")
        print(f"Portability {'PASS' if good else 'FAIL'}: {dest}")
        return 0 if good else 1


if __name__ == "__main__":
    raise SystemExit(main())
