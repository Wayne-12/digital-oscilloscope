# 单元到系统的分层回归与结果复用门禁

类型：案例模板、校验脚本。本目录是独立 Skill 单元，中文为正文，文件路径使用英文。

## 适用范围

具有多个可独立测试模块的 RTL 工程；尤其适合固定种子、长运行和单元结果复用。

## 来源与提炼依据

原回归先跑系统，失败后难以区分模块错误与上层脚本错误；旧 PASS 若与当前源码不一致会掩盖回归。

从本队真实开发问题提炼，原始源码/报告的字节副本列于下方。`provenance.json` 记录来源路径与 SHA256。历史报告只证明其标明版本、环境与范围；本目录新增说明不是当年的大模型对话记录。

## 使用方法

1. 按接口边界建立独立 DUT 顶层，UART PHY 与包解析、触发与测量分别验证。
2. 执行顺序固定为 unit → integration → system；任一前置层失败即停止进入后层。
3. 复用报告时核对 verdict、完整必测项、随机种子和参与源文件 SHA256。源码变化、缺项或失败报告均拒绝。
4. 高层失败时先复跑相关最小单元；单元全通过只说明需继续检查连接、配置或测试框架，不能自动归罪 RTL。

详细操作与迁移规则见 [SKILL.md](SKILL.md)，案例见 [references/case.md](references/case.md)。

## 已验证效果

历史完整回归清单 20261027_223504_45686965 为 PASS，prerequisites_verified=true；本次重跑调度单元测试，见 validation.json。

集合本次实际执行结果见上一级 `validation.json`。不要把文件齐全/说明校验通过理解成新的上板或综合通过。

## 失效条件与边界

源码哈希只能证明清单覆盖的输入；须包含约束、IP 参数、生成表和工具版本。参考调度器绑定原工程的测试集合，迁移时必须重建依赖映射，不能直接照搬测试名。

## 原始依据

- `FPGA/scripts/run_system_regression.py` → [source_01.py](references/source/source_01.py)
- `FPGA/scripts/run_unit_regression.py` → [source_02.py](references/source/source_02.py)
- `PC/tests/test_regression_layers.py` → [source_03.py](references/source/source_03.py)
- `FPGA/reports/system/20261027_223504_45686965/manifest.json` → [source_04.json](references/source/source_04.json)

`references/source/` 是溯源快照；其中脚本可能仍依赖原工程路径、工具、模块或设备，不是可直接跨项目运行的入口。明确标为 `scripts/` 的可执行副本按本页说明运行。迁移时使用自己的参数、硬件合同和验证，保留修改前后证据。
