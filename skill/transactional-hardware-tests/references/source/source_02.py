"""Real DDS/ADC closed-loop relative calibration, with transactional restoration.

No model samples are generated here. Every measurement comes from capture().
The first accepted run defines unity relative gain; it does not calibrate volts.
"""
from datetime import datetime, timezone, timedelta
import json
import math
from pathlib import Path
import struct
import numpy as np

import scope_protocol as p
import awg

SCALE = 10/4095
MAX_TEST_CODE = 819  # established 10% digital peak, never a promised output voltage
AUTO_TRIGGER = struct.pack('<BBhHhhIIHI',6,0,0,0,-2048,2047,1,1,16383,2)
DC_CODES = (-819,-614,-410,-205,0,205,410,614,819)
AMPLITUDES = (205,410,614,819)
FREQUENCIES = (10000,25000,50000,100000,250000,500000,1000000)


def decode_configuration(payload):
    if len(payload) != 48:
        raise ValueError('配置回读必须为 48 字节')
    length,pre = struct.unpack_from('<II',payload)
    trigger,dds = payload[8:32],payload[32:48]
    kind,reserved,threshold,hysteresis,lo,hi,wmin,wmax,amplitude,observation = struct.unpack('<BBhHhhIIHI',trigger)
    wave,enabled,frequency,phase,peak,offset = struct.unpack('<BBIIHi',dds)
    if (length != 16384 or pre >= length or kind > 8 or reserved
            or not -4096 <= threshold <= 4095 or hysteresis > 8191
            or not -4096 <= lo <= 4095 or not -4096 <= hi <= 4095
            or amplitude > 16383 or observation > 16384
            or (kind in (2,3) and lo+hysteresis >= hi-hysteresis)
            or (kind in (4,5) and (not wmin or wmax < wmin))
            or (kind in (6,7) and observation < 2)
            or wave > 3 or enabled > 1 or frequency > 12500000 or peak > 16383
            or not -131072 <= offset <= 131071):
        raise ValueError('设备配置回读字段无效')
    return {'length': length,'pre': pre,'trigger': trigger,'dds': dds,'wave': wave,'enabled': enabled,
                'frequency': frequency,'phase': phase,'amplitude': peak,'offset': offset}


def finite(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)


def validate_fingerprint(data):
    if not isinstance(data,dict) or data.get('format') != 'scope-hardware-calibration-v1' or data.get('source') != 'hardware-uart':
        raise ValueError('需要真实硬件校准指纹，不能载入演示指纹')
    if data.get('status') != 'PASS' or data.get('restored') is not True:
        raise ValueError('校准未完成或原配置未恢复，不能作为基线')
    for key in ('dc_gain','reference_gain'):
        value = data.get(key)
        if not finite(value) or not 0.002 <= abs(value) <= 4:
            raise ValueError('指纹增益无效')
    for key,low,high in (('offset',-5,5),('noise',0,1),('gain',0.01,100)):
        value = data.get(key)
        if not finite(value) or not low <= value <= high:
            raise ValueError('指纹字段无效：'+key)
    if not math.isclose(data['gain'],data['dc_gain']/data['reference_gain'],rel_tol=1e-6,abs_tol=1e-9):
        raise ValueError('指纹相对增益与实测/参考增益不一致')
    if data.get('rate') != 25000000 or data.get('max_test_code') != MAX_TEST_CODE:
        raise ValueError('指纹采样率或测试范围不兼容')
    if not isinstance(data.get('device_id'),str) or not data['device_id']:
        raise ValueError('指纹缺少设备身份')
    frequencies,db = data.get('response_frequency'),data.get('response_db')
    if frequencies != list(FREQUENCIES) or not isinstance(db,list) or len(db) != len(FREQUENCIES):
        raise ValueError('指纹频响点不兼容')
    if any(not finite(v) or not -100 <= v <= 100 for v in db):
        raise ValueError('指纹频响数值无效')
    return data


def fit_dc(points):
    x = np.array([v['code'] for v in points],dtype=float)
    y = np.array([v['mean_code'] for v in points],dtype=float)
    if len(x) != 9 or tuple(x.astype(int)) != DC_CODES or not np.all(np.isfinite(y)):
        raise ValueError('缺少九点真实直流数据')
    gain,intercept = np.polyfit(x,y,1)
    residual = y-(gain*x+intercept)
    span = float(np.ptp(y))
    r2 = 1-float(np.sum(residual**2))/max(float(np.sum((y-y.mean())**2)),1e-20)
    if (not 0.002 <= abs(gain) <= 4 or span < 8 or r2 < 0.98
            or np.max(np.abs(residual)) > max(2,span*0.03)
            or np.any(np.diff(y)*np.sign(gain) <= 0)):
        raise ValueError('直流响应不足、非单调或非线性：检查 OUTA→IN 接线、供电及实体旋钮')
    return {'dc_gain': float(gain),'intercept_code': float(intercept),'dc_span_code': span,
                'dc_r2': r2,'dc_max_residual_code': float(np.max(np.abs(residual)))}


def tone_features(frame,frequency):
    y = frame.volts()
    actual = ((frequency*(1<<32)+12500000)//25000000)*25000000/(1<<32)
    if len(y)*actual/frame.rate < 4 or 5*actual >= frame.rate/2:
        raise ValueError('正弦记录周期数或谐波带宽不足')
    phase = np.arange(len(y))*2*np.pi*actual/frame.rate
    design = np.column_stack([np.ones(len(y))]+[v for k in range(1,6) for v in (np.sin(k*phase),np.cos(k*phase))])
    coeff,_,rank,_ = np.linalg.lstsq(design,y,rcond=None)
    if rank != 11:
        raise ValueError('正弦拟合退化')
    amplitude = float(np.hypot(coeff[1],coeff[2]))
    residual = float(np.sqrt(np.mean((y-design@coeff)**2)))
    fundamental = amplitude**2/2
    if amplitude < 3*SCALE or not fundamental > 0:
        raise ValueError('闭环正弦幅度不足，不能生成有效校准')
    if fundamental < 10*residual**2:
        raise ValueError('闭环正弦信噪比不足，检查连接和供电')
    return {'amplitude': amplitude,'mean': float(coeff[0]),'noise': residual,
                'harmonic_amplitudes': [float(np.hypot(coeff[k],coeff[k+1])) for k in range(3,11,2)],
                'frequency': frequency,'actual_frequency': actual}


def fingerprint_delta(current,baseline):
    if baseline is None:
        return '首次实测：以本次组合链路增益定义 1×；保存指纹后可比较漂移。'
    validate_fingerprint(baseline)
    if baseline['device_id'] != current['device_id'] or baseline['rate'] != current['rate']:
        raise ValueError('健康基线属于其他设备或采样率')
    return (f"相对实测基线：零点 Δ{(current['offset']-baseline['offset'])*1000:+.3f} mV；"
            f"增益 Δ{(current['dc_gain']/baseline['dc_gain']-1)*100:+.3f}%；"
            f"零输入噪声 Δ{(current['noise']-baseline['noise'])*1000:+.3f} mV RMS。")


def relative_comparison(offset,gain,zero,holdout,expected):
    """Compare independent observations in the saved reference's nominal volts.

    The target is a relative baseline, not an external voltage standard. Both
    columns use the same raw observation; only the display conversion changes.
    """
    if not all(finite(v) for v in (offset,gain,zero,holdout,expected)) or gain <= 0:
        raise ValueError('校准前后对比参数必须有限且增益为正')
    result = {}
    for name,observed,target in (('zero',zero,0.0),('dc_holdout',holdout,expected)):
        corrected = (observed-offset)/gain
        result[name] = {'expected_volts': target,'before_volts': observed,
                        'after_volts': corrected,'before_error_volts': observed-target,
                        'after_error_volts': corrected-target}
    return result


def run_closed_loop(worker,output_dir,device_id,baseline=None,progress=None,settle_seconds=0.08):
    """Own the existing worker queue for one bounded transaction, including cleanup."""
    output_dir = Path(output_dir)
    try:
        output_dir.mkdir(parents=True,exist_ok=False)
    except OSError as exc:
        return {'status':'FAIL','restored':True,'output_dir':str(output_dir),
                'error':'未下发硬件命令；无法建立新的原始数据目录：'+str(exc)}
    report = {'format': 'scope-hardware-calibration-v1','source': 'hardware-uart','status': 'FAIL',
                  'created': datetime.now(timezone(timedelta(hours=8))).isoformat(),'device_id': device_id,
                  'max_test_code': MAX_TEST_CODE,'raw_frames': [],'restored': False,
                  'scope': 'DAC+cable+ADC combined relative calibration; no absolute voltage reference'}
    snapshot = None
    awg_before = mode_before = None
    frames = []
    def notify(step,text,state='运行中'):
        if progress:
            progress(step,text,state)
    def check_cancel():
        if worker.shutdown.is_set() or worker.cancel_capture.is_set():
            raise InterruptedError('实物自检已取消')
    def configure(wave=0,frequency=100000,amplitude=MAX_TEST_CODE,offset=0):
        check_cancel()
        if amplitude > MAX_TEST_CODE or abs(offset) > MAX_TEST_CODE:
            raise ValueError('测试码超出既定范围')
        worker.exchange(p.SET_DDS,struct.pack('<BBIIHi',wave,1,frequency,0,amplitude,offset))
        if worker.cancel_capture.wait(settle_seconds):
            check_cancel()
    def capture(label):
        check_cancel()
        frame = worker.capture(3)
        if frame.rate != 25000000 or len(frame.words) != 16384 or frame.source != '硬件 UART':
            raise ValueError('自检必须使用真实 25 MSPS、16384 点完整冻结帧')
        if frames and frame.timestamp in {f.timestamp for f in frames}:
            raise ValueError('设备返回重复帧，拒绝复用旧样本')
        raw = frame.words & 4095
        if np.any(frame.words & 0x8000) or np.any(raw == 0) or np.any(raw == 4095):
            raise ValueError('实物出现 OTR 或满幅码，终止测试并恢复原配置')
        name = f'{len(frames):03d}_{label}.npy'
        np.save(output_dir/name,frame.words)
        report['raw_frames'].append({'file': name,'timestamp': frame.timestamp,'rate': frame.rate,
                                        'trigger': frame.trigger,'points': len(raw),'label': label})
        frames.append(frame)
        return frame
    try:
        if not worker.capabilities & 2:
            raise ValueError('固件缺少配置回读能力，不能安全运行实物自检')
        worker.exchange(p.STOP)
        configuration = worker.exchange(p.GET_CONFIG).payload
        snapshot = decode_configuration(configuration)
        report['configuration_before_hex'] = configuration.hex()
        if getattr(worker,'build_id',None) is not None:report['firmware_build']=f'0x{worker.build_id:08X}'
        if worker.capabilities & p.CAP_CAPTURE_MODES:
            mode_before=worker.exchange(p.GET_CAPTURE_CONFIG).payload
            report['capture_mode_before_hex']=mode_before.hex()
        if worker.capabilities & awg.CAPABILITY:
            awg_before=awg.status(worker);report['awg_before']=awg_before
            disabled=bytearray(snapshot['dds']);disabled[1]=0
            worker.exchange(p.SET_DDS,bytes(disabled))
            awg.ack(worker,awg.SELECT,b'\0')

        if snapshot['length'] != 16384:
            raise ValueError('当前自检仅支持已验证的 16384 点 BRAM 配置')
        report['rate'] = 25000000
        if baseline is not None:
            validate_fingerprint(baseline)
            if baseline['device_id'] != device_id:
                raise ValueError('健康基线不属于当前设备')
        worker.exchange(p.SET_TRIGGER,AUTO_TRIGGER)
        worker.trigger_kind = 6
        notify(0,'DAC 中码 8192；采集三次独立零输入完整帧')
        configure(wave=3,amplitude=0,offset=0)
        zero = [capture('zero') for _ in range(3)]
        zero_means = [float(f.volts().mean()) for f in zero]
        noise = float(np.sqrt(np.mean([np.var(f.volts()) for f in zero])))
        report.update(zero=float(np.mean(zero_means)),noise=noise,zero_frame_means=zero_means)
        notify(0,f"实测零点 {report['zero']*1000:.3f} mV；噪声 {noise*1000:.3f} mV RMS",'完成 · 实物')
        points = []
        for code in DC_CODES:
            notify(1,f'九点直流拟合：DAC 相对中码 {code:+d} LSB')
            configure(wave=3,amplitude=0,offset=code)
            pair = [capture(f'dc_{code}') for _ in range(2)]
            mean_code = float(np.mean([np.mean(2047-(f.words&4095).astype(np.int32)) for f in pair]))
            points.append({'code': code,'mean_code': mean_code})
        fit = fit_dc(points)
        reference = baseline['dc_gain'] if baseline is not None else fit['dc_gain']
        ratio = fit['dc_gain']/reference
        if not 0.01 <= ratio <= 100:
            raise ValueError('增益相对基线极性改变或倍率异常，拒绝应用校正')
        report.update(**fit,dc_points=points,reference_gain=reference,gain=ratio,
                      offset=(fit['intercept_code']+0.5)*SCALE,
                      reference_kind='saved-hardware-baseline' if baseline is not None else 'first-run-self-reference')
        notify(1,f"实测 {fit['dc_gain']:+.6f} ADC码/DAC码；R²={fit['dc_r2']:.6f}；相对增益 {ratio:.6f}×",'完成 · 实物')
        linear = []
        for amplitude in AMPLITUDES:
            notify(2,f'幅度线性：100 kHz，数字峰值 {amplitude} LSB')
            configure(amplitude=amplitude)
            result = tone_features(capture(f'linear_{amplitude}'),100000)
            linear.append(dict(dac_amplitude=amplitude,**result))
        gains = [v['amplitude']/v['dac_amplitude'] for v in linear]
        linear_error = max(abs(v/np.median(gains)-1) for v in gains)
        if any(linear[i+1]['amplitude'] <= linear[i]['amplitude'] for i in range(len(linear)-1)) or linear_error > 0.10:
            raise ValueError('实测正弦幅度非单调或线性偏差超过 10%，拒绝生成校准')
        report.update(linearity=linear,linearity_max_relative_error=float(linear_error))
        notify(2,f'四档幅度单调；相对线性偏差 {linear_error*100:.3f}%；所有采集 OTR=0','完成 · 实物')
        response = []
        for frequency in FREQUENCIES:
            notify(3,f'组合频响：{frequency/1000:g} kHz，数字峰值 {MAX_TEST_CODE} LSB')
            configure(frequency=frequency)
            response.append(tone_features(capture(f'response_{frequency}'),frequency))
        reference_amplitude = response[3]['amplitude']
        response_db = [20*math.log10(v['amplitude']/reference_amplitude) for v in response]
        report.update(response_frequency=list(FREQUENCIES),response_db=response_db,response_samples=response)
        notify(3,'10 kHz～1 MHz 七点实测，归一到本次 100 kHz 响应','完成 · 实物')
        configure(frequency=100000)
        tone = tone_features(capture('harmonics'),100000)
        report.update(harmonic_amplitudes=tone['harmonic_amplitudes'],tone_noise=tone['noise'],
                      polarity='正向' if fit['dc_gain'] > 0 else '反向')
        notify(4,"组合链路噪声 "+f"{tone['noise']*1000:.3f} mV RMS；"+" · ".join(f"H{h} {a*1000:.3f} mV" for h,a in enumerate(tone['harmonic_amplitudes'],2)),'完成 · 实物')
        # Recheck a repeated zero and a DC endpoint for drift during the sweep.
        configure(wave=3,amplitude=0,offset=0)
        end_zero = float(capture('zero_recheck').volts().mean())
        if abs(end_zero-report['zero']) > max(2*SCALE,noise*3):
            raise ValueError('自检期间零点变化过大，请保持接线和实体旋钮不动后重试')
        report.update(zero_recheck=end_zero,holdout_zero_corrected=(end_zero-report['offset'])/ratio)
        if abs(report['holdout_zero_corrected']) > max(2*SCALE,noise*4)/ratio:
            raise ValueError('独立零点复测未通过，拒绝发布校准参数')
        configure(wave=3,amplitude=0,offset=512)
        holdout = capture('dc_holdout_512')
        observed = float(np.mean(2047-(holdout.words&4095).astype(np.int32)))
        error = observed-(fit['dc_gain']*512+fit['intercept_code'])
        report.update(holdout_dc_code=512,holdout_dc_error_code=error)
        if abs(error) > max(2,fit['dc_span_code']*0.03):
            raise ValueError('独立直流校验点未通过，拒绝发布校准参数')
        report['before_after'] = relative_comparison(
            report['offset'],ratio,end_zero,float(holdout.volts().mean()),reference*512*SCALE)
        report['comparison_reference'] = 'saved-relative-baseline' if baseline is not None else 'first-run-relative-fit'
        report['fingerprint_comparison'] = fingerprint_delta(report,baseline)
        report['status'] = 'PASS'
        notify(5,'参数已测得，正在恢复并回读校验原始配置…')
    except InterruptedError as exc:
        report.update(status='CANCELLED',error=str(exc))
    except Exception as exc:
        report.update(status='FAIL',error=str(exc))
    finally:
        if snapshot is not None:
            try:
                worker.exchange(p.STOP,restoring=True)
                worker.parser.buffer.clear()
                if awg_before is not None:
                    disabled=bytearray(snapshot['dds']);disabled[1]=0
                    worker.exchange(p.SET_DDS,bytes(disabled),restoring=True)
                    awg.ack(worker,awg.SELECT,bytes([int(awg_before['selected'])]),restoring=True)
                    awg_after=awg.status(worker,restoring=True)
                    if any(awg_after[k]!=awg_before[k] for k in ('valid','selected','active_crc')):
                        raise ValueError('恢复后任意波形选择或表内容校验状态不一致')
                    report['awg_after']=awg_after
                worker.exchange(p.SET_DDS,snapshot['dds'],restoring=True)
                worker.exchange(p.SET_TRIGGER,snapshot['trigger'],restoring=True)
                restored = worker.exchange(p.GET_CONFIG,restoring=True).payload
                if restored != bytes.fromhex(report['configuration_before_hex']):
                    raise ValueError('恢复后配置与原始回读不一致')
                if mode_before is not None:
                    mode_after=worker.exchange(p.GET_CAPTURE_CONFIG,restoring=True).payload
                    if mode_after!=mode_before:raise ValueError('自检后采集模式不一致')
                    report['capture_mode_after_hex']=mode_after.hex()
                worker.trigger_kind = snapshot['trigger'][0]
                report.update(restored=True,configuration_after_hex=restored.hex())
            except Exception as exc:
                report.update(status='FAIL',restored=False,restore_error=str(exc))
        report['parser_errors'] = dict(worker.parser.errors)
        if report['status'] == 'PASS' and any(report['parser_errors'].values()):
            report.update(status='FAIL',error='自检期间出现协议解析错误')
        report['output_dir'] = str(output_dir)
        try:
            (output_dir/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
        except OSError as exc:
            report.update(status='FAIL',error='无法保存完整报告，未发布校准：'+str(exc))
    if report['status'] == 'PASS':
        validate_fingerprint(report)
        notify(5,'相对参数就绪；原 DDS/触发/记录配置已逐字节回读确认恢复','完成 · 实物')
        notify(6,report['fingerprint_comparison'],'完成 · 实物')
    return report
