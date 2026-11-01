"""Summarize structural, resource and CDC evidence without claiming board signoff."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

CAPACITY = {"lut": 20800, "ff": 41600, "dsp": 90, "bram36_equivalent": 50}
BASE = ("scope_hw_top", "adc_capture", "dds_core", "scope_dds_rate_adapter", "bram_capture",
        "measurement_core", "multires_envelope", "spectrum_analyzer", "scope_uart_endpoint")
OPTIONAL = ("relative_calibrator", "calibration_apply", "health_compare", "capture_moments",
            "capture_result_stream", "capture_result_uart")

def rows(text: str) -> dict[str, float]:
    result = {}
    for line in text.splitlines():
        c = [s.strip() for s in line.split("|")]
        if len(c) >= 4 and re.fullmatch(r"\d+(?:\.\d+)?", c[2]):
            result[c[1].rstrip("*").strip()] = float(c[2])
    return result

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("report", type=Path)
    a = p.parse_args()
    root = a.report.resolve()
    m = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    resources, diagnostics, cdc, methodology = {}, [], {}, {}
    unexpected = []
    fpga = Path(__file__).resolve().parents[1]
    review_root = fpga / "scripts/provisional_diagnostic_reviews"
    for e in m["results"]:
        top = e["top"]
        art = root / top / "artifacts"
        if "resources" not in e:
            unexpected.append(f"{top}: missing structural/resource result")
            continue
        u = rows((art / "utilization.rpt").read_text(errors="replace"))
        r = e["resources"]
        review = None
        review_path = review_root / f"{top}.json"
        if review_path.is_file():
            review = json.loads(review_path.read_text(encoding="utf-8-sig"))
            for name, digest in review.get("evidence_sha256", {}).items():
                if name.endswith(".sv"):
                    matches = list((fpga / "rtl").rglob(name))
                    if len(matches) != 1 or hashlib.sha256(matches[0].read_bytes()).hexdigest() != digest:
                        unexpected.append(f"{top}: reviewed source changed: {name}")
                        review = None
                        break
        resources[top] = {"lut": u["Slice LUTs"], "ff": u["Slice Registers"],
                          "dsp": r["dsp"], "bram36_equivalent": r["bram36"] + r["bram18"] / 2,
                          "lut_as_memory": u.get("LUT as Memory", 0), **r}
        cdc[top] = [s.strip() for s in (art / "cdc.rpt").read_text(errors="replace").splitlines()
                    if re.match(r"\s*CDC-\d+\s+\w+\s+\d+", s)]
        for row in cdc[top]:
            rule, severity = row.split()[:2]
            known_gray = rule == "CDC-6" and top in {"scope_async_fifo"}
            known_bundle = rule == "CDC-15" and top in {"bram_capture"}
            if severity != "Info" and not (known_gray or known_bundle):
                unexpected.append(f"{top}: unreviewed CDC {row}")
        methodology[top] = [s.strip() for s in (art / "methodology.rpt").read_text(errors="replace").splitlines()
                            if re.match(r"\s*\|\s*(?:TIMING|LUTAR|SYNTH|CLOCK)-", s)]
        for s in e["diagnostics"]:
            match = re.search(r"\[([^]]+)\]", s)
            msg_id = match[1] if match else "UNKNOWN"
            # These describe OOC analysis boundaries, not RTL suppressions.
            classification = "review_required"
            if msg_id in {"Timing 38-242", "Timing 38-164", "DRC 23-814", "IP_Flow 19-5611", "Vivado 12-13650", "Netlist 29-101"}:
                classification = "ooc_scope_or_ip_generation"
            if msg_id == "Synth 8-3917" and top == "scope_core" and "port dac_data[" in s and "driven by constant" in s:
                core = (fpga / "rtl/top/scope_core.sv").read_text(encoding="utf-8")
                pkg = (fpga / "rtl/common/scope_pkg.sv").read_text(encoding="utf-8")
                if "assign dac_data = scope_pkg::DAC_MID_CODE;" in core and re.search(r"DAC_MID_CODE\s*=\s*14'd8192", pkg):
                    classification = "reviewed_safe_midpoint_8192"
            if review and msg_id.startswith("Synth 8-"):
                body = re.sub(r"^\w+(?: \w+)?: \[[^]]+\] ", "", s)
                body = re.sub(r"\s+\[[^]]+:\d+\]$", "", body)
                if body in review.get("expected_synth_message_counts", {}):
                    classification = "reviewed_exact_message_and_source_hash"
            if top == "spectrum_analyzer" and msg_id == "IP_Flow 19-982" and review and "Parameter 'super_sample_rates'" in s and "parameter 'scaling_options'" in s:
                classification = "reviewed_fft_configuration_readback"
            if msg_id == "Vivado 12-25344" and top in {"scope_dds_rate_adapter"} and r["ff"] == 0 and r["latches"] == 0:
                classification = "reviewed_pure_combinational_no_clock"
            diagnostics.append({"top": top, "id": msg_id, "classification": classification, "message": s})
            if classification == "review_required":
                unexpected.append(f"{top}: {s}")
        timing = (art / "timing_estimate.rpt").read_text(errors="replace")
        nc = re.search(r"checking no_clock \((\d+)\)", timing)
        resources[top]["no_clock"] = int(nc[1]) if nc else None
        if nc and int(nc[1]):
            unexpected.append(f"{top}: {nc[1]} endpoints have no clock")
        if e["verdict"] != "PASS":
            unexpected.append(f"{top}: synthesis/structural FAIL")
    with (root / "diagnostics.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=("top", "id", "classification", "message"))
        w.writeheader()
        w.writerows(diagnostics)
    def budget(names):
        if any(n not in resources for n in names):
            return None
        totals = {k: sum(resources[n][k] for n in names) for k in CAPACITY}
        return {"modules": list(names), "used": totals,
                "remaining": {k: CAPACITY[k] - totals[k] for k in CAPACITY},
                "percent": {k: round(100 * totals[k] / CAPACITY[k], 2) for k in CAPACITY},
                "fits_resource_counts": all(totals[k] <= CAPACITY[k] for k in CAPACITY)}
    baseline = budget(BASE)
    expanded = budget(BASE + OPTIONAL)
    summary = {"label": "基于暂定 XC7A35T，仅供估算", "capacity": CAPACITY,
               "resources": resources, "baseline_budget": baseline, "optional_budget": expanded,
               "cdc_rows": cdc, "methodology_rows": methodology,
               "unreviewed_diagnostics": unexpected, "board_timing_signoff": False,
               "budget_method": "Sum independent OOC implementations; not a connected placed/routed top"}
    (root / "audit.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 暂定器件综合检查", "", "**基于暂定 XC7A35T，仅供估算**", "",
             "Vivado 2025.2；器件 xc7a35tcsg324-1。报告为独立 OOC 综合与结构检查，不是最终板级时序结论。",
             "", "## 资源与结构", "",
             "| 模块 | LUT（含存储） | FF | DSP48 | BRAM36 等效 | 锁存器 | 黑盒 | 多驱动/组合环路 | 逻辑驱动时钟 |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for top, r in resources.items():
        lines.append(f"| {top} | {r['lut']:g} | {r['ff']:g} | {r['dsp']} | {r['bram36_equivalent']:g} | {r['latches']} | {r['blackboxes']} | {r['structural_drc']} | {r['fabric_clock_drivers']} |")
    lines += ["", "## 同时存在时的保守资源预算", "",
              "基础预算包括硬件时钟安全壳、ADC、DDS、BRAM 捕获、测量、包络、FFT 和 UART 端点。",
              "子模块已包含的触发、FIFO和安全控制不会重复累加。扩展预算再加独立创新功能。",
              "独立 OOC 资源相加用于估算同时存在的容量需求，不等价于功能互连或布局布线通过。", ""]
    for label, b in (("基础", baseline), ("含全部创新扩展", expanded)):
        if b is None:
            lines.append(f"{label}：本次选择的模块不全，不能形成完整预算。")
            continue
        lines += [f"### {label}", "", "| 资源 | 使用 | 可用 | 余量 | 使用率 |", "|---|---:|---:|---:|---:|"]
        for k, cap in CAPACITY.items():
            lines.append(f"| {k} | {b['used'][k]:g} | {cap} | {b['remaining'][k]:g} | {b['percent'][k]}% |")
        lines += ["", "容量计数可容纳。" if b["fits_resource_counts"] else "**容量计数超出：该组合不能宣称已满足暂定器件资源要求。**", ""]
    lines += ["## CDC 与时钟审阅", "",
              "硬件顶层目前仅为 Clocking Wizard、scope_core 和 ODDR/OBUFT 安全壳；系统仿真连接后端仍是 sim/models 文件。",
              "因此报告不宣称完整采集系统已经形成可上板硬件顶层。", "",
              "- Clocking Wizard 输入 100 MHz，输出 25 MHz，由 MMCM/BUFG 及自动生成时钟关系描述。",
              "- ODDR 只转发到外部引脚；未将 ODDR 输出或 LUT/FF 数据输出用作内部时钟。",
              "- scope_core 复位异步置位、在采样域下降沿两级同步释放；使能也经过两级同步。",
              "- BRAM 冻结帧通过请求/应答 toggle 两级同步，元数据保持到应答；双口 RAM 在冻结所有权下读出。",
              "- 配置/arm/module_enable 等 OOC 端口约定由所属时钟域驱动，不能把系统 testbench 的跨域连接直接搬到硬件。",
              "- BRAM/FIFO 各域复位输入必须先经各自时钟域同步释放，并在开始新会话前共同清空。",
              "- Gray 总线最终需按实际时钟约束 max_delay/bus_skew；bundled metadata 需约束稳定数据先于同步控制到达。当前未加入全域 false path 掩盖检查。", ""]
    for top, entries in cdc.items():
        if entries:
            lines += [f"### {top} 原生 CDC 汇总", "", "```text", *entries, "```", ""]
    lines += ["## 原生方法学报告的保留事项", "",
              "- TIMING-6/7：独立 OOC 时钟无公共源，跨域路径尚未以最终物理约束描述；不按同步数据路径验收。",
              "- LUTAR-1：安全壳的紧急复位组合逻辑用于异步置位，去释放经过本域两级同步，属于明确的安全设计。",
              "- SYNTH-6：RAM 输出寄存器可进一步改善时序；目前依赖冻结所有权和有效信号，不是意外锁存器。",
              "- SYNTH-10：定点算术中显式宽乘法，DSP/LUT 开销已计入；与隐式符号扩展警告不同。",
              "- TIMING-16：部分长算术路径在本次估算时钟下有较大 setup 违例；当前结果不能证明目标频率可达，后续需流水化/共享算术及实现时序优化。",
              "- TIMING-18：未提供最终 IO 时序，按任务要求保留。", ""]
    for top, entries in methodology.items():
        if entries:
            lines += [f"### {top} 方法学汇总", "", "| 规则 | 严重性 | 描述 | 数量 |", "|---|---|---|---:|", *entries, ""]
    lines += ["## 分析范围与未完成的板级工作", "",
              "FFT 和 capture_result_stream 的同类 Synth 8-7129 无负载端口提示达到 Vivado 默认100条显示上限。报告逐条审阅了全部已显示诊断，并核对对应端口/容器字段的源码和协议；不宣称被工具省略的重复提示已逐条统计。未降低任何诊断级别。",
              "OOC 的 HD.CLK_SRC 未指定和部分连接 DRC 范围提示均保留；缺少输入/输出延迟的 TIMING-18 也保留。",
              "report_cdc 只分析两端已定义时钟的内部路径，无输入延迟的外部端口会跳过，须结合上述 RTL 审阅。",
              "未绑定 J5 或其他 PACKAGE_PIN，未设置 IOSTANDARD，未伪造 ADC/DAC IO 延迟，未以 false path 隐藏接口。",
              "待实际器件、板级连线与模块时序确认后，还需完成硬件互连、CDC 物理约束、generated_clock 和 input/output_delay、实现与板级时序验收。",
              "", "## 诊断", "", f"需进一步审阅的日志诊断：{len(unexpected)}。完整条目在 diagnostics.csv。"]
    lines.extend("- " + s for s in unexpected)
    (root / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    code = int(bool(unexpected) or (baseline is not None and not baseline["fits_resource_counts"]))
    structural = m.get("structural_verdict", m["verdict"])
    m["structural_verdict"] = structural
    m["audit_exit_code"] = code
    m["verdict"] = "PASS" if code == 0 and structural == "PASS" else "FAIL"
    m["audit_source_sha256"] = {str(x.relative_to(fpga)): hashlib.sha256(x.read_bytes()).hexdigest()
                                for x in [Path(__file__).resolve(), *sorted(review_root.glob("*.json"))]}
    (root / "manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"tops": len(resources), "baseline": baseline, "optional": expanded,
                      "unreviewed": len(unexpected)}, ensure_ascii=False))
    return code

if __name__ == "__main__":
    raise SystemExit(main())
