"""Assemble a disposable, ASCII-named Vivado workspace from submission sources."""
from pathlib import Path
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'build'/'work'

def merge(source,target):
    target.mkdir(parents=True,exist_ok=True)
    shutil.copytree(source,target,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))

def main():
    merge(ROOT/'src',WORK)
    merge(ROOT/'build/scripts/cpu',WORK/'cpu/scripts')
    merge(ROOT/'build/scripts/display',WORK/'display')
    merge(ROOT/'sim/display',WORK/'display')
    merge(ROOT/'sim/cpu',WORK/'cpu/tests')
    merge(ROOT/'sim/pc',WORK/'pc/tests')
    merge(ROOT/'board/scripts',WORK/'display')
    merge(ROOT/'board/runtime',WORK/'display/output')
    merge(ROOT/'board/release',WORK/'display/release')
    (WORK/'cpu/reports').mkdir(parents=True,exist_ok=True)
    (WORK/'tmp').mkdir(parents=True,exist_ok=True)
    (WORK/'tmp/ui-check').mkdir(parents=True,exist_ok=True)
    for sub in ['source_snapshot.json','release_manifest.json']:
        shutil.copy2(ROOT/'report/release_provenance'/sub,WORK/'display/output'/sub)
    for name in ['build.log','timing.rpt','utilization.rpt','cdc.rpt','drc.rpt','methodology.rpt']:
        shutil.copy2(ROOT/'build/reports/production'/name,WORK/'display/output'/name)
    for name in ['simulate.log','c_tests.log']:
        shutil.copy2(ROOT/'sim/results/production'/name,WORK/'display/output'/name)
    # Original signed-off manifests stay byte-identical in report/. The working
    # snapshot only translates source paths and retains its original timestamp.
    snap=WORK/'display/output/source_snapshot.json'
    original=json.loads(snap.read_text(encoding='utf-8-sig'))
    def translate(s):
        return s.replace('VGA显示部分','display').replace('软核','cpu').replace('校正参数.json','voltage_calibration.json').replace('start.S','start.s')
    original['inputs']={translate(k):v for k,v in original['inputs'].items()}
    for name,digest in original['inputs'].items():
        p=WORK/Path(name.replace('\\','/'))
        assert hashlib.sha256(p.read_bytes()).hexdigest()==digest, 'Production source differs: '+name
    snap.write_text(json.dumps(original,ensure_ascii=False,indent=2),encoding='utf-8')
    original_image=json.loads((ROOT/'report/release_provenance/image_manifest.json').read_text(encoding='utf-8'))
    original_image['sha256']['output/source_snapshot.json']=hashlib.sha256(snap.read_bytes()).hexdigest()
    (WORK/'display/release/image_manifest.json').write_text(json.dumps(original_image,indent=2),encoding='utf-8')
    # Full-submission integrity is checked at its root with sim/verify_submission.py.
    print('WORKSPACE_READY',WORK)
    return WORK
if __name__=='__main__':main()
