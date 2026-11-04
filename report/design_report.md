# 数字示波器设计报告

## 方案与数据路径

EGO1 FPGA 接收 AD9226 的 25 MSPS 数据，RTL 完成触发、冻结记录、测量、FFT 与包络等功能；DDS / AWG 驱动 AD9767 A 通道。MicroBlaze MCS 运行 C 固件，通过邮箱与功能核交互，负责本地菜单调度及电脑 / 本地控制权切换。CPU 不承担逐点采样处理。

显示链路使用 1024×600 画面、49 MHz 像素时钟，支持波形、触发、信号源、光标、频谱及回环自检页面。PC 使用 Python / PySide6 / pyqtgraph，通过 UART 921600 8N1 控制板卡并显示、分析和导出数据。

## 代码分工

| 内容 | 入口 |
|---|---|
| 采集、触发、测量、DDS / AWG、FFT | `source/cpu/integration/rtl/` |
| CPU 启动、链接、协议及 MMIO | `source/cpu/firmware/`、`source/cpu/rtl/` |
| 当前 C 主循环与菜单 | `source/display/panel_main.c`、`panel_model.c` |
| 当前显示顶层 | `source/display/scope_cpu_vga_top.sv`、`panel_screen.sv` |
| PC 主界面与协议 | `source/scope_ui.py`、`source/pc/protocol/` |
| 最终烧录镜像及绑定记录 | `source/display/release/` |

## 最新版本与验证依据

2026-11-01：硬件 `0xAF311031`、CPU `trigger_cycle_20261101`、PC `2026.11.01-r6`。最新版包含绘图期间串口服务及 SW7 双向控制权交接修复，电脑界面保留手动选择和下载 AWG CSV 的流程。

既有验证记录：

- [控制权切换修复与固化](source/display/控制权切换修复与固化_20261101.md)：最新修复、Flash 读回和断电启动记录。
- [通信修复验证](source/display/通信修复验证_20261101.md)：通信验证范围。
- [最终验证](source/display/最终验证.md)：C、RTL、布局布线及固化证据；其中 10 月 31 日数据属于复用的父版本硬件构建。
- `source/display/output/`：清单保留的原测试日志与时序、CDC 等报告。

原最终验证报告记录 WNS +0.581 ns、WHS +0.028 ns，LUT 15199/20800、BRAM 45/50、DSP 49/90；此处引用既有报告，不代表本次重新综合得到的新结果。

## 复现与本次整理范围

根目录 `run.ps1` 提供校验、PC 界面、固件、仿真、构建入口，详见 [运行配置](serve/README.md)。保留原 IP 生成、RTL、固件、字模、约束与构建脚本；移至 source 后内部相对路径保持一致。工具链路径需按新机器配置。

本次只调整目录与交付说明，新增统一入口及上传完整性核对。校验冻结清单中的 136 项文件和上传清单；未重新进行综合、仿真、Flash 编程或实物测试。历史实物记录的范围与限制以原报告为准。

冻结包校验通过后才使用其镜像；修改源码并重建后应重新生成对应发布清单。批量仿真 expected/vectors 可由生成脚本重建，不作为本次源码交付的一部分。

## 2026-11-04 当前版收敛

已同步本地 trigger_cycle_20261101 固化版，当前 Flash 编程、独立读回和断电启动依据见 source/display/release/flash_record.json 与触发循环选择说明。本次不是新的硬件验收。

清理旧工程与未使用顶层后，source_snapshot.json 只保留当前构建使用的 72 项输入；保留项与原快照 SHA256 一致。ELF、BIT、BIN、MCS 保持原始字节。最终交付清单仅调整依赖范围和绑定元数据，并记录原清单哈希。C 测试与协议/报告 27 项软件测试本次重新通过；未重新执行 RTL 仿真、综合、实现或上板测试。
