"""Read-only integrity check of the frozen display release and its dependencies."""
from pathlib import Path
import hashlib,json
root=Path(__file__).resolve().parent
manifest=json.loads((root/'release/final_package_manifest.json').read_text(encoding='utf-8'))
for name,digest in manifest['sha256'].items():
    path=(root.parent/name).resolve()
    assert path.is_relative_to(root.parent.resolve()),'Path outside workspace: '+name
    assert hashlib.sha256(path.read_bytes()).hexdigest()==digest,'Changed or missing: '+name
print('FINAL_PACKAGE_VERIFIED',len(manifest['sha256']))
