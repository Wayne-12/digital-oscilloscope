"""Acquire live UART evidence and capture the production Qt view; restore board settings."""
from pathlib import Path
import importlib.util, sys, os, struct, time, json, traceback, threading
os.environ['QT_QPA_PLATFORM']='offscreen'
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/trigger_evidence_20261103'
OUT.mkdir(parents=True,exist_ok=True)
s=importlib.util.spec_from_file_location('evidence_ui',ROOT/'scope_ui.py')
u=importlib.util.module_from_spec(s);sys.modules[s.name]=u;s.loader.exec_module(u)
p,np=u.proto,u.np
app=u.QtWidgets.QApplication([]);u.configure_fonts(app)
w=u.ScopeWindow(profile_path=OUT/'view_profile.json');w.install_absolute_profile(ROOT/'voltage_calibration.json')
w.resize(1480,980);w.set_running(False);w.source.setCurrentIndex(1);w.show();app.processEvents()
w.timer.stop();w.ownership_probe_timer.stop();w.handoff_timer.stop()
link=u.SerialWorker('COM12',921600)
r={'source':'live hardware UART COM12','started':time.strftime('%Y-%m-%d %H:%M:%S'),'frames':[],'waiting':[],'checks':{},'result':'FAIL'}
original=mode=None
def save(): (OUT/'report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
def stop():
    link.exchange(p.STOP);link.stream_mode=None;time.sleep(.1)
def config(kind,match=True):
    threshold=mid; low=mid-span//5; high=mid+span//5; amin=span*2 if kind==6 else max(4,span//2)
    wmin,wmax=8,18
    if not match:
        if kind in (0,1):threshold=4090
        elif kind in (2,3):low,high=3000,3500
        elif kind in (4,5):wmin,wmax=100,200
        elif kind==6:amin=1
        else:amin=8191
    return struct.pack('<BBhHhhIIHI',kind,0,threshold,2,low,high,wmin,wmax,amin,100)
def shot(frame,kind,payload,name,mode_index):
    k,_,th,h,lo,hi,mn,mx,amp,obs=struct.unpack('<BBhHhhIIHI',payload)
    w.hardware_connected=True;w.current=frame;w.device_rate=frame.rate
    w.trigger_type.setCurrentIndex(kind);w.threshold.setValue((th+.5)*u.SCALE);w.hysteresis.setValue(h*u.SCALE)
    w.win_low.setValue((lo+.5)*u.SCALE);w.win_high.setValue((hi+.5)*u.SCALE)
    w.width_min.setValue(mn/25);w.width_max.setValue(mx/25);w.amp_limit.setValue(amp*u.SCALE);w.observation.setValue(obs)
    w.acquisition_mode.setCurrentIndex(mode_index)
    w.timebase.setCurrentIndex(1)
    vv=u.measure(w.display_volts(),frame.rate)
    w.display_center.setValue((vv['maximum']+vv['minimum'])/2)
    choices=[i for i,v in enumerate(u.VOLT_DIVS) if vv['vpp']/v<=7.6]
    w.volts_div.setCurrentIndex(min(choices,key=lambda i:abs(vv['vpp']/u.VOLT_DIVS[i]-6)) if choices else 7)
    w.render_current();w.state_label.setText('STOP · 实物冻结帧')
    w.badge.setText('实物帧回放');w.control_tabs.setCurrentIndex(1)
    w.footer.setText(f'实物 UART · 1 MHz 正弦回环 · {u.TRIGGERS[kind]} · 触发索引 {frame.trigger} · 时间戳 {frame.timestamp}')
    app.processEvents();assert w.grab().save(str(OUT/name))
if '--render-existing' in sys.argv:
    saved=json.loads((OUT/'report.json').read_text(encoding='utf-8'))
    assert saved['result']=='PASS'
    for item in saved['frames']:
        frame=u.Capture(np.load(OUT/(item['name']+'.npy')),25000000,item['trigger'],item['timestamp'],'硬件 UART',item['kind'],fpga_measurement=item['measurement'])
        shot(frame,u.TRIGGERS.index(item['kind']),bytes.fromhex(item['config_hex']),item['name']+'.png',1 if item['mode']=='NORMAL' else 2)
    w.hardware_connected=False;w.close();sys.exit(0)
try:
    link.open_link();r['build']=hex(link.build_id);r['capabilities']=link.capabilities
    original=link.exchange(p.GET_CONFIG).payload;mode=link.exchange(p.GET_CAPTURE_CONFIG).payload
    r['original_config']=original.hex();r['original_mode']=mode.hex();save()
    stop();link.exchange(p.SET_RECORD,struct.pack('<II',16384,500000))
    link.exchange(p.SET_DDS,struct.pack('<BBIIHi',0,1,1000000,0,819,0));time.sleep(.15)
    # AUTO preview establishes measured center/span for trigger limits.
    link.exchange(p.SET_TRIGGER,struct.pack('<BBhHhhIIHI',0,0,0,2,-100,100,1,100,100,100))
    f=link.capture(8,acquisition_mode=0)
    x=2047-(f.words&4095).astype(np.int64);mid=int((x.max()+x.min())//2);span=int(np.ptp(x))
    r['preview']={'minimum':int(x.min()),'maximum':int(x.max()),'vpp_codes':span,'measurement':f.fpga_measurement};save()
    assert span>8 and not np.any(f.words&0x8000),'No valid analog loopback'
    assert abs(f.fpga_measurement['frequency']-1000000)<20000,'Not a 1 MHz analog loopback'
    for kind in range(8):
        stop();payload=config(kind);link.exchange(p.SET_TRIGGER,payload);link.trigger_kind=kind
        for j in range(4):
            # NORMAL supplies two frames; SINGLE supplies two independently armed frames.
            acq=1 if j<2 else 2
            if j==2:stop()
            guard=threading.Timer(8,link.cancel_capture.set);guard.start()
            try:f=link.capture(6,acquisition_mode=acq if acq==1 else None)
            finally:guard.cancel()
            assert len(f.words)==16384 and f.trigger==8192 and f.rate==25000000
            assert not np.any(f.words&0x8000)
            assert abs(f.fpga_measurement['frequency']-1000000)<20000
            name=f'{kind+1:02d}_{j+1:02d}'
            np.save(OUT/(name+'.npy'),f.words,allow_pickle=False)
            item={'name':name,'kind':u.TRIGGERS[kind],'mode':'NORMAL' if j<2 else 'SINGLE','timestamp':f.timestamp,'trigger':f.trigger,'config_hex':payload.hex(),'measurement':f.fpga_measurement}
            r['frames'].append(item);save()
            shot(f,kind,payload,name+'.png',acq)
            if j==3:
                before=link.exchange(p.READ_MEASURE);time.sleep(.1);after=link.exchange(p.READ_MEASURE)
                assert (before.timestamp,before.payload)==(after.timestamp,after.payload)
        stop();link.exchange(p.SET_TRIGGER,config(kind,False));link.exchange(p.SET_CAPTURE_MODE,p.capture_mode_payload(1));link.exchange(p.RUN)
        start=time.monotonic();observations=[]
        while time.monotonic()-start<1.0:
            st=link.read_status();observations.append({'elapsed':time.monotonic()-start,'flags':st['flags']})
            assert st['flags']&1 and not st['flags']&2,'Mismatched trigger captured'
            time.sleep(.05)
        r['waiting'].append({'kind':u.TRIGGERS[kind],'config_hex':config(kind,False).hex(),'seconds':time.monotonic()-start,'observations':observations});save()
        print('DONE',u.TRIGGERS[kind],flush=True)
    stop();link.exchange(p.SET_TRIGGER,config(0,False));f=link.capture(8,acquisition_mode=0)
    r['checks']['AUTO_unmatched_timeout_frame']={'trigger':f.trigger,'timestamp':f.timestamp}
    shot(f,0,config(0,False),'AUTO_timeout.png',0)
    assert len(r['frames'])==32 and len({f['timestamp'] for f in r['frames']})==32
    r['checks']['parser_errors']=link.parser.errors.copy();assert not any(link.parser.errors.values())
    r['result']='PASS'
except BaseException as e:
    r['error']=repr(e);r['traceback']=traceback.format_exc();print(r['traceback'],flush=True)
finally:
    try:
        if original is not None:
            length,pre=struct.unpack('<II',original[:8])
            stop();link.exchange(p.SET_RECORD,struct.pack('<II',length,round(pre*1000000/length)),restoring=True);link.exchange(p.SET_TRIGGER,original[8:32],restoring=True);link.exchange(p.SET_DDS,original[32:48],restoring=True);link.exchange(p.SET_CAPTURE_MODE,mode,restoring=True)
            assert link.exchange(p.GET_CONFIG).payload==original
            r['restored']=True
    except BaseException as e:r['restore_error']=repr(e)
    if link.link:link.link.close()
    r['finished']=time.strftime('%Y-%m-%d %H:%M:%S');save()
    w.hardware_connected=False;w.close()
print(r['result'],len(r['frames']),str(OUT),flush=True)
sys.exit(r['result']!='PASS')
