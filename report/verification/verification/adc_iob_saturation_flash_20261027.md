# 整帧饱和统计与 ADC 输入 IOB 固化验收

2026-10-27 更新：用户授权后，已将包含整帧饱和计数、ADC 输入 IOB 和三种采集模式的 0xA3261027 合并镜像重新下载并固化。完整备份原 Flash 8 MiB，工具校验和独立二进制读回逐字节一致。用户确认真正断电重启后，仅只读检查：Master SPI 模式 001，DONE=1、EOS=1、CRC_ERROR=0；COM12/921600 读回版本 0xA3261027、能力31、默认配置和零错误状态通过。当前启动镜像已为 0xA3261027；下文未固化/旧启动镜像的描述为此前历史状态。任意波形下载和汇总 CSV 继续暂停。当前 SW0 OFF、模块外部5 V关闭；使用时先打开模块5 V，稳定后再将SW0拨到ON。

状态：`PASS_FLASH_PROGRAM_COLD_BOOT_VERIFIED`。

已验收 bitstream SHA256：`5495e0f17a09dfdd6ab560b55c7f1f60f4dca73e44c0574be457cfe488a40a4b`。

BIN/独立读回 SHA256：`7a19589c3bb89807d369d4c6e7a7ea1a9835b0546b570b56985d82adec7d20e6`。

原 Flash 备份 SHA256：`104d150aac1e5f4e98eaf5d20bb2c9ac3c723431e1913a2b1fe94bec6acec080`。

证据目录：`D:\示波器\FPGA\reports\flash\adc_iob_20261027_160138`。本次使用此前通过19帧实物测试的相同镜像，断电启动检查未重新下载、未重新配置。新版本未重做正式UART长稳验收。
