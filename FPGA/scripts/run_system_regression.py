"""One-command clean XSim build, connected cases and prior foundation suites.

All result records are written before a failing invocation returns nonzero.
Only a failed connected simulation is rerun with a full WDB waveform.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from simulation_environment import configure
from datetime import datetime
from pathlib import Path

SCRIPT = Path(__file__).resolve()
FPGA = SCRIPT.parents[1]
ROOT = FPGA.parent
DEFAULT_BIN = Path(r"D:\AMD\Xilinx\vivado_2025.2\2025.2\Vivado\bin")
SOURCE_STAGES = ("scope_pkg", "safe", "ad9226", "dds", "loopback",
                 "capture", "measure", "uart", "multires",
                 "spectrum", "innovation")


class RegressionFailure(Exception):
    def __init__(self, code: str, detail: str, time_ns: float | None = None):
        super().__init__(detail)
        self.code, self.time_ns = code, time_ns


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args: list[str], cwd: Path, log: Path) -> tuple[int, str]:
    if args[0].lower().endswith(".bat"):
        # Python's Windows list-to-batch quoting splits NAME=VALUE into two
        # argv entries in Vivado's loader. Quoting the whole value in cmd.exe
        # preserves the single --generic_top / --testplusarg argument.
        if any('"' in a for a in args):
            raise ValueError("double quote in batch argument")
        command = " ".join(f'"{a}"' for a in args)
        p = subprocess.run(command, cwd=cwd, capture_output=True, shell=True)
    else:
        p = subprocess.run(args, cwd=cwd, capture_output=True, shell=False)
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_bytes(p.stdout + b"\n" + p.stderr)
    return p.returncode, (p.stdout + b"\n" + p.stderr).decode("utf-8", "replace")


def first_time(text: str) -> float | None:
    m = re.search(r"(?im)^Time:\s*([0-9.]+)\s*(fs|ps|ns|us|ms|s)\b", text)
    if m:
        return float(m[1]) * {"fs": 1e-6, "ps": 1e-3, "ns": 1,
                               "us": 1e3, "ms": 1e6, "s": 1e9}[m[2]]
    m = re.search(r"\btime_ns=([0-9.]+)\b", text)
    return float(m[1]) if m else None


def verify_tool(exit_code: int, text: str, stage: str, pass_pattern: str | None = None) -> None:
    problem = re.search(r"(?im)^\s*(?:ERROR:|CRITICAL WARNING:|WARNING:|Fatal:|TEST_FAIL|FATAL_ERROR:)[^\r\n]*", text)
    if exit_code or problem or (pass_pattern and not re.search(pass_pattern, text, re.M)):
        diagnostic = problem.group(0).strip() if problem else f"exit={exit_code} missing={pass_pattern}"
        raise RegressionFailure(stage, diagnostic, first_time(text))


def staged_sources(build: Path) -> list[Path]:
    first = [FPGA / "rtl/common" / n for n in
             ("scope_pkg.sv", "protocol_pkg.sv")]
    others = sorted(p for p in (FPGA / "rtl").rglob("*.sv") if p not in first)
    models = [FPGA / "sim/models" / n for n in
              ("scope_pin_model.sv", "ad9767_model.sv", "ad9226_model.sv",
               "loopback_channel_model.sv", 
               "system_capture_backend.sv")]
    all_sources = first + others + models + [FPGA / "sim/tb/tb_system_case.sv", FPGA / "sim/tb/tb_scope_system.sv"]
    out = []
    for i, source in enumerate(all_sources):
        dest = build / f"{i:03}_{source.name}"
        shutil.copyfile(source, dest)
        out.append(dest)
    return out


def rerun_wave(bin_dir: Path, snapshot: str, vectors: Path, seed: int,
               build: Path, failure_dir: Path, injected_fault: bool) -> None:
    failure_dir.mkdir(parents=True, exist_ok=True)
    wave_stage = build / f"wave_{snapshot}_{seed}"
    wave_stage.mkdir(exist_ok=True)
    tcl = wave_stage / "wave.tcl"
    tcl.write_text("log_wave -r /*\nrun -all\nquit\n", encoding="ascii")
    args = [str(bin_dir / "xsim.bat"), snapshot, "--tclbatch", tcl.as_posix(),
         "--wdb", (wave_stage / "failure.wdb").as_posix(), "--onerror", "quit",
         "--testplusarg", f"VECTOR_DIR={vectors.as_posix()}",
         "--testplusarg", f"TRACE_DIR={wave_stage.as_posix()}",
         "--testplusarg", f"SEED={seed}"]
    if injected_fault:
        args += ["--testplusarg", "FAULT=1"]
    run(args, build, failure_dir / "rerun.log")
    for name in ("failure.wdb", "wave.tcl", "system_uart.hex", "system_live.csv", "system_measure.csv"):
        path = wave_stage / name
        if path.is_file():
            shutil.copyfile(path, failure_dir / name)


def connected_cases(a: argparse.Namespace, report: Path, build: Path,
                    results: list[dict]) -> None:
    sources = staged_sources(build)
    code, output = run([str(a.vivado_bin / "xvlog.bat"), "-sv", *map(str, sources)],
                       build, report / "connected.compile.log")
    verify_tool(code, output, "CONNECTED_COMPILE")
    for case in a.cases:
        snapshot = f"system_case_{case}"
        code, output = run([str(a.vivado_bin / "xelab.bat"), "tb_scope_system",
                            "-s", snapshot, "--generic_top", f"CASE_ID={case}",
                            "--timescale", "1ns/1ps", "--debug", "typical"], build,
                           report / f"connected.case{case}.elaborate.log")
        verify_tool(code, output, f"CONNECTED_ELAB_CASE_{case}")
        for seed in a.seeds:
            label = f"case{case}_seed{seed}"
            vectors = build / label
            code, output = run([str(a.python), str(FPGA / "scripts/generate_system_case.py"),
                                "--case", str(case), "--seed", str(seed),
                                "--out", str(vectors)], build,
                               report / f"{label}.vectors.log")
            verify_tool(code, output, f"VECTOR_{label}", r"SYSTEM_VECTORS_PASS")
            args = [str(a.vivado_bin / "xsim.bat"), snapshot, "--runall",
                    "--onfinish", "quit", "--onerror", "quit",
                    "--sv_seed", str(seed),
                    "--testplusarg", f"VECTOR_DIR={vectors.as_posix()}",
                    "--testplusarg", f"TRACE_DIR={vectors.as_posix()}",
                    "--testplusarg", f"SEED={seed}"]
            if a.inject_failure_case == case:
                args += ["--testplusarg", "FAULT=1"]
            code, output = run(args, build, report / f"{label}.simulate.log")
            try:
                verify_tool(code, output, f"SIM_{label}",
                            rf"^TEST_PASS tb_system_case case={case} seed={seed} .*errors=0\r?$")
            except RegressionFailure as exc:
                exc.replay = dict(snapshot=snapshot, vectors=vectors, seed=seed, case=case,
                                  fault=a.inject_failure_case == case, label=label)
                raise
            audit_path = report / label / "audit.json"
            code, output = run([str(a.python), str(FPGA / "scripts/audit_system_case.py"),
                                "--vectors", str(vectors), "--traces", str(vectors),
                                "--output", str(audit_path)], build,
                               report / f"{label}.audit.log")
            if code or "SYSTEM_AUDIT_PASS" not in output:
                fail = json.loads(audit_path.read_text(encoding="utf-8")) if audit_path.exists() else {}
                exc = RegressionFailure(f"AUDIT_{label}", output.strip(), fail.get("first_error_time_ns"))
                exc.replay = dict(snapshot=snapshot, vectors=vectors, seed=seed, case=case, fault=False, label=label)
                raise exc
            result = json.loads(audit_path.read_text(encoding="utf-8"))
            results.append(result)
            print(f"CONNECTED_PASS case={case} seed={seed} frame={result['frame_length']} "
                  f"compared={result['wave_compared']}", flush=True)
    for seed in a.seeds if 2 in a.cases and 3 in a.cases else ():
        small = next(x for x in results if x["case"] == 2 and x["seed"] == seed)
        large = next(x for x in results if x["case"] == 3 and x["seed"] == seed)
        if large["peak_to_peak"] <= small["peak_to_peak"]:
            raise RegressionFailure("AMPLITUDE_MONOTONIC", f"seed={seed} "
                                    f"small={small['peak_to_peak']} large={large['peak_to_peak']}")
    return None


def prior_suites(a: argparse.Namespace, report: Path, selected=None) -> list[dict]:
    out = []
    def quoted(path: Path) -> str:
        return "'" + str(path).replace("'", "''") + "'"
    # This runner both executes and checks a delete/rebuild of the generated
    # Vivado .sim directory with a fixed seed. Its existing safety checks guard
    # against deleting anything outside the exact generated path.
    stages = [("smoke", "run_smoke.ps1", f"-Seed {a.seeds[0]}")]
    stages += [(name, f"run_{name}_tb.ps1",
                f"-Seeds @({','.join(map(str, a.seeds))})" +
                (" -SkipReplay" if name not in ("scope_pkg",) else ""))
               for name in SOURCE_STAGES]
    for name, script, extra in stages:
        if selected is not None and name not in selected:
            continue
        # Native project scans also require ASCII source/project paths, not
        # merely an ASCII compiler TEMP directory.
        native_fpga = Path(os.environ.get('SCOPE_SIM_PROJECT_ROOT', str(ROOT)))/'FPGA'
        command = f"& {quoted(native_fpga / 'scripts' / script)} -VivadoBin {quoted(a.vivado_bin)} {extra}"
        if name not in ("smoke", "safe", "scope_pkg"):
            command += f" -PythonExe {quoted(a.python)}"
        if name == 'measure':
            command += ' -Project'
        args = ["pwsh", "-NoProfile", "-Command", command]
        code, text = run(args, ROOT, report / f"suite.{name}.log")
        m = re.search(r"(?m)\b(?:[A-Z0-9_]+_)?REGRESSION_PASS reports=(.+)$", text)
        if code or not m:
            raise RegressionFailure(f"SUITE_{name}",
                                    f"exit={code}; {text[-1200:]}", first_time(text))
        stage_report = Path(m[1].strip())
        manifest = stage_report / "manifest.json"
        if not manifest.is_file():
            raise RegressionFailure(f"SUITE_{name}", f"missing PASS manifest: {manifest}")
        payload = json.loads(manifest.read_text(encoding="utf-8-sig"))
        if payload["verdict"] != "PASS":
            raise RegressionFailure(f"SUITE_{name}", f"non-PASS manifest: {manifest}")
        if name == "smoke":
            observed = [payload["seed"]]
        else:
            observed = payload.get("seeds")
            if observed is None:
                observed = [r["seed"] for r in payload.get("results", [])]
        if isinstance(observed, int):
            observed = [observed]
        expected = a.seeds[:1] if name == "smoke" else a.seeds
        if sorted(observed) != sorted(expected):
            raise RegressionFailure(f"SUITE_{name}_SEEDS",
                                    f"expected={expected} observed={observed}")
        item = dict(suite=name, verdict="PASS", seeds=a.seeds,
                    report=str(stage_report), first_error_time_ns=None)
        out.append(item)
        print(f"FOUNDATION_PASS suite={name} report={stage_report}", flush=True)
    return out


def unit_suites(a: argparse.Namespace, report: Path) -> list[dict]:
    from run_unit_regression import TESTS
    paths = a.unit_reports
    if not paths:
        code, text = run([str(a.python), str(FPGA / 'scripts/run_unit_regression.py'),
                          '--vivado-bin', str(a.vivado_bin), '--seeds', *map(str, a.seeds)],
                         ROOT, report / 'layer.unit.log')
        found = re.search(r'(?m)^UNIT_REGRESSION_(?:PASS|FAIL) report=(.+)$', text)
        if not found:
            raise RegressionFailure('UNIT_LAYER', text[-1200:], first_time(text))
        paths = [Path(found[1].strip())]
        if code:
            failure = json.loads((paths[0] / 'manifest.json').read_text(encoding='utf-8'))
            err = failure.get('first_error') or {}
            raise RegressionFailure('UNIT_LAYER', json.dumps(dict(report=str(paths[0]), **err)), err.get('time_ns'))
    coverage = set()
    payloads = []
    for directory in paths:
        file = directory / 'manifest.json'
        payload = json.loads(file.read_text(encoding='utf-8'))
        if payload['verdict'] != 'PASS' or payload.get('layer') != 'unit' or sorted(payload['seeds']) != sorted(a.seeds):
            raise RegressionFailure('UNIT_LAYER', f'incompatible unit report: {file}')
        for rel, digest in payload['source_sha256'].items():
            if sha(FPGA / rel) != digest:
                raise RegressionFailure('UNIT_SOURCE_CHANGED', f'{file}: {rel}')
        coverage.update((r['test'], r['seed']) for r in payload['results'] if r['verdict'] == 'PASS')
        payloads.append(dict(report=str(directory), tests=payload['tests'], verdict='PASS'))
    missing = {(test, seed) for test in TESTS for seed in a.seeds} - coverage
    if missing:
        raise RegressionFailure('UNIT_COVERAGE', f'missing unit runs: {sorted(missing)}')
    print(f'UNIT_LAYER_PASS tests={len(TESTS)}', flush=True)
    return payloads


def execute_layers(a: argparse.Namespace, report: Path, build: Path, manifest: dict) -> None:
    def enter(layer):
        manifest['active_layer'] = layer
        manifest['phase_history'].append(layer)
        print(f'LAYER_START {layer}', flush=True)
    if not a.system_only:
        enter('unit')
        manifest['foundation'].extend(prior_suites(a, report, {'smoke', 'scope_pkg'}))
        manifest['unit_reports'] = unit_suites(a, report)
        manifest['prerequisites_verified'] = True
        # These four legacy families are now provided by the isolated roots;
        # avoid rerunning their unchanged complete suites a second time.
        for family, test in {'safe':'safe_seq','ad9226':'adc_capture','dds':'dds_dac','capture':'capture_bram'}.items():
            source = next(x['report'] for x in manifest['unit_reports'] if test in x['tests'])
            manifest['foundation'].append(dict(suite=family, verdict='PASS', seeds=a.seeds,
                                               report=source, first_error_time_ns=None))
        enter('integration')
        manifest['foundation'].extend(prior_suites(a, report,
            {'loopback', 'measure', 'uart', 'multires', 'spectrum', 'innovation'}))
    enter('system')
    connected_cases(a, report, build, manifest['connected'])


def diagnose_lower_layer(a, report, exc):
    case = getattr(exc, 'replay', {}).get('case')
    seed = getattr(exc, 'replay', {}).get('seed', a.seeds[0])
    if case is not None:
        names = {0:['safe_seq','dds_dac','adc_capture'],1:['trigger','capture_bram','protocol'],
                 2:['dds_dac','adc_capture','measure'],3:['dds_dac','adc_capture','measure'],
                 4:['fft'],5:['envelope'],6:['adc_capture','capture_bram','protocol'],
                 7:['safe_seq']}[case]
    else:
        names = next((v for k,v in {'measure':['trigger','measure','capture_bram'],
            'uart':['uart_phy','protocol'],'multires':['envelope'],
            'spectrum':['fft'],'loopback':['dds_dac','adc_capture']}.items() if exc.code == f'SUITE_{k}'), [])
    if not names:
        return dict(status='not_applicable', reason='failure already belongs to unit/preflight layer')
    code, text = run([str(a.python), str(FPGA/'scripts/run_unit_regression.py'), '--tests', *names,
        '--seeds', str(seed), '--vivado-bin', str(a.vivado_bin)], ROOT, report/'lower_layer_diagnosis.log')
    m = re.search(r'(?m)^UNIT_REGRESSION_(PASS|FAIL) report=(.+)$', text)
    return dict(status='smallest_unit_failed' if code else 'candidate_units_passed_higher_layer_failure',
                candidates=names, seed=seed, report=m[2].strip() if m else None)


def compose_use_cases(connected: list[dict], suites: list[dict], seeds: list[int]) -> list[dict]:
    stages = {x["suite"] for x in suites}
    by_case = {c for c, _ in ((x["case"], x["seed"]) for x in connected)}
    defs = [
        ("safe_start", (0,), ("safe", "smoke")),
        ("mid_loopback", (0,), ("loopback",)),
        ("sine_10khz", (1,), ("capture", "uart")),
        ("sine_100khz", (2, 3), ("measure",)),
        ("coherent_1mhz", (4,), ("spectrum",)),
        ("single_point_spike", (5,), ("multires", "innovation")),
        ("otr_injection", (6,), ("capture", "uart")),
        ("uart_fault", (), ("uart",)),
        ("emergency_disable", (7,), ("safe",)),
    ]
    return [dict(name=name, verdict="PASS" if all(c in by_case for c in cases)
                 and all(s in stages for s in required) else "NOT_RUN",
                 connected_cases=list(cases), foundation_suites=list(required), seeds=seeds,
                 first_error_time_ns=None) for name, cases, required in defs]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--vivado-bin", type=Path, default=DEFAULT_BIN)
    p.add_argument("--python", type=Path, default=Path(sys.executable))
    p.add_argument("--seeds", type=int, nargs="+", default=[20261020, 42])
    p.add_argument("--cases", type=int, nargs="+", default=list(range(8)))
    p.add_argument("--system-only", action="store_true")
    p.add_argument("--unit-reports", type=Path, nargs='+', default=[],
                   help="Reuse only passing isolated unit reports with matching seeds and source hashes")
    p.add_argument("--inject-failure-case", type=int, default=-1)
    p.add_argument("--no-failure-wave", action="store_true")
    a = p.parse_args()
    if not a.seeds or len(a.seeds) != len(set(a.seeds)) or any(s < 0 for s in a.seeds):
        p.error("seeds must be unique, nonnegative integers")
    if any(c not in range(8) for c in a.cases) or len(a.cases) != len(set(a.cases)):
        p.error("cases must be unique integers 0..7")
    if a.inject_failure_case >= 0 and a.inject_failure_case not in a.cases:
        p.error("injected case must be selected")
    environment = configure(a.vivado_bin)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + os.urandom(4).hex()
    report = FPGA / "reports/system" / run_id
    build = Path(tempfile.gettempdir()) / f"scope_system_{run_id}"
    report.mkdir(parents=True)
    build.mkdir()
    manifest: dict = dict(verdict="FAIL", run_id=run_id, seeds=a.seeds,
                          cases=a.cases, system_only=a.system_only,
                          fault_injected_case=a.inject_failure_case if a.inject_failure_case >= 0 else None,
                          toolchain=str(a.vivado_bin), build=str(build),
                          connected=[], foundation=[], use_cases=[], unit_reports=[], phase_history=[],
                          prerequisites_verified=False, active_layer=None, environment=environment,
                          first_error=None, source_sha256={}, temporary_build_removed=False)
    relevant = [*sorted((FPGA / "rtl").rglob("*.sv")),
                *sorted((FPGA / "sim").rglob("*.sv")),
                SCRIPT, FPGA / "scripts/generate_system_case.py",
                FPGA / "scripts/audit_system_case.py",
                FPGA / "scripts/generate_measure_vectors.py",
                FPGA / "scripts/run_unit_regression.py",
                FPGA / "scripts/simulation_environment.py",
                FPGA / "scripts/generate_protocol_unit_vectors.py",
                ROOT / "PC/protocol/scope_protocol.py"]
    manifest["source_sha256"] = {str(x.relative_to(ROOT)): sha(x) for x in relevant}
    try:
        execute_layers(a, report, build, manifest)
        manifest["use_cases"] = compose_use_cases(
            manifest["connected"], manifest["foundation"], a.seeds)
        if not a.system_only and any(x["verdict"] != "PASS" for x in manifest["use_cases"]):
            raise RegressionFailure("USE_CASE_COVERAGE", "one or more mandatory use cases missing")
        for x in relevant:
            if sha(x) != manifest["source_sha256"][str(x.relative_to(ROOT))]:
                raise RegressionFailure("SOURCE_CHANGED", str(x))
        resolved_build = build.resolve()
        resolved_temp = Path(tempfile.gettempdir()).resolve()
        if resolved_build.parent != resolved_temp or resolved_build.is_symlink():
            raise RegressionFailure("UNSAFE_TEMP_CLEANUP", str(resolved_build))
        shutil.rmtree(resolved_build)
        manifest["temporary_build_removed"] = True
        manifest["verdict"] = "PASS"
    except RegressionFailure as exc:
        manifest["first_error"] = dict(code=exc.code, detail=str(exc),
                                       time_ns=exc.time_ns)
        try:
            manifest['lower_layer_diagnosis'] = diagnose_lower_layer(a, report, exc)
        except Exception as diagnostic_error:
            manifest['lower_layer_diagnosis'] = dict(status='diagnostic_tool_failed', detail=str(diagnostic_error))
        if hasattr(exc, 'replay') and not a.no_failure_wave:
            replay = exc.replay
            rerun_wave(a.vivado_bin, replay['snapshot'], replay['vectors'], replay['seed'], build,
                       report/replay['label']/'failure_wave', replay['fault'])
    except Exception as exc:
        manifest["first_error"] = dict(code=type(exc).__name__, detail=str(exc),
                                       time_ns=None)
    finally:
        (report / "manifest.json").write_text(json.dumps(manifest, indent=2,
                                               ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"SYSTEM_REGRESSION_{manifest['verdict']} report={report}", flush=True)
    if manifest["first_error"]:
        print("FIRST_ERROR " + json.dumps(manifest["first_error"], ensure_ascii=False),
              file=sys.stderr, flush=True)
    return 0 if manifest["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
