"""Verify the saved offline evidence and original-source preservation."""
from pathlib import Path
import hashlib,json,re
root=Path(__file__).resolve().parents[1]
def report(name):
    return (root/'reports'/name).read_text(encoding='utf-8',errors='replace')
original=json.loads(report('source_snapshot.json'))
changed=[p for p,digest in original.items()
         if hashlib.sha256((root.parent/p).read_bytes()).hexdigest()!=digest]
synthesis=report('elaborate_system.log')
checks={
    'host_c_tests':'C_TEST_PASS' in report('host_test.txt'),
    'mailbox_rtl_simulation':'MAILBOX_TEST_PASS' in report('xsim_mailbox.txt'),
    'cpu_ip_readback':all(f'requested={v} actual={v}' in report('cpu_ip_readback.txt') for v in (25,32768,1,0)),
    'integrated_synthesis':bool(re.search(r'^INTEGRATED_SYNTHESIS_PASS\s*$',synthesis,re.M)),
    'no_synthesis_error_or_critical':not re.search(r'^(?:ERROR:|CRITICAL WARNING:)',synthesis,re.M),
    'original_rtl_unchanged':not changed,
    'microblaze_elf_exists':(root/'build/scope_cpu.elf').is_file(),
}
hardware_path=root/'reports/hardware_validation.json'
hardware=json.loads(hardware_path.read_text(encoding='utf-8')) if hardware_path.exists() else None
if hardware:
    checks.update({f'hardware_{k}':v for k,v in hardware['checks'].items()})
    checks['runtime_image_matches_physical_report']=hardware['runtime_bit_sha256']==hashlib.sha256((root/'build/scope_cpu_runtime.bit').read_bytes()).hexdigest()
    for relative,digest in hardware.get('rtl_overlay_hashes',{}).items():
        checks[f'active_overlay_matches_report_{relative}']=hashlib.sha256((root/relative).read_bytes()).hexdigest()==digest
result={
    'checks':checks,'original_rtl_files':len(original),'changed_original_rtl':changed,
    'elf_sha256':hashlib.sha256((root/'build/scope_cpu.elf').read_bytes()).hexdigest(),
    'not_verified':hardware['limitations'] if hardware else ['CPU instruction execution and 921600-baud throughput',
                    'post-route timing and DRC','physical UI/ADC/DAC integration'],
    'hardware_access_performed':hardware is not None,
    'volatile_fpga_programming_performed':hardware is not None,
    'flash_programming_performed':False,
    'result':'PASS' if all(checks.values()) else 'FAIL',
}
(root/'reports/delivery_verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
if not all(checks.values()): raise SystemExit(1)
