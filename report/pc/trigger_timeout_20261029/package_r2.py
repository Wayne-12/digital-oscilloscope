"""Seal r2 without altering the historical r1 package or claiming a new boot."""
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT/'releases/scope_20261029_r2'
ZIP = OUT.with_suffix('.zip')
assert not OUT.exists() and not ZIP.exists(), 'Preserve sealed releases'
evidence = Path(__file__).resolve().parent
tests = (evidence/'pc_tests.log').read_text(encoding='utf-8')
assert tests.rstrip().endswith('OK')
count = int(re.search(r'Ran (\d+) tests', tests).group(1))
assert 'All checks passed!' in (evidence/'ruff.log').read_text()
assert json.loads((evidence/'restored_hardware.json').read_text(encoding='utf-8'))['result'] == 'PASS'
sys.path.insert(0, str(ROOT/'FPGA/scripts'))
from verify_current_deployment import validate_images
_, firmware, hardware = validate_images()
previous = json.loads((ROOT/'releases/scope_20261029_r1/delivery_manifest.json').read_text(encoding='utf-8'))
files = set(previous['files_sha256'])-{'README.md'}
files.add('docs/verification/trigger_timeout_20261029_r2.md')
files.add('PC/tests/test_trigger_wait_diagnostics.py')
files.update(f.relative_to(ROOT).as_posix() for f in evidence.iterdir() if f.is_file())
hashes = {}
for name in sorted(files):
    source, dest = ROOT/name, OUT/name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)
    hashes[name] = hashlib.sha256(source.read_bytes()).hexdigest()
readme = '''# 2026.10.29-r2 固定版本

修复触发超时诊断与DDS参数确认/存档/读回。根目录“启动示波器界面.cmd”运行最新版。
实机原因：DDS实际幅度为0码，输入噪声不足以跨越当前迟滞触发范围；不是Flash丢失。
已恢复100kHz正弦、10%幅度并通过3次SINGLE、3次AUTO实机采集，错误计数无新增。
169项PC测试及Ruff通过。完整记录在docs/verification/trigger_timeout_20261029_r2.md。

FPGA版本保留0xA4261027、能力63；41项硬件输入和BIT/BIN/MCS校验一致。
本次为PC修复，未擦写Flash、未重配FPGA、未重新进行真实断电测试。
随包镜像及旧冷启动证据保持可追溯，不能将历史证据当作本次硬件测试。
SINGLE仍严格等待触发；无信号预览使用AUTO后点RUN，修改输出需应用DDS配置。

本包不含Python/Vivado运行环境，复制到其他电脑需准备PC/ui/requirements.txt依赖。
r1原始证据保留其历史版本号和结论；本次交付以delivery_manifest.json和r2记录为准。
'''
(OUT/'README.md').write_text(readme, encoding='utf-8')
hashes['README.md'] = hashlib.sha256((OUT/'README.md').read_bytes()).hexdigest()
manifest = {'format': 'scope-consolidated-delivery-v2',
            'sealed_at': datetime.now(timezone(timedelta(hours=8))).isoformat(),
            'pc_release': '2026.10.29-r2', 'fpga_build': firmware['build'],
            'pc_tests': count, 'ruff': 'PASS', 'hardware_restored_capture': 'PASS_3_SINGLE_3_AUTO',
            'hardware_sources_sha256': hardware,
            'fpga_logic_changed_this_run': False, 'flash_written_this_run': False,
            'flash_readback_this_run': False, 'cold_boot_test_this_run': False,
            'flash_action': 'RETAIN_UNCHANGED_IMAGE_PC_ONLY_FIX',
            'image_and_hardware_source_hash_validation': 'PASS',
            'historical_flash_evidence': 'FPGA/reports/flash/consolidated_20261029/manifest.json',
            'files_sha256': hashes}
(OUT/'delivery_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
for name, digest in hashes.items():
    assert hashlib.sha256((OUT/name).read_bytes()).hexdigest() == digest
with zipfile.ZipFile(ZIP, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(OUT.rglob('*')):
        if path.is_file():
            archive.write(path, path.relative_to(OUT.parent))
with zipfile.ZipFile(ZIP) as archive:
    assert archive.testzip() is None
result = {'files': len(hashes)+1, 'zip': str(ZIP), 'bytes': ZIP.stat().st_size,
          'sha256': hashlib.sha256(ZIP.read_bytes()).hexdigest(), 'archive_and_copy_checks': 'PASS'}
(evidence/'package_result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result))
