---
name: cooperative-serial-service
description: Diagnose display-induced serial starvation and packet-boundary ownership handoff in polling embedded systems using phase-correlated failures and bidirectional service tests.
---

# 显示刷新期间的串口服务与控制权交接

适用：单主循环同时负责绘图、字节桥接和本地/上位机控制的嵌入式系统。

先读 [references/case.md](references/case.md) 的历史故障与验证边界；需要原始证据时按 [README.md](README.md) 的映射读取 `references/source/`，不要一次加载全部文件。

1. 先做与模拟幅度无关的纯回显，把失败相位与绘图周期、parser timeout 增量对齐，避免靠增幅或放宽超时误判根因。
2. 在清屏、查字和绘图等长循环设置有界双向服务点，空闲立即退出；明确本地命令等待期间不能混入电脑请求。
3. 交接先结束当前请求/回复，再 STOP、按帧排空并等待安静窗口；清理按键旧事件与草稿。恢复电脑控制时先读板端实际参数。
4. 覆盖所有页面、半包/长包/CRC 异常、双向切换以及 RUN/STOP/SINGLE 恢复策略，再做相同条件修复前后回显比较。

交付时写明触发条件、输入/目标身份、实际执行步骤、证据位置、结果和未验证范围。对现场没有执行的检查给出待验证状态，不用历史 PASS 替代。

32 轮服务配额、4 ms 和 100 ms 是原案例参数，必须按新系统最坏服务间隔和吞吐重新计算。本次未重跑 C 编译或板端通信。
