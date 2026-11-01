# 第一步：Vivado RTL 工程与最小冒烟测试

2026-10-21：工程及默认运行工具已迁移到 Vivado 2025.2，见 [迁移记录](vivado_2025_2_migration.md)。下文的 2024.2 验收数据保留为历史记录。运行本页脚本会选用第一步的 `smoke_counter / tb_smoke` 顶层；迁移结束时工程保留暂停第二步前的 `scope_hw_top / tb_safe` 顶层。

## 工程配置

- 工程：`FPGA/project/scope_smoke/scope_smoke.xpr`。
- 类型：RTL Project；临时器件 `xc7a35tcsg324-1`，实际器件仍待实物/JTAG 确认。
- 未选择开发板预设，没有添加 EGO1 XDC 或最终管脚约束。
- `FPGA/rtl/` 中的 HDL 加入 Design Sources；设计顶层是临时计数器 `smoke_counter`。
- `FPGA/sim/models/`、`FPGA/sim/tb/` 中的 HDL 仅加入 Simulation Sources，并关闭其综合及实现用途。
- 仿真器：Vivado Simulator（XSim），仿真顶层 `tb_smoke`。

`create_smoke_project.tcl` 可在 Vivado Tcl Console 中 source，从源代码创建工程；工程存在时打开并同步源文件。脚本检查器件、开发板属性、RTL 模式、源文件归属和综合编译顺序，发现越界配置会报错，避免静默覆盖用户设置。

## RTL 与自检约定

`FPGA/rtl/top/smoke_counter.sv` 使用上升沿计数、高有效同步复位。默认 8 位无符号计数器，显式按固定位宽加一并自然回卷，无舍入/饱和，无寄存器声明初值，也没有 `initial` 代替复位。

`FPGA/sim/tb/tb_smoke.sv` 提供 10 ns 周期的 100 MHz 时钟；所有 SV 时间单位/精度为 `1ns/1ps`。独立 32 位整数 scoreboard 使用模 256 算术逐拍比较 DUT，在 NBA 更新后 1 ps 检查实际结果。

测试包含启动复位、300 拍连续计数和回卷、运行中同步复位、上升沿之间的短复位脉冲，以及固定种子的随机复位。`assert` 检查时钟周期、未知状态、同步复位行为、计数结果和必要测试是否执行。默认随机种子 20261020、128 拍随机测试，支持 `SEED` 和 `RANDOM_CYCLES` plusargs。

全部通过时输出 `TEST_PASS tb_smoke ...` 并 `$finish`；失败执行 `$fatal` 输出 `TEST_FAIL`。另有 50 us 看门狗；Vivado 仿真运行上限为 60 us。

## 运行和从零重建验收

```powershell
& 'D:\示波器\FPGA\scripts\run_smoke.ps1'
```

可使用 `-Seed 42 -RandomCycles 256` 更换随机入口。

脚本先创建/打开真实 Vivado 工程并运行 Behavioral Simulation，归档日志后关闭仿真和工程；验证绝对路径及重解析点后，仅删除生成目录 `FPGA/project/scope_smoke/scope_smoke.sim`，保留工程、源代码与已归档日志；再次启动 Vivado，重新编译、展开、仿真，要求两个阶段均 PASS、编译日志表明源文件重新分析、固定种子的结果完全一致。

每次运行的日志和源文件 SHA256 保存在 `FPGA/reports/smoke/<运行编号>/`，包括 `initial/`、`clean_rebuild/`、`clean_rebuild.txt` 和总 `manifest.json`。编译、展开和运行日志中的任何 WARNING/ERROR/Fatal 均使回归失败。

本阶段只验证工程组织与行为仿真，尚未综合、实现、生成 bitstream 或连接/配置板卡。

## 2024.2 历史验收结果

工具为本机 Vivado/XSim 2024.2。最终报告目录：`FPGA/reports/smoke/20261020_195801_91eaf7d2/`。

| 检查 | 结果 |
|---|---|
| RTL 模式、临时器件、无开发板预设 | PASS |
| Design Sources 仅含 rtl，sim/models 与 sim/tb 仅用于仿真 | PASS |
| 综合编译顺序不依赖模型或 testbench | PASS，仅 smoke_counter.sv |
| XDC/最终管脚约束 | 0 个 |
| 仿真器及顶层 | XSim / tb_smoke |
| 首次运行 | PASS |
| 实际删除 scope_smoke.sim 后重新分析、展开、运行 | PASS |
| 清理前后固定种子结果一致 | PASS |
| HDL 编译、展开及仿真日志中的错误/警告 | 0 |

两个阶段均输出：

```text
TEST_PASS tb_smoke seed=20261020 checked_edges=450 reset_edges=16 wraps=1 random_signature=71b85387
```

仿真实际在 4495.002 ns 调用 `$finish`，未触发看门狗。450 个上升沿均由 scoreboard 检查，其中 16 拍复位、至少一次计数回卷；随机签名一致。清理后的 `xvlog.log` 明确记录重新分析 scope_pkg、smoke_counter 和 tb_smoke，`elaborate.log` 记录重新生成快照，`clean_rebuild.txt` 记录了实际删除的绝对路径。

Vivado 启动层还报告环境提示 `[Vivado 12-13340] Unable to auto find GCC executables from simulator install path`。该提示保留在原始日志中，没有屏蔽；本次纯 SystemVerilog 测试没有 SystemC/DPI/C++ 依赖，Behavioral Simulation 已完成上述两次验收。此提示未计入 HDL 编译警告，也未通过指定未经验证的 GCC 来消除。GCC 配置入口见 [AMD UG900 2024.2：GCC 路径设置](https://docs.amd.com/r/2024.2-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87/ug900-vivado-logic-simulation/GCC-%E8%B7%AF%E5%BE%84%E8%AE%BE%E7%BD%AE)。
