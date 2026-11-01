# 第七步：扩展触发与整数测量

本步完成 9 种触发、帧统计/RMS/周期测量，以及实际 BRAM 读出到测量的数字链路验证。使用 Vivado/XSim 2025.2，暂定器件仍为 `xc7a35tcsg324-1`。未添加开发板预设或最终管脚约束。

## 文件与接入方式

| 文件 | 用途 |
| --- | --- |
| `FPGA/rtl/common/scope_pkg.sv` | `trigger_type_t`、`trigger_config_t`、`measurement_result_t` 和配置检查 |
| `FPGA/rtl/trigger/trigger_core.sv` | 可配置触发器，同拍输出符合条件的 `trigger_hit` |
| `FPGA/rtl/capture/bram_capture.sv` | 锁存触发配置，冻结真实 BRAM 帧及元数据 |
| `FPGA/rtl/measure/measurement_core.sv` | 一帧整数测量 |
| `FPGA/rtl/measure/measure_udiv.sv` | 64 拍无符号除法器，仅供测量内部使用 |
| `FPGA/sim/tb/tb_measure.sv` | 分阶段自检、协议断言、复位覆盖 |
| `FPGA/sim/tb/measure_capture_scenario.sv` | 9 种触发各自通过 BRAM、跨域读出、测量的整帧 scoreboard |
| `FPGA/scripts/generate_measure_vectors.py` | Python 任意精度整数黄金模型、刺激及预期结果 |
| `FPGA/scripts/audit_measure_traces.py` | 轨迹完整性、字段和独立整数结果审计 |

RTL 和 testbench 均为 SystemVerilog，时间单位/精度为 `1ns/1ps`，使用 `default_nettype none`。新功能寄存器均采用时钟上升沿同步、高有效复位。BRAM 沿用第六步不复位存储阵列、仅在完整帧冻结后允许读出的方式。RTL 不生成内部时钟。

`trigger_core` 使用采样时钟；`measurement_core` 使用调用者提供的处理时钟。验证中后者为 100 MHz 系统时钟，输入为 BRAM 系统域读出。有符号码、OTR 和 ADC 时间戳沿用原先的数据约定；测量不修改保存的原始码。

## 触发条件

`trigger_config_t` 包含 kind、signed13 threshold、unsigned13 hysteresis、signed13 window_low/window_high、unsigned32 width_min/width_max、unsigned14 amplitude_limit、unsigned15 observation_samples。

以下令 `L=threshold-hysteresis`、`H=threshold+hysteresis`。加减和比较均显式扩展到 signed15，避免阈值相加溢出。

| kind 枚举/编号 | 动作条件 |
| --- | --- |
| `TRIG_RISE` / 0 | 先有 x<=L，随后 x>H 时触发一次 |
| `TRIG_FALL` / 1 | 先有 x>=H，随后 x<L 时触发一次 |
| `TRIG_WINDOW_ENTER` / 2 | 先有 x<=window_low-h 或 x>=window_high+h，再严格进入 window_low+h<x<window_high-h |
| `TRIG_WINDOW_LEAVE` / 3 | 先位于含边界的收缩窗口，再严格越过扩展窗口外界 |
| `TRIG_POS_WIDTH` / 4 | 已知低电平后，完整迟滞上升沿→下降沿的时间戳差在 [width_min,width_max] 内；结束沿触发 |
| `TRIG_NEG_WIDTH` / 5 | 已知高电平后，完整迟滞下降沿→上升沿的时间戳差在同一闭区间内；结束沿触发 |
| `TRIG_UNDER_AMPLITUDE` / 6 | 非重叠观察块末点，块内峰峰值严格小于 amplitude_limit |
| `TRIG_OVER_AMPLITUDE` / 7 | 非重叠观察块末点，块内峰峰值严格大于 amplitude_limit |
| `TRIG_OTR` / 8 | 连续有效样本中 OTR 从低到高时；复位/禁用后首次高 OTR 也触发，连续高仅一次 |

脉宽的内部时间戳差为 unsigned64，单位为 ADC 采样 tick，比较前把 32 位上下限零扩展到 64 位。帧开头只有后半段的脉冲不触发。零迟滞仍保留严格跨越，阈值上不动的平线不会重复触发。

欠幅/过幅按一个完整观察块的 P2P 判断，避免把正弦的瞬时过零当成欠幅。观察块长度为 2～16384 个被接受的有效样本；每个块独立重建最大/最小值。在块长达标前不触发，等于幅度限值时两种触发都不动作。

配置检查拒绝未知枚举编号、窗口内区为空或反向、零最小脉宽/最大值小于最小值，以及非法观察块长度。独立模块在 enable 期间要求配置稳定。sample_valid=0 时保持历史；禁用/复位清空资格；有效样本时间戳必须连续（允许 unsigned64 自然回绕）。跳号当拍不触发，并清空时间相关资格，timestamp_error 保持至复位或禁用。

要接入捕获实例，设 `bram_capture #(.USE_EXTENDED_TRIGGER(1'b1))` 并连接 `cfg_trigger`。配置只在合法 arm 时锁存，输入随后变化不影响本次捕获。冻结元数据的 `extended_trigger=1`，实际条件保存在 `trigger_config`。原有 cfg_rising/cfg_threshold/cfg_hysteresis 及同名元数据是旧接口的兼容字段，扩展模式应读取 `trigger_config`。默认参数 0 仍使用第六步边沿模块，旧调用须显式把 cfg_trigger 接零配置。

触发指向符合条件的当前样本：脉宽为结束沿样本，幅度为观察块末样本，OTR 为首个高样本。预触发历史、AUTO 优先级、单次保持和帧冻结握手沿用第六步。

## 测量接口和有效标志

1. 在 busy=0 时提供 start、18 位 frame_length（1～16384）、非零采样率、阈值与迟滞。start 当拍不收样本。
2. 当 sample_ready=1 时，每个 `sample_valid && sample_ready` 接受一笔 signed13 样本及对应 ADC 时间戳。允许输入空拍；时间戳以有效样本的 ADC 时间为准，不能用系统读出时刻替代。busy 时的 start 脉冲被忽略。
3. 接收设定数量后，sample_ready 清零，模块完成串行除法和整数开方，最多再用 350 个处理时钟。调用者等待 measurement_done，一拍完成脉冲到来时 busy=0。
4. 所有结果保持至下一次 start 或复位。读取者在完成后锁存整份结果；处理中 stats_valid=0，不读取中间更新字段。

| 标志 | 含义 |
| --- | --- |
| `measurement_done` | 处理完成或配置被拒绝的一拍通知 |
| `result.stats_valid` | 样本计数、最大/最小、均值、P2P、RMS、和/平方和完整有效 |
| `measurement_valid`、`result.period_valid` | 至少有一个完整、迟滞合格且时间戳连续的 rise→fall→rise 周期 |
| `result.duty_valid` | 与上述完整周期对应的占空比有效 |
| `measurement_error` | 非法配置或帧内 ADC 时间戳不连续 |

无完整周期时 `measurement_valid=0`、period_valid/duty_valid=0、period_count/period_q16/frequency_hz/duty_ppm 全为 0；不会保留上一帧频率。常量、全零、全正/全负且不跨阈值、只有半周期或幅度不足，仍可返回有效基本统计和 RMS。时间戳跳号时基本统计仍可用，但整个帧的周期结果无效并置错。

周期有效的定义是完整的合格交越序列；不额外假设信号理想周期性。频率和占空比对所有完整周期累计后计算，首尾未闭合的部分不进入周期平均。

## 位宽、单位与整数黄金模型

测量覆盖完整 signed13 范围 [-4096,4095]。实际 AD9226 解码仍为 `2047-raw_code`，范围 [-2048,2047]；二者没有混用。

| 量 | 位宽/范围与计算 |
| --- | --- |
| N、完整周期数 | unsigned18；N<=16384 |
| 最大、最小、均值 | signed13 |
| 峰峰值 | unsigned14；max-min，最大 8191，无符号回绕被禁止 |
| 累加和 S | signed64，覆盖 16K signed13 输入 |
| 平方和 Q | unsigned64，覆盖 16K signed13 输入并保留余量 |
| RMS | unsigned14；最大 4096 |
| 周期 | unsigned64 Q16 ADC tick |
| 频率 | unsigned32，整数 Hz，sample_rate_hz 为 ADC 时间戳 tick 速率 |
| 占空比 | unsigned32，ppm，0～1000000 |

均值 `round(S/N)` 使用最近整数，半值远离零。RMS 精确计算最近整数 `sqrt(Q/N)`：先求 `r=floor(sqrt(floor(Q/N)))`，然后仅在 `4*Q >= N*(2*r+1)^2` 时加一，避免预先舍入均方值带来的二次舍入误差。

设完整周期数 C、完整周期总 tick 数 T、这些周期内的高电平 tick 总数 U，则：

```text
period_q16 = round(T * 65536 / C)
frequency_hz = round(sample_rate_hz * C / T)
duty_ppm = round(U * 1000000 / T)
```

三个非负除法均最近舍入，半值向上。与同一离散交越定义的 Python 任意精度整数黄金模型比较时，允许误差为 0 LSB。输出量化误差不超过 0.5 Hz、0.5 ppm、0.5/65536 tick；这些量化界限不包含实际采样交越位置的时间量化和噪声误差。

64 拍恢复除法和 14 拍根搜索均在处理时钟下工作，没有组合除法或浮点运算。临时平方、边界乘法、和频率分子均留在显式定义的宽数据路径内。

## 自动测试和复现

需要 PowerShell 7、Python 3 和本地 Vivado 2025.2。目录由 `FPGA/scripts/vivado_toolchain.json` 选择；脚本不修改系统 PATH。可重复运行：

```powershell
Set-Location 'D:\示波器'
& ./FPGA/scripts/run_measure_tb.ps1 -Seeds @(20261020,42) -Project
& ./FPGA/scripts/run_measure_synthesis.ps1
```

行为脚本按截图的 1～7 顺序分别启动独立功能阶段；固定种子可替换，默认 20261020、42。再以 STAGE=0 重放首种子，比较 9 个 CSV 的 SHA256。-Project 安全检查唯一指定的工程 .sim 目录及重解析点后删除生成目录，使用原生 `launch_simulation` 从零重编译，再比较同样 9 个轨迹。

每个阶段有立即 assert、scoreboard、终端 FEATURE_PASS/TEST_PASS 和 100ms 看门狗。脚本检查正常结束、用例/轨迹完整性、无意外错误与 HDL 警告，不能仅凭退出码或波形判定。Python 审计逐项核对触发刺激及预期动作、测量结果和 BRAM 整帧字段，保留原始码、有符号码、OTR 和时间戳。

覆盖常量/全零/全正负、极限长帧累加、随机样本、均值/RMS舍入边界，10/50/90%占空比，恰好一周期/部分周期/多个与非整数平均周期，4 档采样率、噪声、削顶、幅度不足、阈值/迟滞等号、时间戳回绕/跳号、有效空拍、最大周期数。触发另覆盖 2/16384 点观察块、幅度限值等号和极值、65535/65536/65537 tick 脉宽、32 位上限配置、复位/禁用/短暂信号。

协议检查包括 3 种非法测量配置、13 个测量状态/除法操作复位点、忙时 start 忽略、分母非零、无陈旧除法完成脉冲、4 种非法扩展 arm，以及启动后配置输入变化不影响冻结配置。

## 验收结果

最终结果和源码快照入口见 `FPGA/reports/measure/20261021_233853_998a2694/acceptance.json`。

- 两个种子各 125 个触发用例、723760 次逐拍触发比较、85 个独立测量帧。
- 两个种子各 9 个真实 BRAM→测量帧，合计 294912 点逐点一致；触发索引、时间戳、原始码、有符号码和 OTR 均正确。
- 所有 7 个功能阶段、首种子重放和原生工程从零编译仿真通过，9 个 CSV 完全一致；编译、展开、运行日志没有重复定义、隐式网络、符号位或其他 HDL 警告/错误。
- 相对整数黄金模型，所有测量字段零误差；每种子轨迹审计 7104980 个字段通过。无有效周期时所有周期有效标志为 0，频率等字段为 0。
- 第六步兼容性回归报告 `FPGA/reports/capture/20261021_221034_825dd339/` 和参数包回归 `FPGA/reports/scope_pkg/20261021_221045_f7f826fb/` 均通过；本轮新改动仅补验证与脚本，已通过的功能 RTL 未再变化。

独立综合报告：`FPGA/reports/measure_synthesis/20261021_233647_0e2fc5f7/`。

| 独立综合顶层 | LUT 原语 | FF | DSP | RAMB36 / RAMB18 | 锁存器 |
| --- | ---: | ---: | ---: | ---: | ---: |
| measurement_core | 2341 | 1424 | 13 | 0 / 0 | 0 |
| trigger_core | 700 | 176 | 0 | 0 / 0 | 0 |
| bram_capture，扩展触发开启 | 1191 | 1493 | 0 | 6 / 1 | 0 |

BRAM 的 12 位原始码和 1 位 OTR 为动态列，3 个固定零保留位被优化，仍是第六步 16384×16 的逻辑存储格式，未退化为 LUT RAM。综合保留一条 `Netlist 29-101`：扁平 trigger_core 对后续层次布局不理想。原始消息和数量保存在 manifest，未压低消息级别；其余综合警告/错误仍使脚本失败。该条建议不属于 HDL 编码或算术位宽诊断。

这是行为仿真和独立可综合性验收。硬件顶层尚未把所有功能组成完整示波器，未进行整机布局布线、板上测量精度或最终管脚验收。
