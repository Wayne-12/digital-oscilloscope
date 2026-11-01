> 2026-10-24 工程范围调整：本文涉及的部分旧版报告已完整移至工程外备份，原始 PASS/FAIL 与哈希未改写；历史路径对照见 `docs/verification/历史报告归档说明.md`。本文旧记录不能代替现版工程验证。

# 第十四步：系统级自检回归

运行入口：

```powershell
& 'D:\Python\python3.14\python3.14.7\python.exe' D:\示波器\FPGA\scripts\run_system_regression.py
```

默认种子为 `20261020`、`42`。用 `--seeds 123 456` 更换种子；`--system-only` 只运行新增的端到端连接用例，完整默认运行还包括从工程仿真生成目录删除后重新编译的 smoke 测试，以及当前保留的基础模块和两个创新点回归。入口从一个新建的 ASCII 临时构建目录编译全部 RTL 和仿真连接层，每条用例单独 elaboration；任何编译、仿真、PC 黄金模型或基础回归失败都使入口返回非零状态。

2026-10-23已按分层建议调整默认顺序：先基础检查与11类独立单元，再集成套件，最后系统连接用例。规范系统入口为 `tb_scope_system.sv`，复用原 `tb_system_case` 场景；独立入口、门控和失败定位方式见 `testbench_layers.md`。`--system-only`是显式调试入口，不表示完整分层验收。


`system_capture_backend.sv` 是验证适配器，连接命令解析、安全状态机、DDS、ADC/DAC 模型、ADC 捕获、BRAM 和测量模块；跨时钟测试控制不作为硬件 CDC。

PC 独立编码命令，解析回帧并检查顺序、CRC、配置、测量、原始码及时间戳；逐点比较实际 ADC 流。失败时保存 WDB 和首错。

系统用例包括安全启动、中码、10 kHz、100 kHz、1 MHz、尖峰、OTR、UART 故障和撤销使能；当前连接用例为 case 0～7。

故障传播可用以下命令检查，预期返回非零状态、打印 `FIRST_ERROR` 的首错时间，并仅在失败时保存波形：

```powershell
& 'D:\Python\python3.14\python3.14.7\python.exe' D:\示波器\FPGA\scripts\run_system_regression.py --seeds 20261020 --system-only --cases 0 --inject-failure-case 0
```

历史完整回归见原报告；范围调整后的实际验证以 `feature_removal_20261025.md` 为准。
