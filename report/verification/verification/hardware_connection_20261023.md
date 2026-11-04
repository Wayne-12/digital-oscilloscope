> 2026-10-24 工程范围调整：本文涉及的部分旧版报告已完整移至工程外备份，原始 PASS/FAIL 与哈希未改写；历史路径对照见 `docs/verification/历史报告归档说明.md`。本文旧记录不能代替现版工程验证。

# 2026-10-23 实物连接与系统仿真

> 后续更新（21:32）：实物固件已完成 N25Q64 Flash 固化和真正断电重启验证；当前 JP2=QSPI、模式 001，DONE=1、EOS=1、CRC_ERROR=0；COM12 / 115200 的 PING、GET_VERSION、GET_STATUS 全部通过。本文下方为较早的发现记录，不能作为当前连接结论；最新证据见 `flash_programming_20261023.md`。

## 本次已执行

- 使用本机 Vivado 2025.2 XSim，运行 `run_system_regression.py --system-only --cases 0 1 2 3 4 5 6 7 8 --seeds 20261020 42`。
- 新结果目录：`FPGA/reports/system/20261023_185234_3f7d73e4/`。
- 系统级9场景、双种子18次全部PASS，均有终止TEST_PASS和独立审计。无首错，临时构建目录已清理。
- 本次未重跑单元及集成层，不替代完整分层回归。仿真使用行为硬件模型，不属于实物采集。
- 已启动根目录示波器UI，切换“硬件串口”，选中COM12、115200，尝试连接。
- UI实际结果：设备响应超时，硬件未连接，图形及测量已清空。

## 实物发现

- USB串口：COM12，FTDI VID:PID=0403:6010，序号1234。
- Vivado JTAG目标：`localhost:3121/xilinx_tcf/Xilinx/1234-tulA`。
- 器件：`xc7a35t_0`，IDCODE_HEX=`0362D093`。
- 配置状态：DONE=1、EOS=1、CRC_ERROR=0。该状态只说明存在配置，不能识别其具体功能或固件路径，也不确认封装和速度等级。
- 115200、230400、460800、921600下发送协议PING，均没有收到有效v1响应。部分探测收到的原始字节预览全为00，不能当成波形或协议数据。
- 未执行下载、重配置、擦写或模块输出使能。

## 实时显示尚未完成的原因

仓库当前 `scope_hw_top.sv` 为安全时钟壳，没有ADC数据、完整采集后端及UART连接；`scope_estimate_template.xdc` 为估算约束，没有实际PACKAGE_PIN和IO时序。项目目录下未发现可下载bitstream。

需要确认板上当前加载的.bit来源、路径和串口参数；如果没有正式固件，需要继续完成真实引脚核对、硬件顶层集成、完整约束和实现，再下载并联调。尚不能据现有信息判定实物故障或断言当前板上固件不兼容。

## 诊断证据

- 系统清单：`FPGA/reports/system/20261023_185234_3f7d73e4/manifest.json`
- JTAG日志：`tmp/scope_hardware_probe.log`
- 串口结果：`tmp/scope_serial_probe.json`
- 只读发现脚本：`tmp/probe_scope_hardware.tcl`、`tmp/probe_scope_serial.py`
- UI输出：`tmp/scope_ui_live.stdout.log`、`tmp/scope_ui_live.stderr.log`
