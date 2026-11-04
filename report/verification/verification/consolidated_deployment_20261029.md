# 本轮更新交付与Flash持久化核验

2026-10-29 状态更新：**已解决（用户确认）**。用户确认真实模拟 OTR、非零饱和等异常情况已完成修复并通过真实模拟验收，电压绝对精度标定已完成，两项均已达到预期。此结论依据用户本次确认；本次仅更新工程文档状态，未重新执行硬件验收或生成测量数据。此前的 INCOMPLETE、NOT_CALIBRATED 及缺少仪器说明为更新前历史记录，以本条最新状态为准。

日期：2026-10-29。当前PC/UI版本为 **2026.10.29-r1**；板端固件为 **0xA4261027**、能力63。

## 固化结果

结论：**PASS_CURRENT_IMAGE_PERSISTENT_AND_TRUE_COLD_BOOT_VERIFIED**。

本轮OTR/饱和验收完善、绝对直流标定、DDS扫频及界面改动没有改变产品RTL、约束或时钟。已核对41项硬件输入哈希，与已验收的0xA4261027发布镜像一致，因此没有制造新的FPGA版本号或重新生成同逻辑镜像。PC代码和标定功能由电脑程序运行，无法装进EGO1的FPGA配置Flash。

用户确认SW0 OFF、ADC/DAC外部5V关闭且开发板/USB保持供电后：

- 校验目标BIT、Flash BIT完全一致；校验MCS记录、BIN内容连续及逐字节一致。
- 识别N25Q64，JEDEC厂商20、类型BA、容量17。
- 完整读回并备份Flash 8MiB，备份SHA256为 `7751c3929d36bea6ce28db160b133002c5daf34906c2fe26b7806a994035f41c`。
- 目标启动区域与现有镜像完全一致，执行 `RETAINED_IDENTICAL_IMAGE`，本轮没有重复擦除/写入Flash。
- 再次独立读回2,192,012字节，与目标BIN逐字节一致；SHA256为 `51b2ca2980a5580a364021a5599db2a997e39812ddf7e5659f2ab585f11b3e2d`。
- 按模式引脚从QSPI启动，MODE=001、DONE=1、EOS=1、CRC_ERROR=0，UART读回固件0xA4261027、能力63、25 MSPS、16K、921600，默认DDS100kHz/819码和SINGLE配置正确，错误计数为零。

随后用户确认开发板电源与USB完全断开、板灯熄灭并重新上电。此后只读JTAG和UART核验，没有重新下载或配置FPGA：MODE=001、DONE=1、EOS=1、CRC_ERROR=0；版本/能力/默认配置、空AWG表及零错误状态再次通过。此次真正断电启动已验证，不以软件重启代替。

发布BIT SHA256：`ddb4aca5667e40ea71628f1fa2ba850ad297a4c20d0bd7dfceb8c34d2acda7d9`。

证据：[manifest.json](../../FPGA/reports/flash/consolidated_20261029/manifest.json)、完整8MiB备份 `hardware/flash_before.bin`、独立读回 `hardware/flash_after.bin`、[真正冷启动串口记录](../../FPGA/reports/flash/consolidated_20261029/true_cold_boot_serial.json)、同目录JTAG日志和寄存器报告。

## 电脑端UI更新

- 窗口标题显示PC版本2026.10.29-r1。
- 输出页可见“闭环已测频点10 kHz～12.49 MHz”和“相对幅度±3dB已测频点至8 MHz”，并附测试日期/条件及分点范围提示；数字设置仍为0～12.5MHz。
- “工具→实物测量与验收说明…”集中显示OTR/非零饱和、绝对直流标定、DDS独立模拟质量及真正断电启动的仪器要求、步骤和现有边界。此入口只读，不发送硬件命令。
- 外部参考直流标定入口与原相对闭环自检继续保留；无独立参考时明确未标定，不生成实际系数，不覆盖现有相对基线。
- 原始码/OTR、整帧统计、采集、触发、AWG和导出行为保留。ADC原量程不变，DDS上限未下调。

最终160项PC回归通过，Ruff通过；日志和常用/小窗口及测量说明截图在 `PC/reports/consolidated_delivery_20261029/`。截图为离线布局检查，不冒充真实模拟数据。此前本轮真实模拟采集证据仍分别保存在各专项目录。

完整测量清单：[实物测量清单](实物测量清单_20261029.md)。实际绝对精度、真实OTR/非零饱和和独立DAC全频段质量仍保留未验收状态，固化核验不会改变这些结论。

当前板卡已从Flash冷启动，保持SW0 OFF、模块外部5V关闭。恢复使用时，先打开模块5V并稳定，再将SW0 OFF→ON；根目录 `启动示波器界面.cmd` 运行最新版PC界面。用户AWG表为易失RAM，断电后需重新下载。
