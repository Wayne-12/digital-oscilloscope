# 第一项三模式固化与断电启动验证（2026-10-27）

结论：**已完成固化、独立读回和真正断电自动启动验证**，状态 `PASS_FLASH_PROGRAM_COLD_BOOT_VERIFIED`。用户要求完成第一项固化后停止，后续整帧饱和统计、ADC 输入 IOB、任意波形下载和汇总 CSV 未开始本次实现。

固化版本 `0xA1261026`，能力值 15，25 MSPS / 16384 点 / UART 921600 bit/s。该镜像固化前已通过 26 个完整帧的 AUTO、NORMAL、SINGLE 专项实物测试、原始码/统计核对、STOP/重启与配置恢复，所有错误新增为零。固化镜像与该已验收 bitstream 相同，SHA256：`249775c0f9665a7f37cf40702ed299cfcd2eb7bba5793fa58f1158315521ad9d`。

## 编程与备份

用户明确选择现在固化，并确认 SW0 OFF、ADC/DAC 外部 5 V 关闭、EGO1 与 USB/JTAG 保持供电。限定原 JTAG 目标 `1234-tulA`、FPGA IDCODE `0362d093`。实际 JEDEC 为 `20 ba 17`，型号 `n25q64-3.3v-spi-x1_x2_x4`。

- 写前完整备份 8,388,608 字节，镜像前缀与原 `0xA0261026` 发布 BIN 逐字节相同。
- 待写 MCS/BIN 已按 Intel HEX 记录校验和、连续地址和 2,192,012 个数据字节核对一致。
- Flash 擦除、空白检查、编程与工具校验通过。
- 独立读回 2,192,012 字节，与已准备 BIN 逐字节一致。BIN/读回 SHA256：`d083179ac36ed805cbe696332df4cf33ab5d79161bc514b62d6e8248fe54adcc`。

备份与读回：[写前完整备份](../../FPGA/reports/flash/capture_modes_20261027_first/flash_before.bin)、[独立读回](../../FPGA/reports/flash/capture_modes_20261027_first/flash_after.bin)。备份 SHA256 和完整身份记录见 [Flash 清单](../../FPGA/output/capture_modes_921600_20261027/flash/flash_manifest.json)。[编程日志](../../FPGA/output/capture_modes_921600_20261027/evidence/flash_program.log) 保留实际操作过程。

## 真正断电自动启动

用户确认断开 EGO1 全部供电（包括 USB），板灯熄灭后重新接回并上电；保持原 QSPI 启动设置、SW0 OFF 和模块外部 5 V 关闭。之后只进行读取，没有重新下载、重新配置 FPGA 或写 Flash。

只读 JTAG 结果：Master SPI 模式 `001`，DONE=1，EOS=1，CRC_ERROR=0。只读串口结果：COM12 / 921600、版本 `0xA1261026`、能力值 15、启动 flags=4、25 MSPS、16384 点、预触发 8192、默认 DDS 100 kHz / 819 码、所选 SINGLE 模式和 AUTO 等待 2500000 周期，主机解析与 FPGA 错误均为零。

证据：[启动寄存器日志](../../FPGA/output/capture_modes_921600_20261027/evidence/cold_boot_registers.log)、[启动串口记录](../../FPGA/reports/flash/capture_modes_20261027_first/cold_boot_serial.json)、[FPGA 启动属性](../../FPGA/reports/flash/capture_modes_20261027_first/cold_boot_fpga.rpt)。

本次断电后保持模块电源关闭，未重复 ADC 采集；功能实物结论来自固化前同一 bitstream 的 [26 帧验收](../../FPGA/reports/capture_modes_hardware/20261027_0008/report.json)。当前安全状态为模块外部 5 V 关闭、SW0 OFF；下次使用按既有顺序先恢复模块电源，稳定后再 SW0 OFF→ON。

原固件 `0xA0261026` 的正式 UART/两小时长稳结果继续按其设备、镜像与条件限定。本次新固件未重新执行正式 UART 长稳，遵循用户排除该项的要求。
