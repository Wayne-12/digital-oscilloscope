"""Real analog acceptance. This module never selects digital diagnostic input.

Loopback stimuli stay inside the DAC's native 14-bit range. Missing physical
overload is INCOMPLETE, even if every counter agrees with the raw record.
"""
from datetime import datetime, timezone, timedelta
from dataclasses import replace
from pathlib import Path
import hashlib
import json
import struct

import numpy as np
import scope_protocol as p
import hardware_calibration as hc
import awg

POINTS = 16384
RATE = 25000000
TZ = timezone(timedelta(hours=8))
REQUIRED = ('normal_clean', 'raw_0', 'raw_4095', 'nonzero_saturation',
            'physical_otr', 'otr_trigger', 'overload_roi', 'recovery')


def check(condition, message):
    if not condition:
        raise ValueError(message)


def raw_statistics(words):
    words = np.asarray(words)
    check(words.shape == (POINTS,) and words.dtype.kind in 'ui'
          and not np.any(words < 0) and not np.any(words > 65535) and not np.any(words & 0x7000),
          '需要保留原始 OTR 的完整 16384 点有效记录')
    raw = words & 4095
    mask = (raw == 0) | (raw == 4095)
    otr = (words & 0x8000) != 0
    return dict(count=POINTS, saturated_samples=int(mask.sum()),
                events=int(np.count_nonzero(mask & ~np.r_[False, mask[:-1]])),
                raw_0=int(np.count_nonzero(raw == 0)),
                raw_4095=int(np.count_nonzero(raw == 4095)),
                otr_samples=int(otr.sum()),
                otr_events=int(np.count_nonzero(otr & ~np.r_[False, otr[:-1]])),
                # Straight-binary AD9226 OTR and output rails refer to the same sample.
                otr_nonrail=int(np.count_nonzero(otr & ~mask)),
                minimum_raw=int(raw.min()), maximum_raw=int(raw.max()))


def verify_record(frame):
    check(frame.source == '硬件 UART' and frame.rate == RATE
          and frame.record_offset == 0 and len(frame.words) == POINTS,
          '验收仅接受真实 UART 完整原始帧')
    stats = raw_statistics(frame.words)
    expected = {k: stats[k] for k in ('count', 'saturated_samples', 'events')}
    expected['diagnostic'] = False
    check(frame.fpga_saturation == expected, '整帧饱和计数不一致或属于数字诊断帧')
    check(stats['otr_nonrail'] == 0, 'OTR 与原始码未同拍对应；检查数据/OTR 接线和采样时序')
    m = frame.fpga_measurement
    x = 2047 - (frame.words & 4095).astype(np.int64)
    check(m is not None and m['stats_valid'] and not m['error']
          and (m['count'], m['minimum'], m['maximum'], m['sum'], m['square_sum'])
          == (POINTS, int(x.min()), int(x.max()), int(x.sum()), int((x*x).sum())),
          'FPGA 基础测量与完整原始帧不一致')
    check(frame.fpga_spectrum is not None and frame.fpga_spectrum['clipped']
          == bool(np.any(frame.words[:1024] & 0x8000)), 'FFT OTR 标志与前 1024 点不一致')
    return stats


def trigger_payload(kind=6):
    # Span cannot exceed 4095: under-amplitude 8191 guarantees a real trigger
    # for clean, clipped, and DC signals alike. OTR mode has no AUTO fallback.
    return struct.pack('<BBhHhhIIHI', kind, 0, 0, 0, -100, 100, 1, 100, 8191, 2)


def native_dds(wave, peak, offset=0, frequency=100000):
    check(type(peak) is int and type(offset) is int and 0 <= peak <= 8191
          and -8192 <= offset-peak and offset+peak <= 8191,
          '验收激励不得触发 DAC 数字限幅或超出原生码域')
    return struct.pack('<BBIIHi', wave, 1, frequency, 0, peak, offset)


def coverage(frames):
    result = dict.fromkeys(REQUIRED, False)
    overload_seen = False
    for row in frames:
        if not row.get('verified'):
            continue
        s = row['statistics']
        clean = s['saturated_samples'] == s['otr_samples'] == 0
        abnormal = bool(s['saturated_samples'] or s['otr_samples'])
        if row['case'] == 'baseline' and clean and s['maximum_raw']-s['minimum_raw'] >= 8:
            result['normal_clean'] = True
        if row['case'].startswith('recovery') and clean and overload_seen:
            result['recovery'] = True
        result['raw_0'] |= s['raw_0'] > 0
        result['raw_4095'] |= s['raw_4095'] > 0
        result['nonzero_saturation'] |= s['saturated_samples'] > 0
        result['physical_otr'] |= s['otr_samples'] > 0
        result['otr_trigger'] |= row.get('otr_trigger_verified', False)
        result['overload_roi'] |= abnormal and row.get('roi_verified', False)
        overload_seen |= abnormal
    return result


def run(worker, output_dir, *, source='dac-loopback', settle_seconds=0.08, progress=print):
    """Bounded transaction with raw evidence and byte-for-byte restoration.

    adc-input observes an already connected external analog input, leaving DDS
    output untouched. It requires both overload polarities and a later clean
    recovery before a combined acceptance can be signed off by the operator.
    """
    check(source in ('dac-loopback', 'adc-input'), '未知模拟输入方式')
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=False)
    report = dict(format='scope-analog-acceptance-v1', source='hardware-uart',
                  analog_input=source, verdict='FAIL', restored=False,
                  started_at=datetime.now(TZ).isoformat(), frames=[],
                  stimulus_limit='native DAC code 0..16383; no digital clipping; fixed physical knob',
                  diagnostic_injection=False)
    original = mode = awg_before = None
    baseline_counters = None
    seen = set()

    def save():
        (out/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                                 allow_nan=False), encoding='utf-8')

    def cancel_check():
        if worker.shutdown.is_set() or worker.cancel_capture.is_set():
            raise InterruptedError('模拟验收取消')

    def frozen_identity(response, frame):
        check((response.timestamp, response.sample_rate, response.trigger_index)
              == (frame.timestamp, frame.rate, frame.trigger), '重复摘要的冻结帧身份不一致')

    def verify_roi(frame):
        env = worker.exchange(p.READ_ENVELOPE, struct.pack('<H', 400),
                              record_length=POINTS, envelope_buckets=400)
        check((env.timestamp, env.rate, env.trigger, env.length)
              == (frame.timestamp, frame.rate, frame.trigger, POINTS), '包络身份不一致')
        expected = []
        for i in range(400):
            block = frame.words[i*POINTS//400:(i+1)*POINTS//400]
            x = 2047-(block & 4095).astype(np.int32)
            expected.append((int(x.min()), int(x.max()), int(bool(np.any(block & 0x8000)))))
        check(tuple(expected) == env.buckets, '模拟异常的 min/max/OTR 包络不一致')
        with_env = replace(frame, overview=env)
        for start in (0, max(0, min(frame.trigger-128, POINTS-257)), POINTS-257):
            roi = worker.read_roi(with_env, start, 257)
            check(np.array_equal(roi.words, frame.words[start:start+257]), 'ROI 原始码或 OTR 不一致')
        repeated = worker.exchange(p.READ_SATURATION)
        frozen_identity(repeated, frame)
        check(p.decode_saturation(repeated) == frame.fpga_saturation, 'ROI 读取改变了完整帧计数')

    def acquire(label, stimulus=None, *, otr_trigger=False):
        cancel_check()
        worker.exchange(p.STOP)
        # STOP clears diagnostics in the current firmware; never enable injection.
        worker.exchange(p.SET_TRIGGER, trigger_payload(8 if otr_trigger else 6))
        worker.trigger_kind = 8 if otr_trigger else 6
        if stimulus is not None:
            worker.exchange(p.SET_DDS, stimulus)
            if worker.cancel_capture.wait(settle_seconds):
                cancel_check()
        frame = worker.capture(3)
        filename = f'{len(report["frames"]):03d}_{label}.npy'
        path = out/filename
        np.save(path, frame.words)
        row = dict(case=label, file=filename, timestamp=frame.timestamp, rate=frame.rate,
                   trigger=frame.trigger, firmware_build=frame.firmware_build,
                   sha256=hashlib.sha256(path.read_bytes()).hexdigest(), verified=False,
                   dds_hex=stimulus.hex() if stimulus is not None else None,
                   saturation=frame.fpga_saturation, measurement=frame.fpga_measurement,
                   spectrum=frame.fpga_spectrum)
        report['frames'].append(row)
        save()  # Preserve a failed raw record too.
        check(frame.timestamp not in seen, '返回了旧冻结帧')
        seen.add(frame.timestamp)
        row['statistics'] = verify_record(frame)
        if otr_trigger:
            otr = (frame.words & 0x8000) != 0
            check(bool(otr[frame.trigger]) and (frame.trigger == 0 or not otr[frame.trigger-1]),
                  'OTR 触发索引未指向原始 OTR 上升沿')
            row['otr_trigger_verified'] = True
        verify_roi(frame)
        row.update(verified=True, roi_verified=True)
        save()
        progress(f'ANALOG_FRAME {label} {row["statistics"]}')
        return row

    try:
        check(worker.capabilities & 31 == 31, '需要完整帧分析、饱和、模式与包络能力')
        report.update(build=f'0x{worker.build_id:08X}', device_id=worker.device_identity,
                      baud=worker.baud)
        # Snapshot before any configuration mutation.
        original = worker.exchange(p.GET_CONFIG).payload
        cfg = hc.decode_configuration(original)
        mode = worker.exchange(p.GET_CAPTURE_CONFIG).payload
        if worker.capabilities & awg.CAPABILITY:
            awg_before = awg.status(worker)
            check(not awg_before['uploading'], '正在上传 AWG；请完成上传后再验收')
        report.update(configuration_before_hex=original.hex(), capture_mode_before_hex=mode.hex(),
                      awg_before=awg_before)
        baseline_counters = worker.read_status()['counters']
        report['baseline_counters'] = list(baseline_counters)
        worker.exchange(p.STOP)
        if source == 'dac-loopback':
            disabled = bytearray(cfg['dds']); disabled[1] = 0
            worker.exchange(p.SET_DDS, bytes(disabled))
            if awg_before is not None:
                awg.ack(worker, awg.SELECT, b'\0')
        worker.exchange(p.SET_RECORD, struct.pack('<II', POINTS, 500000))
        worker.exchange(p.SET_CAPTURE_MODE, p.capture_mode_payload(2))
        if source == 'dac-loopback':
            normal = native_dds(0, 819)
            base = acquire('baseline', normal)
            s = base['statistics']
            check(s['saturated_samples'] == s['otr_samples'] == 0
                  and s['maximum_raw']-s['minimum_raw'] >= 8,
                  '起始正常信号缺失或已过载，不能自动扫幅')
            otr_stimulus = None
            abnormal_stimulus = None
            for peak in (1638, 3276, 4914, 6552, 7372, 8191):
                stimulus = native_dds(0, peak)
                row = acquire(f'sine_peak_{peak}', stimulus)
                if row['statistics']['otr_samples']:
                    otr_stimulus = stimulus
                if row['statistics']['saturated_samples'] or row['statistics']['otr_samples']:
                    abnormal_stimulus = stimulus
                    break  # No further amplitude increase after physical overload.
            # Native endpoint DC values test both polarities without DAC code clipping.
            if abnormal_stimulus is None:
                for offset in (-8192, 8191):
                    row = acquire(f'dc_offset_{offset}', native_dds(3, 0, offset))
                    if row['statistics']['saturated_samples'] or row['statistics']['otr_samples']:
                        abnormal_stimulus = native_dds(3, 0, offset)
            if otr_stimulus is not None:
                for ratio in (0, 500000, 1000000):
                    worker.exchange(p.STOP)
                    worker.exchange(p.SET_RECORD, struct.pack('<II', POINTS, ratio))
                    acquire(f'otr_trigger_ratio_{ratio}', otr_stimulus, otr_trigger=True)
            if abnormal_stimulus is not None:
                for trial in range(3):
                    acquire(f'recovery_{trial}', normal)
                    acquire(f'overload_repeat_{trial}', abnormal_stimulus)
            acquire('recovery_final', normal)
            # Check the real OTR trigger also stays quiet on the restored clean
            # input. SINGLE has a finite host deadline and no AUTO fallback.
            worker.exchange(p.STOP)
            worker.exchange(p.SET_TRIGGER, trigger_payload(8))
            worker.trigger_kind = 8
            try:
                acquire_clean = worker.capture(0.3)
            except TimeoutError:
                report['clean_otr_no_false_trigger'] = True
                worker.exchange(p.STOP)
            else:
                check(False, f'正常输入误触发 OTR，timestamp={acquire_clean.timestamp}')
        else:
            # Observe externally supplied physical overload; do not alter DAC settings.
            acquire('external_input')
            s = report['frames'][-1]['statistics']
            if 0 < s['otr_samples'] < POINTS:
                acquire('external_otr_trigger', otr_trigger=True)
        report['coverage'] = coverage(report['frames'])
        report['missing'] = [k for k, v in report['coverage'].items() if not v]
        report['verdict'] = 'INCOMPLETE' if report['missing'] else 'PASS'
        if report['missing']:
            report['reason'] = '未观测到全部必需的真实模拟场景；零计数与数字注入均不能代替真实过载'
    except BaseException as exc:
        report.update(verdict='CANCELLED' if isinstance(exc, (InterruptedError, KeyboardInterrupt)) else 'FAIL',
                      error=repr(exc))
    finally:
        if original is not None:
            try:
                worker.exchange(p.STOP, restoring=True)
                if source == 'dac-loopback':
                    disabled = bytearray(original[32:48]); disabled[1] = 0
                    worker.exchange(p.SET_DDS, bytes(disabled), restoring=True)
                    if awg_before is not None:
                        awg.ack(worker, awg.SELECT, bytes([int(awg_before['selected'])]), restoring=True)
                        after = awg.status(worker, restoring=True)
                        check(after == awg_before, 'AWG 选择或表状态未恢复')
                    worker.exchange(p.SET_DDS, original[32:48], restoring=True)
                length, pre = struct.unpack_from('<II', original)
                ratio = (pre*1000000+8191)//16383
                worker.exchange(p.SET_RECORD, struct.pack('<II', length, ratio), restoring=True)
                worker.exchange(p.SET_TRIGGER, original[8:32], restoring=True)
                if mode is not None:
                    worker.exchange(p.SET_CAPTURE_MODE, mode, restoring=True)
                after = worker.exchange(p.GET_CONFIG, restoring=True).payload
                check(after == original, '原 DDS/触发/记录配置未逐字节恢复')
                if mode is not None:
                    check(worker.exchange(p.GET_CAPTURE_CONFIG, restoring=True).payload == mode,
                          '采集模式未恢复')
                worker.trigger_kind = original[8]
                report.update(restored=True, configuration_after_hex=after.hex())
            except BaseException as exc:
                report.update(verdict='FAIL', restore_error=repr(exc), restored=False)
                # On restoration failure, attempt to leave loopback at DAC midscale.
                if source == 'dac-loopback':
                    try:
                        worker.exchange(p.SET_DDS, struct.pack('<BBIIHi', 0, 0, 0, 0, 0, 0), restoring=True)
                        report['fallback_dds_disabled'] = True
                    except BaseException as fallback:
                        report['fallback_error'] = repr(fallback)
        try:
            report['parser_errors'] = dict(worker.parser.errors)
            if baseline_counters is not None:
                # Cancellation remains set; query through the restoration path.
                status_frame = worker.exchange(p.GET_STATUS, restoring=True)
                check(len(status_frame.payload) == 48, '最终状态响应长度错误')
                final = dict(flags=status_frame.payload[0], backend_error=status_frame.payload[1],
                             counters=list(struct.unpack_from('<9I', status_frame.payload, 12)))
                report['final_status'] = final
                report['error_deltas'] = [(v-b) & 0xffffffff for v, b in
                                          zip(final['counters'][:8], baseline_counters[:8])]
                check(not final['backend_error'] and not any(report['error_deltas']), '新增 FPGA 错误')
            check(not any(report['parser_errors'].values()), '验收期间发生协议解析错误')
        except BaseException as exc:
            report.update(verdict='FAIL', transport_error=repr(exc))
        report['coverage'] = coverage(report['frames'])
        report['missing'] = [k for k, v in report['coverage'].items() if not v]
        report['finished_at'] = datetime.now(TZ).isoformat()
        save()
    return report
