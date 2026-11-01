"""Read-only verification of all delivered file bytes."""
from pathlib import Path
import hashlib, json
root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / 'UPLOAD_MANIFEST.json').read_text(encoding='utf-8'))
for name, expected in manifest['files'].items():
    path = (root / name).resolve()
    if not path.is_relative_to(root) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise SystemExit('UPLOAD_VERIFY_FAILED: ' + name)
print('UPLOAD_VERIFIED', len(manifest['files']))
