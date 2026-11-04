import csv
import hashlib
import importlib
import inspect
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from .models import MODELS


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    def invalid(value):
        raise ValueError(f"non-finite JSON token: {value}")
    def unique(items):
        d = {}
        for key, value in items:
            if key in d:
                raise ValueError(f"duplicate JSON key: {key}")
            d[key] = value
        return d
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), parse_constant=invalid, object_pairs_hook=unique)


def load_data(spec, base):
    if not isinstance(spec, dict) or "path" not in spec:
        raise ValueError("data source requires a path")
    path = (base / spec["path"]).resolve()
    fmt = spec.get("format", path.suffix.lstrip(".")).lower()
    if fmt == "json":
        data = read_json(path)
        for key in spec.get("keys", []):
            data = data[key]
    elif fmt == "csv":
        column = spec["column"]
        # Scope exports have full-line metadata beginning with '#'.
        with path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(line for line in f if line.strip() and not line.lstrip().startswith("#"))
            if not reader.fieldnames or column not in reader.fieldnames:
                raise ValueError(f"CSV column missing: {column}")
            data = []
            for row in reader:
                value = float(row[column])
                if not math.isfinite(value):
                    raise ValueError("non-finite CSV sample")
                data.append(value)
    else:
        raise ValueError(f"unsupported data format: {fmt}")
    return data, {"path": str(path), "sha256": sha256(path), "selector": spec}


def compare(expected, actual, atol=0.0, rtol=0.0, overrides=None, max_details=30):
    """Strict structure, finite numbers, abs(a-e) <= atol + rtol*abs(e).

    Overrides use JSON Pointer paths to exact leaves. No silently ignored outputs.
    """
    if isinstance(max_details, bool) or not isinstance(max_details, int) or max_details < 0:
        raise ValueError("max_details must be a nonnegative integer")
    if overrides is not None and not isinstance(overrides, dict):
        raise ValueError("overrides must be an object")
    overrides = overrides or {}
    for rule in [{"atol": atol, "rtol": rtol}, *overrides.values()]:
        if not isinstance(rule, dict) or set(rule) - {"atol", "rtol"}:
            raise ValueError("tolerance rules allow only atol and rtol")
        for value in rule.values():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError("tolerances must be finite nonnegative numbers")
    details, errors, total, numeric, max_abs, max_rel = [], 0, 0, 0, 0.0, 0.0
    norm, scaled_sum, used = 0.0, 0.0, set()

    def bad(path, reason, e, a):
        nonlocal errors
        errors += 1
        if len(details) < max_details:
            details.append({"path": path, "reason": reason, "expected": repr(e)[:180], "actual": repr(a)[:180]})

    def walk(e, a, path):
        nonlocal total, numeric, max_abs, max_rel, norm, scaled_sum
        rule = overrides.get(path, {})
        if path in overrides:
            if isinstance(e, (dict, list)):
                raise ValueError("tolerance overrides must target exact leaves")
            used.add(path)
        if isinstance(e, dict) and isinstance(a, dict):
            if set(e) != set(a):
                total += 1
                bad(path, "object keys differ", sorted(e), sorted(a))
            for key in sorted(set(e) & set(a)):
                walk(e[key], a[key], path + "/" + str(key).replace("~", "~0").replace("/", "~1"))
        elif isinstance(e, list) and isinstance(a, list):
            if len(e) != len(a):
                total += 1
                bad(path, "array lengths differ", len(e), len(a))
            for i, (ev, av) in enumerate(zip(e, a)):
                walk(ev, av, path + "/" + str(i))
        else:
            total += 1
            if type(e) is bool or type(a) is bool:
                if type(e) is not type(a) or e != a:
                    bad(path, "boolean/type mismatch", e, a)
            elif isinstance(e, (int, float)) and isinstance(a, (int, float)):
                if not math.isfinite(e) or not math.isfinite(a):
                    bad(path, "non-finite numeric value", e, a)
                    return
                numeric += 1
                delta = abs(a-e)
                if not math.isfinite(delta):
                    bad(path, "numeric error overflow", e, a)
                    return
                max_abs = max(max_abs, delta)
                if e != 0:
                    ratio = delta / abs(e)
                    if math.isfinite(ratio):
                        max_rel = max(max_rel, ratio)
                if delta:
                    if delta > norm:
                        scaled_sum = 1 + scaled_sum * (norm / delta)**2
                        norm = delta
                    else:
                        scaled_sum += (delta / norm)**2
                if delta > rule.get("atol", atol) + rule.get("rtol", rtol)*abs(e):
                    bad(path, "outside tolerance", e, a)
            elif type(e) is not type(a) or e != a:
                bad(path, "value/type mismatch", e, a)
    walk(expected, actual, "")
    if set(overrides) - used:
        raise ValueError(f"unused tolerance paths: {sorted(set(overrides) - used)}")
    # Empty collections cannot provide validation evidence.
    if not total:
        raise ValueError("comparison contains no values")
    return dict(status="FAIL" if errors else "PASS", compared=total, numeric_compared=numeric,
                mismatches=errors, max_abs_error=max_abs,
                max_relative_error_nonzero_reference=max_rel,
                rmse=norm * math.sqrt(scaled_sum / numeric) if numeric else None,
                details=details, details_truncated=errors > len(details))


def resolve_model(name):
    if name in MODELS:
        fn = MODELS[name]
    else:
        module, sep, attr = name.partition(":")
        if not sep:
            raise ValueError(f"unknown reference model: {name}")
        fn = getattr(importlib.import_module(module), attr)
    if not callable(fn):
        raise ValueError("reference model must be callable")
    source = inspect.getsourcefile(fn)
    return fn, {"callable": name, "path": source, "sha256": sha256(source) if source else None}


def run_case(case, base):
    result = {"id": case.get("id", "<missing>"), "evidence": case.get("evidence", "unspecified"),
              "description": case.get("description", ""), "status": "ERROR"}
    try:
        if not isinstance(case.get("id"), str) or not case["id"]:
            raise ValueError("case id must be a nonempty string")
        data, origin = load_data(case["input"], base)
        result["input"] = origin
        model = case["reference"]
        fn, model_origin = resolve_model(model["model"])
        result["reference"] = model_origin
        start = time.perf_counter()
        expected = fn(data, **model.get("params", {}))
        result["reference_seconds"] = time.perf_counter() - start
        # Reject invalid custom results even if all leaves would happen to match.
        json.dumps(expected, allow_nan=False)
        observed = case["observed"]
        mode = observed.get("mode", "file")
        if mode == "file":
            actual, result["observed"] = load_data(observed, base)
            result["observed_wall_seconds"] = None
        elif mode == "command":
            args = observed["argv"]
            timeout = observed.get("timeout_seconds", 30)
            if not isinstance(args, list) or not args or any(not isinstance(x, str) for x in args):
                raise ValueError("argv must be a nonempty string array")
            if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
                raise ValueError("timeout must be finite and positive")
            with tempfile.TemporaryDirectory(prefix="goldencheck_") as td:
                inp, out = Path(td)/"input.json", Path(td)/"output.json"
                inp.write_text(json.dumps(data, allow_nan=False), encoding="utf-8")
                substitutions = {"{python}": sys.executable, "{input}": str(inp), "{output}": str(out)}
                argv = [substitutions.get(arg, arg) for arg in args]
                start = time.perf_counter()
                # Files prevent an excessively chatty process from filling RAM.
                with (Path(td)/"stdout.txt").open("wb") as stdout, (Path(td)/"stderr.txt").open("wb") as stderr:
                    done = subprocess.run(argv, cwd=base, shell=False, stdout=stdout, stderr=stderr, timeout=timeout)
                result["observed_wall_seconds"] = time.perf_counter() - start
                result["command"] = {"argv": args, "returncode": done.returncode, "timeout_seconds": timeout}
                if done.returncode:
                    with (Path(td)/"stderr.txt").open("rb") as f:
                        excerpt = f.read(2000).decode("utf-8", errors="replace")
                    raise ValueError(f"observed command exited {done.returncode}: {excerpt}")
                actual = read_json(out)
                # Preserve output in report as ephemeral source hash; detail artifacts are saved by runner.
                result["observed"] = {"mode": "command", "sha256": sha256(out)}
        else:
            raise ValueError(f"unknown observed mode: {mode}")
        result.update(compare(expected, actual, **case.get("tolerance", {})))
        result["_expected"], result["_actual"] = expected, actual
    except Exception as exc:
        result["status"] = "ERROR"
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result
