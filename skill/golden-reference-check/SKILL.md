---
name: golden-reference-check
description: Compare independent reference models against algorithm outputs and archive strict numeric checks with reproducible reports.
---

# 黄金参考比对与可追溯报告

适用：软件算法、RTL 仿真输出和已导出的硬件数值结果；支持统计、包络、FIR、DFT 及自定义参考。

先读 [references/case.md](references/case.md) 的历史故障与验证边界；需要原始证据时按 [README.md](README.md) 的映射读取 `references/source/`，不要一次加载全部文件。

1. 先写清输入输出的单位、位宽、顺序、缩放与舍入，选择独立于被测实现的参考模型。
2. 使用 examples/demo_suite.json 的文件或外部命令接口接入自己的输出；不要把黄金输出当成实际输出。
3. 运行 python scripts/verify_all.py；总结果查看 reports 下最新 verification_summary.json，故意失败套件的 ERROR 是预期检出。
4. 运行 python scripts/check_portability.py 检查脱离原工程的隔离运行。

交付时写明触发条件、输入/目标身份、实际执行步骤、证据位置、结果和未验证范围。对现场没有执行的检查给出待验证状态，不用历史 PASS 替代。

浮点 DFT 不等同于定点 FFT 签核。CSV 标称电压一致不证明 ADC 绝对精度。主机墙钟时间不等于 FPGA 延迟。本工具未实现 PYNQ 驱动或硬件资源自动采集。
