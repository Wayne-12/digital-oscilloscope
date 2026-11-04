# 第一项：AUTO / NORMAL / SINGLE 三种采集模式

本项已于 2026-10-27 完成实物测试、Flash 固化及真正断电自动启动验证，结论 PASS。新镜像 `0xA1261026` 在 COM12 / 921600 bit/s 下验证 26 个完整帧，所有专项通过，解析错误及 FPGA 八类错误新增均为零，原配置恢复成功。[固化与启动报告](capture_modes_flash_20261027.md) 已保存。按用户最新要求，第一项固化后停止；整帧饱和统计、ADC 输入 IOB、任意波形表下载和汇总 CSV 暂不开始编写。

最终实物报告：[report.json](../../FPGA/reports/capture_modes_hardware/20261027_0008/report.json)。交付镜像与说明：[三模式发布说明](../../FPGA/output/capture_modes_921600_20261027/README.md)。实际验收 bitstream SHA256 为 `249775c0f9665a7f37cf40702ed299cfcd2eb7bba5793fa58f1158315521ad9d`。下文阶段进度和 FFT 审计过程保留为追溯记录，最终全部离线复核已经通过。

## 当前实现

- 新增能力 bit 3，候选固件 build `0xA1261026`，UART 固定 921600 bit/s。
- `SET_CAPTURE_MODE (0x12)`：8 字节 `<B3xI>`，模式 0=AUTO、1=NORMAL、2=SINGLE，后四字节为 AUTO 等待的 25 MHz 采样周期数。保留字节必须零，超时必须非零；活动采集中拒绝修改。
- `GET_CAPTURE_CONFIG (0x13)`：读取相同 8 字节的所选模式与超时。读取的是所选模式；`SINGLE` 临时执行单次不改写这个设置。
- `RUN (0x22)`：按所选模式启动；`SINGLE (0x20)`：强制一次真实触发，完成后保持。
- `RELEASE_FRAME (0x23)`：PC 完成冻结帧读取后通知 FPGA 释放。AUTO/NORMAL 在 FPGA 内重新装载和等待下一触发，无需 PC 再发 SINGLE。SINGLE 模式拒绝 RELEASE_FRAME。
- AUTO 没有符合条件的触发时按采样周期计时并产生自动触发；NORMAL 没有触发时保持等待；正常边沿可在超时之前触发 AUTO。超时从具备预触发历史后开始计算。
- 每帧分析和读取期间保持冻结，具有 UART 带宽造成的采集死区，不能宣传为连续无死区采样。STOP 取消正在等待或采集的记录，保留已有冻结帧供读取。
- UI 新增三模式选择、100 ms AUTO 超时说明；SINGLE 选择后 RUN 一次即停。旧固件单独显示“旧固件 · PC 单次轮询”，不把原有轮询宣称为板端 NORMAL/AUTO。离线演示也按模式处理超时或等待。

## 验证入口

- PC：`python -m unittest discover -s PC/tests -v`。
- FPGA：`FPGA/scripts/build_scope_board.py --implement --hardware-baud 921600`。保留基础板级、启动预设、DDS、包络/ROI、完整帧测量/FFT回归，并新增 `CAPTURE_MODES_TEST` 专项。
- 实物：`FPGA/scripts/verify_capture_modes_hardware.py --port COM12 --firmware <本项bitstream> --output-dir <新证据目录>`。检查不可达门限下的 AUTO 捕获与 NORMAL 等待、上下沿 NORMAL、释放后自动重装、SINGLE 保持、STOP/重启、整帧原始数据与 FPGA 统计、CRC与FPGA错误新增、原配置恢复。

当前为实物 PASS、Flash 编程/独立读回 PASS、真正断电自动启动 PASS。模块外部 5 V 保持关闭，SW0 OFF，后续功能编写已按用户要求暂停。

阶段进度：完整 PC 回归 109 项通过（`tmp/capture_modes_pc_tests.log`），包含 NORMAL 持续等待直到手动停止的验证；旧协议离线 XSim 回归固定种子 42、1 MiB 伪随机负载通过（`FPGA/reports/uart/20261026_234300_e05c066b`）。首次旧验证台因新增枚举输出未显式接空触发未连接告警而按原严格门槛停止，已补齐验证台连接并按同样门槛重跑通过，没有压低告警等级。该离线回归不是重新进行 UART 正式实物验收。

当前构建暂存目录为 `tmp/fpga_ascii/scope_board_20261026_232708_a50fa07f`；为适配 Vivado 的 ASCII 路径使用临时 `R:` 别名指向项目内 `tmp/fpga_ascii`。独立布局布线结果 setup WNS=10.544 ns、hold WHS=0.022 ns、脉宽余量=3.000 ns，相关失败端点为零，生成 bitstream 前 DRC 为零错误。完整板级回归仍在执行，未用上述结果替代实物完成判据。

### FFT 审计补充

初次板级回归的 RTL 自检全部运行结束，但原浮点谐波选峰审计在第二帧 H3 的精确 bin 断言停止：浮点 DFT 的 bin 12/13 幅度分别约 0.07054/0.07177 ADC 码，而硬件摘要选 bin 12。原失败报告保留在 `FPGA/reports/board/20261026_232708`。

调用本次 Vivado 生成的 FFT IP 自带官方 `xfft_v9_1_bitacc_cmodel_nt64.zip`，按实际 radix-2 burst、1024 点、16 位输入、24 位相位因子、不缩放、convergent rounding 配置复算：第一帧 H3 为 bin 13、第二帧为 bin 12，均与 RTL 一致。适配器为 `FPGA/scripts/fft_bitaccurate_reference.py`，仅用于离线验证。

加强复核入口为 `FPGA/scripts/review_capture_modes.py`：额外记录两帧全部 2048 个 FFT 复数输出，与官方整数模型逐点精确比较；同时保持独立浮点 DFT 的原分量误差上限 128 和幅度误差上限 0.125 ADC 码。H2～H5 的 bin 和 Q16 幅度再按整数模型精确核对。复核使用独立日志与 manifest；只有这些检查和三模式专项全部通过，才打包候选镜像并上板。

## 已完成的 UART 正式验收

已找到并核对用户汇报所对应的原始实物报告：`releases/scope_20261026_uart_smoke_v1/PC/acceptance_runs/20261026_210556_574002_soak/report.json`，结论 `PASS`。回显 600.0288608 秒、13,418,616 字节；长稳 7200.2697149 秒、32,961 帧，加恢复检查总 32,963 帧。错误新增和 OTR 均为零，恢复成功。

该验收仅对应原设备、`0xA0261026`、镜像 SHA256 `e69221cabb545f2de1bee2b12d8493a1ad43083c7928a519f45ac4312fb1ea0d`、921600 bit/s 及原报告条件。本次三模式候选镜像使用独立身份和证据，不继承旧镜像的正式长稳结论；本次按要求不重做 UART 正式验收。
