# 示波器 MicroBlaze C 软核控制系统

## 当前入口（2026-10-31最终显示版）

当前显示器工程位于 `../VGA显示部分/`，版本 **0xAF311031**，已固化到N25Q64并完成断电自动启动验证。
本目录采集、触发、DDS、测量、FFT、MicroBlaze IP和固件公共代码仍是最终显示工程的重建依赖。
当前C主循环为 `../VGA显示部分/panel_main.c`，当前显示MMIO为同目录 `scope_cpu_mailbox.sv`。
运行、重建与固化见 `../VGA显示部分/README.md`，最终证据见 `../VGA显示部分/最终验证.md`。
以下为软核历史开发基线。

## 历史透明桥接版本说明

本目录是独立开发版本，针对 EGO1 / XC7A35T、25 MSPS AD9226、AD9767 A 通道，以及现有 PySide6 UI。首版只做离线验证；用户追加授权后已完成临时 JTAG 下载、CDC 修复与有限实物验收，**没有固化 QSPI**。最新结论见 [CDC 修复报告](reports/cdc_repair/修复报告.md)：Critical 路径从 855 条降为 0 条。

CPU 使用 AMD MicroBlaze MCS（经典 MicroBlaze，非 RISC-V）。处理器硬件由 AMD IP 生成，C 编写的是在处理器中运行的固件；不能把普通 C 文件本身当作 FPGA 处理器网表。

## 架构与实现边界

```text
电脑原有 UI / 921600 8N1
           ↕
现有 uart_transport（1024 B RX/TX FIFO）
           ↕
四路 256 B FIFO + MicroBlaze MCS I/O Bus
           ↕
MicroBlaze 25 MHz / 32 KB 本地 BRAM / C 双向调度固件
           ↕
现有 scope_protocol_core → 触发、冻结采集、测量、FFT、包络、DDS、AWG
```

本版 C 固件实际负责 CPU 参与的双向字节调度，提供独立协议打包、CRC、记录与 DDS 参数构造函数。当前运行路径透明转发；命令语义处理、CRC 拒绝、重同步和分包仍由成熟的 RTL 协议引擎执行，**不是把所有示波器算法重新用 C 实现**。C 的编码 API 可供将来的板端菜单或独立控制器调用，当前主循环不主动发控制命令。

保持 RTL 的超时、CRC、错误计数与协议响应，不对损坏包进行软件提前丢弃；STOP 与大量波形响应同时存在时，两方向轮流得到服务。无堆分配、无 printf、无串口调试文字。机械旋钮仍由模拟链路体现。

CPU 不参与逐点 25 MSPS 处理；100 MHz 输入经原时钟模块生成 25 MHz，CPU、协议与邮箱同域。CDC 修复版保留 SW0 人工使能、失锁/复位高阻、完整预热与有序停机；内部使能经过两级本地采样，采集 CE 由时钟沿寄存器输出，消除原始控制旁路。CPU 停止服务时串口会停顿；本版未实现 CPU 看门狗强制关 DAC，不把心跳寄存器冒充安全看门狗。

## 文件入口

| 路径 | 作用 |
|---|---|
| `firmware/main.c` | 片上入口、ID 检查、MMIO、调度循环 |
| `firmware/scope_cpu.c/.h` | C 固件核心、CRC 与协议工具 |
| `firmware/start.S` / `link.ld` | MicroBlaze 启动、32 KB 链接布局，预留至少 4 KB 栈 |
| `rtl/scope_cpu_mailbox.sv` | MCS I/O 总线与四路 FIFO 桥 |
| `rtl/scope_cpu_endpoint.sv` | CPU、桥、UART 与原协议核的组合 |
| `rtl/scope_core.sv` | CDC 修复后的内部同步控制与安全关断覆盖层 |
| `rtl/scope_cpu_board_top.sv` | 实际参与构建的顶层，去掉 ODDR 原始复位旁路 |
| `integration/rtl/` | 原 RTL 独立快照；构建时排除被上述两个修复文件替代的版本 |
| `scripts/prepare_integration.py` | 重新生成快照与适配端点，记录原源文件 SHA256 |
| `scripts/build_firmware.ps1` | 编译真实 MicroBlaze 小端 ELF |
| `scripts/create_cpu_ip.tcl` | 原生 Vivado 2025.2 IP 创建、配置回读与导出 |
| `scripts/elaborate_system.tcl` | 独立整机工程创建、ELF 关联、IP 与整机综合 |
| `tests/`、`reports/` | 可重跑测试及证据 |

新增代码与生成物都在本目录。原 `FPGA/` 与 UI 不被修改。工程版本标记使用 `0xA4261028`，区别原固化的 `0xA4261027`；软核版本的实物验证范围以本目录报告为准，不继承旧版本的长期稳定性结论。

## UI 功能映射

| UI 功能 | 协议命令 | 执行位置 |
|---|---|---|
| 连接、版本、状态、能力、配置回读 | 01、02、03、04、05 | CPU 转发，RTL 响应 |
| 记录长度与预触发 | 10 | 固定 16384 点，0～1000000 ppm |
| 上升/下降、窗口、脉宽、幅度、OTR 触发 | 11 | 原 trigger_core |
| AUTO / NORMAL / SINGLE 模式、读回 | 12、13 | 原采集控制 |
| SINGLE、STOP、RUN、释放帧 | 20、21、22、23 | 原采集控制 |
| 原始波形、冻结帧 ROI | 30 | 原 BRAM 与分包器 |
| 基础测量、FFT、饱和统计 | 31、33、34 | 原测量与分析核 |
| min/max 多分辨率包络 | 32 | 原 envelope 模块 |
| DDS 正弦、方波、三角、直流 | 40 | 原 DDS，C 提供参数构造 API |
| AWG 下载、提交、读回、状态、选择 | 15～1A | 原双表 BRAM，CRC 后切换 |
| 数字诊断注入 | 14 | 原诊断控制 |
| 时基/光标、历史、拟合、校准、CSV/PNG | PC 端逻辑 | 继续由当前 UI 负责 |

## 本地复现

在 `D:\示波器` 的 PowerShell 中运行，均不访问硬件：

```powershell
python .\软核\scripts\prepare_integration.py
& .\软核\scripts\test_host.ps1
& .\软核\scripts\build_firmware.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\软核\scripts\run_cpu_ip.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\软核\scripts\run_cpu_ip.ps1 -Script scripts/test_mailbox.tcl
powershell -NoProfile -ExecutionPolicy Bypass -File .\软核\scripts\run_cpu_ip.ps1 -Script scripts/elaborate_system.tcl
```

脚本按本机已安装的 Vivado 2025.2、MicroBlaze GCC 和 MSVC 配置；`SCOPE_MB_BIN`、`SCOPE_VIVADO_BIN` 可覆盖工具路径。启动脚本在子 PowerShell 中临时映射空闲盘符，避免 Vivado 中文路径问题，所有文件仍落在本目录，结束解除盘符。XSim 仿真引擎若被受限运行环境阻止，需在允许本地原生子进程的环境重跑；编译成功不等于仿真通过。

生成 CPU IP 自带 AMD bootloop ELF；整机脚本另将 `build/scope_cpu.elf` 关联至 `scope_cpu_endpoint` 内的 `cpu/inst/microblaze_I` 处理器。**从 DCP 新会话实施后必须执行 `embed_firmware.tcl`，用布线后 MMI 与 ELF 显式生成 `build/scope_cpu_runtime.bit`。** 原始 `scope_cpu_test.bit` 是未保证嵌入 C 固件的中间镜像，禁止直接下载。当前运行文件为 `scope_cpu_runtime.bit`，CPU 已通过真实串口执行验证。

## MMIO 合同

地址基址 `0xC0000000`，32 位对齐访问，字节低 8 位为传输内容。空 FIFO 读/满 FIFO 写阻塞至可完成；固件先检查状态，不盲读盲写。读写仅在 strobe/ready 同时成立的时钟边沿提交。

| 偏移 | 方向 | 含义 |
|---|---|---|
| 00 | R | ID `0x53435031` |
| 04 | R | bit0 主机 RX 有数据、bit1 后端 TX 可写、bit2 后端 RX 有数据、bit3 主机 TX 可写 |
| 08 | R/pop | 主机输入字节 |
| 0C | W/push | 发给 RTL 协议核 |
| 10 | R/pop | RTL 响应字节 |
| 14 | W/push | 发给主机 UART |
| 18 | RW | 软件心跳，仅用于诊断 |

未映射地址读零、写忽略。所有寄存器只在基址 256 B 内解码。物理 UART 无 RTS/CTS；已测完整波形端到端传输约 88.27 kB/s、约 95.78% 字节线路利用率，534 包双向回显无意外通信错误。这不是纯 CPU 最大吞吐测量，FIFO 也不能保证无限积压不丢字节。

## AMD 参考

- [UG984：MicroBlaze Architecture，2025.2](https://docs.amd.com/r/2025.2-English/ug984-vivado-microblaze-ref/MicroBlaze-Architecture)
- [PG116：MicroBlaze MCS Product Guide](https://docs.amd.com/v/u/en-US/pg116-microblaze-mcs)
- [AMD MicroBlaze MCS 产品说明](https://www.amd.com/en/products/software/adaptive-socs-and-fpgas/mb-mcs.html)

本机使用 2025.2 原生 IP API，并对设置逐项读回；已安装 IP 配置技能面向 2026.1，未把其辅助脚本当作本机已支持的接口。AMD CPU 硬件由官方 IP 提供，本目录自写代码不是 AMD 官方认证设计。

## 验证记录与剩余工作

运行 `python .\软核\scripts\verify_delivery.py` 可重新汇总 `reports/delivery_verification.json`。该检查要求 C 测试、接口实际仿真、IP 回读、整机综合均有成功证据，综合日志不得有 ERROR 或 CRITICAL WARNING，并重新校验原 50 个 RTL 文件没有变化。

已完成离线测试、接口仿真、23 场景异步控制专项仿真、CDC 修复后的整机布局布线，以及真实 CPU/ADC/DAC/FFT/三模式/AWG/包络/ROI/原界面的回归。最新 STA 为 WNS=+10.578 ns、WHS=+0.028 ns，无负裕量路径；布线后 CDC 仅有 5 条 Info，Critical 为 0。其他 LUTAR、RAM 异步控制和性能方法学提示仍保留，未做长期稳定性或外部电源跌落试验。

本次 RTL 修订标记为 `cdc_repair_1`，C 固件与协议 build ID 仍为 `0xA4261028`；用 `reports/cdc_repair/verification.json` 中的镜像 SHA256 区分修复前后。最新证据汇总入口为 `scripts/summarize_cdc_repair.py`。旧版报告与实物数据保存在 `reports/cdc_repair/before/`。

用户明确授权后使用的复现入口（这些操作会临时配置实物，不能当作离线默认动作）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\软核\scripts\run_cpu_ip.ps1 -Script scripts/implement_system.tcl
powershell -NoProfile -ExecutionPolicy Bypass -File .\软核\scripts\run_cpu_ip.ps1 -Script scripts/embed_firmware.tcl
# 保持 SW0 OFF，确认实物准备完成后才能执行下一行：
powershell -NoProfile -ExecutionPolicy Bypass -File .\软核\scripts\run_cpu_ip.ps1 -Script scripts/program_test.tcl
```

原 QSPI 镜像未改写；断电重启后回到原固化镜像。当前测试完成后采集已 STOP，记录/触发/DDS/采集模式恢复原值；未选中的测试 AWG 表仍在易失 RAM，复位/断电后消失。

`build/` 内包括中间调试产物，请以 `scripts/` 的构建流程和最后一次验证记录为入口。最终可继续检查的网表是 `build/scope_cpu_synth.dcp`，不是早期调试留下的工程文件。
