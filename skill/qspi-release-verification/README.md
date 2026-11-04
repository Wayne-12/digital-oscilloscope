# QSPI 固化的备份、独立读回与冷启动验收

类型：案例模板、踩坑清单。本目录是独立 Skill 单元，中文为正文，文件路径使用英文。

## 适用范围

Vivado Hardware Manager 支持的 FPGA 配置 Flash 固化与验收；原案例为 XC7A35T 和 N25Q64。

## 来源与提炼依据

JTAG 临时下载成功不能证明 Flash 已固化；工具 program/verify 通过不能替代独立文件比对；软件重配置不能冒充断电冷启动。

从本队真实开发问题提炼，原始源码/报告的字节副本列于下方。`provenance.json` 记录来源路径与 SHA256。历史报告只证明其标明版本、环境与范围；本目录新增说明不是当年的大模型对话记录。

## 使用方法

1. 先核对实际 FPGA IDCODE、Flash 型号/容量、启动模式和镜像哈希；根据目标板确认外部模块供电与使能状态。
2. 在新的报告目录保存完整 Flash 备份，字节数不符则停止擦除。原例备份为 8 MiB，该数值不能迁移到其他器件。
3. 在已明确授权的目标板上固化，保留工具校验，再独立读回有效地址范围与期望 BIN 逐字节比较。相同镜像可跳过重复擦写。
4. 分别记录从 Flash 重加载和用户真实断电再上电；冷启动后只读检查 MODE/DONE/EOS/CRC 与应用身份，不先 JTAG 下载。

详细操作与迁移规则见 [SKILL.md](SKILL.md)，案例见 [references/case.md](references/case.md)。

## 已验证效果

当前 flash_record.json 记录编程校验、独立读回哈希相等、用户确认真实断电启动和只读启动寄存器 PASS；本次没有操作硬件。

集合本次实际执行结果见上一级 `validation.json`。不要把文件齐全/说明校验通过理解成新的上板或综合通过。

## 失效条件与边界

提供的是适配流程与参考源码，不提供跨板即用烧录器。目标、IDCODE、Flash、时钟和模式都需实际确认。不得从本技能的存在推断允许擦写设备。

## 原始依据

- `VGA显示部分/program_flash.tcl` → [source_01.tcl](references/source/source_01.tcl)
- `VGA显示部分/verify_flash_boot.tcl` → [source_02.tcl](references/source/source_02.tcl)
- `VGA显示部分/prepare_flash.tcl` → [source_03.tcl](references/source/source_03.tcl)
- `VGA显示部分/release/flash_record.json` → [source_04.json](references/source/source_04.json)

`references/source/` 是溯源快照；其中脚本可能仍依赖原工程路径、工具、模块或设备，不是可直接跨项目运行的入口。明确标为 `scripts/` 的可执行副本按本页说明运行。迁移时使用自己的参数、硬件合同和验证，保留修改前后证据。
