"""Bind tested CPU/UI sources to the programmed and cold-booted release."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib
import json
ROOT=Path(__file__).resolve().parents[2]
PANEL=ROOT/'VGA显示部分';RELEASE=PANEL/'release'
CANDIDATE=PANEL/'diagnostics/ownership_20261101'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
name=(RELEASE/'latest_flash_report.txt').read_text().strip()
assert name.startswith('hardware_20261101_')
hardware=RELEASE/name
image=RELEASE/'display_final.bin'
assert (hardware/'flash_before.bin').stat().st_size==8388608
assert (hardware/'flash_after.bin').read_bytes()==image.read_bytes()
assert 'PANEL_FLASH_PROGRAM_PASS' in (CANDIDATE/'output/program_flash.log').read_text()
assert 'FLASH_COLD_BOOT_REGISTERS_PASS' in (PANEL/'output/verify_flash_boot.log').read_text()
review_path=ROOT/'PC/reports/control_handoff_20261101/review_before_flash.json'
review=json.loads(review_path.read_text(encoding='utf-8'))
assert [x['event'] for x in review['events']][:4]==['LOCAL_CONTROL','PC_CONNECTED','LOCAL_CONTROL','PC_CONNECTED']
assert max(x['frames'] for x in review['snapshots'])>=100
assert all(not any(x['parser_errors'].values()) for x in review['snapshots'])
cold=json.loads((ROOT/'PC/reports/control_handoff_20261101/cold_boot_owner.json').read_text())
assert cold['result']=='PASS'
size=image.stat().st_size
runtime=(PANEL/'output/cpu_vga_runtime.bit').read_bytes()
assert runtime[-size:]==(CANDIDATE/'output/cpu_vga_runtime.bit').read_bytes()[-size:]
record={'firmware_build':'0xAF311031','cpu_software_revision':'control_handoff_1','pc_release':'2026.11.01-r4',
    'programmed_at':'2026-11-01T15:55:25+08:00','recorded_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),
    'part':'n25q64-3.3v-spi-x1_x2_x4','jedec':'20ba17','capacity_bytes':8388608,
    'configuration':{'mode':'SPIx1','startup_clock':'CCLK','configuration_rate_mhz':3},
    'runtime_bit_sha256':sha(PANEL/'output/cpu_vga_runtime.bit'),
    'runtime_configuration_payload_sha256':hashlib.sha256(runtime[-size:]).hexdigest(),
    'tested_jtag_bit_sha256':sha(CANDIDATE/'output/cpu_vga_runtime.bit'),
    'elf_sha256':sha(PANEL/'output/panel.elf'),
    'flash_bit_sha256':sha(RELEASE/'display_final.bit'),'flash_bin_sha256':sha(image),
    'readback_sha256':sha(hardware/'flash_after.bin'),'backup_sha256':sha(hardware/'flash_before.bin'),
    'image_bytes':size,'hardware_report':str(hardware.relative_to(ROOT)),
    'program_verify':'PASS','independent_readback':'PASS',
    'boot_registers':{'mode':'001','done':1,'eos':1,'crc_error':0},
    'true_power_cycle_user_confirmed':True,'cold_boot_registers':'PASS','cold_boot_local_owner_reply':6,
    'local_keys_and_waveform_after_power_restore_user_confirmed':True,
    'bidirectional_live_handoff':'PASS','ui_regression_tests_passed':66,
    'handoff_evidence':str(review_path.relative_to(ROOT)),
    'parent_hardware':'RTL/XDC/fonts/routed FPGA unchanged; CPU ELF only updated; existing timing/CDC closure reused'}
(RELEASE/'flash_record.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
manifest_path=PANEL/'output/release_manifest.json'
manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
manifest.update(cpu_software_revision='control_handoff_1',hardware_programmed=True,
                physical_display_verified=True,flash_record='release/flash_record.json')
manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
old=json.loads((RELEASE/'archive_20261031_before_handoff_20261101/final_package_manifest.json').read_text(encoding='utf-8'))
files={ROOT/name for name in old['sha256']}
files.update([PANEL/'控制权切换修复与固化_20261101.md',PANEL/'通信修复验证_20261101.md',
              ROOT/'示波器显示界面.py',ROOT/'PC/protocol/absolute_calibration.py',
              ROOT/'PC/reports/control_handoff_20261101/review_before_flash.json',
              ROOT/'PC/reports/control_handoff_20261101/cold_boot_owner.json',
              CANDIDATE/'candidate_manifest.json',CANDIDATE/'output/program_flash.log',
              CANDIDATE/'output/c_tests.log',hardware/'flash_before.bin',hardware/'flash_after.bin',
              hardware/'cold_boot_fpga.rpt',RELEASE/'latest_flash_report.txt',
              PANEL/'output/release_manifest.json'])
assert all(p.is_file() for p in files)
package={'firmware_build':'0xAF311031','cpu_software_revision':'control_handoff_1',
         'status':'FLASH_PROGRAM_READBACK_COLD_BOOT_HANDOFF_VERIFIED','source_workspace':str(ROOT),
         'sha256':{str(p.relative_to(ROOT)):sha(p) for p in sorted(files)}}
(RELEASE/'final_package_manifest.json').write_text(json.dumps(package,ensure_ascii=False,indent=2),encoding='utf-8')
print('LATEST_HANDOFF_RELEASE_BOUND',len(files),record['flash_bin_sha256'])
