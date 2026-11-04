# 测试数据来源

data/measured 下的 CSV 来自工作区根目录的实物采集导出；data/model_reference 来自原参考数据目录，属于模型生成数据。
measurement_data.xlsx 来自 outputs/otr_retest_20261102/示波器测量数据.xlsx。
overload_data.xlsx 来自同目录 OTR真实过载_待测数据表.xlsx，仅保留填有实测数据的采集记录。
dc_calibration_data.xlsx 来自 outputs/measurement_20261029/误差1百分比加3字/实测值.xlsx。保留原有测量及离线计算值；参考表分辨率条件需结合原验证记录理解，离线计算不扩大校正适用范围。
frequency_response_data.xlsx 来自 outputs/bandwidth_01a1a0e3/幅频响应与带宽.xlsx。超过 12.5 MHz 的输入读数不直接构成 25 MSPS 系统的模拟带宽结论。

工作簿均只保留数据与必要字段名；备注、用途说明、计划值、测量方法、条件说明与结论未放入数据表。原始采集数值与工作簿缓存数值保持一致，未将空白改为零。
CSV 清理统计见 data_cleanup.json。源文件路径与哈希见 path_mapping.json。
