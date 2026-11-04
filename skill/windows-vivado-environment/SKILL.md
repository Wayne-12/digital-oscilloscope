---
name: windows-vivado-environment
description: Diagnose Windows Vivado and XSim path failures using process-local ASCII aliases and writable temporary directories without altering existing drive mappings.
---

# Windows 中文路径下的 Vivado 进程环境隔离

适用：Windows Vivado/XSim 在中文工程路径、临时目录不可写或 Tcl 本地目录初始化失败时。

先读 [references/case.md](references/case.md) 的历史故障与验证边界；需要原始证据时按 [README.md](README.md) 的映射读取 `references/source/`，不要一次加载全部文件。

1. 先保留首个工具错误，区分源码编译错误与路径/权限错误；不要把所有 XSim 报错都归因于中文路径。
2. 检测现有 subst 映射，只复用指向当前工作区的映射或创建空闲盘符，不覆盖其他映射。
3. 对子进程设置可写英文 TEMP/TMP、APPDATA 和实际安装的 Tcl 仓库；为当前运行创建独立工程目录。
4. 退出时恢复原环境，只解除本次创建的映射；从无预置盘符的终端再次运行以验证独立启动。

交付时写明触发条件、输入/目标身份、实际执行步骤、证据位置、结果和未验证范围。对现场没有执行的检查给出待验证状态，不用历史 PASS 替代。

参考实现针对 Windows/Vivado 2025.2；不保证解决工具缺陷、许可证、RTL 错误或全部权限问题。脚本含原工程布局假设，先参数化工作区与工具位置。
