# 闭环自检与校准固化（2026-10-25）

最终状态：`PASS_FLASH_PROGRAM_COLD_BOOT_CALIBRATION_AND_MULTIRES_VERIFIED`。整片备份、编程校验、独立读回逐字节比较、真正断电后的 QSPI 自动启动，以及恢复模块后的闭环自检与多分辨率采集复测全部通过。以后正常上电可自动加载，无需重新 JTAG 下载。

## 固化内容

实测通过的新版本 `0xA0261025`，25 MSPS / 16384 点 BRAM / UART 921600，能力 flags=3。保留此前板端 min/max/OTR 包络和原始 ROI，新增完整配置读回，支持 PC 实物闭环自检与相对校准。零点、直流拟合、幅度线性、频响、谐波及参数计算由 PC 使用真实 ADC 帧完成，FPGA Flash 保存对应硬件固件，实测基线仍保存在电脑。

构建证据为 `FPGA/reports/board/20261025_093107/manifest.json`；固化前实测及回归见 `closed_loop_calibration_20261025.md`。此次复用已验证的 routed checkpoint，只将启动时钟设为 CCLK、配置模式设为 SPIx1、配置速率设为 3，生成 QSPI 镜像，不改变采样和协议逻辑。

## 文件与恢复

- 新版发布目录：`FPGA/output/calibration_921600_20261025/flash/`。
- Flash 记录目录：`FPGA/reports/flash/calibration_921600_20261025/`。
- 整片旧 Flash 备份：记录目录 `flash_before.bin`（必须为 8388608 字节）；写入前强制完成备份。
- 旧多分辨率发布仍在 `FPGA/output/multires_921600_20261024/flash/`，不会覆盖。
- 原始校准基线 `PC/ui/hardware_calibration_baseline.json` 保留，后续自检继续与其比较。

编程脚本限定 JTAG 目标 `1234-tulA`、器件 ID `0362d093`，Flash 定义 `n25q64-3.3v-spi-x1_x2_x4`，依赖 Vivado 的 JEDEC 型号检查。编程时外部 ADC/DAC 5 V 关闭、SW0 OFF，开发板和 USB/JTAG 供电保留。先整片备份，再擦写和 Vivado verify，随后独立读回镜像范围逐字节比较。

编程阶段证据：JEDEC `20 ba 17`；备份 8388608 字节、SHA256 `d11b9e820b163d8ecb359f3c3579e93b1663d1c0af12117d0a34b2e62750b52e`，前缀与原多分辨率镜像完全一致；新镜像读回 2192012 字节、SHA256 `64e5aef0aa338667ffc9ef5b64611f6982812941d185ae1762912ecb1c05dfd8`，逐字节比较通过。`program.console.log` 包含四个成功标记，该阶段状态为 `PASS_FLASH_PROGRAM_COLD_BOOT_PENDING`，随后完成以下冷启动和采集验收。

用户随后确认已断开全部供电及 USB、板灯熄灭并重新上电，JP2=QSPI、SW0=OFF、模块 5 V 关闭。`boot.console.log` 只读验证 mode=001、DONE=1、EOS=1、CRC_ERROR=0；`cold_boot_serial.json` 只读验证版本 `01000000251026a0`、flags=3、启动状态 flags=4、采样率 25 MSPS、16K 记录及全部错误计数为 0。此阶段没有执行 JTAG 下载、重配置、采集或配置写入，状态推进为 `PASS_FLASH_PROGRAM_AND_COLD_BOOT_VERIFIED`。

## 冷启动验收

必须真实断开开发板全部供电（含 USB），板灯熄灭后重新上电，JP2=QSPI、SW0=OFF、模块 5 V 仍关闭。只读取 JTAG 配置状态，不执行 FPGA 下载，验证 mode=001、DONE=1、EOS=1、CRC_ERROR=0；再只读 UART，确认 build=0xA0261025、flags=3、启动 DDS 预设和错误计数。

用户确认模块 5 V 已打开、SW0 OFF→ON 后完成以下复测；期间没有重新下载 FPGA。

| 复测 | 结果与证据 |
|---|---|
| 闭环自检 | `FPGA/reports/hardware_calibration/cold_boot_20261025_095847/verification.json` PASS，35 帧独立完整原始记录；九点直流 R²=0.999998，四档幅度线性偏差 0.338%，七点扫频及谐波测量通过 |
| 参数与独立验证 | 相对原基线增益 1.001083×，独立零点校正后 −0.415 mV，未参与拟合的 +512 DAC 码误差 −0.035 ADC码；配置逐字节恢复成功 |
| 原基线保留 | `baseline_preserved=true`，SHA256 仍为 `d585b8577429616ee1c90c36f3528e32532990bd773adf7e877eb80db29fcdbd`；仅更新最后一次结果 |
| 多分辨率 | `FPGA/reports/multires_hardware/20261025_095912/verification.json` PASS；100/200/400/800/800/800 六帧，3100 桶与完整冻结帧精确一致，额外 21504 ROI 点精确一致，过期 ROI 被拒绝 |
| 通信及后端 | 两项复测 PC 解析错误、FPGA 前八项错误计数增量及后端错误均为 0 |

最终清单同时保存在 `FPGA/reports/flash/calibration_921600_20261025/manifest.json` 与发布目录 `flash/flash_manifest.json`，发布总清单的 deployment 已更新为全部通过。

日常启动 JP2 保持 QSPI；SW0 先 OFF，开发板配置完成等待 DONE 后开启外部模块 5 V，稳定后 SW0 OFF→ON。软件功能仍通过 `启动示波器界面.cmd --calibration` 进入，自检必须保持已有 OUTA→IN 连接与实体旋钮不动。没有外部精密参考，结果属于组合链路相对校准。
