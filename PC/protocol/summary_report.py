"""Version-scoped engineering evidence in one atomic UTF-8-BOM CSV."""
from datetime import datetime,timezone,timedelta
from pathlib import Path
import csv,hashlib,json,math,os,re,tempfile

FIELDS=('category','metric','value','unit','status','scope','firmware_build','source','source_sha256','notes')
ERROR_NAMES=('crc','length','version','timeout','unknown_command','command_rejected','uart_framing','rx_overflow','good_requests')

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))

def implementation_rows(folder):
    """Read actual routed reports; missing/ambiguous data never becomes zero."""
    folder=Path(folder);result=[]
    timing=folder/'timing.rpt';util=folder/'utilization.rpt'
    if timing.exists():
        text=timing.read_text(encoding='utf-8')
        row=re.search(r'^\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(\d+)\s+(\d+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(\d+)\s+(\d+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(\d+)\s+(\d+)\s*$',text,re.M)
        if not row:raise ValueError('无法解析实际布局布线时序汇总')
        values=list(map(float,row.groups()))
        for name,index,unit in [('setup_wns',0,'ns'),('setup_tns',1,'ns'),('setup_failing_endpoints',2,'endpoints'),
                               ('hold_whs',4,'ns'),('hold_ths',5,'ns'),('hold_failing_endpoints',6,'endpoints'),
                               ('pulse_width_slack',8,'ns'),('pulse_width_failing_endpoints',10,'endpoints')]:
            good=values[index]>=0 if 'slack' in name or name in ('setup_wns','hold_whs') else values[index]==0
            result.append(('timing',name,values[index],unit,'PASS' if good else 'FAIL',timing,''))
    else:result.append(('timing','routed_report','','','UNAVAILABLE',timing,'No routed timing report'))
    if util.exists():
        text=util.read_text(encoding='utf-8')
        for label,name,unit in [('Slice LUTs','lut','LUT'),('Slice Registers','register','FF'),('Block RAM Tile','bram','36K_tile'),('DSPs','dsp','DSP'),('Bonded IOB','io','pins')]:
            match=re.search(r'^\|\s*'+re.escape(label)+r'\s*\|\s*([\d.]+)\s*\|\s*\d+\s*\|\s*\d+\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|',text,re.M)
            if not match:raise ValueError('无法解析资源项：'+label)
            used,available,percent=map(float,match.groups())
            for suffix,value,value_unit in (('used',used,unit),('available',available,unit),('utilization',percent,'%')):
                result.append(('resource',name+'_'+suffix,value,value_unit,'MEASURED',util,'Vivado routed utilization'))
    else:result.append(('resource','routed_report','','','UNAVAILABLE',util,'No routed resource report'))
    return result

def matching_release(root,build):
    matches=[]
    for path in (Path(root)/'FPGA/output').glob('*/release_manifest.json'):
        try:
            m=load(path)
            if int(m.get('build','0'),0)==build:
                bit=path.parent/m['bitstream']
                if not bit.is_file() or sha(bit)!=m['bitstream_sha256']:raise ValueError('固件发布镜像哈希不一致')
                matches.append((path,m))
        except (KeyError,TypeError,json.JSONDecodeError):continue
    if len(matches)>1:raise ValueError('同版本有多个发布包，不能自动选取时序/资源报告')
    return matches[0] if matches else (None,None)

def collect(root,live,measurement=None):
    root=Path(root);rows=[];build=int(live['build']);build_text=f'0x{build:08X}'
    def add(category,metric,value='',unit='',status='MEASURED',scope='current-device',source='',notes='',version=None):
        if isinstance(value,float) and not math.isfinite(value):value='';status='UNAVAILABLE'
        source=Path(source) if source else None
        rows.append(dict(zip(FIELDS,(category,metric,value,unit,status,scope,version or build_text,
            str(source) if source else '',sha(source) if source and source.is_file() else '',notes))))
    add('report','format','scope-summary-csv-v1',status='INFO')
    add('report','generated_at',datetime.now(timezone(timedelta(hours=8))).isoformat(),status='INFO')
    for key in ('build','capabilities','port','baud','device_id','sample_rate','captured_at'):
        add('device',key,live.get(key,''),'bit/s' if key=='baud' else 'SPS' if key=='sample_rate' else '',source=live.get('snapshot_path',''))
    manifest,m=matching_release(root,build)
    if manifest:
        add('firmware','bitstream_sha256',m['bitstream_sha256'],status='VERIFIED_FILE',source=manifest,
            notes='Package hash verified; device version matches build. No on-device bitstream hash command.')
        for category,name,value,unit,status,source,notes in implementation_rows(manifest.parent/'implementation'):
            add(category,name,value,unit,status,'current-build',source,notes)
        add('firmware','hardware_acceptance',m.get('hardware_verdict','UNAVAILABLE'),status='INFO',source=manifest)
        add('firmware','flash_programmed',m.get('flash_programmed',False),status='INFO',source=manifest)
    else:
        add('timing','routed_report',status='UNAVAILABLE',notes='No release matches current build')
        add('resource','routed_report',status='UNAVAILABLE',notes='No release matches current build')
    if measurement is not None:
        if measurement.get('firmware_build')!=build or measurement.get('source')!='硬件 UART':
            add('measurement','snapshot',status='UNAVAILABLE',notes='Snapshot source or firmware does not match current device')
        else:
            for key in ('timestamp','record_offset','record_length','read_samples','rate','trigger_index'):
                add('measurement',key,measurement.get(key,''),scope='frozen-frame')
            for section in ('pc','fpga','saturation'):
                values=measurement.get(section)
                if not values:add('measurement',section,status='UNAVAILABLE',scope='frozen-frame');continue
                for name,value in values.items():
                    if isinstance(value,(int,float,bool)):
                        unit=('V' if section=='pc' and name in ('vpp','rms','mean','minimum','maximum') else 'Hz' if name=='frequency' else 'ADC_LSB' if section=='fpga' and name in ('minimum','maximum','vpp','rms','mean') else '')
                        add('measurement',section+'.'+name,value,unit,scope='frozen-frame',notes='PC values use nominal ADC voltage conversion' if section=='pc' else '')
            spectrum=measurement.get('spectrum')
            if spectrum:
                for name in ('valid','peak_bin','frequency','amplitude','clipped'):
                    add('spectrum',name,spectrum.get(name,''),'Hz' if name=='frequency' else 'ADC_LSB' if name=='amplitude' else '',scope='frozen-frame')
                for h in spectrum['harmonics']:
                    add('spectrum',f"H{h['order']}_amplitude",h['amplitude'] if h['valid'] else '', 'ADC_LSB',
                        'VALID' if h['valid'] else 'INVALID','frozen-frame',notes='1024 point FPGA Hann FFT')
            calibration=measurement.get('voltage_calibration',{})
            add('voltage-calibration','mode',calibration.get('mode','nominal'),status='INFO',scope='display-only',
                notes='No external-reference DC calibration' if calibration.get('mode')!='external-reference-dc' else
                      'DC checked points only; no AC or full-range accuracy qualification')
            for name,value in calibration.items():
                if name!='mode' and isinstance(value,(str,int,float,bool)):
                    add('voltage-calibration',name,value,status='INFO',scope='display-only')
            for name,value in measurement.get('display_pc',{}).items():
                if isinstance(value,(int,float)):
                    add('display-measurement',name,value,'V' if name in ('vpp','rms','mean','minimum','maximum') else '',
                        scope='frozen-frame',notes='Displayed voltage conversion; see voltage-calibration mode')
    else:add('measurement','snapshot',status='UNAVAILABLE',notes='No frozen frame selected')
    for index,name in enumerate(ERROR_NAMES):
        add('communication','fpga_'+name,live['counters'][index],'count',scope='since-fpga-reset',source=live.get('snapshot_path',''),
            notes='Cumulative counter; includes deliberate invalid-command tests' if name=='command_rejected' else '')
    for name,value in live['pc_errors'].items():add('communication','pc_'+name,value,'count',scope='current-connection',source=live.get('snapshot_path',''))
    add('communication','bit_error_rate',status='NOT_MEASURED',notes='CRC counters are not bit error rate; use matched echo evidence')
    # Report all explicit hardware UART evidence, with scope and version retained.
    paths=list((root/'PC/acceptance_runs').glob('*/report.json'))
    paths+=list((root/'releases').glob('*/PC/acceptance_runs/*/report.json'))
    seen=set();current_formal=False
    for path in sorted(paths):
        try:e=load(path);key=(e.get('started_at'),e.get('build'),e.get('firmware_sha256'))
        except (OSError,ValueError):continue
        if e.get('source')!='hardware-uart' or key in seen:continue
        seen.add(key)
        same=(int(e.get('build','0'),0)==build and m is not None and e.get('firmware_sha256')==m['bitstream_sha256'] and e.get('baud')==live['baud'])
        formal=same and e.get('device_id')==live['device_id'] and e.get('verdict')=='PASS' and e.get('restored') and live['baud'] in e.get('qualified_bauds',[])
        current_formal|=bool(formal)
        scope='current-image-test' if same else 'historical-other-image'
        version=e.get('build','UNKNOWN')
        for name in ('verdict','started_at','baud','device_id','echo_payload_bytes','echo_seconds','soak_seconds','soak_captures','captures','incomplete_captures','recovery','restored'):
            if name in e:add('uart-test',name,e[name],'bytes' if name=='echo_payload_bytes' else 's' if name.endswith('seconds') else '',str(e.get('verdict','UNKNOWN')),scope,path,version=version)
        for section in ('transport_errors','pc_errors','fpga_error_deltas'):
            for name,value in e.get(section,{}).items():add('uart-test',section+'.'+name,value,'count',str(e.get('verdict','UNKNOWN')),scope,path,version=version)
    add('qualification','current_image_formal_uart',bool(current_formal),status='PASS' if current_formal else 'NOT_QUALIFIED',
        notes='Qualification restricted to image SHA256, device record, baud and conditions; historical results are not inherited')
    return rows

def export(path,root,live,measurement=None):
    rows=collect(root,live,measurement);path=Path(path);temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8-sig',newline='',dir=path.parent,prefix='.scope-summary-',suffix='.tmp',delete=False) as f:
            temporary=Path(f.name);writer=csv.DictWriter(f,fieldnames=FIELDS);writer.writeheader();writer.writerows(rows)
        os.replace(temporary,path);temporary=None
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)
    return rows
