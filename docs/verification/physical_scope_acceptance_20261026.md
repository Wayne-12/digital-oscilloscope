# 精简范围实物验收（2026-10-26）

本次按用户要求，在用户接入 EGO1、AD9226、AD9767 后完成真实硬件验证。FPGA 基础测量、1024 点 FFT、主频及 H2～H5 摘要、零点/增益相对校准、七点基本扫频、校准前后对比及保留的包络/ROI 均通过本次功能验收。

## 硬件与加载

- 用户确认 SW0 OFF、接线和实体旋钮保持原样后，通过 JTAG 临时加载新固件；用户随后确认外部 5V 正常、SW0 OFF→ON，再开始真实采集。
- 器件 `xc7a35t_0`、IDCODE `0362d093`，加载后 DONE=1；[JTAG 原始日志](../../FPGA/reports/analysis_hardware/session_20261026/program_jtag.log)。
- 固件 `0xA0261026`、能力值 7、COM12 / 921600 bit/s、25 MSPS、16384 点 BRAM。bitstream 加载前已与原发布清单核对 SHA256。
- 本次未写 Flash。当前新固件属于易失 JTAG 配置，断电后仍从原 Flash 版本启动。

## 验证结果

| 项目 | 结果及证据 |
|---|---|
| 四种波形与 FPGA 测量 | 正弦、方波、三角波、直流各一帧；最大/最小、Vpp、均值、RMS、精确和/平方和、周期、频率、占空比与原始码独立计算一致。三种交流波均通过 100 kHz 检查；[结果](../../FPGA/reports/analysis_hardware/session_20261026/summary/verification.json)。 |
| FPGA 1024 点 FFT | 主峰、H2～H5 幅度与独立定点预处理/FFT 计算符合既定容差；重复读取和同帧时间戳一致。H3/主峰幅度比：正弦 0.00218、方波 0.31780、三角波 0.10727，波形差异可分辨。直流无有效交流主峰。 |
| 两轮真实相对校准 | 每轮 35 帧：三帧零点、九点直流、四档幅度、七点频响、谐波、独立零点及 +512 DAC 码验证。两轮配置恢复均逐字节相同；[校准汇总](../../FPGA/reports/analysis_hardware/session_20261026/calibration/verification.json)。 |
| 基本扫频 | 10、25、50、100、250、500、1000 kHz 七点，归一到当轮 100 kHz。第二轮相对响应约 −0.0071、−0.0037、−0.0030、0、−0.0024、−0.0060、−0.0209 dB，仅代表当前组合链路及这些测试频点。 |
| 取消与原始码保真 | 在真实零点步骤后注入取消，状态 CANCELLED、原配置恢复；显示应用校准后原始 ADC 码逐点不变。旧实测基线 SHA256 保持不变，新指纹仅保存到本次验收目录。 |
| 包络与 ROI | 6 帧，100/200/400/800/800/800 桶，共 3100 桶，与同一冻结整帧的 min/max/OTR 逐桶完全一致；每帧三个 ROI 共 21504 样本逐点一致，过期 ROI 被拒绝；[结果](../../FPGA/reports/multires_hardware/20261026_192548/verification.json)。 |
| 连续完整帧核对 | 30 帧、491520 样本，在约 13.47 秒内重复执行整帧测量、FFT、谐波及唯一时间戳检查，全部通过；[结果](../../FPGA/reports/analysis_hardware/session_20261026/continuous/verification.json)。这是短时功能回归，不是两小时长稳测试。 |
| 错误及恢复 | 本次各阶段 CRC、协议长度/版本/超时解析错误为 0，FPGA 前八项错误计数增量为 0，后端错误为 0；保存原始记录的所有测试均在既定低幅条件下进行。测试结束发送 STOP，DDS/触发/记录配置与开始时一致。 |

共使用 114 个独立真实冻结帧：四种波形 4 帧、校准/取消/显示 74 帧、包络 6 帧、连续回归 30 帧。未启用已删除的硬件分段采集或完整 SNR、SINAD、SFDR、ENOB 指标体系。

## 校准前后对比与基线变化

第二轮独立验证点使用同一原始观测，仅改变显示换算：

| 验证点 | 相对目标 | 校准前误差 | 校准后误差 |
|---|---:|---:|---:|
| 独立零点复测 | 0 mV | +5.8585 mV | −0.2475 mV |
| 未参与拟合的 +512 DAC 码 | +139.5908 mV | −43.7576 mV | −0.0407 mV |

直流拟合 R²≈0.9999918。当前组合链路增益约为旧保存基线的 0.643608 倍，即变化约 −35.639%；本次两轮拟合增益只相差约 +0.0293%。这说明当前结果可重复，不能单凭这次测试确定与旧基线差异的来源。旧基线未被重建或覆盖。

以上目标来自保存的组合链路相对参考，电压按现有标称换算。它们不构成独立 ADC、DAC 或绝对电压精度的可溯源校准。

## 文件与当前状态

- [实物频谱界面](../../FPGA/reports/analysis_hardware/session_20261026/continuous/hardware_fft.png)
- [实物校准与前后对比界面](../../FPGA/reports/analysis_hardware/session_20261026/calibration/hardware_calibration.png)
- [校准后波形界面](../../FPGA/reports/analysis_hardware/session_20261026/calibration/corrected_waveform.png)
- [本次实测指纹](../../FPGA/reports/analysis_hardware/session_20261026/calibration/measured_fingerprint.json)
- [最终实物证据清单](../../FPGA/reports/analysis_hardware/session_20261026/acceptance_manifest.json)
- 可重运行的 [相对校准实物验收入口](../../FPGA/scripts/verify_relative_calibration_hardware.py)，仅在板卡和人工使能已准备好时运行。

最后的界面截图通过正式 UI 类回放已核验的真实采样帧和实测校准报告生成，显示“实物记录回放”，未使用软件演示数据补齐。截图串口为 COM12。

当前无需用户继续操作。采集已停止、原配置已恢复；SW0 仍由用户保持 ON，软件 STOP 不撤销模块硬件使能。未执行 Flash 擦写或断电冷启动验收。
