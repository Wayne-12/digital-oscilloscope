# 显示刷新期间的串口服务与控制权交接

类型：踩坑清单、案例模板。本目录是独立 Skill 单元，中文为正文，文件路径使用英文。

## 适用范围

单主循环同时负责绘图、字节桥接和本地/上位机控制的嵌入式系统。

## 来源与提炼依据

每 100 ms 绘制页面时不服务串口，超过后端约 4 ms 的接收窗口；控制权切换又可能切断半包，使残留回复污染本地命令。

从本队真实开发问题提炼，原始源码/报告的字节副本列于下方。`provenance.json` 记录来源路径与 SHA256。历史报告只证明其标明版本、环境与范围；本目录新增说明不是当年的大模型对话记录。

## 使用方法

1. 先做与模拟幅度无关的纯回显，把失败相位与绘图周期、parser timeout 增量对齐，避免靠增幅或放宽超时误判根因。
2. 在清屏、查字和绘图等长循环设置有界双向服务点，空闲立即退出；明确本地命令等待期间不能混入电脑请求。
3. 交接先结束当前请求/回复，再 STOP、按帧排空并等待安静窗口；清理按键旧事件与草稿。恢复电脑控制时先读板端实际参数。
4. 覆盖所有页面、半包/长包/CRC 异常、双向切换以及 RUN/STOP/SINGLE 恢复策略，再做相同条件修复前后回显比较。

详细操作与迁移规则见 [SKILL.md](SKILL.md)，案例见 [references/case.md](references/case.md)。

## 已验证效果

保留 400 次回显前后原始 JSON，原失败 13 次，修复后 0 次；历史 C 测试含绘图双向服务与交接场景，另有 20 次重连及真实切换记录。

集合本次实际执行结果见上一级 `validation.json`。不要把文件齐全/说明校验通过理解成新的上板或综合通过。

## 失效条件与边界

32 轮服务配额、4 ms 和 100 ms 是原案例参数，必须按新系统最坏服务间隔和吞吐重新计算。本次未重跑 C 编译或板端通信。

## 原始依据

- `VGA显示部分/通信修复验证_20261101.md` → [source_01.md](references/source/source_01.md)
- `VGA显示部分/控制权切换修复与固化_20261101.md` → [source_02.md](references/source/source_02.md)
- `VGA显示部分/panel_main.c` → [source_03.c](references/source/source_03.c)
- `VGA显示部分/test_panel.c` → [source_04.c](references/source/source_04.c)
- `PC/reports/final_acceptance_20261101/bridge_before.json` → [source_05.json](references/source/source_05.json)
- `PC/reports/final_acceptance_20261101/bridge_after.json` → [source_06.json](references/source/source_06.json)
- `PC/reports/control_handoff_20261101/review_before_flash.json` → [source_07.json](references/source/source_07.json)

`references/source/` 是溯源快照；其中脚本可能仍依赖原工程路径、工具、模块或设备，不是可直接跨项目运行的入口。明确标为 `scripts/` 的可执行副本按本页说明运行。迁移时使用自己的参数、硬件合同和验证，保留修改前后证据。
