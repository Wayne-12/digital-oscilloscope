"""Verify every delivered file and all frozen production artifact hashes."""
from pathlib import Path
import hashlib,json,re,sys
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((ROOT/'report/submission_manifest.json').read_text(encoding='utf-8'))
for name,digest in manifest['sha256'].items():
    p=(ROOT/name).resolve()
    assert p.is_relative_to(ROOT) and sha(p)==digest,'Missing or modified: '+name
for p in ROOT.rglob('*'):
    if any(x in {'work','__pycache__'} for x in p.relative_to(ROOT).parts):continue
    assert re.fullmatch(r'[a-zA-Z0-9_.-]+',p.name),'Invalid filename: '+str(p)
original=json.loads((ROOT/'report/release_provenance/image_manifest.json').read_text(encoding='utf-8'))
for name,digest in original['sha256'].items():
    if name=='output/source_snapshot.json':target=ROOT/'report/release_provenance/source_snapshot.json'
    else:target=ROOT/'board'/name.replace('output/','runtime/')
    assert sha(target)==digest,'Frozen artifact differs: '+name
print('SUBMISSION_VERIFIED',len(manifest['sha256']))
