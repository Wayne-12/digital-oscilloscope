# 921600 高速固件 Flash 固化

## 结论

2026-10-24 已完成 N25Q64 Flash 固化、完整备份、独立读回比较和真正断电后的 QSPI 启动验证。COM12 / 921600 从 Flash 启动后通信及闭环采集通过；没有在断电启动后重新下载 FPGA。

发布目录：`FPGA/output/low_latency_921600_20261024/`。

验证报告：`FPGA/reports/flash/low_latency_921600_20261024/`。

最终状态：`PASS_FLASH_PROGRAM_COLD_BOOT_AND_CAPTURE_VERIFIED`，以两目录中的 JSON 清单为准。

## 来源和安全流程

- 来源：`FPGA/reports/board/20261024_160120/`，25 MSPS、16K BRAM、921600 bit/s；常规及上电默认预设管脚级仿真、实现、时序和 DRC 检查均通过。
- 准备前逐项校验 RTL 源哈希，使用已布线 checkpoint，仅设置 SPIx1、CCLK、3 MHz 配置启动参数。
- 用户明确要求固化并确认 SW0 OFF、外部 ADC/DAC 5 V 关闭，开发板和 USB/JTAG 保持供电。
- 实物 JTAG 目标 1234-tulA，FPGA IDCODE 0362d093，Flash JEDEC 20 ba 17，型号 N25Q64（8 MiB）。未绕过器件识别检查。
- 在擦除前读取整个 Flash 并验证大小 8,388,608 字节。旧备份前缀与上一版已固化的 115200 镜像一致。

## 写入与独立读回

Vivado 擦除、空白检查、编程和校验均通过；另外独立读回新镜像覆盖的 2,192,012 字节，与准备的 BIN 逐字节完全一致。

- `FLASH_BACKUP_PASS`
- `FLASH_PROGRAM_VERIFY_PASS`
- `FLASH_BINARY_COMPARE_PASS`
- `FLASH_PROGRAM_PASS_BOOT_TEST_PENDING`

备份 SHA256：`dd04fa6211121d3950cdb4a7b6490313385d21d31a2a2ad69e45f09c88507150`。

新 BIN 与独立读回的共同 SHA256：`a2566a461ec198154c92e6655f191509969c62e47ef29a6f5f40f2574b6a8b63`。

完整备份、读回、器件报告和 Vivado 日志均保留在报告目录；原发布文件未覆盖。

## 真正断电启动

用户确认完全断电后重上电，JP2=QSPI、DONE 亮，SW0 OFF、外部模块 5 V 继续关闭。只读寄存器与串口验证结果：

- M[2:0]=001，DONE=1，EOS=1，CRC_ERROR=0。
- COM12 / 921600 的 PING、GET_VERSION、GET_STATUS 通过，版本响应 `0100000024102620`，设备回报 25 MSPS、16384 点和 DDS 上电预设已启用。
- CRC、长度、版本、超时解析错误均为 0。
- 未发送 SET_RECORD、SET_TRIGGER、SET_DDS，也未通过 JTAG 重新下载或重配置。

证据为 `boot.console.log`、`cold_boot_fpga.rpt`、`cold_boot_serial.json`。Flash 校验与真正掉电启动分别验证，二者均通过。

## 冷启动闭环采集

用户随后确认模块 5 V 恢复、供电稳定、SW0 OFF→ON。保持 Flash 内的启动预设，不下发任何配置修改，连续采集 10 帧、813 点/帧：

- 采集时间中位数 64.854 ms。
- 频率约 99.98 kHz，Vpp 约 449 mV。
- 正弦软件模型有效，OTR=0，协议解析错误均为 0。

证据为 `cold_boot_capture.json` 和 `cold_boot_raw_words.npy`。低延时 UI 随后恢复 RUN；冷启动后连续 65 帧的界面刷新中位数 64.961 ms、95 分位 66.338 ms，约 15.385 次/秒，软件模型有效、协议错误全为 0。记录保存为 `cold_boot_ui.json` 及同名 PNG。此测量为采集/刷新周期，不是人工旋转到像素显示的直接延迟测量。

## 以后使用

保持 JP2=QSPI，上电先 SW0 OFF，等 DONE 后恢复模块 5 V，稳定后 SW0 ON。双击根目录 `启动示波器界面.cmd`，使用“实物联动演示”、COM12、921600，连接后 RUN。固件上电预设为正弦 100 kHz、数字幅度 10%；保存的 UI DDS 参数需手动应用才会覆盖该预设。
