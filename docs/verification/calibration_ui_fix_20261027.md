# 实物闭环自检与校准 UI 修复验收（2026-10-27）

结论：真实ScopeWindow/SerialWorker/COM12实物验收通过。修复在PC端，无FPGA RTL修改，仍使用已验收0xA4261027。

已复现根因：实物联动RUN时按钮保持可用，但start_hardware_calibration被can_configure直接拒绝；界面只写日志，进度停在0%。现在点击后自动请求STOP，等待当前捕获/ROI/配置确认及STOP响应完成，再进入自检。等待期间禁用重复启动/采集/配置，支持取消及断连处理，15秒超时明确反馈。

自检显式暂时选择标准DDS；成功、取消或失败时，先禁用DDS，恢复原AWG选择，核对活动表CRC及有效状态，再恢复原DDS/触发，逐字节回读配置，并核对所选采集模式。用户波形表不改写。原±819码直流/最高10%数字正弦范围保持，原始ADC码保留，校正仅用于显示相对组合链路结果。

实物路径：
- RUN→点击自检→自动STOP→完整35帧PASS，进度100%、七行结果、七点频响、独立零点和+512码复测显示正常。
- 第二轮零点阶段后取消，3帧，CANCELLED且原配置恢复；不发布可应用校准。
- 已选AWG表时重新自检35帧PASS，原AWG选择及CRC、DDS/触发/采集模式完整恢复；与前次真实基线比较通过。

共73个完整实物帧。最终解析错误和意外FPGA错误均零；累计command_rejected=5源于此前AWG主动错误命令验收，没有新增。125项PC回归全部通过，含等待启动、等待时取消、成功/取消/失败时恢复AWG三条路径。

证据：[实物验收](../../FPGA/reports/calibration_ui/20261027_physical/report.json)、[完成截图](../../FPGA/reports/calibration_ui/20261027_physical/completed.png)、[AWG恢复截图](../../FPGA/reports/calibration_ui/20261027_physical/awg_restored.png)、[最终只读状态](../../FPGA/reports/calibration_ui/20261027_physical/final_status.json)。35+3+35帧原始NPY及逐项报告在各case所列PC/calibration_runs目录，副本已封入发布包evidence/calibration_ui_acceptance。

测试使用独立验收profile文件夹，不覆盖用户现有相对健康基线。正常启动根目录UI可连接并重新运行自检；旧UI进程需要重启才加载修复。当前SRAM镜像0xA4261027，Flash仍为0xA3261027，尚未固化本轮AWG新固件。
