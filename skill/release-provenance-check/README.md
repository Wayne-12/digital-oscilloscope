# 源码、ELF、位流与发布镜像的一致性校验

类型：校验脚本、踩坑清单。本目录是独立 Skill 单元，中文为正文，文件路径使用英文。

## 适用范围

FPGA 发布包、带 MicroBlaze ELF 的位流，以及同一硬件 build ID 下的软件修订。

## 来源与提炼依据

硬件 build ID 不会随 CPU 程序更新而必然改变；新会话打开 DCP 不保证沿用 ELF 关联，中间位流可能没有正确嵌入 C 程序。

从本队真实开发问题提炼，原始源码/报告的字节副本列于下方。`provenance.json` 记录来源路径与 SHA256。历史报告只证明其标明版本、环境与范围；本目录新增说明不是当年的大模型对话记录。

## 使用方法

1. 冻结来源清单，记录相对路径 SHA256、工具版本、器件和配置；将输入源、ELF、运行 bit 与 SPI 文件分开标识。
2. 在实施后显式用匹配的 MMI/处理器路径执行 UpdateMEM，产出独立 runtime 位流；不得把中间 bit 作为已嵌入固件发布。
3. 在工作区运行 python scripts/verify_manifest.py --root WORKSPACE --manifest MANIFEST，核对 sha256 映射中的每个文件并拒绝越界路径。
4. 发布时再运行项目自身的源快照、功能、时序和 Flash 图像校验。通用哈希脚本只做文件一致性，不替代这些检查。

详细操作与迁移规则见 [SKILL.md](SKILL.md)，案例见 [references/case.md](references/case.md)。

## 已验证效果

当前最终清单绑定 219 项文件，创建前已通过项目校验；通用校验器会用现有清单与篡改/缺失/越界负例再次验证。

集合本次实际执行结果见上一级 `validation.json`。不要把文件齐全/说明校验通过理解成新的上板或综合通过。

## 失效条件与边界

哈希不证明功能正确性或清单真实性；核验清单应来自可信发布过程。通用脚本只支持 sha256 字段，不自动猜测其他清单格式。固件更新后的真实板端执行仍需独立确认。

## 原始依据

- `VGA显示部分/verify_package.py` → [source_01.py](references/source/source_01.py)
- `VGA显示部分/verify_release.py` → [source_02.py](references/source/source_02.py)
- `VGA显示部分/verify_flash_image.py` → [source_03.py](references/source/source_03.py)
- `软核/scripts/embed_firmware.tcl` → [source_04.tcl](references/source/source_04.tcl)
- `VGA显示部分/release/image_manifest.json` → [source_05.json](references/source/source_05.json)
- `VGA显示部分/release/flash_record.json` → [source_06.json](references/source/source_06.json)

`references/source/` 是溯源快照；其中脚本可能仍依赖原工程路径、工具、模块或设备，不是可直接跨项目运行的入口。明确标为 `scripts/` 的可执行副本按本页说明运行。迁移时使用自己的参数、硬件合同和验证，保留修改前后证据。
