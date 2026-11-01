# 运行配置与入口

在仓库根目录执行。首次运行 PC 界面前安装 `python -m pip install -r ./source/PC/ui/requirements.txt`。可先激活自己的 Python 虚拟环境；入口使用当前 PATH 中的 python。

| 命令 | 作用 |
|---|---|
| `./run.ps1 -Action verify` | 只读校验发布清单和全部上传文件 SHA256 |
| `./run.ps1 -Action ui` | 打开 PC 界面；在界面中选择串口和连接 |
| `./run.ps1 -Action firmware` | 编译显示屏 MicroBlaze 固件，需 GCC |
| `./run.ps1 -Action simulate` | 运行现有显示屏 XSim 流程，需 Vivado 及现有测试前置产物 |
| `./run.ps1 -Action build` | 运行现有整机综合与实现脚本，需先生成 CPU IP 和固件 |
| `bash run.sh verify` / `bash run.sh ui` | Bash 下的校验 / PC 界面入口 |

CPU IP 生成见 `source/软核/README.md`；字体、测试页面、固件与显示屏构建顺序见 `source/VGA显示部分/README.md`。构建入口只调度现有脚本，不替代其前置步骤；不要将重新构建后的文件与冻结发布的哈希混用。

烧录属于单独流程，按显示屏 README 核对镜像和设备后使用原 program/flash 脚本。统一入口不自动烧录硬件。
