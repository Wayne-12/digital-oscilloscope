# 硬件自检的状态快照、恢复与证据边界

类型：案例模板、踩坑清单。本目录是独立 Skill 单元，中文为正文，文件路径使用英文。

## 适用范围

会改变 DDS、触发、采集、AWG 波形表或校准状态的自动实物验收。

## 来源与提炼依据

AWG 验收曾留下测试波形表；上传迭代器被二次消费或回调修改原列表导致误报；仅逐字段检查能接受内部增益相互矛盾的校准指纹。

从本队真实开发问题提炼，原始源码/报告的字节副本列于下方。`provenance.json` 记录来源路径与 SHA256。历史报告只证明其标明版本、环境与范围；本目录新增说明不是当年的大模型对话记录。

## 使用方法

1. 测试前读回并冻结真实配置和有效波形表，记录初始选择；不可用 UI 草稿代替设备实际状态。
2. 开始事务前复制一次性迭代器和可变输入，整个上传/校验使用相同快照；不在回调中重新读取调用者列表。
3. 成功与失败路径都恢复原表、CRC、选择及配置，并读回确认。设备若没有清表命令，明确记录无法恢复“从无表到无表”的限制。
4. 校准指纹检查来源、设备、版本和代数一致性；闭环相对增益不等于外部参考绝对电压标定。只声明本轮实测和恢复覆盖的范围。

详细操作与迁移规则见 [SKILL.md](SKILL.md)，案例见 [references/case.md](references/case.md)。

## 已验证效果

修复记录包含迭代器/回调变更的复现测试、两种原 AWG 选择状态的实物恢复核对和相对增益一致性拒绝用例。本次未连接硬件或执行需 NumPy/Qt 的测试。

集合本次实际执行结果见上一级 `validation.json`。不要把文件齐全/说明校验通过理解成新的上板或综合通过。

## 失效条件与边界

恢复可能因断电、通信中断或硬件缺少逆操作而失败；必须保留恢复失败状态，不能一律 PASS。不要把相对自检或合成夹具结果称为绝对精度证明。

## 原始依据

- `PC/protocol/awg.py` → [source_01.py](references/source/source_01.py)
- `PC/protocol/hardware_calibration.py` → [source_02.py](references/source/source_02.py)
- `PC/tests/test_awg.py` → [source_03.py](references/source/source_03.py)
- `PC/tests/test_hardware_calibration.py` → [source_04.py](references/source/source_04.py)
- `FPGA/scripts/verify_awg_hardware.py` → [source_05.py](references/source/source_05.py)
- `docs/verification/repair_calibration_regression_20261027.md` → [source_06.md](references/source/source_06.md)

`references/source/` 是溯源快照；其中脚本可能仍依赖原工程路径、工具、模块或设备，不是可直接跨项目运行的入口。明确标为 `scripts/` 的可执行副本按本页说明运行。迁移时使用自己的参数、硬件合同和验证，保留修改前后证据。
