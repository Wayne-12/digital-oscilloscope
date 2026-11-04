"""Bind SPI programming files to the verified display bitstream and firmware."""
from pathlib import Path
import hashlib,json,sys
root=Path(__file__).resolve().parent
files=('output/cpu_vga_runtime.bit','output/panel.elf','output/source_snapshot.json',
       'release/display_final.bit','release/display_final.bin','release/display_final.mcs')
actual={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in files}
path=root/'release/image_manifest.json'
if len(sys.argv)>1 and sys.argv[1]=='snapshot':
    release=json.loads((root/'output/release_manifest.json').read_text(encoding='utf-8-sig'))
    assert release['bit_sha256']==actual['output/cpu_vga_runtime.bit']
    assert release['elf_sha256']==actual['output/panel.elf']
    path.write_text(json.dumps({'firmware_build':release['firmware_build'],'sha256':actual},indent=2),encoding='utf-8')
else:
    expected=json.loads(path.read_text(encoding='utf-8'))
    assert expected['sha256']==actual,'SPI files do not match the verified display release'
print('FLASH_IMAGE_VERIFIED')
