> 2026-10-24 工程范围调整：本文涉及的部分旧版报告已完整移至工程外备份，原始 PASS/FAIL 与哈希未改写；历史路径对照见 `docs/verification/历史报告归档说明.md`。本文旧记录不能代替现版工程验证。

# 分层 testbench 与回归入口

工程按单元、集成和系统分层。UART 位级与协议解析分别测试。
原总回归也先运行系统连接测试，再运行基础套件。本次按建议补齐独立入口和执行顺序。

| 层级 | 建议文件/当前入口 | 验证职责 |
|---|---|---|
| 单元 | `FPGA/sim/tb/tb_safe_seq.sv` | 安全上电、等待和退出顺序；复用安全场景 |
| 单元 | `FPGA/sim/tb/tb_adc_capture.sv` | ADC编码、7+1延迟、OTR；复用AD9226场景 |
| 单元 | `FPGA/sim/tb/tb_dds_dac.sv` | DDS波形及AD9767锁存时序；复用DDS场景 |
| 单元 | `FPGA/sim/tb/tb_trigger.sv` | 独立触发DUT，边沿/窗口/脉宽/幅度/OTR及迟滞 |
| 单元 | `FPGA/sim/tb/tb_capture_bram.sv` | 环形缓存、预后触发、冻结帧及跨域读出 |
| 单元 | `FPGA/sim/tb/tb_measure.sv` | 独立测量DUT；统计量、RMS、频率、占空比和复位异常 |
| 单元 | `FPGA/sim/tb/tb_uart_phy.sv` | 仅UART TX/RX；8N1、分频、±2%周期、坏停止位/短脉冲 |
| 单元 | `FPGA/sim/tb/tb_protocol.sv` | 仅帧编解码；PC黄金模型、CRC、重同步、超时和1MiB负载 |
| 单元 | `FPGA/sim/tb/tb_envelope.sv` | 分桶不重不漏、正负尖峰保留和ROI索引 |
| 单元 | `FPGA/sim/tb/tb_fft.sv` | 相干bin、幅度缩放、双音与谐波；另运行FFT接口/开方单元 |
| 集成 | `FPGA/sim/tb/tb_loopback.sv` | DDS→DAC→通道→ADC闭环 |
| 系统 | `FPGA/sim/tb/tb_scope_system.sv` | UART命令到采样、捕获、测量及返回帧 |

部分规范入口是轻量包装，复用原有同职责场景、scoreboard和watchdog，避免复制测试逻辑。
职责混合的测量测试已实际拆分：`tb_trigger`、纯测量 `tb_measure`、独立集成 `tb_measure_capture`。
`tb_uart_phy` 不实例化协议模块；`tb_protocol` 不实例化 DDS、采集或 UART 串口模块。
旧入口保留兼容性，其包含的集成检查安排在全体单元通过之后，不替代独立单元验收。

## 执行方式

完整回归（默认两个固定种子）：

```powershell
& 'D:\Python\python3.14\python3.14.7\python.exe' D:\示波器\FPGA\scripts\run_system_regression.py
```

单独运行最小单元：

```powershell
& 'D:\Python\python3.14\python3.14.7\python.exe' D:\示波器\FPGA\scripts\run_unit_regression.py --tests trigger --seeds 20261020
```

`--tests` 可选：`safe_seq adc_capture dds_dac trigger capture_bram measure uart_phy protocol envelope fft`。
每个单元单独编译、展开和运行，自动PASS/FAIL；沿用 `1ns/1ps`，断言、scoreboard、固定种子与可换种入口。
数据生成器分别使用自己的新目录；FFT库列表从当前Vivado导出脚本读取，继续使用Vivado Simulator。

默认执行顺序被固定为：

1. smoke/参数包基础检查和所有独立单元。
2. 闭环、捕获到测量、UART 后端、包络/FFT 和创新点集成。
3. `tb_scope_system`命令到返回帧的端到端用例。

一层失败即停止进入更高层。`manifest.json`记录 `phase_history`、`active_layer`、首错及单元结果来源。
`--unit-reports`可复用已通过的单元报告，但必须覆盖全部必测项、种子相同且源码SHA256完全匹配。
`--system-only`仅是显式调试入口，会标记 `prerequisites_verified=false`，不能作为完整分层验收。

## 失败定位

单元失败直接报告最小入口、种子、日志和首错时间；不会继续运行集成或系统。
集成或系统失败时，入口先按失败用例重跑关联的独立单元，记录 `lower_layer_diagnosis`；系统完整波形保存在这一步之后。
候选单元全部通过时，明确标记为更高层连接/配置/测试问题，不把它误报成某个单元故障，也不会自动盲改RTL。

五项调度测试验证层级顺序、单元/集成失败阻断、缺失单元结果阻断及源码变化使旧结果失效。
故意破坏协议黄金模型首字节时，独立scoreboard在3655ns失败并返回非零，见 `FPGA/reports/unit/20261022_234939_027108/manifest.json`。

## 本次验收记录

- 11类独立单元使用种子 `20261020`、`42` 全部PASS；FFT额外运行接口和整数开方入口，合计26次运行。报告：`FPGA/reports/unit/20261022_234331_296512/manifest.json`、`FPGA/reports/unit/20261022_235115_948321/manifest.json`。
- 测量拆分后的原生Vivado工程模式也从零编译三个独立顶层，9份捕获轨迹与独立仿真一致。报告：`FPGA/reports/measure/20261023_001411_41b9cb8b/manifest.json`。
- 首次总回归在测量工程日志汇总缺陷处停止，`phase_history`仅含unit和integration；关联单元复跑全部PASS，定位为上层脚本问题。修复后重新验收，保留原失败报告 `FPGA/reports/system/20261023_000225_582d0e37/manifest.json`。
- 最终完整分层验收：`FPGA/reports/system/20261023_001101_7a301f98/manifest.json`，退出码0、PASS。`phase_history=[unit,integration,system]`，`prerequisites_verified=true`；14个基础及集成套件、18次系统连接运行、10个汇总用例全部PASS，`first_error=null`，临时构建目录已删除。单元报告按源码哈希和两个固定种子校验后复用。

本次分层调整没有修改功能RTL；暂定器件综合结论及板级时序限制仍见步骤15说明。

