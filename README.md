# 基于 FPGA 的数字示波器

本项目基于 EGO1（XC7A35T）、AD9226 和 AD9767，包含采集、触发、DDS、FFT、MicroBlaze 固件、本地显示及 Python 上位机。
正式固化版本为 `0xAF311031`，CPU 修订为 `trigger_cycle_20261101`，PC 版本为 `2026.11.01-r6`。2026-11-04 中午的上位机改动已撤销；整理前根目录、暂存区和已有发布包的主程序 SHA256 均为 `98392a0fe86e0e551232be668aacd76dfbd805558bc491f663b77d41bd6fab83`。

```text
digital_oscilloscope/
  README.md
  src/       当前 RTL、C 固件、PC 程序及运行配置
  sim/       测试源码、验证入口和测试结果
  build/     重建脚本、IP 配置及综合实现报告
  board/     正式镜像、固化恢复备份及上板入口
  data/      纯测试数据和单独归类的模型参考数据
  skill/     12 项可复用技能包
  report/    正式报告、海报、视频、协作记录及文件溯源
```

## 运行与校验

Python 3.10 及以上。在项目根目录运行：

```powershell
python -m pip install -r src/pc/ui/requirements.txt
python sim/verify_submission.py
python src/pc/ui/launch_scope.py --offline
python src/pc/ui/launch_scope.py --hardware --baud 921600 --port COM12
```

串口按实际设备选择。`launch_scope.cmd` 默认使用 COM12。SW7 ON 交给电脑，OFF 使用本地控制。
运行 `python sim/run_tests.py` 执行离线 PC 回归，结果写入 `sim/results/submission_pc_tests.log`。
PC 说明位于 `src/pc/ui/user_guide.md`，测量指引位于 `src/pc/ui/measurement_guide.md`。

## 构建与上板

Windows、Vivado 2025.2、MicroBlaze 工具链及 MSVC；工具安装位置见 `build/scripts/`，Vivado 可用环境变量 `SCOPE_VIVADO_BIN` 覆盖。

```powershell
./build/build.ps1 -Action stage
./build/build.ps1 -Action simulate
./build/build.ps1 -Action build
```

`build/work/` 是按需生成的完整临时工作区，不属于提交源码。重建产生的新文件写入该工作区，不覆盖 `board/` 中的正式镜像。
`board/run.ps1` 提供 `program`、`prepare_flash`、`program_flash` 和 `verify_flash_boot`。重新固化前按 `board/hardware.md` 和 `report/design/display_readme.md` 检查供电、SW0 和接线。只读检查使用 `./board/run.ps1 -Action verify_flash_boot`。
原始固化清单及源快照原样保存在 `report/release_provenance/`；当前提交树由 `report/submission_manifest.json` 校验。目录迁移仅调整主机脚本中的路径和名称，生产 RTL、C 源码、ELF、BIT、BIN、MCS 保持原始字节。2026-11-04 的独立验证报告在 `build/reports/revalidation/`，该次新位流未上板，正式镜像仍采用已固化版本。

## 数据与报告

`data/measured/` 保存实际采集 CSV 及四份纯数据工作簿；CSV 注释行、说明列、说明页和结论文字已去除，表头与数据保留。`data/model_reference/` 为模型生成数据。校正运行需要的原始证据与参数保存在 `src/`，不改动其校验绑定。
测量条件、来源和校正范围见 `report/data_sources.md`，原路径与英文路径对应关系见 `report/path_mapping.json`。
正式技术报告为 `report/submission/design_report.pdf`；其余提交材料位于 `report/submission/`；旧报告和验证证据的内容可能包含历史路径与版本，当前入口以本 README 为准。
大模型协作整理记录见 `report/collaboration_record.md`。完整回归历史上曾被目录清理中断，该项不记为全部通过。
