"""Record source identity and reject stale or failed build/test artifacts."""
from pathlib import Path
import hashlib,json,re,sys,time
root=Path(__file__).resolve().parent
project=root.parent
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def inputs():
    found=[p for p in root.iterdir() if p.suffix in {'.c','.h','.sv','.svh','.mem','.xdc'}]
    cpu=project/'软核'
    for folder in ('firmware','rtl','integration'):
        found.extend(p for p in (cpu/folder).rglob('*') if p.suffix in {'.c','.h','.S','.ld','.sv','.v','.xdc'})
    found.append(project/'校正参数.json')
    return {str(p.relative_to(project)):sha(p) for p in sorted(set(found))}
stamp=root/'output/source_snapshot.json'
if len(sys.argv)>1 and sys.argv[1]=='snapshot':
    stamp.write_text(json.dumps({'created':time.time(),'inputs':inputs(),'elf':sha(root/'output/panel.elf')},ensure_ascii=False,indent=2),encoding='utf-8')
    print('SOURCE_SNAPSHOT_READY');raise SystemExit
before=json.loads(stamp.read_text(encoding='utf-8'))
assert before['inputs']==inputs(),'Sources changed after snapshot'
assert before['elf']==sha(root/'output/panel.elf'),'ELF changed after snapshot'
for file,markers in {'c_tests.log':['NAVIGATION_TEST_PASS','COMMAND_TEST_PASS','PANEL_C_TEST_PASS'],
                     'simulate.log':['PANEL_SIMULATION_PASS'],'build.log':['PANEL_BUILD_PASS']}.items():
    content=(root/'output'/file).read_text(encoding='utf-8',errors='replace')
    assert all(re.search(r'^'+marker+r'$',content,re.M) for marker in markers),file
bit=root/'output/cpu_vga_runtime.bit'
assert bit.stat().st_mtime>=before['created'],'Stale bitstream'
timing=(root/'output/timing.rpt').read_text()
assert 'All user specified timing constraints are met.' in timing,'Timing not closed'
cdc=(root/'output/cdc.rpt').read_text()
assert not re.search(r'^CDC-\d+\s+Critical\s+[1-9]',cdc,re.M),'Critical CDC'
manifest={'verified_at':time.time(),'firmware_build':'0xAF311031','inputs':inputs(),
          'elf_sha256':sha(root/'output/panel.elf'),'bit_sha256':sha(bit),
          'hardware_programmed':False,'physical_display_verified':False}
previous_path=root/'output/release_manifest.json'
if previous_path.exists():
    previous=json.loads(previous_path.read_text(encoding='utf-8-sig'))
    if previous.get('bit_sha256')==manifest['bit_sha256']:
        for key in ('hardware_programmed','physical_display_verified','program_record','flash_record'):
            if key in previous:manifest[key]=previous[key]
(root/'output/release_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print('RELEASE_VERIFIED')
