---
name: transactional-hardware-tests
description: Design hardware self-tests that snapshot configuration and waveform state, restore transactionally and distinguish relative calibration from absolute metrology.
---

# 硬件自检的状态快照、恢复与证据边界

适用：会改变 DDS、触发、采集、AWG 波形表或校准状态的自动实物验收。

先读 [references/case.md](references/case.md) 的历史故障与验证边界；需要原始证据时按 [README.md](README.md) 的映射读取 `references/source/`，不要一次加载全部文件。

1. 测试前读回并冻结真实配置和有效波形表，记录初始选择；不可用 UI 草稿代替设备实际状态。
2. 开始事务前复制一次性迭代器和可变输入，整个上传/校验使用相同快照；不在回调中重新读取调用者列表。
3. 成功与失败路径都恢复原表、CRC、选择及配置，并读回确认。设备若没有清表命令，明确记录无法恢复“从无表到无表”的限制。
4. 校准指纹检查来源、设备、版本和代数一致性；闭环相对增益不等于外部参考绝对电压标定。只声明本轮实测和恢复覆盖的范围。

交付时写明触发条件、输入/目标身份、实际执行步骤、证据位置、结果和未验证范围。对现场没有执行的检查给出待验证状态，不用历史 PASS 替代。

恢复可能因断电、通信中断或硬件缺少逆操作而失败；必须保留恢复失败状态，不能一律 PASS。不要把相对自检或合成夹具结果称为绝对精度证明。
