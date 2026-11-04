---
name: qspi-release-verification
description: Plan and audit FPGA QSPI deployment using device identification, full backup, independent binary readback and separate true cold-boot evidence.
---

# QSPI 固化的备份、独立读回与冷启动验收

适用：Vivado Hardware Manager 支持的 FPGA 配置 Flash 固化与验收；原案例为 XC7A35T 和 N25Q64。

先读 [references/case.md](references/case.md) 的历史故障与验证边界；需要原始证据时按 [README.md](README.md) 的映射读取 `references/source/`，不要一次加载全部文件。

1. 先核对实际 FPGA IDCODE、Flash 型号/容量、启动模式和镜像哈希；根据目标板确认外部模块供电与使能状态。
2. 在新的报告目录保存完整 Flash 备份，字节数不符则停止擦除。原例备份为 8 MiB，该数值不能迁移到其他器件。
3. 在已明确授权的目标板上固化，保留工具校验，再独立读回有效地址范围与期望 BIN 逐字节比较。相同镜像可跳过重复擦写。
4. 分别记录从 Flash 重加载和用户真实断电再上电；冷启动后只读检查 MODE/DONE/EOS/CRC 与应用身份，不先 JTAG 下载。

交付时写明触发条件、输入/目标身份、实际执行步骤、证据位置、结果和未验证范围。对现场没有执行的检查给出待验证状态，不用历史 PASS 替代。

提供的是适配流程与参考源码，不提供跨板即用烧录器。目标、IDCODE、Flash、时钟和模式都需实际确认。不得从本技能的存在推断允许擦写设备。
