"""Regenerate deterministic software fixtures; does not import the golden models."""
import json
import math
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "examples"
DATA = BASE / "data"


def save(name, data):
    (DATA / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    save("small.json", [-3, -1, 1, 3])
    save("stats_actual.json", {"count": 4, "minimum": -3, "maximum": 3, "mean": 0, "rms": math.sqrt(5), "vpp": 6})
    save("envelope_input.json", [2, -1, 7, 7, 0, -4, 3])
    save("envelope_actual.json", [
        dict(first=0, last=1, count=2, minimum=-1, maximum=2, min_index=1, max_index=0),
        dict(first=2, last=3, count=2, minimum=7, maximum=7, min_index=2, max_index=2),
        dict(first=4, last=6, count=3, minimum=-4, maximum=3, min_index=5, max_index=6)])
    save("fir_input.json", [1, 0, 0, 0, -2, 1, 0, 3, -1, 0, 0])
    save("fft_input.json", [0.3 + math.sin(2*math.pi*5*i/64) + 0.2*math.cos(2*math.pi*13*i/64) for i in range(64)])
    save("wrong.json", [-3, -1, 1, 4])
    save("short.json", [-3, -1, 1])
    save("empty.json", [])
    suite = {"schema_version": 1, "name": "通用算法验证示例（软件合成数据）", "cases": [
        {"id": "statistics-known-values", "evidence": "synthetic-hand-calculated",
         "description": "已知四点统计；期望 RMS=sqrt(5)",
         "input": {"path": "data/small.json"}, "reference": {"model": "statistics"},
         "observed": {"path": "data/stats_actual.json"}, "tolerance": {"atol": 1e-12}},
        {"id": "envelope-uneven-and-ties", "evidence": "synthetic-hand-calculated",
         "description": "7点分3桶，非整除分区、同值首索引", "input": {"path": "data/envelope_input.json"},
         "reference": {"model": "envelope", "params": {"buckets": 3}},
         "observed": {"path": "data/envelope_actual.json"}},
        {"id": "fir-independent-process", "evidence": "synthetic-software-dut",
         "description": "移位寄存器 FIR 对照直接卷积参考；不依赖示波器", "input": {"path": "data/fir_input.json"},
         "reference": {"model": "fir", "params": {"taps": [0.25, 0.5, 0.25]}},
         "observed": {"mode": "command", "argv": ["{python}", "dut_program.py", "fir", "{input}", "{output}"], "timeout_seconds": 10},
         "tolerance": {"atol": 1e-12}},
        {"id": "fft-vs-direct-dft", "evidence": "synthetic-software-dut",
         "description": "独立基2FFT与直接DFT比对，64点全复谱", "input": {"path": "data/fft_input.json"},
         "reference": {"model": "dft"},
         "observed": {"mode": "command", "argv": ["{python}", "dut_program.py", "fft", "{input}", "{output}"], "timeout_seconds": 10},
         "tolerance": {"atol": 1e-10, "rtol": 1e-12}}], "evidence_files": ["dut_program.py"]}
    (BASE / "demo_suite.json").write_text(json.dumps(suite, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    cases = []
    for name, path in (("numeric-mismatch", "wrong.json"), ("length-mismatch", "short.json"), ("missing-output", "not_present.json")):
        cases.append({"id": name, "evidence": "deliberate-negative-test", "input": {"path": "data/small.json"},
                      "reference": {"model": "identity"}, "observed": {"path": "data/"+path}})
    (BASE / "negative_suite.json").write_text(json.dumps({"schema_version": 1, "name": "预期失败：错误检出示例", "cases": cases}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


if __name__ == "__main__":
    main()
