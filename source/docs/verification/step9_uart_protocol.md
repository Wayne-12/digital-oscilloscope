# 第九步：UART 收发与二进制帧协议

本步在已有参数包、DDS、BRAM 捕获和测量模块基础上增加 UART 与协议端点。验收使用 Vivado/XSim 2025.2、100 MHz 系统时钟、115200 bit/s、8N1；保持临时器件 `xc7a35tcsg324-1`，未选开发板预设，未添加最终管脚约束。

协议完整定义见 [protocol_spec.md](D:/示波器/PC/protocol/protocol_spec.md)。本步明确冻结 26 字节头、0～1024 字节负载、小端序字段、CRC-16/CCITT-FALSE 参数及三个已知向量。波形分段每包最多 508 个原始样本，保留 OTR，不丢弃原始 ADC 编码。

## 实现与复用

| 文件 | 职责 |
|---|---|
| `FPGA/rtl/common/protocol_pkg.sv` | 帧字段、命令/状态码、CRC 更新与线序 |
| `FPGA/rtl/uart_proto/uart_tx.sv` / `uart_rx.sv` | 相位累加分频、两级 RX 同步、起始位确认和停止位检查 |
| `byte_fifo.sv` / `uart_transport.sv` | 双向字节 FIFO、背压、溢出/假起始/停止位错误计数 |
| `frame_rx.sv` | 保留候选字节队列、完整 CRC 验证、逐字节滑动重同步和超时 |
| `frame_tx.sv` | 包头、payload、CRC 串行化；背压期间保持数据 |
| `protocol_commands.sv` | 命令语义/范围校验、配置提交、响应快照；复用 `measure_udiv` 整数除法器 |
| `protocol_wave_tx.sv` | 后端读样本、分段、sequence 回绕、时间戳进位和 STOP 取消 |
| `scope_protocol_core.sv` | 协议层连接、按包锁定发送仲裁，完整最近请求头诊断输出 |
| `scope_uart_endpoint.sv` | UART 位级接口与协议核心的可综合连接 |
| `PC/protocol/scope_protocol.py` | 无串口库依赖的编解码、错误恢复、波形分段重组 |

所有新增 RTL 为 SystemVerilog，`1ns/1ps`，`default_nettype none`，功能寄存器使用系统时钟同步高有效复位。FIFO 和 payload RAM 不清零，由指针、计数和状态保证有效读取。UART TX 复位为空闲高电平。

刺激保存在 `FPGA/sim/vectors/uart`，黄金字节、配置快照与计数保存在 `FPGA/sim/expected/uart`，运行日志和实际输出保存在 `FPGA/reports/uart`；执行时使用 ASCII 临时目录副本，以避开本机工具对路径的限制。

`uart_capture_backend.sv` 仅是验证适配器，实际实例化前面已通过的 `bram_capture`、`trigger_core`、`measurement_core` 和 `dds_core`。ADC 域为理想 25 MHz，系统域 100 MHz；读取真实冻结 BRAM 并核对 OTR、原码、逻辑索引、时间戳。配置和 arm 的 task 适配不能作为硬件 CDC 电路使用。

## 两层验证

`tb_uart_bits` 使用独立实数时间串口发送器和独立引脚接收器，不用同一 RTL 收发自环作为黄金模型。三个完整协议包分别在标称位周期、+2% 位周期、-2% 位周期下输入。发送每个 UART 位的累计周期数与 `ceil(n*100000000/115200)` 直接比较；RX 采样必须位于各数据位中间 50% 区间。

每次位级运行比较 88 个协议输入字节及 96 个响应字节；另有 8 个 FIFO 压力字节，其中前 4 个按序接收、后 4 个丢弃并精确计数。自动检查 960 次发送位长和 776 个接收采样点，确认一个假起始和一个错误停止位只各计数一次，随后完整帧仍能正常收发。

`tb_uart_bytes` 使用 Python 独立整数/协议黄金结果。每个种子传输 **1,048,576 字节（1 MiB）伪随机 PING 负载**，并逐字节比较全部 1,083,017 个响应线序字节。核对 1064 个通过 CRC 的请求头、1,048,862 个已接受负载字节、11 组配置快照；响应经 PC Parser 再次独立校验 CRC 与字段。

| 类别 | 检查内容 |
|---|---|
| 正常协议 | 空 PING、任意二进制回显、版本、状态、最短/最大帧、连续帧 |
| 记录与触发 | 16K 记录参数、预触发比例和触发配置；非法字段在缩窄前拒绝 |
| 捕获控制 | 释放旧帧后重新单次捕获；捕获中 STOP；未完成帧读取返回 ERR_NO_FRAME |
| 测量与 DDS | 真实整数测量结果编码；DDS 波形、频率字、相位、幅度和偏置配置及安全中码 |
| 重新同步 | 坏 CRC、非法版本、过长长度、丢字节、插字节、重叠 `55 55 AA`、部分帧超时；每项后接有效哨兵包 |
| 错误计数 | 每种子 CRC=3、长度=1、版本=1、超时=1、未知命令=1、命令语义错误=11 |
| 背压 | 输出暂停 8000 周期、随机 ready、队列满；阻塞期间 valid/data 保持，输入满时确实产生等待 |
| 分段 | 1600 点分为 4 包，首序号 FFFF，下一包 0000；时间戳从 FFFFFFFFFFFFFFF8 进位 |
| 中途停止 | 首包发送时 STOP，首包完整发完、后续包取消，STOP 响应不插入包中 |
| 数据路径 | 每种子 2113 个 BRAM 样本经波形包逐字节比较，包含触发附近和 OTR 样本 |

1 MiB 指负载本身，不把帧头、CRC 或重放次数充作负载。两个固定种子 20261020、42 合计 2,097,152 字节伪随机负载；额外进行第一种子重放。每个 testbench 有 watchdog 和唯一自动 PASS/FAIL 终点；脚本同时检查进程、日志、完整用例数和输出轨迹，不能只依据退出码。

## 最终结果与重现

最终仿真验收目录为 `FPGA/reports/uart/20261022_010136_ca06e863`，`manifest.json` 保存源码 SHA-256、完整命令、种子、独立审计、重放和原工程结果；`acceptance.json` 是最后归档门限。两个种子、固定种子重放、删除原工程生成的 `scope_smoke.sim` 后重新运行两个行为仿真顶层均已通过，且重放与原工程输出轨迹一致。生成目录清理只针对经过绝对路径和重解析点校验的该目录。

独立综合结果：`FPGA/reports/uart_synthesis/20261022_005617_07673c3e`。

| 独立综合顶层 | LUT* 单元 | FF* 单元 | RAM* 非 BRAM 单元 | 锁存器 | 警告 |
|---|---:|---:|---:|---:|---:|
| uart_transport | 234 | 269 | 120 | 0 | 0 |
| scope_uart_endpoint | 3473 | 3267 | 840 | 0 | 0 |

表中 RAM* 是综合网表原语计数，不等同于按位容量，也未计入 LUT* 列。完整资源使用报告一并保留。首轮综合暴露的未使用请求元数据接口已改为独立命令头和可追踪完整请求头；payload 缓存改成单写口 RAM，未通过屏蔽警告或保持无用寄存器处理。

原工程的 HDL 编译、展开和运行日志没有 warning/error。Vivado 主控制台仍保留环境提示：55 条未使用板卡库提示 Board 49-26、一条 Project 1-5713、一条既有 IP 路径提示 Vivado 12-13650，以及两条 Wavedata 42-489（默认波形窗口不能展示整块 16 Mbit 黄金数组）。这些提示的完整文本保存在 project/console.log；它们不属于 HDL 编译诊断，也未通过调整消息严重度隐藏。

```powershell
# D:\示波器，PowerShell 7
& .\FPGA\scripts\run_uart_tb.ps1 -PythonExe 'D:\Python\python3.14\python3.14.7\python.exe' -Project
& .\FPGA\scripts\run_uart_synthesis.ps1
& 'D:\Python\python3.14\python3.14.7\python.exe' -m unittest discover -s .\PC\tests -p test_scope_protocol.py -v

# 保留可更换种子的入口；仍逐种子传输 1 MiB
& .\FPGA\scripts\run_uart_tb.ps1 -Seeds 123,456
```

## 当前边界

本步验证 UART/协议和 16K BRAM 回读。最终硬件 CDC、管脚和时序检查见板级验收记录。

物理 UART 无 RTS/CTS；暂停线上接收会丢新字节并计数，PC 应使用逐命令等待或受控窗口。1 MiB 压力测试在字节 valid/ready 层执行，真实 115200 位级冒烟测试独立保留。本步独立综合确认可映射与零锁存器，不表示已经完成物理串口连线或板上性能验证。
