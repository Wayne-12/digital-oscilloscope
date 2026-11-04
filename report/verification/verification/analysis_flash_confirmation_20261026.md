# 当前验收版本的 Flash 固化确认（2026-10-26）

最终结果：**Flash 内已是本次功能验收的版本，完整读回一致，真正断电自动启动及启动后四种波形复测均通过。** 本轮无需重复擦写，未执行 Flash 擦除或编程；已另存完整 8 MiB 备份。

## 核验过程

1. 用户确认 SW0 OFF、ADC/DAC 外部 5V 关闭，USB/JTAG 保持供电。
2. 本次验收的原始 JTAG bitstream 与布局布线 checkpoint 均与离线报告核对 SHA256 一致。由同一 checkpoint 生成 SPIx1、CCLK、3 MHz 的启动镜像，未修改 RTL、管脚或采样逻辑。
3. 检查发现已有 `analysis_1024_20261026_190729` 固化记录。重新读取实物 N25Q64，JEDEC 为 `20 ba 17`；完整备份 8388608 字节，镜像范围 2192012 字节与目标 `.bin` 逐字节相同，SHA256 为 `afc0171f310d31c365fb3b0b5e4270b8b7bec11b803e2668f078973b52bfa434`。
4. Flash 内容已符合目标，未执行重复擦写。从 Flash 重载后 DONE 正常。
5. 用户确认开发板完全断电、板灯熄灭、等待后重接 USB；此时模块 5V 仍关闭、SW0 OFF。只读 JTAG 检查确认模式 `001`、DONE=1、EOS=1、CRC_ERROR=0；只读 UART 确认 `0xA0261026`、能力值 7、921600 bit/s、25 MSPS、16384 点，以及初始状态/预设配置正确。
6. 用户开启模块 5V、SW0 OFF→ON 后，正弦、方波、三角波、直流四种真实波形的基础测量、1024 点 FFT、主峰/H2～H5、重复读取及同帧身份核对全部通过。原 DDS/触发/记录配置逐字节恢复，PC 协议解析错误为 0。

## 当前状态

- 当前版本已保存在非易失 Flash，断电再上电会自动加载，无需每次 JTAG 下载。
- 原校准基线仍保存在电脑中，未覆盖。PC 界面和相对校准报告不会因 FPGA Flash 固化而写入板卡。
- **两小时连续长稳测试尚未执行**；不能用本次冷启动和四波形复测代替。
- 测试结束已 STOP 并释放串口，保留恢复后的 DDS 配置；软件 STOP 不等于撤销 SW0 硬件使能。
- 正常断电顺序为 SW0 OFF → 关闭模块外部 5V → 断开开发板 USB/供电。正常启动使用 QSPI，SW0 先 OFF，开发板 DONE 后开启模块 5V，稳定后 SW0 OFF→ON。

此前聊天中“断电后回到旧固件”的判断基于不完整的固化状态信息，现已由本轮实物读回和真正冷启动结果纠正。最新状态以本记录为准。

## 证据

- [最终确认清单](../../FPGA/reports/flash/analysis_confirm_20261026_1937/manifest.json)
- [完整 Flash 备份](../../FPGA/reports/flash/analysis_confirm_20261026_1937/flash_before.bin)
- [读回与匹配日志](../../FPGA/reports/flash/analysis_confirm_20261026_1937/readback.log)
- [冷启动 JTAG 日志](../../FPGA/reports/flash/analysis_confirm_20261026_1937/cold_boot.log)
- [冷启动 UART 结果](../../FPGA/reports/flash/analysis_confirm_20261026_1937/cold_boot_serial.json)
- [冷启动后四波形验收](../../FPGA/reports/flash/analysis_confirm_20261026_1937/cold_boot_summary/verification.json)

发布目录中重新生成的 `.bit` 仅因文件头时间改变而产生不同文件哈希，Flash `.bin` 与 `.mcs` 均与既有发布清单一致；已恢复原发布 `.bit`，三个发布文件现与原 `prepared_manifest.json` 的哈希逐项一致。重新生成的文件另存在本次确认目录，不用于宣称发生了新的 Flash 写入。
