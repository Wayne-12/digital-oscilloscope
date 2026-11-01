"""Reuse existing board acceptance contracts with an explicit CPU build guard."""
from pathlib import Path
import hashlib,json
r=Path(__file__).resolve().parents[1]
manifest={}
for filename,old,new in [
 ('verify_capture_modes_hardware.py',"report['build']=='0xa1261026' and worker.capabilities==15", "report['build']=='0xa4261028' and worker.capabilities==63"),
 ('verify_awg_hardware.py','0xA4261027','0xA4261028')]:
 src=r.parent/'FPGA/scripts'/filename
 text=src.read_text(encoding='utf-8')
 if old not in text:raise ValueError(f'Original build guard changed: {filename}')
 dst=r/'scripts'/filename.replace('_hardware','_cpu_hardware')
 dst.write_text(text.replace(old,new),encoding='utf-8')
 manifest[dst.name]={'source':str(src),'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),
                     'change':{'from':old,'to':new}}
(r/'reports/acceptance_test_sources.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print('CPU_BOARD_TESTS_PREPARED')
