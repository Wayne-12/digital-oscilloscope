# 多分辨率采集版本 Flash 固化

## 当前状态

2026-10-24 已完成 N25Q64 Flash 的完整备份、擦除、空白检查、编程、工具校验、独立二进制读回比较、真正断电启动及冷启动多分辨率采集验证。最终状态为 `PASS_FLASH_PROGRAM_COLD_BOOT_AND_MULTIRES_CAPTURE_VERIFIED`，以发布清单与 Flash 报告清单为准。

发布目录：`FPGA/output/multires_921600_20261024/flash/`。

Flash 报告与写前完整备份：`FPGA/reports/flash/multires_921600_20261024/`。

## 固件来源

- build `0xA0261024`，COM12 / 921600 bit/s，单通道 25 MSPS、16384 点 BRAM。
- 来源 `FPGA/reports/board/20261024_203912/artifacts/routed.dcp`。所有生产 RTL SHA256 与已仿真、实现和实物验证的版本逐项匹配。
- 复用已布线检查点，仅设置 Flash 启动属性 SPIx1、CCLK、3 MHz；没有更改 RTL、外部管脚或采样时钟。
- 既有实物验证见 `multires_physical_20261024.md`，包含板端 min/max/OTR 概览、同帧原始 ROI、分包与取消、连续采集。此次固化没有加入闭环自动自检或校准功能。

## 写入及独立读回

用户明确要求先固化此版本，并确认 SW0 OFF、外部 ADC/DAC 5 V 关闭、开发板与 USB/JTAG 供电保持。先核对实物目标 `1234-tulA`、FPGA IDCODE `0362d093`；Vivado 识别 Flash JEDEC `20 ba 17`，匹配 N25Q64、8 MiB，没有绕过型号检查。

- 写前读取完整 8,388,608 字节 Flash 并核对大小；备份前缀与原 921600 高速固化镜像一致。
- `FLASH_BACKUP_PASS`、`FLASH_PROGRAM_VERIFY_PASS`、`FLASH_BINARY_COMPARE_PASS`、`FLASH_PROGRAM_PASS_BOOT_TEST_PENDING` 均有保存的终端日志证据。
- 独立读回新镜像覆盖的 2,192,012 字节，与准备的 BIN 逐字节完全相同。
- 写前完整备份 SHA256：`19e4a0c6777926e013e1d4b01f28a214da720791dd6b4aca73331d1e1866f95c`。
- 新 BIN 和独立读回共同 SHA256：`7db46272db46a2ad2725d073c62b6d38f733d81b34fb2109be544ab4895a45ca`。
- 旧版固化镜像、旧版报告及本次写前完整备份均保留。`prepared_manifest.json` 和 `flash_manifest.json` 记录镜像哈希及状态，原本的 JTAG bitstream 同样保留。

## 冷启动验收流程

保持 JP2=QSPI、SW0 OFF、外部 ADC/DAC 5 V 关闭。由用户将开发板全部供电（包括 USB）断开，待灯熄灭后重新上电，再读取模式 001、DONE、EOS、CRC_ERROR 及串口版本/能力。该阶段禁止重新下载 FPGA或发送 DDS/触发/记录配置命令，以区分 Flash 启动与临时 JTAG 加载。

确认冷启动后，由用户恢复外部模块 5 V，稳定后 SW0 OFF→ON。再重新获取板端 100/200/400/800 桶概览及同帧原始 ROI，并用完整原始记录逐桶、逐点比对。此阶段结果通过后才标记全部验收完成。

## 真正断电启动与实物结果

用户确认开发板全部供电断开、灯灭后重新上电且 DONE 亮。首次只读检查时电脑没有看到 COM12 和 JTAG，保留失败记录于 `boot_attempt_usb_absent/`；用户重新插回原 USB/JTAG 数据线后，以下读取全部通过，没有重新下载 FPGA：

- 启动模式 M[2:0]=001（QSPI），DONE=1、EOS=1、CRC_ERROR=0。
- COM12 / 921600 的 PING、版本、能力和状态查询 PASS；版本 `01000000241026a0`，能力 flags=1，设备回报 25 MSPS、16384 点，DDS 上电预设启用。
- 该识别阶段未发送 SET_RECORD、SET_TRIGGER、SET_DDS、SINGLE 或 JTAG 重配置；证据为 `boot.console.log`、`cold_boot_fpga.rpt`、`cold_boot_serial.json`。

用户随后确认外部 ADC/DAC 模块 5 V 恢复并将 SW0 OFF→ON。保持 Flash 上电预设，执行六次独立采集（100/200/400/800/800/800 桶）：

- 3100 个板端 min/max/OTR 桶与同一冻结帧完整原始数据全部精确一致；初始 2048 点 ROI 及每帧另外三段 ROI 均逐点一致。
- 三段追加 ROI 合计 21504 点；旧帧被新采集替换后的 ROI 被正确拒绝，未混帧。
- 三次 800 桶 + 2048 点 ROI 的采集回传中位数约 153.75 ms；包络和 ROI 响应数据共 8436 B，完整原始响应 33956 B。
- 实测频率约 100 kHz，Vpp 约 134～144 mV；PC 解析错误与 FPGA 八项协议/UART 错误计数增量均为 0，后端错误为 0。
- 本次采集没有发送 DDS/触发/记录配置命令，也没有重新编程 FPGA。独立证据目录为 `FPGA/reports/multires_hardware/20261024_210941/`，完整原始码保留在该目录；Flash 报告中另存 `cold_boot_capture.json` 和 `cold_boot_multires.png`。

## 日常使用

JP2 保持 QSPI。上电前 SW0 OFF、外部模块 5 V 关闭；DONE 亮后恢复模块 5 V，供电稳定后 SW0 ON。启动 `启动示波器界面.cmd --multires`，COM12 / 921600，连接后 SINGLE 或 RUN。STOP 并等待接收结束后拖动概览选区查看按需原始 ROI。以后上电无需再通过 JTAG 下载本版固件。
