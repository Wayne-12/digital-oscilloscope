---
name: layered-rtl-regression
description: Organize RTL regression into gated unit, integration and system layers, diagnosing higher-layer failures without reusing stale test evidence.
---

# 单元到系统的分层回归与结果复用门禁

适用：具有多个可独立测试模块的 RTL 工程；尤其适合固定种子、长运行和单元结果复用。

先读 [references/case.md](references/case.md) 的历史故障与验证边界；需要原始证据时按 [README.md](README.md) 的映射读取 `references/source/`，不要一次加载全部文件。

1. 按接口边界建立独立 DUT 顶层，UART PHY 与包解析、触发与测量分别验证。
2. 执行顺序固定为 unit → integration → system；任一前置层失败即停止进入后层。
3. 复用报告时核对 verdict、完整必测项、随机种子和参与源文件 SHA256。源码变化、缺项或失败报告均拒绝。
4. 高层失败时先复跑相关最小单元；单元全通过只说明需继续检查连接、配置或测试框架，不能自动归罪 RTL。

交付时写明触发条件、输入/目标身份、实际执行步骤、证据位置、结果和未验证范围。对现场没有执行的检查给出待验证状态，不用历史 PASS 替代。

源码哈希只能证明清单覆盖的输入；须包含约束、IP 参数、生成表和工具版本。参考调度器绑定原工程的测试集合，迁移时必须重建依赖映射，不能直接照搬测试名。
