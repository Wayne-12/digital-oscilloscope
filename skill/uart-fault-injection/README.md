# 串口协议故障注入与验收证据分级

类型：校验脚本、案例模板。本目录是独立 Skill 单元，中文为正文，文件路径使用英文。

## 适用范围

有帧头、长度、序号、CRC 与超时机制的二进制串口协议；包含原项目协议的可运行离线测试。

## 来源与提炼依据

只跑正常帧无法发现粘包/分包、坏帧重同步、丢失响应与错误恢复问题；离线虚拟时间通过不能被升级为实物长稳通过。

从本队真实开发问题提炼，原始源码/报告的字节副本列于下方。`provenance.json` 记录来源路径与 SHA256。历史报告只证明其标明版本、环境与范围；本目录新增说明不是当年的大模型对话记录。

## 使用方法

1. 运行 python -m unittest discover -s tests -v，确认当前复制的编解码和验收逻辑对故障的拒绝行为。
2. 迁移时替换帧契约与设备适配层，保留已知 CRC 向量、逐字节喂入、帧头出现在载荷、坏包后好包恢复及截断超时。
3. 把短写、序号错误、回显不一致、恢复失败和不完整采集作为独立检查，记录错误增量及原始收发。
4. 真实验收另行固定镜像 SHA256、设备、波特率、条件和真实持续时间；用明确 OFFLINE/SHORT/PASS/INCOMPLETE 状态区分结果。

详细操作与迁移规则见 [SKILL.md](SKILL.md)，案例见 [references/case.md](references/case.md)。

## 已验证效果

复制的 test_scope_protocol 和 test_uart_acceptance 为标准库测试，本次已实跑通过；副本测试结果见 validation.json。

集合本次实际执行结果见上一级 `validation.json`。不要把文件齐全/说明校验通过理解成新的上板或综合通过。

## 失效条件与边界

本目录运行离线测试不连接串口。协议源码仍采用原工程报文定义；迁移需要适配。CRC 包错误计数不等于逐位 BER，虚拟时间不等于真实长稳。

## 原始依据

- `PC/protocol/scope_protocol.py` → [source_01.py](references/source/source_01.py)
- `PC/protocol/uart_acceptance.py` → [source_02.py](references/source/source_02.py)
- `PC/tests/test_scope_protocol.py` → [source_03.py](references/source/source_03.py)
- `PC/tests/test_uart_acceptance.py` → [source_04.py](references/source/source_04.py)
- `docs/verification/uart_soak_acceptance_20261026.md` → [source_05.md](references/source/source_05.md)

`references/source/` 是溯源快照；其中脚本可能仍依赖原工程路径、工具、模块或设备，不是可直接跨项目运行的入口。明确标为 `scripts/` 的可执行副本按本页说明运行。迁移时使用自己的参数、硬件合同和验证，保留修改前后证据。
