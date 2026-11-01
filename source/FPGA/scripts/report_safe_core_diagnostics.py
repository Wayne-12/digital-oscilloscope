"""Account for every observed safe-core Synth warning; keep midpoint unchanged."""
import csv
import re
import sys
from pathlib import Path

top = Path(sys.argv[1])
out = top / "vivado_agentic_ai_reports/rtl-elaboration-analysis"
out.mkdir(parents=True, exist_ok=True)
messages = []
for line in (top / "console.log").read_text(encoding="utf-8", errors="replace").splitlines():
    m = re.match(r"(WARNING|ERROR|CRITICAL WARNING): \[Synth 8-(\d+)\] (.*)", line)
    if m:
        if m[2] != "3917" or "port dac_data[" not in m[3] or "driven by constant" not in m[3]:
            raise RuntimeError(f"Unexpected diagnostic: {line}")
        messages.append([len(messages) + 1, m[1], m[2], m[3], "D:/示波器/FPGA/rtl/top/scope_core.sv", 35, "VLOG"])
source = Path("D:/示波器/FPGA/rtl/top/scope_core.sv").read_text(encoding="utf-8")
assert "assign dac_data = scope_pkg::DAC_MID_CODE;" in source
pkg = Path("D:/示波器/FPGA/rtl/common/scope_pkg.sv").read_text(encoding="utf-8")
assert re.search(r"DAC_MID_CODE\s*=\s*(?:dac_code_t'\()?14'd8192", pkg), "verify midpoint definition"
with (out / "messages.csv").open("w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["S.No", "Severity", "Msg_ID", "Message", "File", "Line", "Language"])
    w.writerows(messages)
(out / "resolution_checklist.md").write_text("# Resolution Checklist\n\n## HAS RESOLUTION FILE\n\n| ID | Severity | Resolution File | Loaded? |\n|---|---|---|---|\n|3917|Warning|resolution/8-3917.md|[x]|\n\n## NO RESOLUTION FILE\n\nNone.\n", encoding="utf-8")
lines = ["# RTL Elaboration Analysis Report", "", "基于暂定 XC7A35T，仅供估算。", "",
         f"Error=0; Critical Warning=0; Warning={len(messages)}; actionable=0; intentional constant output={len(messages)}.", "",
         "安装技能解析器在暂存源码 C: 与报告 D: 跨盘 relpath 时失败，改用等价逐行解析。所有非 INFO Synth 诊断已计入 CSV。", "",
         "### [Synth 8-3917] 安全中码常量输出（相同根因的重复诊断）", "",
         "File: [scope_core.sv](D:/示波器/FPGA/rtl/top/scope_core.sv:35)。", "",
         "源码显式将 dac_data 设为 DAC_MID_CODE=8192，位13为1、位12:0为0。这是安全壳的规定行为，不是遗漏连接。",
         "已读取 resolution/8-3917.md，按其策略3保留接口和已定义常量。无需修改 RTL。", "",
         "Problematic Code (诊断所指代码，设计意图正确):", "", "```diff",
         "  assign dac_data = scope_pkg::DAC_MID_CODE;", "```", "",
         "Recommended Fix: 保持代码，记录预期常量。", "", "```diff",
         "  assign dac_data = scope_pkg::DAC_MID_CODE;", "```", "",
         "Corrected Code (paste-ready；与原始源码相同):", "", "```systemverilog",
         "assign dac_data = scope_pkg::DAC_MID_CODE;", "```", "",
         "> 可将上述代码复制到 scope_core.sv 第35行；本次无需替换。", "",
         "Occurrences:", "", "| S.No | Message |", "|---:|---|"]
lines.extend(f"|{r[0]}|{r[3]}|" for r in messages)
lines += ["", f"核对：CSV 非 INFO 行数={len(messages)}，本节 occurrence 数={len(messages)}，无诊断遗漏。", ""]
(out / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
print(f"SAFE_CORE_DIAGNOSTICS_REVIEWED count={len(messages)}")
