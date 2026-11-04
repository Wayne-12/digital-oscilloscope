"""Read-only verification of a trusted {sha256: {relative_path: digest}} manifest."""
import argparse
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re
import sys


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key: ' + key)
        result[key] = value
    return result


def verify(root, manifest):
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('Root must be a directory')
    data = json.loads(Path(manifest).read_text(encoding='utf-8-sig'),
                      object_pairs_hook=unique_object)
    entries = data.get('sha256') if isinstance(data, dict) else None
    if not isinstance(entries, dict) or not entries:
        raise ValueError('Expected a nonempty sha256 object')
    seen = set()
    for name, expected in entries.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError('Invalid relative path')
        relative = Path(name.replace('\\', '/'))
        if relative.anchor or PureWindowsPath(name).anchor or '..' in relative.parts:
            raise ValueError('Path must stay inside root: ' + name)
        target = (root / relative).resolve(strict=True)
        if not target.is_relative_to(root) or not target.is_file():
            raise ValueError('Not an in-root file: ' + name)
        if target in seen:
            raise ValueError('Duplicate file through aliases: ' + name)
        seen.add(target)
        if not isinstance(expected, str) or not re.fullmatch('[0-9a-fA-F]{64}', expected):
            raise ValueError('Invalid SHA256: ' + name)
        digest = hashlib.sha256()
        with target.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        if digest.hexdigest() != expected.lower():
            raise ValueError('Hash mismatch: ' + name)
    return len(entries)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--manifest', required=True, type=Path)
    args = parser.parse_args()
    try:
        count = verify(args.root, args.manifest)
    except (OSError, ValueError, TypeError) as exc:
        print('MANIFEST_FAILED: ' + str(exc), file=sys.stderr)
        return 1
    print('MANIFEST_VERIFIED', count)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
