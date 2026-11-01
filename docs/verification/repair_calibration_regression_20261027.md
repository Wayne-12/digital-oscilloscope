# 校准基线、AWG接口与仿真环境修复（2026-10-27）

本轮按用户要求处理增益基线和完整仿真回归，并检查相关隐藏问题。40分钟短稳测试已按用户要求中止、恢复原配置并暂停监控；不会自动恢复，不能以其未完成结果认定短稳通过。

## 校准条件与新基线

用户确认建立旧基线后调过实体旋钮，并确认本轮保持旋钮、接线与供电不变。因此此前−74.192%的差异不能直接作为软件故障判据。首次校准因模块未就绪返回ERR_BUSY，未取得样本也未修改基线；用户确认外部5V及SW0 OFF→ON后重新执行。

两轮独立真实闭环校准各35帧，总计70帧；第一轮建立当前设置的相对参考，第二轮使用第一轮参考进行独立验证。直流增益分别为0.071377559和0.071395360 ADC码/DAC码，重复差+0.024940%；两轮R²均约0.999989，四档幅度单调，七点频响、独立零点/直流验证通过，原配置逐字节恢复，通信错误新增为零。当前设置相对旧基线0.111645376约下降36.068%；它与先前−74.192%的记录对应不同的旋钮状态，不应混用。

已更新 `PC/ui/hardware_calibration_baseline.json` 与 `hardware_calibration_last.json`；新文件包含用户条件确认、旧基线SHA256和独立重复验证路径。旧基线完整备份在 `../../FPGA/reports/calibration_rebaseline/20261027_220528/previous_baseline.json`，新基线及70帧原始码、两轮报告位于同目录。当前仍为DAC＋线缆＋ADC的组合链路相对校准，没有外部电压参考，不能写成绝对精度校准。

## 已修复的仿真入口问题

- 为 `tb_system_case`、`tb_uart_bytes`、`tb_uart_bits` 显式连接AWG扩展端口；旧场景保持标准DDS范围，AWG由专用测试覆盖。
- 为板端DDS参考测试显式关闭AWG输入，避免悬空接口。
- 将已有 `tb_awg` 纳入默认独立单元入口，检查命令拒绝、表事务及逐DAC码输出。
- 新增 `simulation_environment.py`：为Vivado/XSim及其C编译子进程设置可写的英文TEMP/TMP、独立应用目录与已安装Tcl仓库；同时对源码/工程提供英文路径别名。配置只作用于当前进程树，既有其他盘符不覆盖。
- 原生批处理回归使用本轮独立工程目录，保留显式顶层与手动依赖顺序；包文件必须在首次加入源文件时排在依赖模块之前。避免自动层次更新清空多顶层项目的所选测试台，也避免事后重排设计文件未同步仿真继承顺序的问题。
- 原生各套件的清理路径统一读取同一个项目目录，保留删除前的绝对路径与重解析点检查。

Windows一键入口为 `FPGA/scripts/run_regression.ps1`，例如 `./FPGA/scripts/run_regression.ps1 -Seeds 20261027`。它在启动Python前准备英文工作区别名，解决受限进程无法自行创建盘符的问题；只移除本次新建的映射，保留原有映射。`-UnitsOnly -Tests awg` 可运行单元专项，`-SystemOnly` 可运行系统层。默认不限制层时执行完整分层回归，不会操作实物。该入口的AWG专项已实际通过。

工具行为参考AMD关于[显式顶层与编译顺序](https://docs.amd.com/r/2021.2-English/ug895-vivado-system-level-design-entry/Specifying-the-Top-Module-and-Reordering-Source-Files)及[reorder_files](https://docs.amd.com/r/en-US/Vivado-Design-Suite-Tcl-Command-Reference-Guide-UG835/reorder_files?contentId=LPtITuEOsLnGZEz96SLgSw)的说明；修复效果以本机2025.2实跑结果为准，没有安装厂商补丁或切换仿真器。

单独FFT三个测试根（整数平方根、FFT包装器、42个频谱场景）已通过，原先错误43-3409未再出现。8个系统场景已通过。原生smoke初始与删除生成目录后的清理重建结果一致，固定种子20261027、450个检查边沿，均通过。最终完整分层回归结果在下方补记。

## 额外复现并修复的隐藏问题

1. **AWG上传的输入并未冻结。** `encode_table`会消耗一次性迭代器，而上传结束又读取它进行比较，导致实际成功提交后误报不一致；调用方在进度回调中修改原列表也会产生同类误报。现在在发送BEGIN前一次性复制输入，同一次事务始终使用同一份数据。新增测试覆盖迭代器、传输回调修改输入及最终读回。
2. **校准指纹内部增益缺少一致性检查。** 旧代码分别检查各字段范围，却能接受相对增益与实测/参考增益互相矛盾的指纹，可能产生错误显示校正。现在验证 `gain≈dc_gain/reference_gain`，并拒绝极性或倍率矛盾。新增测试覆盖三种损坏字段。新旧保存基线均保持合法。
3. **实物AWG验收未完整保留用户波形表。** 原脚本会留下测试表，且在开始时已选用任意波形的情况下拒绝执行后仍可能改变选择状态。现在测试前读回并保存原有效表，结束逐点恢复原表、校验CRC并恢复原选择。已在“原表未选用”和“原表已选用”两种实物边界下各完成4帧专项并确认恢复。若开始时没有有效表，固件没有清表命令，脚本明确记录未选用的测试表可能留在RAM中，不伪称恢复了无表状态。

新增测试在修复前真实复现上述失败；修复后127项PC回归通过。日志：`../../tmp/hidden_awg_before_20261027.log`、`../../tmp/hidden_calibration_before_20261027.log`、`../../tmp/hidden_fixes_pc_tests_20261027.log`。

修复后另外完成16帧实物功能回归：AWG四波形与表事务、测量/FFT四波形，以及上述两种AWG表恢复边界均PASS；各专项配置恢复，协议解析及意外FPGA错误新增为零。AWG各次专项中的五次非法命令拒绝为预期结果。加上本轮两轮校准，共86帧真实ADC记录。证据：`../../FPGA/reports/repair_validation_20261027/`，已选表边界另见 `awg_selected_restore/selected_state_verification.json`。

本轮没有修改产品FPGA RTL、约束或重新固化Flash。当前板端仍为0xA4261027；发布bitstream身份不变。对隐藏问题的结论仅限于已检查和已运行的用例，不表示证明不存在任何其他缺陷。

## 最终完整回归

最终状态：**PASS**。工具为Vivado/XSim 2025.2，行为仿真，随机种子20261027；本轮没有进行SDF时序仿真或重新布局布线。

- 11类独立单元全部通过（共13个测试根，FFT包括整数平方根、包装器和频谱主测试）。FFT 42个主场景、43008个输出点，AWG 33个命令场景、2066个DAC码逐点核对。
- 按已有源码哈希门禁复用两个当前源码一致的PASS单元报告，未复用失败清单：`../../FPGA/reports/unit/20261027_220138_267347/manifest.json` 与 `../../FPGA/reports/unit/20261027_223250_694447/manifest.json`。
- 12项基础/集成记录全部PASS：smoke、scope_pkg、safe、ad9226、dds、capture、loopback、measure、uart、multires、spectrum、innovation。其中safe/ADC/DDS/capture复用相应独立单元，其他集成套件按本轮顺序实跑。
- 频谱集成核对44帧、45056个频谱点及2048个ROI点，原有负向断言测试保留；包络集成80个场景通过。
- 8个系统场景及9项组合用例全部PASS，覆盖安全启动、中码回环、10/100 kHz正弦、相干1 MHz、单点尖峰、OTR数字注入、UART故障和紧急关闭。
- 原生smoke完成初始运行、仅删除已校验边界内的生成目录、清理重建及固定种子一致性检查；测量集成包含原生工程复核。所有功能断言、错误门禁保持，不新增告警豁免。
- 总报告：`../../FPGA/reports/system/20261027_223504_45686965/manifest.json`。清单记录unit→integration→system三层，verdict=PASS，源码身份复核通过，系统临时构建目录已按边界检查清理。
- 最后一轮移除仅本轮手动创建的Y/Z别名后，直接运行 `run_regression.ps1 -SystemOnly -Seeds 20261027`，自动准备工作路径、8场景回归和退出清理均通过。独立报告：`../../FPGA/reports/system/20261027_225049_174fb8fc/manifest.json`。这验证了启动器不依赖本轮预先配置的盘符。

可复现最终聚合命令（相对工作区根目录）：

```powershell
.\.venv-ui\Scripts\python.exe FPGA\scripts\run_system_regression.py --seeds 20261027 --unit-reports FPGA\reports\unit\20261027_220138_267347 FPGA\reports\unit\20261027_223250_694447
```

从无预置环境开始，使用前述PowerShell一键入口；不传单元报告时，会从头构建并运行全部所需单元与集成用例。40分钟短稳维持用户中止状态，不纳入本轮PASS结论。
