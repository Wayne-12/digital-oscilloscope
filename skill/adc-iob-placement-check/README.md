# ADC 输入 IOB 的实际布局与时序验收

类型：校验模板、踩坑清单。本目录是独立 Skill 单元，中文为正文，文件路径使用英文。

## 适用范围

并行 ADC 输入寄存器计划放入 AMD 7 Series IOB/ILOGIC 的工程。

## 来源与提炼依据

设计文档描述为 IOB 采样，但原输入寄存器实际位于 SLICE；只写 IOB 属性或看到全局时序通过不能证明目标位置已实现。

从本队真实开发问题提炼，原始源码/报告的字节副本列于下方。`provenance.json` 记录来源路径与 SHA256。历史报告只证明其标明版本、环境与范围；本目录新增说明不是当年的大模型对话记录。

## 使用方法

1. 确认首级采样寄存器、复位、使能和数据延迟契约，覆盖数据位和 OTR 等伴随标记。
2. 综合后严格核对目标寄存器数量；布线后导出 cell/ref_name/LOC/BEL/site_type/IOB，逐项检查输入寄存器站点。
3. 单独输出 ADC 输入 setup/hold 报告，并保留全局时序和约束；不要通过增加未说明流水级改变时间戳契约。
4. 用独立 ADC 随机/边界测试和实际数据位翻转验证功能；数字 OTR 注入与真实模拟过载分开标记。

详细操作与迁移规则见 [SKILL.md](SKILL.md)，案例见 [references/case.md](references/case.md)。

## 已验证效果

原例 12 位数据加 OTR 共 13 个寄存器均在 ILOGICE2.IFF；历史报告记录时序通过与 19 帧实物核验；本包附原始位置表和输入时序报告。

集合本次实际执行结果见上一级 `validation.json`。不要把文件齐全/说明校验通过理解成新的上板或综合通过。

## 失效条件与边界

13 个寄存器、ILOGICE2 和原 ADC 延迟只对应原器件与接口；迁移到其他架构需改站点规则。放入 IOB 不是提高模拟精度或已完成过载测试的证明。

## 原始依据

- `FPGA/scripts/build_scope_board.tcl` → [source_01.tcl](references/source/source_01.tcl)
- `FPGA/scripts/build_adc_iob.py` → [source_02.py](references/source/source_02.py)
- `docs/verification/adc_iob_implementation_20261027.md` → [source_03.md](references/source/source_03.md)
- `FPGA/output/adc_iob_921600_20261027/implementation/adc_iob_placement.tsv` → [source_04.tsv](references/source/source_04.tsv)
- `FPGA/output/adc_iob_921600_20261027/implementation/adc_input_setup.rpt` → [source_05.rpt](references/source/source_05.rpt)
- `FPGA/output/adc_iob_921600_20261027/implementation/adc_input_hold.rpt` → [source_06.rpt](references/source/source_06.rpt)

`references/source/` 是溯源快照；其中脚本可能仍依赖原工程路径、工具、模块或设备，不是可直接跨项目运行的入口。明确标为 `scripts/` 的可执行副本按本页说明运行。迁移时使用自己的参数、硬件合同和验证，保留修改前后证据。
