# 固定验收版本（2026-10-26）

已封存 `scope_20261026_uart_smoke_v1`，供用户之后直接进行短测或正式长稳。原有 139 帧实物短测对应的协议及验收核心源码 SHA256 与固定包完全一致。

板端仍使用已固化的 `0xA0261026` / 921600 / 25 MSPS / 16384 点 / 能力值 7。现有 N25Q64 完整读回备份的镜像范围与发布 `.bin` 再次逐字节核对一致，备份和镜像 SHA256 均匹配先前实物记录；真正断电 QSPI 自动启动和之后采集的证据保留。本次只封存软件和镜像，没有再次擦写 Flash，也没有启动长稳或修改硬件配置。

## 后续入口

- [启动固定版界面](../../releases/scope_20261026_uart_smoke_v1/启动固定版界面.cmd)
- [启动30秒实物短测](../../releases/scope_20261026_uart_smoke_v1/启动30秒实物短测.cmd)
- [启动两小时长稳验收](../../releases/scope_20261026_uart_smoke_v1/启动两小时长稳验收.cmd)
- [校验固定版本](../../releases/scope_20261026_uart_smoke_v1/校验固定版本.cmd)
- [固定版操作说明](../../releases/scope_20261026_uart_smoke_v1/README.md)

使用 QSPI，SW0 先 OFF，开发板上电并等待 DONE 后开启外部模块 5 V，稳定后 SW0 OFF→ON。验收前关闭普通 UI，保持既有 OUTA→IN 闭环与合适幅度。启动验收入口后输入实际接线、电源、旋钮位置及环境观察；默认 COM12，端口改变可追加 `--port COM新号`。

正式长稳入口先执行至少 1 MiB / 10 分钟伪随机回显，再连续至少 2 小时采集，之后恢复检查，总时长至少约 2 小时 10 分钟。结果写入固定版目录的 `PC/acceptance_runs/`，不会覆盖历史证据。本次仍为 `SHORT_PASS`，`qualified_bauds=[]`，两小时与其他档位实物验收保持待办。

## 版本与验证

包中包括固定 UI、协议/验收工具、初始配置独立快照、依赖精确版本、JTAG/Flash 镜像及短测/冷启动证据。每个入口启动前校验 47 个不可变文件；运行时配置与新增测试结果允许变化。完整 Vivado 项目仍保存在原工作区，本包不声称是独立可重建的 FPGA 源工程。

- [版本校验清单](../../releases/scope_20261026_uart_smoke_v1/release_manifest.json)
- [封存 ZIP](../../releases/scope_20261026_uart_smoke_v1.zip)
- [ZIP SHA256](../../releases/scope_20261026_uart_smoke_v1.zip.sha256)

ZIP SHA256：`d1cda092d8645a8040359b078594dfc9613e83c38d12ea7f1142da2660a90a22`。

封存后直接从包内执行 21 项协议与验收单元测试，全部通过；四个入口分别以校验或 `--dry-run` 模式检查，不打开串口。长稳入口的参数已核对为 `--duration 7200 --uart-duration 600 --min-echo-bytes 1048576`。固定包实际硬件能力证据沿用 [本轮实物短测](uart_physical_smoke_20261026.md) 与 [已有 Flash 冷启动确认](analysis_flash_confirmation_20261026.md)，本次不新增长期稳定结论。
