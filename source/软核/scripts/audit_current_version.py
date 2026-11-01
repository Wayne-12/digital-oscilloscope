"""Read-only version/source audit; does not configure hardware or refresh snapshots."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'软核/reports/version_sync_20261030'
OUT.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((ROOT/'软核/reports/source_snapshot.json').read_text(encoding='utf-8'))
changes=[k for k,h in manifest.items() if not (ROOT/k).is_file() or sha(ROOT/k)!=h]
rtl_differences=[]
for p in (ROOT/'FPGA/rtl').rglob('*.sv'):
    q=ROOT/'软核/integration/rtl'/p.relative_to(ROOT/'FPGA/rtl')
    if not q.is_file() or p.read_bytes()!=q.read_bytes():rtl_differences.append(str(p.relative_to(ROOT/'FPGA/rtl')))
report=dict(original_manifest_changes=changes,integration_rtl_differences=rtl_differences,
 files={str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'示波器显示界面.py',ROOT/'PC/protocol/absolute_calibration.py',ROOT/'校正参数.json',ROOT/'VGA显示部分/板端独立版/panel_main.c',ROOT/'VGA显示部分/板端独立版/panel_screen.sv']})
sys.path.insert(0,str(ROOT/'软核/scripts'))
try:
 from hardware_client import Client,baseline
 c=Client()
 try:report['hardware']=baseline(c)
 finally:c.close()
except Exception as exc:report['hardware_error']=repr(exc)
(OUT/'audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
