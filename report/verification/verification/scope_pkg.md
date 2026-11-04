# 公共参数与类型包

2026-10-21：默认工具已切换到 Vivado/XSim 2025.2，见 [迁移记录](vivado_2025_2_migration.md)。原 2024.2 验收记录保留。

本次范围是 `FPGA/rtl/common/scope_pkg.sv` 及 `FPGA/rtl/common/sample_stream_if.sv`。包和接口只包含常量、类型、无状态函数及信号定义，没有寄存器或复位需求。后续时序模块仍须按统一约定实现复位。

## 冻结的基线

| 项目 | 定义 | 值 |
|---|---|---|
| 系统时钟 | `SYS_CLK_HZ` | 100 MHz |
| ADC 采样率 | `adc_rate_t`、`adc_rate_hz()` | 10 / 25 / 50 / 65 MSPS，默认 25 MSPS |
| ADC 原始码 | `adc_raw_t` | 12 位无符号，原始数据始终保留 |
| ADC 算法码 | `adc_sample_t` | 13 位有符号，实际有效范围 −2048～2047 |
| ADC 默认极性 | `ADC_INVERT_DEFAULT` | 启用 12 位取反 |
| ADC 流水线 | `ADC_PIPELINE_CYCLES` | 7 个完整 ADC 周期 |
| 额外捕获边沿 | `ADC_CAPTURE_EXTRA_CYCLES` | 1，下一内部上升沿读取已稳定总线 |
| 采集输出总延迟 | `ADC_SAMPLE_LATENCY_CYCLES` | 8，时间戳对应原采样序号 |
| DAC 码 | `dac_code_t`、`DAC_MID_CODE` | 14 位无符号，中码 8192 |
| BRAM | `BRAM_DEPTH`、`BRAM_DATA_WIDTH` | 16384 × 16，14 位地址 |
| 存储字 | `sample_word_t`、`sample_record_t` | 16 位，`{OTR, 3'b000, raw_code}` |
| 流时间戳 | `sample_timestamp_t` | 64 位无符号 |
| 流载荷 | `sample_payload_t` | 90 位，原始码、有符号码、OTR、时间戳 |
| UART | `UART_BAUD_DEFAULT` 等 | 115200，8N1 |
| 包络列数 | `ENVELOPE_COLUMNS` | 800，每桶 min/max 由后续模块实现 |
| FFT 点数 | `FFT_POINTS_DEFAULT`、`FFT_POINTS_EXTENDED` | 1024，预留 2048 |

安全相关常量：ADC 流水线 7 周期，启动或换频后等待至少 256 个 ADC 周期；DAC 初始化至少提供 16 个锁存时钟上升沿。这些常量没有实现供电判断、人工使能、高阻输出或时钟状态机。

第三步已在 `adc_capture` 与 AD9226 行为模型中验证 7+1 延迟，详见 [第三步验收记录](step3_ad9226_model_capture.md)。8 周期采集预热不能替代上述 256 周期时钟稳定等待。

采样率枚举用于模型配置描述，不生成时钟；当前板级采样率固定为 25 MSPS。

## 函数和数值约定

使用方先编译包，再编译流接口，最后编译使用它们的 RTL 和 testbench。包只编译一次，使用方通过 `import scope_pkg::*;` 或 `scope_pkg::类型名` 引用，禁止反复用文本 `include` 引入包定义。所有 SV 文件均明确声明 `timeunit 1ns; timeprecision 1ps;`，并用 `default_nettype none` 禁止隐式网络，文件末尾恢复为 `wire`。

公共源文件顺序保存在 `FPGA/scripts/scope_common.f`，路径相对工程根目录。后续编译从工程根目录运行，先用 `xvlog --sv --file FPGA/scripts/scope_common.f` 加入公共文件，再加入业务 RTL 和 testbench；不要在多个源文件列表中重复加入同一个包。

- `adc_rate_hz(rate)`：返回对应的整数 Hz；配置含未知位时返回 0，由后续控制模块拒绝无效配置。
- `adc_raw_to_signed(raw_code)`：固定为 `13'sd2047 - $signed({1'b0, raw_code})`。原始码先零扩展到 13 位，再显式解释为有符号数；两个操作数及结果均为 13 位有符号数，没有截断、舍入、饱和或电压单位换算。`ADC_INVERT_DEFAULT=1` 是极性约定，不提供绕过固定反相转换的函数参数。
- `pack_sample(raw_code, otr)`：保留原始 ADC 码，强制三个保留位为零。
- `unpack_sample(word)`：将所有位解释为结构体；不悄悄清除输入中的保留位，调用方负责检查它们。

固定反相转换的边界如下：

| 原始码 | 有符号码 |
|---:|---:|
| 0 | 2047 |
| 2047 | 0 |
| 2048 | −1 |
| 4095 | −2048 |

该整数表示选取 2048 为偏置码；规划书的电压公式按 4095 个间隔映射 ±5000 mV。后续显示换算应保留原始码并使用明确的换算/校准规则，不能将此有符号码直接当作 mV。

UART 帧字段、CRC 和 FFT 定点格式仍待对应任务冻结。第七步的触发配置和测量数据格式已建立，见本文末尾及第七步说明。

## 统一流接口

`sample_stream_if` 提供如下信号；生产者使用 `producer` modport，消费者使用 `consumer`，被动观察使用 `monitor`。

```systemverilog
sample_valid
sample_ready
sample_raw[11:0]
sample_signed signed [12:0]
sample_otr
sample_timestamp[63:0]
```

同一流的信号属于同一个时钟域，在采样时钟上升沿且 `sample_valid && sample_ready` 时传输。生产者在反压期间保持 valid 和全部载荷稳定；消费者可独立控制 ready。时钟与复位作为使用模块的显式端口传入，接口本身不产生时钟或复位。未来时序模块的复位应清零 valid；时间戳记录对应原始采样的采样计数，流水线和缓存必须与样本一起传递。

ADC 实物不能因下游反压而停止产生样本，后续采集入口必须通过缓存和溢出统计处理反压。本接口本身不实现缓存、CDC、丢样策略或时间戳计数器。16 位存储格式只包含原始码与 OTR，时间戳需要后续存储模块另行管理。

## 自动验证

测试文件：`FPGA/sim/tb/tb_scope_pkg.sv`。

1. 检查参数、类型位宽和默认配置。
2. 检查默认极性及四个关键码值。
3. 穷举 4096 个原始码 × 2 种 OTR，共 8192 笔。scoreboard 用独立的 32 位整数算术黄金模型比较有符号结果、存储位序、原码恢复、OTR 和保留位。
4. 默认追加 1000 笔随机输入，默认种子为 20261020；支持 `SEED`、`RANDOM_CASES` plusargs。脚本同时设置 XSim 种子并记录实际测试种子。
5. 单独编译验证用组合 RTL 模型 `FPGA/sim/models/scope_pkg_import_probe.sv`，同时检查包限定类型的 ANSI 端口、模块内 import、接口 modport 和 testbench import；覆盖四种 valid/ready 状态，并检查负数符号和完整 64 位时间戳传递。该模型只用于编译和类型检查，不接入硬件设计。

每项检查使用立即 `assert`，失败执行 `$fatal` 并输出 `TEST_FAIL`；每组完成输出 `TEST_CASE_PASS`，全部完成才输出 `TEST_PASS`。100 us 看门狗防止仿真挂起。脚本同时检查进程退出码、错误/警告日志、终止 PASS 标记和事务总数；编译或展开出现任何警告即判失败，包括重复定义、隐式网络或符号位问题。本次仅定义接口并验证组合传递，没有生产者或消费者状态机，因此握手保持与复位等时序断言在后续时序模块测试中补充。

运行默认测试（PowerShell）：

```powershell
& 'D:\示波器\FPGA\scripts\run_scope_pkg_tb.ps1' `
  -VivadoBin 'D:\AMD\Xilinx\vivado_2025.2\2025.2\Vivado\bin'
```

更换种子或运行多种子回归：

```powershell
& 'D:\示波器\FPGA\scripts\run_scope_pkg_tb.ps1' `
  -VivadoBin 'D:\AMD\Xilinx\vivado_2025.2\2025.2\Vivado\bin' `
  -Seeds 20261020,42 -RandomCases 1000
```

当前项目统一使用 PowerShell 7 和已安装的 Vivado/XSim。脚本不创建 Vivado 器件工程，不依赖尚未核实的 FPGA 型号。编译输入暂存系统 TEMP 的独立目录；结果、编译/运行日志、命令参数、源文件 SHA256 和逐种子结果保存在 `FPGA/reports/scope_pkg/<运行编号>/`。TEMP 目录路径记录在 `manifest.json`，保留用于追溯。

行为仿真的 PASS 仅覆盖本包的数字约定，不代表综合、时序收敛、板上接线或硬件安全已经验收。

运行脚本已在本机 Vivado 2024.2 和 2025.2 验证，默认目录由 `FPGA/scripts/vivado_toolchain.json` 指定。Windows 批处理转发时对含等号的 plusargs 保留引号；详细命令及实际生效的种子均保存在日志中。参考 [AMD UG900 的 XSim 命令行选项](https://docs.amd.com/r/2024.2-English/ug900-vivado-logic-simulation/xsim-Executable-Options) 及本机 `xsim --help`。

## 2024.2 历史验证结果

- 工具：Vivado/XSim 2024.2，行为仿真，时间精度 1 ps。
- 最终运行目录：`FPGA/reports/scope_pkg/20261020_194642_41989672/`。
- 编译和展开：PASS，零错误、零警告；包定义只编译一次，组合 RTL 模型和 testbench 均成功引用。
- 种子 20261020、42：均 PASS；每个种子 8192 笔穷举 + 1000 笔随机，共 9192 笔 scoreboard 事务，46029 次计数检查，仿真结束时间 9196 ns。
- 每个种子的终止标记、完整运行日志、种子清单、源文件 SHA256 和命令均已保存。未使用禁用断言或降低错误级别的选项。
- 早期脚本参数/环境问题的失败记录仍保留在各自运行目录中，不计入最终通过结果；本次未修改 Vivado 安装文件。

第四步新增 DDS 参数：32 位相位、1024 点 LUT、默认 DAC 时钟 25 MHz，以及 `DDS_SINE/DDS_SQUARE/DDS_TRIANGLE/DDS_DC` 四值 `dds_wave_t`。详细数值和接口约定见 [第四步说明](step4_dds_ad9767.md)。原有 ADC/存储/安全状态机参数保持原值。

第六步新增 `capture_mode_t`、`capture_state_t` 和 `capture_metadata_t`，定义 AUTO/NORMAL/SINGLE、捕获与冻结状态及 16K 帧元数据。存储字、ADC 编码和既有安全状态枚举值保持不变。捕获时间戳按 unsigned64 模 2^64 重建，并要求帧内已接受样本连续；详情见 [第六步说明](step6_bram_trigger.md)。

第七步新增 `trigger_type_t` 的 0～8 九种触发、`trigger_config_t`、`trigger_config_valid()` 和 `measurement_result_t`。捕获元数据增加 `extended_trigger` 与实际 `trigger_config` 快照，旧边沿接口仍可使用。测量支持完整 signed13 输入；累加和为 signed64，平方和为 unsigned64，均值和 RMS 采用明确的最近舍入。周期为 unsigned64 Q16 ADC tick，频率为 unsigned32 Hz，占空比为 unsigned32 ppm；stats_valid 与周期/占空比有效标志分开，无完整周期时 measurement_valid=0 且频率等字段清零。各条件边界、舍入与接口时序见 [第七步说明](step7_trigger_measure.md)。存储字仍是 `{OTR,3'b000,raw_code}`，未改变原始码格式。

