import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from verify_manifest import verify


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.file = self.root / 'runtime.bit'
        self.file.write_bytes(b'accepted-image')
        self.digest = hashlib.sha256(self.file.read_bytes()).hexdigest()
        self.manifest = self.root / 'manifest.json'

    def save(self, entries):
        self.manifest.write_text(json.dumps({'sha256': entries}), encoding='utf-8')

    def test_valid_image_and_windows_relative_separator(self):
        sub = self.root / 'output'
        sub.mkdir()
        (sub / 'image.bit').write_bytes(self.file.read_bytes())
        self.save({'output\\image.bit': self.digest})
        self.assertEqual(verify(self.root, self.manifest), 1)

    def test_tamper_is_rejected(self):
        self.save({'runtime.bit': self.digest})
        self.file.write_bytes(b'changed')
        with self.assertRaises(ValueError):
            verify(self.root, self.manifest)

    def test_missing_image_is_rejected(self):
        self.save({'missing.bit': self.digest})
        with self.assertRaises(OSError):
            verify(self.root, self.manifest)

    def test_escaping_and_absolute_paths_are_rejected(self):
        for name in ('../outside.bit', '/outside.bit', 'C:/outside.bit', 'C:relative.bit'):
            with self.subTest(name=name):
                self.save({name: self.digest})
                with self.assertRaises(ValueError):
                    verify(self.root, self.manifest)

    def test_duplicate_json_entries_are_rejected(self):
        self.manifest.write_text('{"sha256":{"x":"a","x":"b"}}', encoding='utf-8')
        with self.assertRaises(ValueError):
            verify(self.root, self.manifest)

    def test_bad_digest_empty_manifest_and_alias_are_rejected(self):
        for entries in ({'runtime.bit': 'not-sha256'}, {},
                        {'runtime.bit': self.digest, './runtime.bit': self.digest}):
            with self.subTest(entries=entries):
                self.save(entries)
                with self.assertRaises(ValueError):
                    verify(self.root, self.manifest)


if __name__ == '__main__':
    unittest.main()
