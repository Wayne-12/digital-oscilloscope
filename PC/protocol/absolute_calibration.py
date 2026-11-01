"""External-reference DC voltage calibration with raw evidence and held-out checks.

Reference voltages and error limits must come from an independent instrument.
DAC codes, nominal voltages, and relative fingerprints are never references.
The result qualifies measured DC points only, not AC or full-range accuracy.
"""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import hashlib
import io
import json
import math
import os
import tempfile

import numpy as np

FORMAT = 'scope-absolute-dc-calibration-v1'
RANGE_ID = 'AD9226-module-original-10Vpp'
SCALE = 10/4095
MAX_PROFILE_BYTES = 2*1024*1024


def firmware_matches(report, build):
    # These releases share the byte-identical ADC mapping (scope_pkg.sv),
    # 25 MSPS capture and original analog range. VGA changes only presentation.
    # Device identity and input-range checks remain required by applicable().
    adc_equivalent = {0xA4261027, 0xA7261029, 0xAF311031}
    original = report.get('firmware_build')
    return original == build or (original in adc_equivalent and build in adc_equivalent)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def dc_statistics(words):
    words = np.asarray(words)
    require(words.shape == (16384,) and words.dtype.kind in 'ui'
            and not np.any(words < 0) and not np.any(words > 65535)
            and not np.any(words & 0xf000), '标定需要完整原始 ADC 帧，禁止 OTR 或保留位')
    require(not np.any((words == 0) | (words == 4095)), '饱和帧不能用于电压标定')
    mean = float(np.mean(words))
    std = float(np.std(words, ddof=1))
    drift = abs(float(np.mean(words[:8192]))-float(np.mean(words[8192:])))
    require(std <= 4 and int(np.ptp(words)) <= 32 and drift <= 1,
            '输入不是稳定直流；检查输出波形、接线、噪声与参考读数')
    return {'mean_raw': mean, 'std_raw': std, 'peak_to_peak_raw': int(np.ptp(words)), 'drift_raw': drift}


def point_from_frame(frame, *, reference_volts, reference_error_volts, role, device_id,
                     instrument, conditions, externally_measured):
    require(externally_measured is True, '必须提供独立仪器的实际电压读数')
    require(role in ('fit', 'check'), '标定点类型必须为拟合点或独立验证点')
    require(number(reference_volts) and -4.9 <= reference_volts <= 4.9,
            '参考电压必须为原量程内的有限实测值')
    require(number(reference_error_volts) and 0 < reference_error_volts <= .1,
            '需填写该读数下参考仪器的最大误差界限，不能填零')
    require(isinstance(device_id, str) and 0 < len(device_id.strip()) <= 256,
            '缺少被标定设备身份')
    require(isinstance(instrument, str) and 3 <= len(instrument.strip()) <= 512,
            '需记录参考仪器型号、编号及误差界限依据')
    require(isinstance(conditions, str) and 3 <= len(conditions.strip()) <= 1024,
            '需记录接线、供电、温度或预热等标定条件')
    require(frame.source == '硬件 UART' and frame.rate == 25000000
            and frame.record_offset == 0 and frame.overview is None and len(frame.words) == 16384
            and type(frame.firmware_build) is int, '需要带固件身份的硬件完整帧，不能使用演示或 ROI')
    stats = dc_statistics(frame.words)
    require(frame.fpga_saturation == {'count': 16384, 'saturated_samples': 0, 'events': 0, 'diagnostic': False},
            '缺少真实完整帧统计，或记录是数字诊断帧')
    return dict(role=role, reference_volts=reference_volts, reference_error_volts=reference_error_volts,
                instrument=instrument.strip(), conditions=conditions.strip(), device_id=device_id,
                firmware_build=frame.firmware_build, rate=frame.rate, timestamp=frame.timestamp,
                captured_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),
                source='hardware-uart', externally_measured=True, **stats)


def save_point(folder, frame, **metadata):
    # Validate before writing anything. A rejected point never enters a session.
    point = point_from_frame(frame, **metadata)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    name = 'raw_'+str(point['timestamp'])+'_'+os.urandom(4).hex()+'.npy'
    path = folder/name
    with path.open('xb') as file:
        np.save(file, frame.words, allow_pickle=False)
    point.update(raw_file=name, raw_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    return point


def validate_points(points, folder):
    require(type(points) is list and 5 <= len(points) <= 32, '至少需要 3 个拟合点和 2 个独立验证点，最多32点')
    folder = Path(folder).resolve()
    identities, timestamps, files = set(), set(), set()
    for point in points:
        require(type(point) is dict, '标定点格式错误')
        name = point['raw_file']
        require(isinstance(name, str) and Path(name).name == name and name.endswith('.npy')
                and '/' not in name and '\\' not in name and ':' not in name,
                '原始证据必须是标定目录内的 NPY 文件')
        path = (folder/name).resolve()
        require(path.parent == folder, '原始证据路径无效')
        with path.open('rb') as file:
            data = file.read(65536)
        require(len(data) < 65536, '原始证据大小无效')
        require(hashlib.sha256(data).hexdigest() == point['raw_sha256'], '原始标定证据哈希不匹配')
        stream = io.BytesIO(data)
        require(np.lib.format.read_magic(stream) == (1, 0), '原始证据 NPY 版本无效')
        shape, fortran, dtype = np.lib.format.read_array_header_1_0(stream)
        require(shape == (16384,) and not fortran and dtype == np.dtype('<u2'), '原始证据数组格式无效')
        stats = dc_statistics(np.load(io.BytesIO(data), allow_pickle=False))
        require(all(number(point.get(k)) and math.isclose(point[k], v, abs_tol=1e-10, rel_tol=1e-10)
                    for k, v in stats.items()), '原始证据与保存的统计不一致')
        require(point.get('source') == 'hardware-uart' and point.get('externally_measured') is True
                and point.get('role') in ('fit', 'check') and point.get('rate') == 25000000
                and type(point.get('firmware_build')) is int and type(point.get('timestamp')) is int,
                '标定点来源或设备元数据无效')
        require(isinstance(point.get('device_id'), str) and point['device_id'].strip()
                and isinstance(point.get('instrument'), str) and len(point['instrument'].strip()) >= 3
                and isinstance(point.get('conditions'), str) and len(point['conditions'].strip()) >= 3,
                '标定点缺少外部参考仪器与条件')
        require(number(point.get('reference_volts')) and -4.9 <= point['reference_volts'] <= 4.9
                and number(point.get('reference_error_volts')) and 0 < point['reference_error_volts'] <= .1,
                '参考读数或最大误差界限无效')
        identities.add((point['device_id'], point['firmware_build'], point['rate']))
        require(point['timestamp'] not in timestamps and name not in files, '拟合与验证必须使用不同采集帧')
        timestamps.add(point['timestamp']); files.add(name)
    require(len(identities) == 1, '不能混用不同设备、固件或采样率的标定点')


def fit(points, folder, tolerance_volts, *, created_at=None):
    validate_points(points, folder)
    require(number(tolerance_volts) and 0 < tolerance_volts <= .1, '需指定直流点检允许误差，范围 (0, 100mV]')
    training = [v for v in points if v['role'] == 'fit']
    checks = [v for v in points if v['role'] == 'check']
    require(len(training) >= 3 and len(checks) >= 2, '需至少3个拟合点和2个未参与拟合的验证点')
    require(max(v['timestamp'] for v in training) < min(v['timestamp'] for v in checks),
            '先完成拟合点采集，再使用后续新帧做独立验证；复位后请新建标定会话')
    x = np.asarray([v['mean_raw'] for v in training])
    y = np.asarray([v['reference_volts'] for v in training])
    require(np.ptp(x) >= 256 and y.min() < -.1 and y.max() > .1
            and np.min(np.abs(y)) <= .05, '拟合点需覆盖负电压、近零和正电压，跨度至少256个ADC码')
    ordered = np.argsort(x)
    require(np.all(np.diff(x[ordered]) >= 16) and np.all(np.diff(y[ordered]) < 0),
            '拟合点需充分分离，且符合模块反相输入极性')
    center = float(x.mean())
    design = np.column_stack((x-center, np.ones(len(x))))
    solution, _, rank, _ = np.linalg.lstsq(design, y, rcond=None)
    slope, centered_intercept = map(float, solution)
    intercept = centered_intercept-slope*center
    require(rank == 2 and .5*SCALE <= -slope <= 2*SCALE, '增益异常；检查参考电压、量程、接线及单位')
    inverse = np.linalg.pinv(design)
    # Conservative propagation of supplied bounded reference errors through the
    # linear fit. ADC frame variation adds an observed repeatability allowance.
    u = np.asarray([v['reference_error_volts']+abs(slope)*max(v['std_raw'], v['drift_raw'], .5)
                    for v in training])
    results = []
    for point in points:
        raw = point['mean_raw']
        if point['role'] == 'check':
            require(x.min() < raw < x.max() and min(abs(raw-x)) >= 16,
                    '验证点必须位于拟合范围内，并与拟合电压点分离至少16个ADC码')
        predicted = slope*raw+intercept
        weights = np.asarray([raw-center, 1.]) @ inverse
        allowance = (point['reference_error_volts'] + float(np.abs(weights) @ u)
                     + abs(slope)*max(point['std_raw'], point['drift_raw'], .5))
        error = predicted-point['reference_volts']
        results.append({'role': point['role'], 'timestamp': point['timestamp'],
                            'reference_volts': point['reference_volts'], 'calibrated_volts': predicted,
                            'before_error_volts': 5-SCALE*raw-point['reference_volts'],
                            'after_error_volts': error, 'allowance_volts': allowance,
                            'acceptance_bound_volts': abs(error)+allowance,
                            'passed': abs(error)+allowance <= tolerance_volts})
    require(all(v['passed'] for v in results), '拟合或独立验证点未满足误差限与参考误差裕量，拒绝发布参数')
    # Both polarities need independently checked points; a single-side check
    # cannot qualify a bipolar correction.
    require(min(v['reference_volts'] for v in checks) < -.05
            and max(v['reference_volts'] for v in checks) > .05, '独立验证点须覆盖正、负电压')
    return {'format': FORMAT, 'status': 'VERIFIED_DC_POINTS', 'source': 'external-voltage-reference',
                'range_id': RANGE_ID, 'device_id': points[0]['device_id'], 'firmware_build': points[0]['firmware_build'],
                'rate': 25000000, 'created_at': created_at or datetime.now(timezone(timedelta(hours=8))).isoformat(),
                'scope': 'DC checked points only; no AC, full-range accuracy, or metrological traceability claim',
                'slope_volts_per_raw': slope, 'intercept_volts': intercept,
                'raw_range': [float(x.min()), float(x.max())], 'voltage_range': [float(y.min()), float(y.max())],
                'display_offset': 5+intercept*SCALE/slope, 'display_gain': -SCALE/slope,
                'tolerance_volts': tolerance_volts, 'points': points, 'verification': results}


def validate_profile(report, folder):
    require(type(report) is dict and report.get('format') == FORMAT
            and report.get('status') == 'VERIFIED_DC_POINTS' and report.get('range_id') == RANGE_ID
            and report.get('source') == 'external-voltage-reference', '不是有效的外部参考直流标定文件')
    rebuilt = fit(report['points'], folder, report['tolerance_volts'], created_at=report['created_at'])
    for key in ('device_id', 'firmware_build', 'rate', 'scope', 'raw_range', 'voltage_range'):
        require(report[key] == rebuilt[key], '标定元数据或适用范围被改变')
    for key in ('slope_volts_per_raw', 'intercept_volts', 'display_offset', 'display_gain'):
        require(number(report.get(key)) and math.isclose(report[key], rebuilt[key], rel_tol=1e-10, abs_tol=1e-10),
                '标定系数与原始证据重算不一致')
    # Return newly computed validation results; never trust saved PASS flags.
    return rebuilt


def load_profile(path):
    path = Path(path)
    require(path.stat().st_size <= MAX_PROFILE_BYTES, '标定文件过大')
    report = json.loads(path.read_text(encoding='utf-8-sig'))
    return validate_profile(report, path.parent)


def save_profile(path, report):
    path = Path(path)
    validated = validate_profile(report, path.parent)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.absolute-', suffix='.tmp', delete=False) as file:
            temporary = Path(file.name)
            json.dump(validated, file, ensure_ascii=False, indent=2, allow_nan=False)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def applicable(report, frame, device_id):
    if (frame is None or frame.source != '硬件 UART' or device_id != report['device_id']
            or not firmware_matches(report, frame.firmware_build) or frame.rate != report['rate']):
        return False
    raw = frame.words & 4095
    low, high = float(raw.min()), float(raw.max())
    if frame.fpga_measurement is not None:
        low = min(low, 2047-frame.fpga_measurement['maximum'])
        high = max(high, 2047-frame.fpga_measurement['minimum'])
    if frame.overview is not None:
        low = min(low, min(2047-b[1] for b in frame.overview.buckets))
        high = max(high, max(2047-b[0] for b in frame.overview.buckets))
        if any(b[2] for b in frame.overview.buckets):
            return False
    stats = frame.fpga_saturation
    if (np.any(frame.words & 0x8000) or stats is None or stats['diagnostic']
            or stats['saturated_samples'] or (frame.fpga_spectrum is not None and frame.fpga_spectrum['clipped'])):
        return False
    # Do not extrapolate beyond the actually observed calibration input range.
    return report['raw_range'][0] <= low <= high <= report['raw_range'][1]
