# FPGA 基础测量与 1024 点 FFT 固化（2026-10-26）

最终状态：**Flash固化、真正断电自动启动及启动后四波形采集全部通过**（`PASS_FLASH_PROGRAM_COLD_BOOT_AND_ANALYSIS_CAPTURE_VERIFIED`）。以后正常上电会自动加载，无需重新JTAG下载。最新机器状态见 [Flash 清单](../../FPGA/output/analysis_1024_921600_20261026/flash/flash_manifest.json)。

## 固化内容与证据

固件版本 `0xA0261026`，能力值 7，25 MSPS / 16384 点 BRAM / UART 921600。包含 FPGA 整帧基础测量、前1024点周期 Hann FFT、主交流谱峰及 H2～H5 幅度摘要；保留包络和单帧 ROI。2048点FFT及复杂频谱指标已移除。

复用已验证的 routed checkpoint（SHA256 `38cac78a06022d69eca2a5f51dbb6746675ef13bce82a46f2fb96d1690a0a984`），只设置 SPIx1、CCLK、3 MHz 启动属性，不修改采集、FFT、协议、管脚和采样时钟。固化前完整实物验证见 [96帧实物记录](fpga_measure_fft_hardware_20261026.md)。

用户明确要求固化，并确认 SW0 OFF、ADC/DAC 外部5 V关闭、开发板和USB/JTAG保持连接。限定 JTAG 目标 `1234-tulA`、FPGA IDCODE `0362d093`；Vivado实际识别 JEDEC `20 ba 17`，匹配 `n25q64-3.3v-spi-x1_x2_x4`，没有绕过型号检查。

| 检查 | 结果 |
|---|---|
| 写前完整备份 | 8,388,608字节；前缀与原0xA0261025发布镜像逐字节一致。 |
| 擦除与空白检查 | 通过。 |
| 编程与工具校验 | 通过。 |
| 独立读回 | 2,192,012字节，与准备镜像逐字节一致。 |
| 备份 SHA256 | `7eec0895add7981faa4edbeba225a444d501d930d95022d13ab898fe7ed82936` |
| 新 BIN/独立读回 SHA256 | `afc0171f310d31c365fb3b0b5e4270b8b7bec11b803e2668f078973b52bfa434` |

发布文件：[启动镜像清单](../../FPGA/output/analysis_1024_921600_20261026/flash/prepared_manifest.json)、[发布总清单](../../FPGA/output/analysis_1024_921600_20261026/release_manifest.json)。

恢复资料：[完整写前备份](../../FPGA/reports/flash/analysis_1024_20261026_190729/flash_before.bin)、[编程日志](../../FPGA/reports/flash/analysis_1024_20261026_190729/program.console.log)、[独立读回](../../FPGA/reports/flash/analysis_1024_20261026_190729/flash_after.bin)。原固件发布及本次原始JTAG bitstream均保留。PC界面和相对校准基线保存在电脑，未写入板卡Flash。

## 断电启动验证

用户已明确确认断开全部板卡供电（包括USB）、板灯熄灭后重新上电，JP2保持QSPI，SW0 OFF，模块外部5 V关闭。随后仅进行只读JTAG状态与UART查询，没有JTAG下载或重新配置：模式001、DONE=1、EOS=1、CRC_ERROR=0；串口921600、版本0xA0261026、能力值7、启动状态flags=4、记录16384点、采样率25 MSPS，全部错误计数为0。

证据：[启动寄存器日志](../../FPGA/reports/flash/analysis_1024_20261026_190729/boot.console.log)、[启动FPGA属性](../../FPGA/reports/flash/analysis_1024_20261026_190729/cold_boot_fpga.rpt)、[只读串口查询](../../FPGA/reports/flash/analysis_1024_20261026_190729/cold_boot_serial.json)。


## 冷启动后实物复测

用户确认两块模块外部5.0 V电源开启、供电稳定且SW0 OFF→ON后，复测正弦、方波、三角波和直流；测试DDS幅度不超过既定10%，没有重新JTAG下载或再次写入Flash。

| 波形 | 时域频率 | 峰峰值（ADC码） | RMS（ADC码） | FFT主峰桶 |
|---|---:|---:|---:|---:|
| 正弦 | 100006 Hz | 122 | 42 | 4 |
| 方波 | 100000 Hz | 126 | 59 | 4 |
| 三角波 | 99994 Hz | 120 | 34 | 4 |
| 直流 | 0（周期无效） | 6 | 3 | 0（交流主峰无效） |

每帧保存16384点原始数据，独立核对基础统计、周期/频率/占空比、1024点FFT及H2～H5幅度和频点，确认重复读取摘要不变且与原始帧同时间戳。无OTR；三种交流波形的谐波比例能区分输出类型，避免静止输入误通过。25 MSPS/1024点FFT间隔为24.4140625 kHz，第4桶约97.656 kHz，精细测频使用时域整帧结果。

[四波形原始数据与数值核验](../../FPGA/reports/flash/analysis_1024_20261026_190729/cold_boot_summary/verification.json)、[最终只读配置和错误计数](../../FPGA/reports/flash/analysis_1024_20261026_190729/final_readback_serial.json)。最终FPGA八项错误计数及PC解析器CRC/长度/版本/超时错误均为0，48字节配置与冷启动时逐字节一致，原100 kHz/10% DDS设置恢复。采集STOP，COM12释放；外部模块电源和SW0仍由用户控制。

## 日常使用

JP2保持QSPI。SW0先OFF，开发板上电并完成配置（DONE亮）后开启模块外部5V，供电稳定后SW0 OFF→ON。保持原OUTA→IN接线及实体旋钮设置，再启动电脑上的示波器界面，连接COM12/921600。结束时SW0 OFF → 模块外部5V关闭 → 开发板/USB断电。

校准与PC界面仍在电脑运行；本次验证不替代外部标准源的绝对精度检定或长时间稳定性验收。
