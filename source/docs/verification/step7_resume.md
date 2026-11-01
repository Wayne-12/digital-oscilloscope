# 第七步历史暂停记录（已恢复并完成）

保存日期：2026-10-21。原暂停后的工作已按用户“继续第七步”恢复。**现已完成补充边界测试、最终双种子/原生工程回归及独立综合。** 当前说明见 [第七步说明](step7_trigger_measure.md)，最终验收入口为 `FPGA/reports/measure/20261021_233853_998a2694/acceptance.json`。以下保留暂停时的历史细节，不代表仍有待做事项。

用户最新指示：完成眼前最先完成的一项任务后暂停，保留本次工作记忆，额度重置后继续。不要自动启动后续工作；用户恢复时先读此文。此前用户还要求额度剩余 2% 时停止并保存，此次提前暂停以最新指示为准。

## 已保存的实现

- `FPGA/rtl/common/scope_pkg.sv`：增加 9 种触发枚举、`trigger_config_t`、配置合法性函数、`measurement_result_t`。捕获元数据增加扩展触发配置快照。
- `FPGA/rtl/trigger/trigger_core.sv`：上升沿、下降沿、窗口进入/离开、正/负脉宽、欠幅/过幅、OTR；同步高有效复位，sample_valid 资格检查，时间戳断续清空时间相关资格并记录错误。
- `FPGA/rtl/capture/bram_capture.sv`：增加参数 `USE_EXTENDED_TRIGGER`（默认 0，保持旧边沿接口）和 `cfg_trigger`；扩展模式使用新触发器，配置只在 arm 时锁存，触发配置随冻结元数据保存。
- `FPGA/rtl/measure/measurement_core.sv`：一帧 1～16384 个有符号 13 位样本，最大/最小/均值/峰峰值/RMS、完整周期平均、频率、占空比。输入 start 锁存配置，sample_ready 表示接受样本，measurement_done 表示完成，结果保持至下一次 start 或复位。
- `FPGA/rtl/measure/measure_udiv.sv`：64 拍无符号恢复除法；测量模块 14 拍整数开方，避免组合除法/组合开方。
- `FPGA/sim/tb/tb_measure.sv`：7 个功能阶段分别回归，可用 STAGE=0 一次全部运行；断言、自检、100ms watchdog、终端 PASS。
- `FPGA/sim/tb/measure_capture_scenario.sv`：9 种触发器分别走实际 BRAM 冻结帧和系统域读出，然后送入测量模块；整帧检查原始码、符号码、OTR、时间戳、触发位置和配置快照。
- `FPGA/scripts/generate_measure_vectors.py`：独立 Python 整数黄金模型与可更换固定种子。
- `FPGA/scripts/audit_measure_traces.py`：检查全部 CSV 的用例/逐点完整性与整数黄金结果。
- `FPGA/scripts/run_measure_tb.ps1`、`check_measure_project.tcl`：双种子、分阶段独立测试、全功能重放、原生工程从零编译、源码哈希及轨迹一致性检查。
- 兼容性修改：`capture_scenario.sv` 显式连接零配置；`run_capture_tb.ps1` 的编译/综合暂存源增加 trigger_core。

## 本轮已经采用的数值与触发契约

所有新 HDL 为 SystemVerilog，`1ns/1ps`，`default_nettype none`。寄存器显式同步复位。

- 输入测量范围为完整 signed13 的 [-4096,4095]；AD9226 原始码解码仍是 [-2048,2047]，公式仍为 2047-raw。
- 累加和 signed64，平方和 unsigned64。16384 点全 -4096 的平方和为 274877906944（2^38），实测边界无溢出。均值向最近整数舍入，正负半值远离零。
- RMS = round(sqrt(sum(x*x)/N))，不先舍入均方值；先取整数根，再比较 `4*S >= N*(2*r+1)^2` 确定舍入。
- 周期为 Q16 ADC 时间戳 tick，频率为整数 Hz，占空比为 ppm，均最近舍入。完整 rise→fall→rise 才贡献一个周期，跨多个完整周期累计时间后计算；使用 ADC 时间戳而不是系统读出间隔。时间戳允许模 2^64 回绕。
- `result.stats_valid=1` 说明基本统计量已完成。没有完整周期（包括常量、幅度不足、仅半周期）时 `measurement_valid=0`、period_valid/duty_valid=0，period/frequency/duty 均为 0；直流基本统计和 RMS 仍有效。时间戳跳号使周期无效并置 measurement_error，基本统计仍可用。
- 边沿：先到 threshold-hysteresis 以下（含等号）使上升沿待触发，再严格超过 threshold+hysteresis；下降沿对称。沿用第六步零迟滞严格跨越语义。
- 窗口进入：先在扩展外界之外/边界上（x<=low-h 或 x>=high+h），然后严格进入收缩内区（low+h<x<high-h）。窗口离开：先在收缩内区/边界内，然后严格越过扩展外界。必须 low+h<high-h。
- 正/负脉宽：先建立相反电平，再检测完整的两个迟滞跨越边沿，时间戳差落入 inclusive [width_min,width_max] 时在结束沿动作；前导未完成脉冲不触发，width_min 必须非零。
- 欠幅/过幅：非重叠的 observation_samples 个有效样本块（2～16384），仅块结束时按 P2P 严格小于/大于 amplitude_limit 触发；等于不动作。不会将正弦过零当作欠幅。
- OTR：每段连续 OTR=1 仅首个有效样本触发；复位/禁用后首次高 OTR 可触发。sample_valid=0 时保持状态。
- 配置在 trigger_core 单独使用时须在 enable=1 期间保持稳定；bram_capture 自动锁存。任意时间戳跳号抑制当拍触发并清空资格。

## 已通过的结果（可直接查阅，不必重新推断）

正式第七步报告：`FPGA/reports/measure/20261021_220956_1f29ca59/manifest.json`。

- Vivado Simulator 2025.2；种子 20261020、42。
- 每种子 85 个触发用例、34412 个触发逐拍比较、79 个测量帧。
- 每种子 9 种类型各一帧真实 BRAM→测量链路：9×16384=147456 点；双种子共 294912 点。
- 7 个功能按顺序分别运行，每阶段都有 FEATURE_PASS 和 TEST_PASS。
- Python 轨迹审计每种子 625468 个字段检查通过。
- 首种子 STAGE=0 重放全部功能，9 个 CSV SHA256 完全一致。
- 删除工程 `scope_smoke.sim` 后原生 Behavioral Simulation 从零重编译通过，9 个 CSV 与非工程运行逐字节一致；xvlog/elaborate/simulate 日志零 HDL warning/error。
- 原生工程保持 xc7a35tcsg324-1、board 为空、XSim、约束 0、Design top scope_hw_top；Simulation top 现为 tb_measure。Design Sources 与 TB 隔离已由原生审计检查。
- 测试覆盖常量/正负满量程、全零、全正负、随机、极限累加、均值/RMS舍入边界，恰好一周期/部分周期/多周期、非整数平均周期、10/50/90%占空比、4档采样率、噪声、削顶、迟滞等号、幅度不足、时间戳回绕/跳号、valid 空拍、非法配置和复位中止。

第六步兼容性回归：`FPGA/reports/capture/20261021_221034_825dd339/manifest.json`：两个种子和首种子重放全部 PASS（每种子 71 帧，含单次保持等既有测试），未重跑其原生工程和综合。

参数包回归：`FPGA/reports/scope_pkg/20261021_221045_f7f826fb/manifest.json`：两个种子各 9192 transactions、46029 checks PASS。

早期开发试验位于 `%TEMP%/measure_step7_dev`，仅作诊断，以正式报告为准。`FPGA/reports/measure/20261021_220947_40be07ba/` 是误用 Windows PowerShell 5 启动导致 Get-FileHash 管道不兼容的空目录，不是功能结果；当前正式脚本在工具默认 PowerShell 7 执行已通过。

## 恢复后的剩余工作

1. 先读最新用户指示；确认仍继续第七步。不要自动开始第八步。
2. 复核新 RTL/黄金模型/测量有效性契约，特别是资源可综合性和无关周期无有效频率；当前只有行为验证，不应宣称已完成实现或时序收敛。
3. 可补一轮新模块的 OOC 综合验证（measurement_core、trigger_core，以及 extended bram_capture），检查综合警告/锁存器和资源；未运行。使用 ASCII TEMP 暂存树、工作目录和日志，避免本机中文路径综合进程异常退出。暂不加最终引脚或整板 XDC。
4. 审阅覆盖是否要补：最大 16384 点幅度观察窗口、脉宽计数极端边界、各复位/中断位置；目前脉宽窗口主要 3～7 tick、幅度块主要 16 点。协议测试的 reset_aborts=5 不是所有内部最终处理状态的完整覆盖，不夸大。
5. 清理复制脚本里的遗留 CAPTURE 文字和未使用 synthesis 变量；只影响可读性，先前正式结果有效。若修改文件，按变更范围重跑对应回归。Windows PowerShell 5 不兼容可明确规定需要 PowerShell 7 或另修兼容性，当前默认环境是 7。
6. 完成面向使用者的 `step7_trigger_measure.md`、参数包文档更新和最终验收 JSON/完整可复现源包。当前续做记录和暂停快照不等于最终验收。
7. 工作区根目录因一次在错误 cwd 调用 xvlog，留下 xsim.dir、xvlog.log、xvlog.pb；检查后移动到开发诊断报告目录（递归移动前验证绝对路径边界和 reparse point）。根 .Xil/dfx_runtime.txt 也有 Vivado 启动产物，先确认归属再归档。不要删除用户资料或既有报告。

## 续做环境与命令

- 根目录 `D:/示波器`，默认 PowerShell 7，Python `D:/Python/python3.14/python3.14.7/python.exe`。
- Vivado bin `D:/AMD/Xilinx/vivado_2025.2/2025.2/Vivado/bin`；已有本地工具链配置，勿退回 2024.2。
- `& ./FPGA/scripts/run_measure_tb.ps1 -Seeds @(20261020,42) -Project`：正式回归，Project 会安全删除唯一指定 .sim 并原生重编译。
- `& ./FPGA/scripts/run_capture_tb.ps1 -Seeds @(20261020,42)`；`& ./FPGA/scripts/run_scope_pkg_tb.ps1 -Seeds @(20261020,42)`：依赖回归，已通过，不改相关源则不必重复。
- 原生 Vivado 需沙盒外访问本机 AppData TclStore，沿用 require_escalated 工具调用。没有 Vivado MCP，用本机 CLI；使用技能 `C:/Users/lenovo/.codex/skills/vivado-simulate-rtl/SKILL.md`，可用 2025.2，交互逐步修复模式未启用。
- `$fatal` 可能 exit0，因此脚本同时要求终端 PASS、所有用例完整性、无意外 warning/error 和轨迹审计。BAT 的 `--testplusarg` 中保留字面双引号。
- 原生工程绝对路径输入正常；CSV 输出使用 TRACE_DIR=.，随后 Tcl 复制到归档目录，避免本机 `$fopen` 绝对路径问题。
- Python 文本读写显式 encoding='utf-8'，manifest 读取 utf-8-sig，避免默认 GBK。

暂停时未留后台仿真；所有已启动回归均已自然结束。后续从此记录和对应报告恢复，不需重做第一至六步。
