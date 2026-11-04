# Windows 中文路径下的 Vivado 进程环境隔离

类型：案例模板、踩坑清单。本目录是独立 Skill 单元，中文为正文，文件路径使用英文。

## 适用范围

Windows Vivado/XSim 在中文工程路径、临时目录不可写或 Tcl 本地目录初始化失败时。

## 来源与提炼依据

该工程曾因中文路径、工具临时目录和 Tcl 应用目录导致编译子进程失败；预先手工映射盘符掩盖了启动脚本依赖。

从本队真实开发问题提炼，原始源码/报告的字节副本列于下方。`provenance.json` 记录来源路径与 SHA256。历史报告只证明其标明版本、环境与范围；本目录新增说明不是当年的大模型对话记录。

## 使用方法

1. 先保留首个工具错误，区分源码编译错误与路径/权限错误；不要把所有 XSim 报错都归因于中文路径。
2. 检测现有 subst 映射，只复用指向当前工作区的映射或创建空闲盘符，不覆盖其他映射。
3. 对子进程设置可写英文 TEMP/TMP、APPDATA 和实际安装的 Tcl 仓库；为当前运行创建独立工程目录。
4. 退出时恢复原环境，只解除本次创建的映射；从无预置盘符的终端再次运行以验证独立启动。

详细操作与迁移规则见 [SKILL.md](SKILL.md)，案例见 [references/case.md](references/case.md)。

## 已验证效果

修复记录包含 FFT 三个测试根、原生 smoke 清理重建、系统回归及无预置别名启动通过。本次仅核对脚本与历史清单，未启动 Vivado。

集合本次实际执行结果见上一级 `validation.json`。不要把文件齐全/说明校验通过理解成新的上板或综合通过。

## 失效条件与边界

参考实现针对 Windows/Vivado 2025.2；不保证解决工具缺陷、许可证、RTL 错误或全部权限问题。脚本含原工程布局假设，先参数化工作区与工具位置。

## 原始依据

- `FPGA/scripts/simulation_environment.py` → [source_01.py](references/source/source_01.py)
- `FPGA/scripts/run_regression.ps1` → [source_02.ps1](references/source/source_02.ps1)
- `docs/verification/repair_calibration_regression_20261027.md` → [source_03.md](references/source/source_03.md)
- `FPGA/reports/system/20261027_225049_174fb8fc/manifest.json` → [source_04.json](references/source/source_04.json)

`references/source/` 是溯源快照；其中脚本可能仍依赖原工程路径、工具、模块或设备，不是可直接跨项目运行的入口。明确标为 `scripts/` 的可执行副本按本页说明运行。迁移时使用自己的参数、硬件合同和验证，保留修改前后证据。
