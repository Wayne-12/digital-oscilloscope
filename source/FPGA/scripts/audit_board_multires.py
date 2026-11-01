"""Audit physical-board UART test traces against every independently observed ADC word."""
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'PC/protocol'))
import scope_protocol as proto


def audit(folder):
    folder = Path(folder)
    parser = proto.Parser()
    packets = parser.feed(bytes.fromhex((folder/'uart.hex').read_text()))
    assert len(packets) == 36 and not parser.buffer and not any(parser.errors.values())
    frozen = [int(x,16) for x in (folder/'frozen.hex').read_text().split()]
    source = {int(t):int(raw,16)|(int(otr)<<15) for t,raw,otr in
              (line.strip().split(',') for line in (folder/'live.csv').open())}
    caps = [f for f in packets if f.kind == 0x84]
    assert len(caps) == 1 and caps[0].payload == struct.pack('<IHH',15,800,2048)
    for sequence,buckets in ((13,800),(14,400),(23,100)):
        assembly = proto.EnvelopeAssembler(sequence,buckets,16384)
        started = False
        for f in packets:
            # Packet sequence values may overlap between independent requests.
            # Only FIRST with the current request sequence can start assembly.
            if f.kind != 0xb2 or f.flags & proto.ERROR:
                continue
            if not started:
                if not (f.flags & proto.FIRST and f.sequence == sequence):
                    continue
                started = True
            assembly.accept(f)
            if assembly.complete:
                break
        assert assembly.complete and len(assembly.buckets) == buckets
        base,rate,trigger = assembly.identity
        assert rate == 25000000 and trigger == 8192
        assert frozen == [source[base+j] for j in range(16384)]
        for j,(lo,hi,otr) in enumerate(assembly.buckets):
            block = frozen[j*16384//buckets:(j+1)*16384//buckets]
            signed = [2047-(x&4095) for x in block]
            assert (lo,hi,otr) == (min(signed),max(signed),int(any(x&32768 for x in block)))
    raw = proto.WaveAssembler()
    roi = None
    for f in packets:
        if f.kind == 0xb0 and 15 <= f.sequence <= 17:
            roi = raw.accept(f)
    assert roi == frozen[7000:8024]
    for seq,code,kind in ((16,2,0xb2),(17,2,0xb2),(18,1,0xb2),(19,2,0xb0)):
        bad = [f for f in packets if f.sequence == seq and f.kind == kind and f.flags & proto.ERROR]
        assert len(bad) == 1 and bad[0].payload == bytes([code]) and bad[0].flags == proto.RESPONSE|proto.ERROR
    cancelled = [f for f in packets if f.kind == 0xb2 and f.sequence == 20]
    assert len(cancelled) == 1 and cancelled[0].flags == proto.RESPONSE|proto.FIRST|proto.MORE
    assert any(f.kind == 0xa1 and f.sequence == 21 and f.payload == b'\0' for f in packets)
    assert any(f.kind == 0x81 and f.sequence == 22 and f.payload == b'AFTER_CANCEL' for f in packets)
    configs = {f.sequence:f.payload for f in packets if f.kind == 0x85 and not f.flags & proto.ERROR}
    trigger = struct.pack('<BBhHhhIIHI',0,0,0,8,-100,100,1,100,100,256)
    expected = struct.pack('<II',16384,8192)+trigger+struct.pack('<BBIIHi',0,1,100000,0,819,0)
    assert configs[24] == expected and configs[29] == expected
    assert configs[26] == expected[:32]+struct.pack('<BBIIHi',3,1,234567,0x23456789,300,-123)
    assert any(f.kind == 0x85 and f.sequence == 28 and f.flags == proto.RESPONSE|proto.ERROR and f.payload == b'\x01' for f in packets)
    return dict(multires_simulation='PASS',multires_compared_buckets=1300,
                multires_roi_compared_samples=1024,multires_stop_cancel_recovery='PASS',configuration_readback_simulation='PASS')


if __name__ == '__main__':
    print(json.dumps(audit(sys.argv[1]),indent=2))
