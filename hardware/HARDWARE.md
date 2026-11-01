# 硬件与版本声明

| 项目 | 配置 |
|---|---|
| 开发板 / FPGA | EGO1 / XC7A35T CSG324 -1 |
| 采集 | AD9226，25 MSPS |
| 输出 | AD9767 A 通道，DDS / AWG |
| CPU | AMD MicroBlaze MCS，25 MHz，32 KB 本地 BRAM |
| 本地显示 | 1024×600，49 MHz 像素时钟；VGA 经有源 VGA→HDMI 转换器 |
| PC 通信 | UART，921600，8N1；端口在界面选择 |
| Flash | N25Q64，8 MiB |
| 工具链 | Vivado 2025.2、随附 MicroBlaze GCC；Python 3 与 PC/ui/requirements.txt |
| 最新硬件 / CPU / UI | 0xAF311031 / control_handoff_1 / 2026.11.01-r6 |

硬件版本号不区分 CPU 软件修订，识别发布版本须同时核对镜像哈希和 `source/VGA显示部分/release/flash_record.json`。IP 配置和约束以源码中的 Tcl/XDC 为准。

SW0 用于外部模块安全使能，配置后须 OFF→ON；SW7 ON 为电脑控制，OFF 为本地。实物接线、按键引脚和显示时序详见 `../source/VGA显示部分/README.md`，不要仅凭分辨率判断转换器兼容性。

软件工具路径含原开发机路径，构建前按实际安装位置调整。`SCOPE_VIVADO_BIN` 可覆盖显示屏 run.ps1 中的 Vivado bin 路径，固件脚本中的 GCC 路径单独配置。
