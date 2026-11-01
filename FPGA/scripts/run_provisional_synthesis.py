"""Fresh, isolated Vivado 2025.2 OOC checks on the provisional XC7A35T.

No board pins, implementation, timing exceptions or simulation models are used.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import sys
from datetime import datetime
from pathlib import Path

FPGA = Path(__file__).resolve().parents[1]
TOPS = ("scope_hw_top", "scope_core", "adc_capture", "dds_core", "trigger_core",
        "bram_capture", "capture_bram",
        "scope_async_fifo", "measurement_core", "multires_envelope",
        "spectrum_analyzer", "scope_uart_endpoint", "relative_calibrator",
        "calibration_apply", "health_compare", "capture_moments",
        "capture_result_stream", "capture_result_uart",
        "scope_dds_rate_adapter")

def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tops", nargs="+", choices=TOPS, default=list(TOPS))
    parser.add_argument("--vivado-bin", type=Path)
    parser.add_argument("--baseline-report", type=Path,
                        help="Reuse verified passing OOC runs; all failed tops must be explicitly rerun")
    a = parser.parse_args()
    tool = (a.vivado_bin or Path(json.loads((FPGA / "scripts/vivado_toolchain.json").read_text())["bin"])) / "vivado.bat"
    if not tool.is_file():
        raise FileNotFoundError(tool)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    report = FPGA / "reports/provisional_synthesis" / run_id
    report.mkdir(parents=True)
    build = Path(tempfile.mkdtemp(prefix="scope_estimate_"))
    sources = sorted((FPGA / "rtl").rglob("*.sv"))
    sources += [FPGA / "scripts" / n for n in ("check_provisional_synthesis.tcl", "ensure_scope_clock_ip.tcl", "ensure_scope_fft_ip.tcl")]
    sources += [FPGA / "ip" / n / f"{n}.xci" for n in ("scope_clk_wiz", "scope_fft_1024")]
    sources += [FPGA / "constraints/scope_estimate_template.xdc"]
    hashes = []
    for p in sources:
        rel = p.relative_to(FPGA)
        dest = build / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, dest)
        digest = sha(p)
        if sha(dest) != digest:
            raise RuntimeError(f"staging mismatch: {rel}")
        hashes.append({"file": rel.as_posix(), "sha256": digest})
    manifest = {"verdict": "RUNNING", "label": "基于暂定 XC7A35T，仅供估算",
                "part": "xc7a35tcsg324-1", "board_timing_signoff": False,
                "full_hardware_integration": False, "tool": str(tool),
                "temporary_build": str(build), "source_sha256": hashes,
                "results": [], "failure": None}
    def save():
        (report / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    save()
    print(f"PROVISIONAL_REPORT={report}", flush=True)
    failed = False
    if a.baseline_report:
        prior = a.baseline_report.resolve()
        old = json.loads((prior / "manifest.json").read_text(encoding="utf-8"))
        if old["verdict"] not in ("PASS", "FAIL") or old["tool"] != str(tool):
            raise RuntimeError("Baseline must be finished and use the same tool")
        failed_tops = {e['top'] for e in old['results'] if e['verdict'] != 'PASS'}
        if old['verdict'] == 'FAIL' and (not failed_tops or not failed_tops.issubset(a.tops)):
            raise RuntimeError("A failed baseline requires explicitly rerunning every failed top; audit-only failures cannot be reused")
        old_hashes = {h["file"]: h["sha256"] for h in old["source_sha256"]}
        if set(old_hashes) - {h["file"] for h in hashes}:
            raise RuntimeError("Baseline sources removed; full rerun required")
        changed = [h["file"] for h in hashes if old_hashes.get(h["file"]) != h["sha256"]]
        changed_modules = []
        for rel in changed:
            if not rel.startswith("rtl/") or not rel.endswith(".sv"):
                raise RuntimeError(f"Non-RTL source changed; full rerun required: {rel}")
            modules = re.findall(r"(?m)^\s*module\s+(\w+)", (FPGA / rel).read_text(encoding="utf-8"))
            if not modules:
                raise RuntimeError(f"Package/interface changed; full rerun required: {rel}")
            changed_modules.extend(modules)
        manifest["baseline_report"] = str(prior)
        manifest["baseline_verdict"] = old['verdict']
        manifest["rerun_failed_tops"] = sorted(failed_tops)
        manifest["changed_files"] = changed
        for e in old["results"]:
            top = e["top"]
            if top in a.tops:
                continue
            if e['verdict'] != 'PASS':
                raise RuntimeError(f"Cannot reuse a failed OOC result: {top}")
            log = (prior / top / "console.log").read_text(encoding="utf-8", errors="replace")
            if any(re.search(r"synthesizing module '" + re.escape(mod) + r"'", log) for mod in changed_modules):
                raise RuntimeError(f"Changed module affects {top}; include it in --tops")
            shutil.copytree(prior / top, report / top)
            manifest["results"].append({**e, "reused_from": str(prior / top),
                                        "dependency_check": "changed modules absent from elaborated hierarchy"})
        save()
    for top in a.tops:
        work = build / "runs" / top
        work.mkdir(parents=True)
        out = work / "artifacts"
        out.mkdir()
        args = [str(tool), "-mode", "batch", "-notrace", "-source",
                str(build / "scripts/check_provisional_synthesis.tcl"), "-log",
                str(work / "vivado.log"), "-journal", str(work / "vivado.jou"),
                "-tclargs", top, str(out), str(build)]
        print(f"START {top}", flush=True)
        # Quote every argument for the vendor Windows batch loader.
        command = " ".join('"' + s + '"' for s in args)
        dest = report / top
        dest.mkdir()
        with (dest / "console.log").open("wb") as log:
            code = subprocess.run(command, cwd=work, stdout=log, stderr=subprocess.STDOUT, shell=True).returncode
        text = (dest / "console.log").read_text(encoding="utf-8", errors="replace")
        diagnostics = re.findall(r"(?m)^\s*(?:ERROR|CRITICAL WARNING|WARNING):.*", text)
        ok = code == 0 and f"PROVISIONAL_OOC_PASS top={top}" in text
        entry = {"top": top, "verdict": "PASS" if ok else "FAIL", "exit_code": code,
                 "diagnostics": [s.strip() for s in diagnostics], "arguments": args}
        resource_file = out / "resources.json"
        if resource_file.is_file():
            entry["resources"] = json.loads(resource_file.read_text())
        for p in work.rglob("*"):
            if p.is_file() and p.suffix in {".log", ".jou", ".rpt", ".json", ".tsv", ".xdc", ".dcp"}:
                target = dest / p.relative_to(work)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(p, target)
        manifest["results"].append(entry)
        save()
        print(f"{entry['verdict']} {top} diagnostics={len(diagnostics)}", flush=True)
        failed |= not ok
    for h in hashes:
        if sha(FPGA / h["file"]) != h["sha256"]:
            failed = True
            manifest["failure"] = "Source changed while synthesis was running"
    manifest["verdict"] = "FAIL" if failed else "PASS"
    save()
    auditor = FPGA / "scripts/audit_provisional_synthesis.py"
    audit_code = subprocess.run([sys.executable, str(auditor), str(report)]).returncode
    manifest = json.loads((report / "manifest.json").read_text(encoding="utf-8"))
    manifest["audit_exit_code"] = audit_code
    if audit_code:
        failed = True
        manifest["verdict"] = "FAIL"
    save()
    print(f"PROVISIONAL_SYNTHESIS_{manifest['verdict']} reports={report}", flush=True)
    # Keep the isolated build until diagnostics and CDC are reviewed.
    return int(failed)

if __name__ == "__main__":
    raise SystemExit(main())
