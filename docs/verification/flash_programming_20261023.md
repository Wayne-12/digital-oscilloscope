# EGO1 示波器 Flash 固化（2026-10-23）

## 实物与镜像

- FPGA：`xc7a35t_0`，IDCODE `0362d093`。
- JTAG：`localhost:3121/xilinx_tcf/Xilinx/1234-tulA`。
- 实测 Flash：Micron `n25q64-3.3v`，JEDEC `20 ba 17`，64 Mbit / 8 MiB。
- 随板资料写 N25Q32，但与本机实物不同。第一次 N25Q32 备份请求被 Vivado 的器件识别检查拒绝，未执行 Flash 擦除或写入；记录位于 `FPGA/reports/flash/20261023_212517/` 和 `tmp/flash_prepare/program_20261023_212517.log`。
- 正式镜像目录：`FPGA/output/flash_n25q64/`。旧 `flash_n25q32/` 目录仅为未使用的准备文件。
- 复用已通过实现的 `FPGA/reports/board/20261023_194352/artifacts/routed.dcp`，保留采集逻辑、引脚和布局布线，仅设置 SPIx1、CCLK、3 MHz 启动参数后重新生成 bitstream。
- 运行功能仍为 25 MSPS、16K BRAM、115200 8N1；烧写没有增加采集功能。

## 安全准备

用户已确认外部 ADC/DAC 5 V 关闭、SW0 OFF，开发板和 USB/JTAG 保持供电连接，并明确要求开始固化。

SW0 是左侧一排 8 个独立滑动开关中的最右端，板上标识 `SW0-R1`，不是右侧整块 DIP 开关。按手册照片接口在上的方向，OFF 为朝板子下边缘。固件还要求观察到 OFF 后再 ON，才允许驱动模块。

## 执行与证据

- 离线生成：`FPGA/scripts/prepare_scope_flash.tcl`。
- 备份、编程、校验：`FPGA/scripts/program_scope_flash.tcl`。
- 正式报告：`FPGA/reports/flash/20261023_212730/`。
- Vivado 日志：`tmp/flash_prepare/program_n25q64_20261023_212730.log`。
- 原 Flash 完整备份：报告目录中的 `flash_before.bin`，8,388,608 字节。
- 状态：2026-10-23 21:29:43 烧写完成。Vivado 擦除、空白检查、编程及校验全部通过；独立读回 2,192,012 字节，与 BIN 逐字节完全一致。读回 SHA256 为 `1a268a19d99a6b5ae919ceaac1d107c7e6e0e4c761a2cb39d4c1ecfecd7feb4c`。
- 日志已归档到报告目录 `program.log` / `program.jou`。最终 `manifest.json` 状态为 `PASS_FLASH_PROGRAM_AND_COLD_BOOT_VERIFIED`。
- 原 Flash 备份 SHA256 为 `dd0001cd5a1639d374858b8f24e73222cc1f2c7a787967eeb9e08fc6f85b63c4`。

脚本在完整备份且容量检查成功后，才擦除镜像覆盖的地址范围；启用擦除、空白检查、编程和校验。随后单独读回镜像地址范围，与生成的 BIN 逐字节比较。器件 ID 检查保留，未绕过型号不匹配错误。

## 冷启动验证通过

用户已确认将 JP2 切到 QSPI 并真正重新上电。2026-10-23 21:32:47 验证通过：

- 未再次通过 JTAG 下载或重配置。
- 启动模式 `M[2:0]=001`，DONE=1、EOS=1、CRC_ERROR=0。
- COM12 / 115200 的 PING 回显、GET_VERSION、GET_STATUS 全部通过，协议解析 CRC、长度、版本及超时错误均为 0。
- 固件回报采样率 25,000,000 Hz。该值为设备状态回报，不是实际 ADC 波形采集或模拟性能测试。
- 证据：`cold_boot_verified.log`、`cold_boot_fpga.rpt`、`cold_boot_serial.json`。
- 首次只读寄存器检查在模式引脚属性名称上少补了 0，导致脚本失败；设备寄存器报告已正常导出。修正格式后复查通过，首次日志 `cold_boot.log` 保留，无硬件重写。

后续使用保持 JP2 在 QSPI，即可上电自动加载。先等待 FPGA 配置完成，再给 ADC/DAC 模块上 5 V，最后将 SW0 从 OFF 切到 ON。界面选择“硬件串口”、COM12、115200 后连接。本次未恢复外部模块供电或启动实物采集。

### 本次采用的断电验证步骤

烧写前读取的模式引脚为 `M[2:0]=101`（JTAG）。仅写 Flash 不会改变物理启动模式。需要在烧写完成后：

1. 保持 SW0 OFF、模块外部 5 V OFF。
2. 完全关闭开发板供电；若 USB 也给板子供电，需要断开 USB。
3. 将板上 JP2 跳线移到丝印 `QSPI` 一侧（模式应为 `001`）。JP2 是板子中部偏右、旁边印有 `QSPI/JTAG` 的三针跳线，不是 SW0。
4. 重新连接 USB、给 EGO1 供电；等待 DONE 指示灯 D24 点亮。
5. 不经 JTAG 下载，读取 DONE/EOS 和串口 PING / GET_VERSION / GET_STATUS，以验证从 Flash 启动。
6. 验证通过后，才恢复 ADC/DAC 模块 5 V，再把 SW0 从 OFF 切到 ON 允许采集。

Flash 校验与断电自动启动是两项独立结果；本次两项均已通过。
