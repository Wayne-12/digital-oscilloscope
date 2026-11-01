# EGO1 25 MSPS 首版实现检查

## 结果

流水线DDS版本已生成bitstream：`FPGA/output/board_25m/scope_board_25m.bit`。Vivado 2025.2完整实现报告为`FPGA/reports/board/20261023_194352/artifacts/`。39个顶层端口均已逐项核对与终稿接线表一致。

| 项目 | 原DDS、正确约束 | 流水线DDS、正确约束 |
|---|---:|---:|
| setup最差余量 | -35.123 ns | 10.319 ns |
| hold最差余量 | 无负余量 | 0.043 ns |
| setup失败端点 | 存在 | 0 |
| 未约束内部端点 | 0 | 0 |
| 无时钟寄存器 | 0 | 0 |
| 无延迟且无例外的输入/输出端口 | 0 | 0 |

LUT 4194/20800（20.16%），FF 3323/41600（7.99%）。以上为当前基线的真实布局布线结果，不沿用先前模块资源相加估算。

## TIMING-16

首错路径为`uart/protocol/commands/dds_phase_offset_reg`到`dds/dac_code_reg`。原DDS一次完成相位加法、查表/三角波、64位乘除、偏移与饱和；最差组合延迟54.644 ns，且存在上升沿配置到下降沿DDS的半周期路径。

新`scope_board_dds`将相位、波形、乘法、精确归一化和偏移饱和分开寄存。除32767采用`32767=2^15-1`的整数恒等式，保留原算法最近舍入、负数处理和饱和，不改变时钟周期以隐藏违例。稳定配置的码序列相对原DDS延后3周期。独立对比包含四波形、16配置，65728个输出逐点一致。

| Aspect | Constraint | Period | Waveform | Clock Definition Object |
|---|---|---|---|---|
| Before | `create_generated_clock -name dac_external -source [get_pins dac_oddr/C] -divide_by 1 [get_ports dac_aclk]` | 40.000 ns | {0 20.000} | dac_external |
| After | `create_generated_clock -name dac_external -source [get_pins dac_oddr/C] -divide_by 1 [get_ports dac_aclk]` | 40.000 ns | {0 20.000} | dac_external |

## XDC和IO

首次XDC误用了`read_xdc`不接受的for/foreach，导致部分引脚和输出延迟未生效，被NSTD-1、UCIO-1拦截，未下载该版本。已展开为逐条管脚和延迟设置。约束前后HTML对比见同目录`constraints_diff.html`。

ADC按tCO=3.5..7 ns加2 ns布线/偏斜预算，输入min=1.5、max=9 ns；DAC按setup>=2 ns、hold>=1.5 ns加2 ns预算，对ACLK和WR1都检查max=4、min=-3.5 ns。预算尚未通过外部仪器实测；长接线或升速需重核。

机械开关、复位和UART输入不具有同步输入时序，例外只覆盖相应异步路径；UART内部逻辑仍在25 MHz下分析。LED和异步UART外部接收端没有共享捕获时钟。ADC数据及DAC数据均保留真实接口时序检查。

## 尚存告警及边界

- TIMING-18为DAC数据相对`adc_external`的14项关联时钟提示；当前实际DAC锁存关系已分别对`dac_external`和`wr_external`约束，check_timing无缺失输出延迟。没有伪造相对ADC时钟的DAC负载要求来消除提示。
- LUTAR-1两项是安全复位/使能的组合异步撤销路径；CDC报告仍有自定义异步安全控制相关Critical条目（CDC-1=746、CDC-13=10），不能称零CDC告警或CDC签核。
- RAMB异步控制告警来自异步断言、同步释放的复位对RAM使能/输出的影响。复位后协议和冻结帧均失效，下一帧必须完整重写，不读取被复位中断的记录；仍保留告警，未作waiver。
- DSP流水线、宽乘法和LUT-ROM输出寄存建议保留。当前布局布线时序通过，不将这些建议说成已全部消除。
- 未建立任何waiver。仿真及静态时序不代替真实ADC/DAC、串口、线缆信号完整性与长期稳定性验收。

## 依据

- AMD UG903：<https://docs.amd.com/r/en-US/ug903-vivado-using-constraints/Entering-XDC-Constraints>
- AMD UG906：<https://docs.amd.com/r/en-US/ug906-vivado-design-analysis/TIMING-16-Large-Setup-Violation>
