# 工程清理记录（2026-11-04）

已完成：删除 175 项缓存、日志或工具依赖链接；成功删除项包含 281 个普通文件、6,141,190 字节。外部 node_modules 链接仅删除链接本身，外部依赖保持完整。部分未完成目录可能已删除部分文件，未计入以上统计。

保护：当前最终发布清单绑定的 219 个文件，以及软核 CPU/FFT IP 完整目录。当前源码、实测数据、校正参数、当前固件与必要 Flash 备份保持完整。独立 github_upload 仓库、供应商资料和 UI 虚拟环境未清理。

验证：FINAL_PACKAGE_VERIFIED 219、RELEASE_VERIFIED、FLASH_IMAGE_VERIFIED 均通过。PC 测试运行 66 项，55 项通过，11 项因现有虚拟环境 Qt DLL 加载失败而未能执行；系统 Python 另缺少 numpy。未修改依赖环境。

自动审批拒绝原批量删除：其认为旧发布包、仿真数据、报告及构建目录可能含不可恢复证据，概括性清理授权不足。因此下列 129 项未执行，等待明确确认。

## 待确认删除项

| 路径 | 判断依据 |
|---|---|
| `tmp` | 历史临时目录、旧发布包或可重建仿真数据 |
| `releases` | 历史临时目录、旧发布包或可重建仿真数据 |
| `.poster-review` | 历史临时目录、旧发布包或可重建仿真数据 |
| `scope_board_my0wxr9k` | 历史单次测试临时工作目录 |
| `scope_persist_20261029_2qar_h42` | 历史单次测试临时工作目录 |
| `scope_units_1l6353da` | 历史单次测试临时工作目录 |
| `scope_units_4br9zmfn` | 历史单次测试临时工作目录 |
| `scope_units_6dvnqxte` | 历史单次测试临时工作目录 |
| `scope_units_8v50ymvp` | 历史单次测试临时工作目录 |
| `scope_units_jeu4m421` | 历史单次测试临时工作目录 |
| `constraints_diff.html` | 历史日志、缓存、波形或检查中间文件 |
| `dfx_runtime.txt` | 历史日志、缓存、波形或检查中间文件 |
| `xelab.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\sim\vectors` | 历史临时目录、旧发布包或可重建仿真数据 |
| `FPGA\sim\expected` | 历史临时目录、旧发布包或可重建仿真数据 |
| `软核\build\dfx_runtime.txt` | 已由当前显示工程取代的软核构建产物 |
| `软核\build\recreate_cpu_ip.tcl` | 已由当前显示工程取代的软核构建产物 |
| `软核\build\scope_cpu.disasm` | 已由当前显示工程取代的软核构建产物 |
| `软核\build\scope_cpu.elf` | 已由当前显示工程取代的软核构建产物 |
| `软核\build\scope_cpu.map` | 已由当前显示工程取代的软核构建产物 |
| `软核\build\scope_cpu.obj` | 已由当前显示工程取代的软核构建产物 |
| `软核\build\scope_cpu_before_cdc.bit` | 已由当前显示工程取代的软核构建产物 |
| `软核\build\scope_cpu_before_cdc.dcp` | 已由当前显示工程取代的软核构建产物 |
| `软核\build\scope_cpu_routed.dcp` | 已由当前显示工程取代的软核构建产物 |
| `软核\build\scope_cpu_runtime.bit` | 已由当前显示工程取代的软核构建产物 |
| `软核\build\scope_cpu_synth.dcp` | 已由当前显示工程取代的软核构建产物 |
| `软核\build\scope_cpu_test.bit` | 已由当前显示工程取代的软核构建产物 |
| `软核\build\system` | 已由当前显示工程取代的软核构建产物 |
| `软核\build\test_scope_cpu.exe` | 已由当前显示工程取代的软核构建产物 |
| `软核\build\test_scope_cpu.obj` | 已由当前显示工程取代的软核构建产物 |
| `软核\build\xelab.log` | 已由当前显示工程取代的软核构建产物 |
| `软核\build\xelab.pb` | 历史日志、缓存、波形或检查中间文件 |
| `软核\build\xsim.jou` | 已由当前显示工程取代的软核构建产物 |
| `软核\build\xsim.log` | 已由当前显示工程取代的软核构建产物 |
| `软核\build\xvlog.log` | 已由当前显示工程取代的软核构建产物 |
| `软核\build\xvlog.pb` | 历史日志、缓存、波形或检查中间文件 |
| `VGA显示部分\release\archive_20261031_before_handoff_20261101` | 未绑定的旧镜像备份 |
| `PC\tools\finalize_handoff_release_20261101.py` | 旧发布包的一次性组包代码或失效启动代码 |
| `PC\tools\launch_frozen_release.py` | 旧发布包的一次性组包代码或失效启动代码 |
| `outputs\rewrite_part2_20261102\原始模板备份.docx` | 报告编辑前历史备份 |
| `outputs\rewrite_part4_20261102\修改第四部分前备份.docx` | 报告编辑前历史备份 |
| `outputs\otr_report_update_20261102\修改前备份\基于FPGA的数字示波器.docx` | 报告编辑前历史备份 |
| `outputs\otr_report_update_20261102\修改前备份\旧报告.docx` | 报告编辑前历史备份 |
| `FPGA\reports\ad9226\20261021_193104_646cd731\project` | 编译缓存、仿真工作目录或重复文档工具依赖 |
| `FPGA\reports\ad9226\20261021_193730_820c2320\project` | 编译缓存、仿真工作目录或重复文档工具依赖 |
| `FPGA\reports\capture\20261021_214113_8f0a79c3\project` | 编译缓存、仿真工作目录或重复文档工具依赖 |
| `FPGA\reports\dds\20261021_200909_521f7e77\project` | 编译缓存、仿真工作目录或重复文档工具依赖 |
| `FPGA\reports\dds\20261021_201056_a11d9e21\project` | 编译缓存、仿真工作目录或重复文档工具依赖 |
| `FPGA\reports\dds\20261021_201510_0aefce03\project` | 编译缓存、仿真工作目录或重复文档工具依赖 |
| `FPGA\reports\innovation\20261022_143341_a1fd011f\project` | 编译缓存、仿真工作目录或重复文档工具依赖 |
| `FPGA\reports\loopback\20261021_203438_32689c3d\project` | 编译缓存、仿真工作目录或重复文档工具依赖 |
| `FPGA\reports\loopback\20261021_205120_4aa69a61\project` | 编译缓存、仿真工作目录或重复文档工具依赖 |
| `FPGA\reports\measure\20261021_220956_1f29ca59\project` | 编译缓存、仿真工作目录或重复文档工具依赖 |
| `FPGA\reports\measure\20261021_233507_a175ac17\project` | 编译缓存、仿真工作目录或重复文档工具依赖 |
| `FPGA\reports\measure\20261021_233853_998a2694\project` | 编译缓存、仿真工作目录或重复文档工具依赖 |
| `FPGA\reports\measure\20261027_223733_f8cf3549\project` | 编译缓存、仿真工作目录或重复文档工具依赖 |
| `FPGA\reports\measure_development\root_artifacts_20261021\xvlog.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\multires\20261022_125121_d0347ac8\project` | 编译缓存、仿真工作目录或重复文档工具依赖 |
| `FPGA\reports\safe\20261020_201544_99511ba9\xelab.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\safe\20261020_201544_99511ba9\xvlog.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\safe\20261021_003958_8e9f1fdb\xelab.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\safe\20261021_003958_8e9f1fdb\xvlog.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\safe\20261021_185006_4b624be1\xelab.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\safe\20261021_185006_4b624be1\xvlog.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\safe\20261021_185321_11060e49\xelab.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\safe\20261021_185321_11060e49\xvlog.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\safe\20261021_185441_6d8ed82a\xelab.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\safe\20261021_185441_6d8ed82a\xvlog.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\safe\20261021_185552_45617a10\xelab.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\safe\20261021_185552_45617a10\xvlog.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\safe\20261021_193101_d9cf410e\xelab.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\safe\20261021_193101_d9cf410e\xvlog.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\safe\20261021_200955_ef3bd3e0\xelab.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\safe\20261021_200955_ef3bd3e0\xvlog.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\safe\20261022_182001_1b44c93f\xelab.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\safe\20261022_182001_1b44c93f\xvlog.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\safe\20261022_182519_45bcda85\xelab.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\safe\20261022_182519_45bcda85\xvlog.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\safe\20261025_152206_627662e1\xelab.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\safe\20261025_152206_627662e1\xvlog.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\20261020_193748_ef89b4d0\xelab.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\20261020_193748_ef89b4d0\xvlog.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\20261020_193847_2156a28d\xelab.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\20261020_193847_2156a28d\xvlog.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\20261020_194258_c7df2b1b\xvlog.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\20261020_194322_3b86cb0e\xelab.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\20261020_194322_3b86cb0e\xvlog.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\20261020_194420_7adf2fa2\xelab.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\20261020_194420_7adf2fa2\xvlog.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\20261020_194528_f09d7c31\xelab.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\20261020_194528_f09d7c31\xvlog.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\20261020_194642_41989672\xelab.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\20261020_194642_41989672\xvlog.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\20261021_003957_c63dd278\xelab.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\20261021_003957_c63dd278\xvlog.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\20261021_200934_2dff2aab\xelab.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\20261021_200934_2dff2aab\xvlog.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\20261021_214244_503b8999\xelab.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\20261021_214244_503b8999\xvlog.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\20261021_221045_f7f826fb\xelab.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\20261021_221045_f7f826fb\xvlog.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\20261022_181956_eb933919\xelab.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\20261022_181956_eb933919\xvlog.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\20261022_182511_45876422\xelab.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\20261022_182511_45876422\xvlog.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\20261023_000320_993e2553\xelab.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\20261023_000320_993e2553\xvlog.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\20261023_001156_d29c313a\xelab.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\20261023_001156_d29c313a\xvlog.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\20261023_162611_9e674e67\xelab.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\20261023_162611_9e674e67\xvlog.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\20261025_235058_04d2cde9\xelab.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\20261025_235058_04d2cde9\xvlog.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\20261027_222637_f8c1f245\xelab.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\20261027_222637_f8c1f245\xvlog.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\20261027_223547_39add566\xelab.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\20261027_223547_39add566\xvlog.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\tool_preflight\xelab.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\scope_pkg\tool_preflight\xvlog.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\spectrum\20261022_132343_c1e2f042\project` | 编译缓存、仿真工作目录或重复文档工具依赖 |
| `FPGA\reports\uart\20261022_005150_d8eecf8f\project` | 编译缓存、仿真工作目录或重复文档工具依赖 |
| `FPGA\reports\uart\20261022_005708_a88bf502\project` | 编译缓存、仿真工作目录或重复文档工具依赖 |
| `FPGA\reports\uart\20261022_010136_ca06e863\project` | 编译缓存、仿真工作目录或重复文档工具依赖 |
| `FPGA\reports\safe_project\20261021_185844_cb49fd95\wrapper\failure.wdb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\safe_project\20261021_190440_fe649239\core\success.wdb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\reports\safe_project\20261021_190440_fe649239\wrapper\success.wdb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\project\scope_smoke\scope_smoke.sim\sim_1\behav\xsim\tb_smoke_behav.wdb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\project\scope_smoke\scope_smoke.sim\sim_1\behav\xsim\xelab.pb` | 历史日志、缓存、波形或检查中间文件 |
| `FPGA\project\scope_smoke\scope_smoke.sim\sim_1\behav\xsim\xvlog.pb` | 历史日志、缓存、波形或检查中间文件 |

## 权限阻碍

以下两个临时缓存目录未删净，原因是 Windows 拒绝访问：

- `软核\build\tool_tmp`
- `VGA显示部分\output\tool_tmp`

完整执行记录见 cleanup_results_20261104.json；原候选及保护路径见 cleanup_plan_20261104.json。
