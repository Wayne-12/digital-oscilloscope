---
name: adc-iob-placement-check
description: Verify that intended ADC input registers actually occupy ILOGIC after routing, with explicit register counts and input setup and hold reports.
---

# ADC 输入 IOB 的实际布局与时序验收

适用：并行 ADC 输入寄存器计划放入 AMD 7 Series IOB/ILOGIC 的工程。

先读 [references/case.md](references/case.md) 的历史故障与验证边界；需要原始证据时按 [README.md](README.md) 的映射读取 `references/source/`，不要一次加载全部文件。

1. 确认首级采样寄存器、复位、使能和数据延迟契约，覆盖数据位和 OTR 等伴随标记。
2. 综合后严格核对目标寄存器数量；布线后导出 cell/ref_name/LOC/BEL/site_type/IOB，逐项检查输入寄存器站点。
3. 单独输出 ADC 输入 setup/hold 报告，并保留全局时序和约束；不要通过增加未说明流水级改变时间戳契约。
4. 用独立 ADC 随机/边界测试和实际数据位翻转验证功能；数字 OTR 注入与真实模拟过载分开标记。

交付时写明触发条件、输入/目标身份、实际执行步骤、证据位置、结果和未验证范围。对现场没有执行的检查给出待验证状态，不用历史 PASS 替代。

13 个寄存器、ILOGICE2 和原 ADC 延迟只对应原器件与接口；迁移到其他架构需改站点规则。放入 IOB 不是提高模拟精度或已完成过载测试的证明。
