# 当前显示工程的共享后端

当前版本：FPGA 0xAF311031，CPU trigger_cycle_20261101，PC 2026.11.01-r6。

本目录仅保留当前显示工程调用的固件公共代码、RTL 后端、IP 配置和工具。C 主循环与显示顶层位于 ../display。旧独立cpu整机入口、透明桥接旧顶层和旧构建镜像已移除。

## 依赖与入口

- firmware：scope_cpu.c/.h、memory.c、start.S、link.ld。
- rtl/scope_core.sv：当前使用的同步控制与安全序列。
- integration：当前显示工程所需的功能后端、时钟与约束。
- build/cpu_ip/scope_microblaze/scope_microblaze.xci 和 build/fft_ip/scope_fft_1024/scope_fft_1024.xci：当前 IP 配置，生成物由 Vivado 重建。
- scripts/create_cpu_ip.tcl、ensure_scope_fft_ip.tcl、run_cpu_ip.ps1：IP 创建与运行入口。
- scripts/hardware_client.py：当前 PC 专项验收调用的串口客户端。
- scripts/test_host.ps1、test_cdc_safety.tcl 和 tests：共享 C 核与 CDC 专项测试。

需要重新生成 CPU IP 时，在工程根目录执行 `powershell -ExecutionPolicy Bypass -File ./cpu/scripts/run_cpu_ip.ps1`。字体、页面、固件与整机重建顺序见 ../display/README.md。不要再运行已移除的 prepare_integration.py：共享后端以当前保留版本为准，不从旧 FPGA 工程覆盖生成。

本次清理不重新综合、不下载硬件，也不新增实测结论；当前 ELF、位流与 Flash 镜像保持原始字节，验证依据保留其原版本范围。
