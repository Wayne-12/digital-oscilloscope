# 触发类型循环选择

触发页面九种类型按原顺序双向循环：上升沿、下降沿、窗口进入、窗口离开、正脉宽、负脉宽、欠幅、过幅、超量程。最前项向左到最后项，最后项向右回到最前项。草稿修改后仍须中心键确认。

仅修改panel_model.c中类型索引的边界行为；触发协议编号和采集RTL不变。test_panel.c新增两端回绕、双向遍历全部九项以及确认前后参数隔离检查，TRIGGER_CYCLE_TEST_PASS及所有原C回归通过。固件text25976、data2、bss2372字节，链接器栈保护通过。

本次候选镜像在diagnostics/trigger_cycle_20261101/output/。以修改前标准output/cpu_vga_runtime.bit为基础，经UpdateMEM显式嵌入新ELF；没有重新布局布线，没有改动FPGA逻辑，保留最新控制权交接修复。program.log记录已知目标1234-tulA、XC7A35T、DONE=1及BOARD_PROGRAM_PASS。

本次候选的源码、ELF、基底位流和生成位流哈希由candidate_manifest.json绑定，SPI镜像另由release/image_binding.json绑定。固化前再次核验上述文件。识别实际N25Q64，JEDEC 20 BA 17，先完整备份8MiB，再擦除、空白检查、编程校验和独立回读逐字节比较。最终QSPI加载MODE=001、DONE=1、EOS=1、CRC_ERROR=0，全部通过。

标准output和release已同步本次版本。更新前镜像、ELF及清单保存在release/archive_before_trigger_cycle_20261101/；本次完整Flash恢复备份及读回证据见release/latest_flash_report.txt指向的目录。标准运行位流和已测试候选位流的配置负载哈希一致，只有头部生成时间不同。verify_release.py及verify_flash_image.py均通过。

用户已完全断开开发板电源与USB，确认灯熄灭后重上电，回复“一切OK”，确认自动启动及上升沿/超量程双向回绕正常。随后只读检查MODE=001、DONE=1、EOS=1、CRC_ERROR=0，FLASH_COLD_BOOT_REGISTERS_PASS与PANEL_FLASH_BOOT_PASS均通过，未执行下载或重新配置。固化和真正冷启动验证完成。

无需再次断电。恢复模块5V、SW0 OFF→ON，并将SW7 OFF后使用本地按键。
