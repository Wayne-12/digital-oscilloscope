---
name: uart-fault-injection
description: Test binary UART framing and acceptance logic with fragmented packets, CRC corruption, timeouts, recovery and explicit offline-versus-hardware evidence labels.
---

# 串口协议故障注入与验收证据分级

适用：有帧头、长度、序号、CRC 与超时机制的二进制串口协议；包含原项目协议的可运行离线测试。

先读 [references/case.md](references/case.md) 的历史故障与验证边界；需要原始证据时按 [README.md](README.md) 的映射读取 `references/source/`，不要一次加载全部文件。

1. 运行 python -m unittest discover -s tests -v，确认当前复制的编解码和验收逻辑对故障的拒绝行为。
2. 迁移时替换帧契约与设备适配层，保留已知 CRC 向量、逐字节喂入、帧头出现在载荷、坏包后好包恢复及截断超时。
3. 把短写、序号错误、回显不一致、恢复失败和不完整采集作为独立检查，记录错误增量及原始收发。
4. 真实验收另行固定镜像 SHA256、设备、波特率、条件和真实持续时间；用明确 OFFLINE/SHORT/PASS/INCOMPLETE 状态区分结果。

交付时写明触发条件、输入/目标身份、实际执行步骤、证据位置、结果和未验证范围。对现场没有执行的检查给出待验证状态，不用历史 PASS 替代。

本目录运行离线测试不连接串口。协议源码仍采用原工程报文定义；迁移需要适配。CRC 包错误计数不等于逐位 BER，虚拟时间不等于真实长稳。
