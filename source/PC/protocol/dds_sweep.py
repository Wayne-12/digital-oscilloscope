"""Bounded DAC->ADC survey. Digital limit stays 12.5 MHz.

Results describe discrete test points of the combined loopback, never an
independent DAC bandwidth, absolute voltage, THD, SFDR or clock accuracy.
"""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import hashlib
import json
import math
import struct

import numpy as np
import scope_protocol as p
import hardware_calibration as hc
import analog_acceptance as aa
import awg

RATE = 25000000
N = 16384
PEAK = 819
TZ = timezone(timedelta(hours=8))
WAVES = ('sine', 'square', 'triangle')
FREQUENCIES = (10000, 25000, 50000, 100000, 250000, 500000, 1000000,
               1500000, 2000000, 2500000, 3000000, 4000000, 5000000,
               6000000, 6250000, 7500000, 8000000, 9000000, 10000000,
               11000000, 12000000, 12400000, 12490000, 12499000)


def check(condition, message):
    if not condition:
        raise ValueError(message)


def actual_frequency(frequency):
    check(type(frequency) is int and 0 <= frequency <= 12500000, 'DDS 频率超出原有数字设置范围')
    return ((frequency*(1 << 32)+12500000)//RATE)*RATE/(1 << 32)


def stimulus(wave, frequency, phase=0, enabled=True):
    check(type(wave) is int and wave in (0, 1, 2), '扫频只使用标准 DDS 波形')
    actual_frequency(frequency)
    check(type(phase) is int and phase in (0, 45, 90, 135), '无效测试相位')
    return struct.pack('<BBIIHi', wave, int(enabled), frequency, phase*(1 << 32)//360, PEAK, 0)


def plan():
    result = [(0, f, 0) for f in (0, 1, 10, 100, 1000, 5000)]
    for wave in range(3):
        for frequency in FREQUENCIES:
            result.append((wave, frequency, 0))
            if frequency >= 5000000:
                result.append((wave, frequency, 90))
        result.extend((wave, 12500000, phase) for phase in (0, 45, 90, 135))
    return result


def analyze(words, frequency, wave):
    stats = aa.raw_statistics(words)
    check(stats['otr_samples'] == stats['saturated_samples'] == 0, '出现模拟过载，终止扫频')
    y = 2047-(np.asarray(words) & 4095).astype(float)
    actual = actual_frequency(frequency)
    distance = min(actual, RATE/2-actual)
    result = {'requested_hz': frequency, 'dds_hz_relative_to_nominal_clock': actual,
              'raw_min': stats['minimum_raw'], 'raw_max': stats['maximum_raw'],
              'vpp_adc_codes': int(np.ptp(y)), 'std_adc_codes': float(np.std(y)),
              'observable_edge_cycles': distance*N/RATE, 'basic_pass': False,
              'frequency_scope': 'relative to the same nominal 25 MHz clock; not independent frequency accuracy'}
    if frequency == 0:
        result['status'] = 'DC_BOUNDARY_OBSERVATION'
        return result
    if frequency == RATE//2:
        result['status'] = 'NYQUIST_BOUNDARY_ONLY'
        return result
    if distance*N/RATE < 4:
        result['status'] = 'INSUFFICIENT_RECORD_CYCLES'
        return result
    phase = np.arange(N)*(2*np.pi*actual/RATE)
    design = np.column_stack((np.sin(phase), np.cos(phase), np.ones(N)))
    coefficients, _, rank, _ = np.linalg.lstsq(design, y, rcond=None)
    check(rank == 3, '正弦拟合退化；不能判定该频点')
    amplitude = float(np.hypot(coefficients[0], coefficients[1]))
    residual = float(np.sqrt(np.mean((y-design@coefficients)**2)))
    normalized = residual/max(float(np.std(y)), 1e-20)
    power = np.abs(np.fft.rfft((y-y.mean())*np.hanning(N)))
    peak_bin = int(np.argmax(power[1:])+1)
    peak_frequency = peak_bin*RATE/N
    peak_error = abs(peak_frequency-actual)
    passed = amplitude >= 4 and np.ptp(y) >= 8 and peak_error <= 1.5*RATE/N
    if wave == 0:
        passed = passed and normalized <= .10
    result.update(status='PASS' if passed else 'NOT_PASSED', basic_pass=bool(passed),
                  fitted_peak_adc_codes=amplitude, fundamental_residual_ratio=normalized,
                  fft_peak_hz=peak_frequency, fft_bin_hz=RATE/N, fft_peak_error_hz=peak_error,
                  fit_condition=float(np.linalg.cond(design)),
                  criterion='sine sampled-tone residual <=10%' if wave == 0 else
                            'fundamental presence only; edge/shape quality not qualified')
    # Diagnostic in-band components only: these are not a qualified THD figure.
    if 5*actual < RATE/2:
        harmonics = np.column_stack([np.ones(N)]+[v for k in range(1, 6)
                                      for v in (np.sin(k*phase), np.cos(k*phase))])
        values, _, harmonic_rank, _ = np.linalg.lstsq(harmonics, y, rcond=None)
        if harmonic_rank == 11:
            fundamental = float(np.hypot(values[1], values[2]))
            result['in_band_h2_h5_ratios_not_thd'] = [float(np.hypot(values[k], values[k+1]))/max(fundamental, 1e-20)
                                                    for k in (3, 5, 7, 9)]
    return result


def summarize(frames):
    by_wave = {}
    for wave in range(3):
        rows = [row for row in frames if row.get('verified') and row['wave'] == wave
                and row['case'] == 'survey']
        anchors = [row['analysis']['fitted_peak_adc_codes'] for row in frames
                   if row.get('verified') and row['wave'] == wave and row['frequency_hz'] == 100000
                   and row['case'] in ('survey', 'anchor') and row['analysis'].get('basic_pass')]
        anchor = float(np.median(anchors)) if anchors else None
        grouped = {}
        for row in rows:
            grouped.setdefault(row['frequency_hz'], []).append(row)
            amplitude = row['analysis'].get('fitted_peak_adc_codes')
            if anchor and amplitude and amplitude > 0:
                row['analysis']['relative_to_100khz_db'] = 20*math.log10(amplitude/anchor)
        passed, flat, rejected, observations = [], [], [], []
        for frequency, entries in sorted(grouped.items()):
            expected_phases = {0, 45, 90, 135} if frequency == 12500000 else ({0, 90} if frequency >= 5000000 else {0})
            complete = all(sum(row['phase_degrees'] == phase for row in entries) == 2 for phase in expected_phases)
            if not all(row['analysis']['status'] in ('PASS', 'NOT_PASSED') for row in entries):
                observations.append(frequency)
                continue
            amplitudes = [row['analysis']['fitted_peak_adc_codes'] for row in entries]
            variation = (max(amplitudes)-min(amplitudes))/max(float(np.mean(amplitudes)), 1e-20)
            # Includes repeat acquisitions and both programmed phases at high frequencies.
            good = complete and all(row['analysis']['basic_pass'] for row in entries) and variation <= .10
            if good:
                passed.append(frequency)
                if anchor and all(abs(row['analysis'].get('relative_to_100khz_db', math.inf)) <= 3 for row in entries):
                    flat.append(frequency)
            else:
                rejected.append(frequency)
        by_wave[WAVES[wave]] = {'passed_discrete_hz': passed, 'relative_3db_discrete_hz': flat,
                               'not_passed_discrete_hz': rejected, 'observation_only_hz': observations,
                               'reference_100khz_peak_adc_codes': anchor,
                               'scope': 'combined loopback discrete points; no continuous bandwidth qualification'}
    return by_wave


def run(worker, folder, *, progress=print, settle_seconds=.04, cases=None):
    out = Path(folder)
    out.mkdir(parents=True, exist_ok=False)
    report = {'format': 'scope-dds-loopback-survey-v1', 'source': 'hardware-uart', 'verdict': 'FAIL',
              'digital_limit_hz': 12500000, 'sample_rate': RATE, 'stimulus_peak_code': PEAK,
              'started_at': datetime.now(TZ).isoformat(), 'frames': [], 'restored': False,
              'absolute_amplitude_qualified': False, 'independent_dac_quality_qualified': False,
              'scope': 'DAC+cable+ADC fixed-knob survey; discrete points only; no THD/SFDR/AC bandwidth qualification',
              'criteria': {'minimum_vpp_codes': 8, 'minimum_fitted_peak_codes': 4,
                           'minimum_cycles_from_dc_and_nyquist': 4, 'sine_residual_ratio_max': .10,
                           'repeat_phase_amplitude_variation_max': .10, 'relative_amplitude_screen_db': 3}}
    original = mode = table_state = baseline = None
    seen = set()

    def save():
        (out/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')

    def acquire(wave, frequency, phase, trial, label):
        if worker.shutdown.is_set() or worker.cancel_capture.is_set():
            raise InterruptedError('扫频取消')
        frame = worker.capture(3)
        name = f'{len(report["frames"]):03d}_{label}_w{wave}_f{frequency}_p{phase}_r{trial}.npy'
        path = out/name
        np.save(path, frame.words, allow_pickle=False)
        row = {'file': name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
               'case': label, 'wave': wave, 'frequency_hz': frequency, 'phase_degrees': phase,
               'repeat': trial, 'timestamp': frame.timestamp, 'rate': frame.rate, 'trigger': frame.trigger,
               'verified': False, 'measurement': frame.fpga_measurement, 'spectrum': frame.fpga_spectrum,
               'saturation': frame.fpga_saturation}
        report['frames'].append(row)
        save()
        check(frame.timestamp not in seen and frame.firmware_build == worker.build_id, '旧帧或固件身份不一致')
        seen.add(frame.timestamp)
        stats = aa.verify_record(frame)
        check(stats['otr_samples'] == stats['saturated_samples'] == 0, '出现饱和或OTR，停止扫频')
        row['analysis'] = analyze(frame.words, frequency, wave)
        row['verified'] = True
        save()
        return row

    def condition(wave, frequency, phase, label):
        worker.exchange(p.STOP)
        # A disabled interval resets the phase accumulator, making the exact
        # Nyquist zero-phase case reproducible, unlike live frequency changes.
        worker.exchange(p.SET_DDS, stimulus(wave, frequency, phase, False))
        if worker.cancel_capture.wait(.005):
            raise InterruptedError('扫频取消')
        worker.exchange(p.SET_DDS, stimulus(wave, frequency, phase))
        if worker.cancel_capture.wait(settle_seconds):
            raise InterruptedError('扫频取消')
        rows = [acquire(wave, frequency, phase, trial, label) for trial in range(2)]
        return rows

    try:
        check(worker.capabilities & 31 == 31, '需要完整帧、测量、饱和与采集模式能力')
        original = worker.exchange(p.GET_CONFIG).payload
        config = hc.decode_configuration(original)
        mode = worker.exchange(p.GET_CAPTURE_CONFIG).payload
        if worker.capabilities & awg.CAPABILITY:
            table_state = awg.status(worker)
            check(not table_state['uploading'], 'AWG上传未结束，拒绝开始扫频')
        baseline = worker.read_status()['counters']
        report.update(build=f'0x{worker.build_id:08X}', device_id=worker.device_identity, port=worker.port,
                      baud=worker.baud, configuration_before_hex=original.hex(), capture_mode_before_hex=mode.hex(),
                      awg_before=table_state, counters_before=list(baseline))
        worker.exchange(p.STOP)
        disabled = bytearray(config['dds']); disabled[1] = 0
        worker.exchange(p.SET_DDS, bytes(disabled))
        if table_state is not None:
            awg.ack(worker, awg.SELECT, b'\0')
        worker.exchange(p.SET_RECORD, struct.pack('<II', N, 500000))
        worker.exchange(p.SET_CAPTURE_MODE, p.capture_mode_payload(2))
        worker.exchange(p.SET_TRIGGER, aa.trigger_payload())
        worker.trigger_kind = 6
        anchors = condition(0, 100000, 0, 'anchor')
        check(all(row['analysis']['basic_pass'] for row in anchors), '起始100kHz闭环信号不足或异常；检查模块供电/SW0/接线')
        schedule = plan() if cases is None else list(cases)
        report['planned_conditions'] = len(schedule)
        for i, (wave, frequency, phase) in enumerate(schedule):
            rows = condition(wave, frequency, phase, 'survey')
            if i % 5 == 0 or frequency >= 12499000:
                progress(f'DDS_SWEEP {i+1}/{len(schedule)} {WAVES[wave]} {frequency}Hz phase={phase} '
                         f'{rows[-1]["analysis"]["status"]}')
        recovery = condition(0, 100000, 0, 'recovery')
        check(all(row['analysis']['basic_pass'] for row in recovery), '测试后100kHz恢复失败')
        start_amplitude = np.mean([v['analysis']['fitted_peak_adc_codes'] for v in anchors])
        end_amplitude = np.mean([v['analysis']['fitted_peak_adc_codes'] for v in recovery])
        report['anchor_recovery_relative_change'] = float(end_amplitude/start_amplitude-1)
        check(abs(report['anchor_recovery_relative_change']) <= .10, '测试后基准幅度变化超过10%')
        report['survey_completed'] = True
        report['verdict'] = 'SURVEY_COMPLETE'
    except BaseException as exc:
        report.update(verdict='CANCELLED' if isinstance(exc, (KeyboardInterrupt, InterruptedError)) else 'FAIL', error=repr(exc))
    finally:
        if original is not None:
            try:
                worker.exchange(p.STOP, restoring=True)
                disabled = bytearray(original[32:48]); disabled[1] = 0
                worker.exchange(p.SET_DDS, bytes(disabled), restoring=True)
                if table_state is not None:
                    awg.ack(worker, awg.SELECT, bytes([int(table_state['selected'])]), restoring=True)
                    check(awg.status(worker, restoring=True) == table_state, 'AWG选择或表状态未恢复')
                worker.exchange(p.SET_DDS, original[32:48], restoring=True)
                length, pre = struct.unpack_from('<II', original)
                ratio = (pre*1000000+8191)//16383
                worker.exchange(p.SET_RECORD, struct.pack('<II', length, ratio), restoring=True)
                worker.exchange(p.SET_TRIGGER, original[8:32], restoring=True)
                if mode is not None:
                    worker.exchange(p.SET_CAPTURE_MODE, mode, restoring=True)
                    check(worker.exchange(p.GET_CAPTURE_CONFIG, restoring=True).payload == mode, '采集模式未恢复')
                restored = worker.exchange(p.GET_CONFIG, restoring=True).payload
                check(restored == original, '原始配置未逐字节恢复')
                worker.trigger_kind = original[8]
                report.update(restored=True, configuration_after_hex=restored.hex())
            except BaseException as exc:
                report.update(verdict='FAIL', restore_error=repr(exc), restored=False)
                try:
                    worker.exchange(p.SET_DDS, struct.pack('<BBIIHi', 0, 0, 0, 0, 0, 0), restoring=True)
                    report['fallback_dds_disabled'] = True
                except BaseException as fallback:
                    report['fallback_error'] = repr(fallback)
        try:
            status = worker.exchange(p.GET_STATUS, restoring=True)
            check(len(status.payload) == 48 and not status.payload[1], '最终状态错误')
            counters = struct.unpack_from('<9I', status.payload, 12)
            if baseline is not None:
                report['error_deltas'] = [(a-b) & 0xffffffff for a, b in zip(counters[:8], baseline[:8])]
                check(not any(report['error_deltas']), '新增FPGA错误')
            report['parser_errors'] = dict(worker.parser.errors)
            check(not any(report['parser_errors'].values()), '协议解析错误')
        except BaseException as exc:
            report.update(verdict='FAIL', transport_error=repr(exc))
        report['summary'] = summarize(report['frames'])
        report['finished_at'] = datetime.now(TZ).isoformat()
        save()
    return report
