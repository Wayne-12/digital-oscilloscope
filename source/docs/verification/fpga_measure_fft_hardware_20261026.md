# FPGA 测量、1024 点 FFT 实物验证记录（2026-10-26）

> 后续更新：用户随后要求固化，新镜像已完成Flash写入、校验和独立读回。断电启动状态见 [固化记录](analysis_flash_20261026.md)；下文“未写Flash”保留本次临时JTAG实物验收阶段的事实。

本次实物验证通过。经用户确认接线、外部 5.0 V 电源及 SW0 状态后，在 xc7a35t 板卡上临时 JTAG 加载新固件，通过 COM12、921600 bit/s 完成真实串口采集和正式 GUI 工作线程验证。固件版本为 `0xA0261026`、能力值为 `7`，采样率 25 MSPS，完整冻结记录长度 16384 点。

**本次没有写入 Flash，没有验证断电冷启动。断电后会重新加载原 Flash 固件。** 2048 点 FFT 及复杂频谱指标已移出当前交付范围；2048 点原始 ROI 仍保留。

## 验证结果

| 项目 | 结果 |
|---|---|
| 四种实物波形 | 正弦、方波、三角波及直流均通过；同时检查交流幅度与频率，避免静止 ADC 数据误通过。 |
| FPGA 基础测量 | 对完整原始帧独立核对最值、精确求和及平方和、均值、RMS、周期、频率和占空比；无有效交流周期时检查无效标志。 |
| FPGA 1024 点 FFT | 独立复现既定定点加窗并使用 NumPy FFT 核对主峰及 H2～H5，幅度容差保持 0.125 ADC 码；不修改 RTL 或放宽容差。 |
| 同帧一致性 | 原始帧与两类摘要的时间戳、采样率、触发位置一致，冻结后重复读取的摘要不变。 |
| 包络及 ROI | 800 个 FPGA min/max/OTR 桶与完整帧逐桶一致；2048 点 ROI 及另外三个位置共 3072 点 ROI 与完整帧逐点一致。 |
| 连续采集 | 20 帧、约 8.97 秒通过，每帧独立核对基础测量与 FFT；本项是短时连续性检查。 |
| 独立闭环校准 | 35 个完整帧通过，涵盖零点、九点直流、四档幅度、七点扫频及独立复测。 |
| 正式 GUI 实物流程 | 真实 SerialWorker 连接 COM12，完成完整帧、FFT 页、包络/ROI 页和界面发起的另一轮 35 帧校准；仅 Qt 窗口绘制采用 offscreen，串口及数据均来自实物。 |
| 错误与恢复 | 96 个不同时间戳的完整帧，共 1,572,864 个原始样本，均无 OTR/保留位异常；最终 FPGA 八项错误计数和 PC CRC/长度/版本/超时错误均为 0。原 48 字节配置逐字节恢复一致。 |

100 kHz 正弦的正式 GUI 读数为频率 100 kHz、峰峰值约 298 mV、RMS 约 102 mV。25 MSPS/1024 点 FFT 的频率间隔为 24.4140625 kHz，因此 FFT 主峰位于第 4 桶，即约 97.656 kHz；精细频率使用整帧时域测量。谐波摘要为整数倍主峰附近 ±1 桶的峰值幅度，不等同于完整失真指标。

## 校准独立复测

下表来自正式 GUI 第二轮实物校准。单位均为 mV，前后误差使用同一份独立原始观测计算。

| 独立复测点 | 相对目标 | 校准前误差 | 校准后误差 |
|---|---:|---:|---:|
| 零点复测 | 0.0000 | +5.5267 | -0.3260 |
| 未参与拟合的 +512 DAC 码 | +139.5908 | -43.9394 | -0.0500 |

本轮直流拟合 R² 为 0.999990，四档幅度最大相对偏差约 0.308%，零输入噪声约 1.914 mV RMS。测试最大 DDS 码为 819，未提高至满幅。校准仅验证 DAC、线缆及 ADC 组合链路的相对换算；目标取自保存的相对基线，没有外部绝对电压参考。本轮相对增益约为旧基线的 0.644 倍，不能据此单独判断 DAC 或 ADC 故障，也不作为绝对精度或长期温漂结论。

## 原始证据和源码身份

- [汇总清单及全部 96 帧的路径、时间戳和 SHA256](../../FPGA/reports/analysis_hardware/20261026_183504/verification.json)
- [四波形及摘要数值核对](../../FPGA/reports/analysis_hardware/20261026_183504/summary_checks/verification.json)
- [包络、ROI 和连续采集](../../FPGA/reports/analysis_hardware/20261026_183504/integration_checks/verification.json)
- [独立闭环校准](../../FPGA/reports/analysis_hardware/20261026_183504/closed_loop_calibration/report.json)
- [正式 GUI 真实串口验证及校准结果](../../FPGA/reports/analysis_hardware/20261026_183504/gui_checks/verification.json)
- [最终版本、配置及错误计数读回](../../FPGA/reports/analysis_hardware/20261026_183504/final_readback.json)
- [JTAG 加载日志](../../FPGA/reports/analysis_hardware/20261026_183504/program.console.log)
- [本次使用的 PC 源码快照](../../FPGA/reports/analysis_hardware/20261026_183504/tested_pc_source/示波器显示界面.py)
- [发布清单](../../FPGA/output/analysis_1024_921600_20261026/release_manifest.json)

本次加载的 bitstream SHA256 为 `e69221cabb545f2de1bee2b12d8493a1ad43083c7928a519f45ac4312fb1ea0d`，与离线发布包一致，FPGA RTL 哈希亦一致。当前 UI 的哈希与较早离线清单不同；本次测试直接导入当前 UI，其修改时间早于本次硬件会话，已单独归档实际源码及两份哈希。未覆盖历史离线清单或发布包原源码快照，也不把其旧版离线测试结论直接转记给新 UI。

界面截图：[波形](../../FPGA/reports/analysis_hardware/20261026_183504/gui_checks/waveform.png)、[FFT](../../FPGA/reports/analysis_hardware/20261026_183504/gui_checks/fft.png)、[包络/ROI](../../FPGA/reports/analysis_hardware/20261026_183504/gui_checks/multires.png)、[校准前后对比](../../FPGA/reports/analysis_hardware/20261026_183504/gui_checks/calibration_bottom.png)。

## 测试结束状态

采集已 STOP，原 100 kHz/10% DDS、触发和记录配置已恢复，COM12 已释放；原用户配置文件和已有校准基线未改变。外部 5 V 电源及 SW0 仍由用户控制。结束使用时按 SW0 OFF → 模块外部 5 V 关闭 → USB 断电的顺序操作。

此前离线实现的 CDC 与方法学提示仍见原实现复核，本次通过不表示这些提示已清零，也不代表长时间稳定性或绝对电气精度验收完成。
