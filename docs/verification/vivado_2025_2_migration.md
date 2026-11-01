# Vivado 2025.2 工程迁移记录

迁移日期：2026-10-21。迁移完成；当时第二步保持搁置，迁移本身仅升级工程、IP 与运行工具并运行已有测试检查兼容性。用户随后恢复第二步，完成结果另见 [第二步验收记录](step2_clock_reset_safety.md)，以下保留迁移时的历史数据。

## 当前入口

- 工程仍在 `D:\示波器\FPGA\project\scope_smoke\scope_smoke.xpr`，已由 Vivado 2025.2 保存并重新打开检查。工程 XML Minor 从 68 更新为 71。
- 实际工具目录：`D:\AMD\Xilinx\vivado_2025.2\2025.2\Vivado\bin`；Vivado SW Build 6299465，XSim v2025.2。
- `FPGA/scripts/vivado_toolchain.json` 统一配置默认版本和目录；公共包、安全逻辑、冒烟及工程检查脚本均默认使用这里的工具，不再依赖 PATH 中可能存在的旧版本。仍可显式传入 `-VivadoBin`。
- Windows 的 `.xpr` 文件关联可能仍指向旧版。可运行下面的入口明确使用 2025.2 打开工程：

```powershell
& 'D:\示波器\FPGA\scripts\open_scope_project.ps1'
```

没有向 Vivado 安装目录移动项目源码，也没有修改安装文件或系统 PATH。

## 工程及 IP

| 项目 | 迁移后的设置 |
|---|---|
| 工程数量 | 1 个：scope_smoke |
| 类型 / 器件 | RTL Project / 临时 `xc7a35tcsg324-1` |
| 开发板预设 / 工程约束文件 | 无 / 0 个 |
| 仿真器 | Vivado Simulator（XSim） |
| 当前设计 / 仿真顶层 | `scope_hw_top` / `tb_safe`，与暂停前相同 |
| Design Sources | `FPGA/rtl` 及 IP 生成的两个 Verilog 文件 |
| Simulation Sources | `FPGA/sim/models`、`FPGA/sim/tb`；关闭综合和实现用途 |
| Clocking Wizard | 6.0 Rev.15 → 6.0 Rev.17，XCI 工具版本更新为 2025.2 |
| 时钟配置 | 输入 100 MHz，输出 25 MHz，高有效复位，提供 locked |

已有 XCI 先复制到独立 ASCII TEMP 目录，通过原生 `upgrade_ip` 升级并重新生成输出，再复制回 `FPGA/ip/scope_clk_wiz`。升级前后 IP 状态报告均已归档，升级后为 `Up-to-date / No changes required`。原 XCI 中所有标记为用户设置的参数逐项比较，变化数为 0。

工程延续原有导入方式：直接使用生成的两个 HDL 文件，XCI 留在 IP 目录用于重建。IP 自带的约束产品也保留，但没有加入完整 EGO1 XDC 或最终管脚约束。

16 个手写 RTL、模型及 testbench 的 SHA256 与迁移前完全一致。

## 2025.2 验证结果

| 检查 | 结果 | 报告目录，均相对 `FPGA/reports/` |
|---|---|---|
| 公共包，种子 20261020、42 | PASS；每种子 9192 笔事务、46029 次检查 | `scope_pkg/20261021_003957_c63dd278` |
| 冒烟测试，首次运行 | PASS；450 拍 scoreboard 检查 | `smoke/20261021_004134_e0653b09/initial` |
| 实际删除 `.sim` 后完整重编译 | PASS；结果与首次完全一致 | `smoke/20261021_004134_e0653b09/clean_rebuild` |
| 已有核心测试，两个种子、四种采样时钟 | PASS；每种时钟 10/10 状态，断言零失败 | `safe/20261021_003958_8e9f1fdb` |
| 工程模式核心测试 | PASS | `safe_project/20261021_004243_c5bd2bd7/core` |
| 新 IP 与 UNISIM 包装层测试 | PASS；3 个 ODDR、17 个 OBUFT、两次启动、1117 次时钟连接检查 | `safe_project/20261021_004243_c5bd2bd7/wrapper` |
| 源文件归属、综合编译顺序、临时器件 | PASS；综合不依赖 testbench | 同一工程报告的 `project_audit.txt` |

上述 HDL 编译、展开及仿真日志没有 WARNING、ERROR 或 Fatal。所有测试均要求实际终止 PASS 标记，没有仅凭 Vivado 的退出码判定。

工程启动日志仍保留安装自带板卡库的提示：部分其他系列的板卡预设对应器件未安装（`Board 49-26`），以及空 BoardPart 的提示（`Project 1-5713`）。本项目没有使用这些预设，临时 Artix-7 器件已由 `get_parts` 确认可用。导出工程 Tcl 还记录无 BD 和源码位置提示；IP 在 TEMP 暂存时记录路径变更提示。没有屏蔽或降低这些提示的级别。2024.2 历史记录中的 GCC 提示没有在本次检查中出现。

## 备份和追溯

迁移总目录：`FPGA/reports/migration/20261021_003759_89b4bc35/`。

- `before_vivado_2024_2.zip`：升级前工程（含当时的仿真生成文件）、IP、RTL、仿真源、脚本、文档和两份规划书，共 141 个文件；逐文件校验备份内数据与备份前 SHA256 一致。
- `before_sha256.json`：迁移前文件哈希。
- `manifest.json`：迁移结果、备份哈希、源码一致性和四组回归入口。
- `ip_user_setting_changes.json`：空数组，用户参数没有变化。
- `project_migration_retry.log`、`project_settings.tcl`、`recreate_project.tcl`：原生迁移日志、revision-control skill 捕获的配置和 Vivado 导出的重建脚本。该重建脚本是配置快照，本次没有额外执行整工程重建；从零重编译验收针对仿真生成目录。

2024.2 的历史报告保留在原位置。第一次沙箱内打开工程因无法初始化 AppData 的 Tcl 组件失败，其日志也保留；获准在沙箱外重试后成功。未修改 RTL 来绕过工具问题。

迁移使用 `vivado-revision-control` 的设置捕获流程，以及已验证支持 2025.2 的 `vivado-simulate-rtl` 验证约定。当前无 Vivado MCP 连接，执行通过本机原生 CLI/Tcl 完成。IP 升级命令已对照 [AMD UG835 2025.2：upgrade_ip](https://docs.amd.com/r/2025.2-English/ug835-vivado-tcl-commands/upgrade_ip) 核对。

## 后续复跑

```powershell
& 'D:\示波器\FPGA\scripts\run_scope_pkg_tb.ps1' -Seeds 20261020,42
& 'D:\示波器\FPGA\scripts\run_smoke.ps1'
& 'D:\示波器\FPGA\scripts\run_safe_tb.ps1' -Seeds 20261020,42
& 'D:\示波器\FPGA\scripts\check_safe_project.ps1'
```

`run_smoke.ps1` 会选择第一步的 `smoke_counter / tb_smoke` 顶层；最后运行已有工程检查脚本会恢复当前的 `scope_hw_top / tb_safe` 顶层。只有需要重新生成 IP 时才追加 `-RegenerateClockIp`。
