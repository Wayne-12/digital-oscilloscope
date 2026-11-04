# 复位与使能 CDC 的根因排查和异步切换验证

类型：踩坑清单、案例模板。本目录是独立 Skill 单元，中文为正文，文件路径使用英文。

## 适用范围

异步开关、复位、时钟失锁信号进入同步采集/输出逻辑时的结构审查与修复验证。

## 来源与提炼依据

原始 SW0 组合旁路进入大量寄存器 D/CE，raw reset/失锁绕过同步结构进入输出单元；仅增加某处两级同步并未切断全部旁路。

从本队真实开发问题提炼，原始源码/报告的字节副本列于下方。`provenance.json` 记录来源路径与 SHA256。历史报告只证明其标明版本、环境与范围；本目录新增说明不是当年的大模型对话记录。

## 使用方法

1. 从真实 CDC 路径和 RTL 追踪每个原始异步信号到内部状态、CE、OE 及 ODDR 复位的扇出，区分内部同步控制与外部紧急关断。
2. 保留短 OFF 脉冲资格捕获和必要异步关断；内部状态机使用本地同步后的资格，采集使能在本地时钟沿寄存。
3. 测试多个相位的亚周期 OFF 脉冲、长 OFF、失锁并停钟、短复位和恢复预热；使用实际原语模型，检查顺序和高阻。
4. 重跑综合/布线 CDC、时序、DRC 和功能/板级回归；记录新增同步延迟，不能靠加 false path 或降严重度替代结构修复。

详细操作与迁移规则见 [SKILL.md](SKILL.md)，案例见 [references/case.md](references/case.md)。

## 已验证效果

原报告记录 Critical 855→0、23 个异步场景通过，并附 before/after 原始 CDC 与 verification.json；均是历史修复的验证，本次未重跑综合。

集合本次实际执行结果见上一级 `validation.json`。不要把文件齐全/说明校验通过理解成新的上板或综合通过。

## 失效条件与边界

数字仿真不能测量模拟亚稳态概率。异步关断和复位结构必须按目标器件原语及系统需求重新分析，Critical=0 不代表全部 CDC/产品安全风险已关闭。

## 原始依据

- `软核/reports/cdc_repair/修复报告.md` → [source_01.md](references/source/source_01.md)
- `软核/reports/cdc_repair/verification.json` → [source_02.json](references/source/source_02.json)
- `软核/reports/cdc_repair/after_synth_cdc.rpt` → [source_03.rpt](references/source/source_03.rpt)
- `软核/reports/cdc_repair/safety_simulation_pass.txt` → [source_04.txt](references/source/source_04.txt)
- `软核/tests/tb_cdc_safety.sv` → [source_05.sv](references/source/source_05.sv)
- `软核/rtl/scope_core.sv` → [source_06.sv](references/source/source_06.sv)

`references/source/` 是溯源快照；其中脚本可能仍依赖原工程路径、工具、模块或设备，不是可直接跨项目运行的入口。明确标为 `scripts/` 的可执行副本按本页说明运行。迁移时使用自己的参数、硬件合同和验证，保留修改前后证据。
