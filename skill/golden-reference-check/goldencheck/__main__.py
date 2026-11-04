import argparse
from datetime import datetime, timezone
import platform
from pathlib import Path
import shutil
import sys

from . import __version__
from .core import load_data, read_json, run_case, sha256
from .report import write_json, write_reports


def collect_metrics(specs, base):
    rows = []
    for spec in specs:
        data, source = load_data(spec, base)
        scope = data["scope"]
        if not isinstance(scope, str) or not scope.strip():
            raise ValueError("metrics require a nonempty scope")
        for metric in data["metrics"]:
            if not isinstance(metric.get("name"), str) or not isinstance(metric.get("unit"), str):
                raise ValueError("metric name and unit must be strings")
            value = metric.get("value")
            # Scalar user-supplied evidence, never automatically called measured hardware.
            if value is not None:
                import math
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError("metric values must be finite numbers or null")
            rows.append(dict(metric, status="PROVIDED" if value is not None else "UNAVAILABLE",
                             scope=scope, source=source["path"], source_sha256=source["sha256"]))
    if not rows:
        rows = [dict(name=k, value=None, unit=u, status="UNAVAILABLE", scope="No evidence supplied")
                for k, u in (("hardware_latency", "s"), ("hardware_throughput", "samples/s"), ("resource_utilization", "%"))]
    return rows


def run_suite(config_path, out):
    config_path = Path(config_path).resolve()
    base = config_path.parent
    config = read_json(config_path)
    if config.get("schema_version") != 1 or not isinstance(config.get("cases"), list) or not config["cases"]:
        raise ValueError("suite requires schema_version=1 and a nonempty cases array")
    ids = [c.get("id") for c in config["cases"]]
    if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("case IDs must be nonempty unique strings")
    if not isinstance(config.get("name"), str) or not config["name"]:
        raise ValueError("suite name is required")
    out = Path(out).resolve()
    # Require a fresh output directory to preserve previous evidence.
    out.mkdir(parents=True, exist_ok=False)
    artifacts = out / "artifacts"
    artifacts.mkdir()
    shutil.copy2(config_path, out / "suite.snapshot.json")
    report = dict(format="goldencheck-report-v1", suite=config["name"],
                  generated_at_utc=datetime.now(timezone.utc).isoformat(),
                  configuration={"path": str(config_path), "sha256": sha256(config_path)},
                  environment={"tool_version": __version__, "python": sys.version,
                               "platform": platform.platform(), "executable": sys.executable},
                  cases=[], metrics=[], evidence_files=[])
    try:
        report["metrics"] = collect_metrics(config.get("metrics", []), base)
        for i, spec in enumerate(config.get("evidence_files", [])):
            source = (base / spec).resolve()
            dest = artifacts / f"evidence_{i:03d}{source.suffix}"
            shutil.copy2(source, dest)
            report["evidence_files"].append({"source": str(source), "sha256": sha256(dest),
                                             "artifact": str(dest.relative_to(out))})
    except Exception as exc:
        report["evidence_error"] = f"{type(exc).__name__}: {exc}"
    for i, case in enumerate(config["cases"]):
        result = run_case(case, base)
        for key in ("_expected", "_actual"):
            if key in result:
                dest = artifacts / f"case_{i:03d}{key}.json"
                write_json(dest, result.pop(key))
                result[key[1:] + "_artifact"] = {"path": str(dest.relative_to(out)), "sha256": sha256(dest)}
        # Preserve original input and observed files independently of parent workspace.
        try:
            for key in ("input", "observed"):
                origin = result.get(key, {})
                if "path" in origin:
                    src = Path(origin["path"])
                    dest = artifacts / f"case_{i:03d}_{key}{src.suffix}"
                    shutil.copy2(src, dest)
                    if sha256(dest) != origin["sha256"]:
                        raise ValueError("source changed during run")
                    origin["artifact"] = str(dest.relative_to(out))
        except Exception as exc:
            result["status"] = "ERROR"
            result["error"] = f"artifact copy: {exc}"
        report["cases"].append(result)
    counts = {s: sum(c["status"] == s for c in report["cases"]) for s in ("PASS", "FAIL", "ERROR")}
    report["status"] = "ERROR" if counts["ERROR"] or "evidence_error" in report else "FAIL" if counts["FAIL"] else "PASS"
    report["summary"] = counts
    write_reports(report, out)
    return report


def main():
    parser = argparse.ArgumentParser(description="Independent golden-reference comparison and evidence reports")
    parser.add_argument("suite", help="JSON suite; data and command paths resolve relative to this file")
    parser.add_argument("--out", required=True, help="new output directory (must not already exist)")
    args = parser.parse_args()
    try:
        report = run_suite(args.suite, args.out)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"{report['status']}: {report['summary']} -> {Path(args.out).resolve() / 'report.html'}")
    return {"PASS": 0, "FAIL": 1, "ERROR": 2}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
