"""Explicit, opt-in verification of the 1024-point board-analysis firmware.

Run only after the board is connected and the manual safety enable is ready.
Uses the established <=10% DDS stimulus, saves raw frames, and restores the
original DDS, trigger and record configuration. Does not program JTAG or Flash.
"""
from pathlib import Path
from datetime import datetime
import argparse
import importlib.util
import json
import math
import os
import struct
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'PC/protocol'))
import spectrum_reference as reference

def verify_frame(frame,measurement,spectral,threshold=0,hysteresis=8):
    x=2047-(frame.words&4095).astype(np.int64)
    assert measurement['count']==len(x)==16384
    assert (measurement['minimum'],measurement['maximum'],measurement['vpp'])==(int(x.min()),int(x.max()),int(np.ptp(x)))
    assert (measurement['sum'],measurement['square_sum'])==(int(x.sum()),int((x*x).sum()))
    assert measurement['mean']==int(np.sign(x.mean())*math.floor(abs(x.mean())+.5))
    assert measurement['rms']==math.floor(math.sqrt(float(np.mean(x*x)))+.5)
    spec=importlib.util.spec_from_file_location('measure_oracle',ROOT/'FPGA/scripts/generate_measure_vectors.py')
    oracle=importlib.util.module_from_spec(spec);spec.loader.exec_module(oracle)
    expected=oracle.stats(x.tolist(),list(range(len(x))),frame.rate,threshold,hysteresis)
    assert (measurement['periods'],measurement['period_q16'],measurement['frequency'],measurement['duty_ppm'])==tuple(expected[8:12])
    assert measurement['period_valid']==bool(expected[-1]) and not measurement['error']
    z=np.fft.rfft(reference.preprocess(x[:1024].tolist(),1))
    amplitudes=np.abs(z)/2048
    peak=int(np.argmax(amplitudes[2:511])+2)
    if amplitudes[peak]>=2.25:
        assert spectral['valid'] and spectral['peak_bin']==peak
        assert abs(spectral['amplitude']-amplitudes[peak])<reference.AMPLITUDE_TOLERANCE_Q16/65536
    elif amplitudes[peak]<1.75:
        assert not spectral['valid']
    if spectral['valid']:
        for harmonic in spectral['harmonics']:
            if harmonic['valid']:
                k=harmonic['bin']
                assert abs(spectral['peak_bin']*harmonic['order']-k)<=1
                assert abs(harmonic['amplitude']-amplitudes[k])<reference.AMPLITUDE_TOLERANCE_Q16/65536
    assert spectral['clipped']==bool(np.any(frame.words[:1024]&32768))

def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--port',required=True)
    cli.add_argument('--baud',type=int,choices=(115200,921600),default=921600)
    cli.add_argument('--output-dir',type=Path)
    cli.add_argument('--threshold-code',type=int,default=4)
    cli.add_argument('--hysteresis-code',type=int,default=2)
    a=cli.parse_args()
    if not -2048<=a.threshold_code<=2047 or not 0<=a.hysteresis_code<=8191:
        cli.error('ADC threshold or hysteresis is out of range')
    sys.stdout.reconfigure(encoding='utf-8')
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    spec=importlib.util.spec_from_file_location('analysis_verification_ui',ROOT/'示波器显示界面.py')
    ui=importlib.util.module_from_spec(spec);sys.modules[spec.name]=ui;spec.loader.exec_module(ui)
    output=a.output_dir or ROOT/'FPGA/reports/analysis_hardware'/datetime.now().strftime('%Y%m%d_%H%M%S')
    output.mkdir(parents=True,exist_ok=False)
    worker=ui.SerialWorker(a.port,a.baud)
    result={'verdict':'FAIL','hardware_verified':False,'port':a.port,'frames':[], 'restored':False}
    original=None
    try:
        worker.open_link()
        assert worker.capabilities&7==7,'New frozen-analysis firmware is required'
        worker.exchange(ui.proto.STOP)
        original=worker.exchange(ui.proto.GET_CONFIG).payload
        ui.hwcal.decode_configuration(original)
        worker.exchange(ui.proto.SET_TRIGGER,struct.pack('<BBhHhhIIHI',6,0,a.threshold_code,
                        a.hysteresis_code,-100,100,1,100,16383,2))
        for wave in (0,1,2,3):
            worker.exchange(ui.proto.SET_DDS,struct.pack('<BBIIHi',wave,1,100000,0,819 if wave!=3 else 0,0))
            worker.cancel_capture.wait(.08)
            frame=worker.capture(8)
            m,s=frame.fpga_measurement,frame.fpga_spectrum
            assert m is not None and s is not None
            # Preserve evidence even when a numerical or signal check fails.
            np.save(output/f'wave_{wave}.npy',frame.words)
            row={'wave':wave,'timestamp':frame.timestamp,'measurement':m,'spectrum':s,'verified':False}
            result['frames'].append(row)
            verify_frame(frame,m,s,a.threshold_code,a.hysteresis_code)
            assert not np.any(frame.words&32768),'ADC OTR observed'
            if wave!=3:
                assert m['vpp']>=8 and m['period_valid'],'Input amplitude or threshold crossing is insufficient'
                assert abs(m['frequency']-100000)<=1000,'Real waveform frequency differs from DDS setting'
                assert s['valid'] and s['peak_bin']==4,'Expected 100 kHz FFT main peak was not observed'
            else:
                assert not s['valid'],'Unexpected AC peak in the zero-output DC test'
            again_m=worker.exchange(ui.proto.READ_MEASURE)
            again_s=worker.exchange(ui.proto.READ_SPECTRUM)
            assert ui.proto.decode_measurement(again_m)==m and ui.proto.decode_spectrum(again_s)==s
            assert again_m.timestamp==again_s.timestamp==frame.timestamp
            row['verified']=True
        ratios=[row['spectrum']['harmonics'][1]['amplitude']/row['spectrum']['amplitude'] for row in result['frames'][:3]]
        assert ratios[1]>ratios[0]+.03 and ratios[1]>ratios[2]+.03,'DDS waveform changes were not resolved in the real harmonics'
        assert result['frames'][3]['measurement']['vpp']<min(row['measurement']['vpp'] for row in result['frames'][:3])*.5,'DC record still has large AC variation'
        result['h3_to_main_amplitude_ratios']=dict(zip(('sine','square','triangle'),ratios))
        assert not any(worker.parser.errors.values())
        result['parser_errors']=worker.parser.errors.copy()
        result['verdict']='PASS'
        result['hardware_verified']=True
    except Exception as error:
        result['error']=repr(error)
    finally:
        if original is not None:
            worker.cancel_capture.clear()
            try:
                worker.exchange(ui.proto.STOP,restoring=True)
                decoded=ui.hwcal.decode_configuration(original)
                worker.exchange(ui.proto.SET_RECORD,struct.pack('<II',decoded['length'],
                                round(decoded['pre']*1000000/(decoded['length']-1))),restoring=True)
                worker.exchange(ui.proto.SET_TRIGGER,decoded['trigger'],restoring=True)
                worker.exchange(ui.proto.SET_DDS,decoded['dds'],restoring=True)
                assert worker.exchange(ui.proto.GET_CONFIG,restoring=True).payload==original
                result['restored']=True
            except Exception as error:
                result.update(verdict='FAIL',restore_error=repr(error))
        if worker.link is not None:worker.link.close()
        (output/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'verdict':result['verdict'],'restored':result['restored'],'report':str(output)},ensure_ascii=False))
    return result['verdict']!='PASS'

if __name__=='__main__':raise SystemExit(main())
