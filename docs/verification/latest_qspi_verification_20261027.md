# 最新固件QSPI固化核验（2026-10-27）

结论：**PASS，最新已验收固件0xA4261027已保存在QSPI Flash中，从QSPI重新启动和串口复核通过。**

本次用户明确授权固化，并确认SW0 OFF、ADC/DAC外部5V关闭、开发板保持供电和下载连接。核验目标为通过半小时短稳及当前功能验收的同一固件，能力63、25 MSPS、16384点、921600 bit/s。

- 发布bitstream SHA256：`ddb4aca5667e40ea71628f1fa2ba850ad297a4c20d0bd7dfceb8c34d2acda7d9`。Flash BIT与已测试BIT逐字节一致；MCS记录校验及完整BIN一致性检查通过；产品RTL和约束与该发布清单一致。
- 识别到N25Q64，实际返回JEDEC厂商20、类型BA、容量17；完整读回并备份QSPI 8 MiB。
- Flash启动区域与目标BIN逐字节一致，因此本次**未重复擦除或写入**。随后再次独立读取2,192,012字节验证一致，BIN/读回SHA256均为 `51b2ca2980a5580a364021a5599db2a997e39812ddf7e5659f2ab585f11b3e2d`。
- 使用 `boot_hw_device` 按模式引脚从QSPI重新加载，而非通过JTAG下载用户bitstream。Master SPI模式001，DONE=1、EOS=1、CRC_ERROR=0。
- 串口只读复核：0xA4261027、能力63、921600、25 MSPS、16384点，默认正弦100 kHz、数字幅度819；FPGA错误计数和解析错误为0。未启动采集、未修改输出配置。
- 本轮执行了软件触发的QSPI启动，未声称进行了人工断电测试。同一镜像此前的真实断电验证仍保存在原固化报告。

后续修复的是PC上位机、校准文件和测试台，没有产生新的FPGA bitstream。它们保存在电脑项目目录，不能通过写FPGA Flash更新。用户任意波形表属于易失RAM，重新配置后为空，使用时需从PC重新下载；本轮只验证了该复位状态。

首次尝试因工具返回多个同名Flash定义而在任何Flash访问前停止，日志已保留；修正为项目原有型号选择方式后完成核验，未跳过型号或硬件识别检查。

证据目录：`../../FPGA/reports/flash/latest_verified_20261027_2344/`，含 `flash_before.bin`、`flash_after.bin`、`deployment.log`、`fpga_after_qspi_boot.rpt`、`qspi_boot_serial.json` 和 `manifest.json`。当前输出目录新增 `FPGA/output/awg_921600_20261027/flash/latest_verification.json`，未覆盖原历史固化清单。

当前模块外部5V关闭、SW0 OFF。恢复使用时先打开模块5V，供电稳定后再将SW0从OFF拨到ON。
