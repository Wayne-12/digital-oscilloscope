# EGO1 数字示波器 · 2026-11-01 最新版

FPGA：XC7A35T，25 MSPS AD9226 采集、AD9767 输出；MicroBlaze MCS 软核；1024×600 本地显示；PySide6 电脑界面。

当前硬件版本 `0xAF311031`，CPU 修订 `control_handoff_1`，PC 界面 `2026.11.01-r6`。包含 11 月 1 日串口服务和 SW7 控制权切换修复。

- `FPGA/`：功能 RTL、约束、仿真和构建脚本。
- `软核/`：MicroBlaze C 固件、启动代码、链接脚本、邮箱 RTL、公共功能快照、CPU/FFT IP 创建脚本。
- `VGA显示部分/`：当前整机入口、显示/菜单、固件、字模及最终烧录镜像。
- `PC/` 和根目录 `示波器显示界面.py`：电脑界面、协议、测试及工具。
- `docs/`、`参考数据/`：说明和参考数据。

## 核对版本

```powershell
python ./VGA显示部分/verify_package.py
python -m pip install -r ./PC/ui/requirements.txt
python ./PC/ui/start_latest_scope.py
```

构建与固化步骤见 `VGA显示部分/README.md`、`软核/README.md`。Vivado 2025.2 及 MicroBlaze 工具链须自行安装；脚本中的本机工具路径须按安装位置调整。CPU IP 由 `软核/scripts/create_cpu_ip.tcl` 生成，FFT IP 由脚本重建；不需要上传 Vivado 缓存工程。

原发布清单涉及的文件按原路径完整保留，便于校验。未重新进行综合、烧录或硬件验证，本次仅整理和校验已有最新发布版本。
