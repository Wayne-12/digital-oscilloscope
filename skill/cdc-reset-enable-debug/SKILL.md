---
name: cdc-reset-enable-debug
description: Investigate asynchronous reset and enable bypasses using actual CDC paths and phase-swept fault tests while preserving external shutdown behavior.
---

# 复位与使能 CDC 的根因排查和异步切换验证

适用：异步开关、复位、时钟失锁信号进入同步采集/输出逻辑时的结构审查与修复验证。

先读 [references/case.md](references/case.md) 的历史故障与验证边界；需要原始证据时按 [README.md](README.md) 的映射读取 `references/source/`，不要一次加载全部文件。

1. 从真实 CDC 路径和 RTL 追踪每个原始异步信号到内部状态、CE、OE 及 ODDR 复位的扇出，区分内部同步控制与外部紧急关断。
2. 保留短 OFF 脉冲资格捕获和必要异步关断；内部状态机使用本地同步后的资格，采集使能在本地时钟沿寄存。
3. 测试多个相位的亚周期 OFF 脉冲、长 OFF、失锁并停钟、短复位和恢复预热；使用实际原语模型，检查顺序和高阻。
4. 重跑综合/布线 CDC、时序、DRC 和功能/板级回归；记录新增同步延迟，不能靠加 false path 或降严重度替代结构修复。

交付时写明触发条件、输入/目标身份、实际执行步骤、证据位置、结果和未验证范围。对现场没有执行的检查给出待验证状态，不用历史 PASS 替代。

数字仿真不能测量模拟亚稳态概率。异步关断和复位结构必须按目标器件原语及系统需求重新分析，Critical=0 不代表全部 CDC/产品安全风险已关闭。
