> 2026-10-24 工程范围调整：本文涉及的部分旧版报告已完整移至工程外备份，原始 PASS/FAIL 与哈希未改写；历史路径对照见 `docs/verification/历史报告归档说明.md`。本文旧记录不能代替现版工程验证。

# EGO1 首次上板版本

> 后续采集更新：已在 100 kHz DDS、10% 数字幅度下读取真实 16K ADC 波形，并在 UI 用普通上升沿 SINGLE 两次成功显示。实测标称幅度约 31.7 mVpp，中心约 +10 mV；最终触发电平 0.010 V、迟滞 0.005 V。此前触发超时由输入幅度/偏置与触发门限不匹配造成，原始数据及诊断见 `trigger_timeout_20261023.md`。该结果不是模拟精度校准或完整性能验收。

> 2026-10-23 21:32 更新：已完成实物 N25Q64（JEDEC `20 ba 17`，8 MiB）Flash 固化，工具校验和独立二进制读回比较通过。用户切换 JP2 到 QSPI 并真正断电重启后，模式 001、DONE=1、EOS=1、CRC_ERROR=0，COM12 / 115200 的 PING、版本和状态查询全部通过。完整备份及报告在 `FPGA/reports/flash/20261023_212730/`。下方“未写Flash”和串口缺失是此前历史状态；详见 `flash_programming_20261023.md`。

本次工作目标是25 MSPS、16K BRAM、115200 8N1的实际采集链路。用户已确认完全按终稿6.2/6.3接线，模块外部5.0 V和共地已确认。

## 源码和操作

- 实物顶层：`FPGA/rtl/top/scope_board_top.sv`。
- 实物约束：`FPGA/constraints/scope_board_25m.xdc`，引脚按已确认的接线表，接口使用2 ns外部布线/偏斜预算。该预算不是实测线缆延迟，升速前需重新评估。
- DDS：`scope_board_dds.sv`保留原DDS整数舍入/饱和，增加流水线。稳定配置的输出码序列比原DDS延后3个时钟。
- UART、触发、采集和读口统一为同一25 MHz时钟域。
- 此版本只接受 16384 点记录，其他长度返回 ERR_CONFIG。测量和 FFT 由 PC 基于原始快照计算；FPGA 测量响应有效标志为 0。
- 启动时无论SW0初始位置如何，均不直接使能模块。需先让SW0为低并稳定，再置高使能。SW0按硬件手册对应R1；厂商XDC中的数组编号顺序与手册相反。
- 状态LED引脚：K3=时钟锁定，M1=允许采样，L1=冻结帧，K6=有效协议包计数最低位。界面STOP停止采集，人工SW0撤销后才依序关闭模块时钟并高阻。

## 入口

```powershell
python FPGA/scripts/build_scope_board.py
python FPGA/scripts/build_scope_board.py --simulation-baud 115200
python FPGA/scripts/build_scope_board.py --implement
```

测试台覆盖上电高阻、UART 握手、拒绝非法记录长度、16K 捕获和全部冻结 BRAM 字比较，再通过 UART 引脚读回首尾各 64 点，最后验证撤销使能后高阻。

`--reuse-report <PASS报告目录> --implement`只复用源码哈希和暂存文件均匹配的PASS仿真；旧RTL改变后必须重新仿真。使用ASCII临时目录规避工具中文路径问题，结果保存在`FPGA/reports/board/`。

## 已完成及待确认

- 现有协议双种子：`FPGA/reports/unit/20261023_191853_760291` PASS。
- 原DDS顶层加速自检：`FPGA/reports/board/20261023_193252` PASS。
- 原DDS顶层115200自检：`FPGA/reports/board/20261023_193726` PASS。
- 流水线DDS与原DDS65728次对比、新顶层加速自检及完整实现：`FPGA/reports/board/20261023_194352`，全部PASS。最差setup=10.319 ns、hold=0.043 ns，无负余量；39个实际IO映射已核对。
- 流水线DDS顶层115200自检：`FPGA/reports/board/20261023_194518`，PASS。
- 旧约束循环未被read_xdc接受，首次实现被NSTD/UCIO拦截；约束已展开为单条设置。修正约束后的旧DDS实现被实际setup违例拦截，最差-35.123 ns。失败证据保留在`193555`和`194041`报告。
- 初次新测试台的ADC模型需在首个真实ADC时钟边沿执行仿真flush；另修正UART接收检查器的无符号长度解析，生产ADC及UART算法未因此修改。
- 2026-10-23 19:50已通过JTAG下载成功，DONE=1。稳定固件路径`FPGA/output/board_25m/scope_board_25m.bit`，SHA256=`66ae44bd2a53cbfc9177063315e2338108bf875f7088ed76e4364944dff4b736`，下载日志为同目录`program.log`。未写Flash，断电后需重新下载。
- 下载后首次电脑界面操作被用户Esc停止；后续重新授权后，UI已调到前台并选硬件模式、COM12、115200。连接时报Write timeout；Windows Win32_SerialPort当前未列出COM12，但pyserial注册表枚举仍保留此端口。不能据此声称已收到真实波形。已请用户检查USB和电源，如重插则先SW0 OFF并关闭外部模块5V。UI后台驱动收尾尚未完成，连接按钮暂不可用。
- 本轮新115200复跑报告为`FPGA/reports/board/20261023_195719`，最终PASS：65728次DDS对比、12个有效协议包、16384个冻结样本逐点核对、UART首尾共128点读回均通过。即插即用PresentOnly列表也未发现FTDI/COM12，真实数据仍等待物理USB连接恢复；界面保持打开。
