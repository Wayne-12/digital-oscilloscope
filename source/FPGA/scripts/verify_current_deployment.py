"""Verify/persist the unchanged FPGA image; preserve full QSPI backup and new evidence.

PC/UI changes are distributed separately. Never invent a new FPGA build ID.
Requires the operator's current SW0 OFF / modules 5V OFF confirmation.
"""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
TZ = timezone(timedelta(hours=8))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_images():
    package = ROOT/'FPGA/output/awg_921600_20261027'
    manifest = json.loads((package/'release_manifest.json').read_text(encoding='utf-8'))
    require(manifest['build'] == '0xA4261027' and manifest['hardware_verdict'] == 'PASS', 'Unexpected target release')
    bit = package/manifest['bitstream']
    require(sha(bit) == manifest['bitstream_sha256'] ==
            'ddb4aca5667e40ea71628f1fa2ba850ad297a4c20d0bd7dfceb8c34d2acda7d9', 'Target BIT hash differs')
    flash = package/'flash'
    require((flash/'scope_awg_flash.bit').read_bytes() == bit.read_bytes(), 'Flash BIT differs from tested BIT')
    expected = (flash/'scope_awg_flash.bin').read_bytes()
    require(hashlib.sha256(expected).hexdigest() ==
            '51b2ca2980a5580a364021a5599db2a997e39812ddf7e5659f2ab585f11b3e2d', 'Target BIN hash differs')
    base = end = 0
    eof = False
    for line in (flash/'scope_awg_flash.mcs').read_text().splitlines():
        require(line.startswith(':') and not eof, 'Invalid MCS record')
        record = bytes.fromhex(line[1:])
        require(len(record) == record[0]+5 and sum(record) % 256 == 0, 'MCS checksum failed')
        offset, kind, data = int.from_bytes(record[1:3],'big'), record[3], record[4:-1]
        if kind == 4:
            require(len(data) == 2, 'Invalid MCS address record')
            base = int.from_bytes(data,'big') << 16
        elif kind == 0:
            require(base+offset == end and expected[end:end+len(data)] == data, 'MCS and BIN differ')
            end += len(data)
        elif kind == 1:
            require(not data, 'Invalid MCS EOF')
            eof = True
        else:
            raise ValueError('Unsupported MCS record')
    require(eof and end == len(expected), 'Incomplete MCS image')
    hardware = {}
    for name, digest in manifest['source_sha256'].items():
        normalized = name.replace('\\','/')
        if normalized.startswith(('FPGA/rtl/', 'FPGA/constraints/', 'FPGA/ip/')):
            require(sha(ROOT/name) == digest, 'Hardware source differs; must rebuild before programming: '+name)
            hardware[normalized] = digest
    require(len(hardware) >= 41, 'Incomplete hardware-source identity check')
    return package, manifest, hardware


def serial_snapshot(port, folder, name='qspi_boot_serial.json'):
    sys.path.insert(0, str(ROOT/'PC/protocol'))
    import serial
    import scope_protocol as p
    result = {'source':'hardware-uart-read-only','port':port,'baud':921600,'verdict':'FAIL','responses':[]}
    parser = p.Parser()
    with serial.Serial(port,921600,timeout=.02,write_timeout=2) as link:
        link.reset_input_buffer()
        requests = (p.PING,p.GET_VERSION,p.GET_CAPABILITIES,p.GET_STATUS,p.GET_CONFIG,p.GET_CAPTURE_CONFIG,0x19)
        for sequence, kind in enumerate(requests,0x5000):
            payload = b'PERSISTENT_IMAGE_VERIFY' if kind == p.PING else b''
            wire = p.encode(p.Frame(kind, sequence=sequence, payload=payload))
            require(link.write(wire) == len(wire), 'Short serial write')
            deadline = time.monotonic()+3
            response = None
            while response is None and time.monotonic() < deadline:
                for frame in parser.feed(link.read(max(1,min(link.in_waiting,4096)))):
                    if frame.kind == kind|128 and frame.sequence == sequence:
                        response = frame
                        break
            require(response is not None and response.flags == p.RESPONSE, 'Missing or invalid UART response')
            body = response.payload
            result['responses'].append({'command':kind,'payload_hex':body.hex(),'rate':response.sample_rate})
            if kind == p.PING:
                require(body == payload, 'PING mismatch')
            elif kind == p.GET_VERSION:
                require(body == b'\x01\x00\x00\x00'+struct.pack('<I',0xA4261027), 'Wrong booted firmware')
                result['build'] = '0xA4261027'
            elif kind == p.GET_CAPABILITIES:
                require(body == struct.pack('<IHH',63,800,2048), 'Wrong capabilities')
            elif kind == p.GET_STATUS:
                require(len(body) == 48 and response.sample_rate == 25000000 and body[:4] == bytes([4,0,1,0]), 'Unexpected boot state')
                counters = struct.unpack_from('<9I',body,12)
                require(not any(counters[:8]), 'Nonzero boot error counters')
                result['fpga_error_counters'] = list(counters[:8])
            elif kind == p.GET_CONFIG:
                require(len(body) == 48 and struct.unpack_from('<II',body) == (16384,8192), 'Unexpected record defaults')
                require(struct.unpack('<BBIIHi',body[32:]) == (0,1,100000,0,819,0), 'Unexpected DDS defaults')
                result['configuration_hex'] = body.hex()
            elif kind == p.GET_CAPTURE_CONFIG:
                require(p.decode_capture_configuration(response) == (2,2500000), 'Unexpected capture defaults')
            elif kind == 0x19:
                require(len(body) == 16 and body[0] == 1 and body[1] == 0, 'AWG must be empty and unselected after reset')
        require(not any(parser.errors.values()), 'UART parser errors')
        result.update(verdict='PASS',parser_errors=dict(parser.errors),finished_at=datetime.now(TZ).isoformat())
    (Path(folder)/name).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirmed-modules-off',action='store_true')
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--port',default='COM12')
    a = parser.parse_args()
    require(a.confirmed_modules_off, 'Operator readiness confirmation is required')
    out = a.output_dir.resolve()
    out.mkdir(parents=True,exist_ok=False)
    record = {'status':'FAIL','operator_confirmed_sw0_off_modules_5v_off':True,
              'started_at':datetime.now(TZ).isoformat(),'operator_power_cycle_performed_this_run':False,
              'pc_features_location':'PC workspace; PC/UI code cannot be stored in the FPGA configuration Flash'}
    stage = None
    try:
        package, manifest, hardware = validate_images()
        record.update(build=manifest['build'],bitstream_sha256=manifest['bitstream_sha256'],hardware_sources_sha256=hardware,
                      expected_bin_sha256=sha(package/'flash/scope_awg_flash.bin'),mcs_bin_exact_compare='PASS')
        stage = Path(tempfile.mkdtemp(prefix='scope_persist_20261029_'))
        record['temporary_stage'] = str(stage)
        for name in ('tool_tmp','tool_appdata'):
            (stage/name).mkdir()
        for suffix in ('mcs','bin'):
            shutil.copyfile(package/f'flash/scope_awg_flash.{suffix}',stage/f'image.{suffix}')
        tcl = stage/'verify_or_program_scope_flash.tcl'
        shutil.copyfile(ROOT/'FPGA/scripts'/tcl.name,tcl)
        binary = Path(json.loads((ROOT/'FPGA/scripts/vivado_toolchain.json').read_text())['bin'])
        env = os.environ.copy()
        for key in ('TEMP','TMP','TMPDIR'):
            env[key] = str(stage/'tool_tmp')
        env.update(APPDATA=str(stage/'tool_appdata'),XILINX_LOCAL_USER_DATA='NO',
                   XILINX_TCLAPP_REPO=str(binary.parent/'data/XilinxTclStore'))
        command = [binary/'vivado.bat','-mode','batch','-notrace','-source',tcl,
                   '-log',stage/'deployment.log','-journal',stage/'deployment.jou','-tclargs',
                   stage/'image.mcs',stage/'image.bin',stage/'hardware_report']
        print('START_FULL_QSPI_BACKUP_VERIFY_AND_MODE_PIN_BOOT '+str(out),flush=True)
        with (stage/'console.log').open('wb') as stream:
            process = subprocess.run(subprocess.list2cmdline([str(v) for v in command]),shell=True,
                                     cwd=stage,env=env,stdout=stream,stderr=subprocess.STDOUT)
        log = (stage/'console.log').read_text(encoding='utf-8',errors='replace')
        require(process.returncode == 0 and 'QSPI_DEPLOYMENT_PASS' in log, log[-9000:])
        hardware_report = stage/'hardware_report'
        require((hardware_report/'flash_before.bin').stat().st_size == 8388608, 'Incomplete full Flash backup')
        require((hardware_report/'flash_after.bin').read_bytes() == (stage/'image.bin').read_bytes(), 'Flash differs')
        action = (hardware_report/'action.txt').read_text().strip()
        snapshot = serial_snapshot(a.port,out)
        record.update(status='PASS_CURRENT_IMAGE_PERSISTENT_AND_QSPI_BOOT_VERIFIED',action=action,
                      flash_erased_or_written_this_run=action=='PROGRAMMED_AND_VERIFIED',
                      backup_bytes=8388608,backup_sha256=sha(hardware_report/'flash_before.bin'),
                      readback_sha256=sha(hardware_report/'flash_after.bin'),qspi_boot_verified=True,
                      uart_boot_verdict=snapshot['verdict'])
    except BaseException as exc:
        record['error'] = repr(exc)
    finally:
        if stage is not None:
            for name in ('deployment.log','deployment.jou','console.log'):
                if (stage/name).exists():
                    shutil.copyfile(stage/name,out/name)
            if (stage/'hardware_report').exists():
                shutil.copytree(stage/'hardware_report',out/'hardware',dirs_exist_ok=False)
        record['finished_at'] = datetime.now(TZ).isoformat()
        (out/'manifest.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({key:record.get(key) for key in ('status','action','flash_erased_or_written_this_run','qspi_boot_verified','error')},ensure_ascii=False,indent=2),flush=True)
    return 0 if record['status'].startswith('PASS_') else 1


if __name__=='__main__':
    raise SystemExit(main())
