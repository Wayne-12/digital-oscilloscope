# 数字示波器方案包

基于 EGO1 / XC7A35T 的数字示波器，包含 FPGA 功能代码、MicroBlaze 软核、1024×600 本地显示和 PC 操作界面。按“源码、硬件声明、启动服务、统一入口、设计报告”组织。

```text
digital-oscilloscope/
├── hardware/
│   └── HARDWARE.md              # 板卡、采样链路、工具链与版本声明
├── source/
│   ├── FPGA/                    # 功能 RTL、约束、仿真与生成脚本
│   ├── 软核/                    # C 固件、启动、链接、邮箱、IP 创建脚本
│   ├── VGA显示部分/             # 显示、菜单、整机入口与 release 镜像
│   ├── PC/                      # PC 界面、串口协议、测试与工具
│   ├── 示波器显示界面.py        # PC 主界面
│   ├── docs/                    # 原设计与验证文档
│   └── 参考数据/                # 校准和测量参考
├── serve/
│   └── README.md                # 运行环境和启动配置
├── run.ps1                      # Windows 统一入口
├── run.sh                       # Bash 入口（校验 / PC 界面）
├── REPORT.md                    # 设计报告、验证依据和复现边界
└── UPLOAD_MANIFEST.json         # 上传文件 SHA256 清单
```

硬件版本 `0xAF311031`，CPU 修订 `control_handoff_1`，PC 界面 `2026.11.01-r6`（2026-11-01）。

## 快速使用

Windows PowerShell：

```powershell
./run.ps1 -Action verify
python -m pip install -r ./source/PC/ui/requirements.txt
./run.ps1 -Action ui
```

串口与波特率在 PC 界面选择，板上 SW7 ON 交给电脑，OFF 回到本地；外部模块安全使能见硬件说明。

Bash（需已安装 Python 3）：`bash run.sh verify` 或 `bash run.sh ui`。FPGA 与 MicroBlaze 构建使用 Windows Vivado 2025.2，详见 [启动说明](serve/README.md)。

原构建、固化和版本说明见 [显示屏说明](source/VGA显示部分/README.md)、[软核说明](source/软核/README.md)；设计与证据索引见 [REPORT.md](REPORT.md)。

源码内部的相对目录保持一致；本次调整外层目录、入口和文档。仿真批量数据由生成脚本产生，未提交重复的 expected/vectors 目录。最终发布清单要求的依赖及镜像保留。Vivado 和 MicroBlaze 工具链自行安装，本包使用板端 RTL 和固件，无 AI 模型配置。
