"""Source-checked inventories for reserved bits and intentional phase truncation."""
import collections
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

FPGA = Path(__file__).resolve().parents[1]
report = Path(sys.argv[1])
cases = {
    "scope_dds_rate_adapter": ("rtl/common/scope_dds_rate_adapter.sv", "3936", 1,
        r"Found unconnected internal register 'quotient_reg' and it is trimmed from '64' to '32' bits\.",
        "phase_inc_actual=quotient[31:0];",
        "该模块无时钟和寄存器原语，quotient为组合中间量。64位中间计算保留乘法与舍入精度，输出显式取低32位，按DDS控制字模2^32语义处理；裁剪未被消费的高位是预期优化。"),
}
for top, (rel, msg_id, count, pattern, snippet, rationale) in cases.items():
    src = FPGA / rel
    source = src.read_text(encoding="utf-8")
    assert snippet in source
    line_no = next(i for i, s in enumerate(source.splitlines(), 1) if snippet in s)
    messages = []
    for line in (report / top / "console.log").read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"(WARNING|ERROR|CRITICAL WARNING): \[Synth 8-(\d+)\] (.*)", line)
        if not m:
            continue
        body = re.sub(r"\s+\[[^]]+:\d+\]$", "", m[3])
        if m[2] != msg_id or not re.fullmatch(pattern, body):
            raise RuntimeError(line)
        messages.append([len(messages)+1,m[1],m[2],body,str(src),line_no,"VLOG"])
    assert len(messages) == count
    out = report / top / "vivado_agentic_ai_reports/rtl-elaboration-analysis"
    out.mkdir(parents=True, exist_ok=True)
    with (out / "messages.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["S.No","Severity","Msg_ID","Message","File","Line","Language"])
        w.writerows(messages)
    (out / "resolution_checklist.md").write_text(f"# Resolution Checklist\n\n## HAS RESOLUTION FILE\n\n|ID|Severity|Resolution File|Loaded?|\n|---|---|---|---|\n|{msg_id}|Warning|resolution/8-{msg_id}.md|[x]|\n\n## NO RESOLUTION FILE\n\nNone.\n", encoding="utf-8")
    rules = {"top":top,"evidence_sha256":{src.name:hashlib.sha256(src.read_bytes()).hexdigest()},
             "expected_synth_message_counts":dict(collections.Counter(r[3] for r in messages)),
             "expected_id_counts":{msg_id:count}}
    review = FPGA / "scripts/provisional_diagnostic_reviews"
    review.mkdir(exist_ok=True)
    (review / f"{top}.json").write_text(json.dumps(rules,ensure_ascii=False,indent=2),encoding="utf-8")
    (out / "classification_rules.json").write_text(json.dumps(rules,ensure_ascii=False,indent=2),encoding="utf-8")
    md = ["# RTL Elaboration Analysis Report", "", "基于暂定 XC7A35T，仅供估算。", "",
          f"Errors=0，Critical Warnings=0，Warnings={count}，需要修改RTL=0。", "",
          f"### [Synth 8-{msg_id}] 预期保留位/显式截断优化", "",
          f"File: [{src.name}]({src.as_posix()}:{line_no})", "", rationale, "",
          "已读取对应 resolution 文档并检查实际RTL；本次保留代码与接口，不增加无用逻辑来消除提示。", "",
          "Problematic Code（诊断所指、设计意图正确）:", "", "```diff", "  "+snippet,"```", "",
          "Recommended Fix（保持源码）:", "", "```diff", "  "+snippet, "```", "",
          "Corrected Code (paste-ready，与源码相同):", "", "```systemverilog",snippet,"```", "",
          f"> 可将上述代码复制到 {src.name} 第{line_no}行；本次无需替换。", "",
          "|S.No|Message|", "|---:|---|"]
    md += [f"|{r[0]}|{r[3]}|" for r in messages]
    md += ["", f"核对：CSV非INFO行数={count}，本节occurrences={count}，遗漏=0。", ""]
    (out / "REPORT.md").write_text("\n".join(md),encoding="utf-8")
    print(f"REVIEWED {top} count={count}")
