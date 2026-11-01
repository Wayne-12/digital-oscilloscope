"""Version 1 byte codec; no serial-driver dependency. All integers little endian."""
from dataclasses import dataclass
import binascii,struct
MAGIC=b'\x55\xaa';VERSION=1;MAX_PAYLOAD=1024
HEADER=struct.Struct('<2sBBHHQIIH')
RESPONSE,ERROR,MORE,FIRST,LAST=1,2,4,8,16
PING,GET_VERSION,GET_STATUS,SET_RECORD,SET_TRIGGER,SINGLE,STOP,READ_WAVE,READ_MEASURE,SET_DDS=1,2,3,0x10,0x11,0x20,0x21,0x30,0x31,0x40
GET_CAPABILITIES, READ_ENVELOPE = 4, 0x32
GET_CONFIG = 5
READ_SPECTRUM = 0x33
CAP_FROZEN_ANALYSIS = 4
CAP_CAPTURE_MODES = 8
CAP_SATURATION = 16
READ_SATURATION, SET_DIAGNOSTIC = 0x34, 0x14

def decode_saturation(frame):
    if frame.kind != 0xb4 or frame.flags != RESPONSE or len(frame.payload) != 16:
        raise ValueError('invalid saturation response')
    version,flags,reserved,count,samples,events=struct.unpack('<BBHIII',frame.payload)
    if (version!=1 or flags&~3 or not flags&1 or reserved or count!=16384
            or samples>count or bool(events)!=bool(samples)
            or events>min(samples,count-samples+1)):
        raise ValueError('invalid complete-frame saturation statistics')
    return {'count':count,'saturated_samples':samples,'events':events,'diagnostic':bool(flags&2)}

SET_CAPTURE_MODE, GET_CAPTURE_CONFIG, RUN, RELEASE_FRAME = 0x12, 0x13, 0x22, 0x23

def capture_mode_payload(mode, timeout_ticks=2500000):
    if type(mode) is not int or mode not in (0,1,2) or type(timeout_ticks) is not int or not 1 <= timeout_ticks <= 0xffffffff:
        raise ValueError('invalid capture mode or auto timeout')
    return struct.pack('<B3xI', mode, timeout_ticks)

def decode_capture_configuration(frame):
    if frame.kind != 0x93 or frame.flags != RESPONSE or len(frame.payload) != 8 or any(frame.payload[1:4]):
        raise ValueError('invalid capture configuration response')
    mode, ticks = struct.unpack('<B3xI', frame.payload)
    capture_mode_payload(mode, ticks)
    return mode, ticks


def decode_measurement(frame):
    """Frozen 16K record statistics in ADC integer units (v1, 64 bytes)."""
    p = frame.payload
    if frame.kind != 0xb1 or frame.flags != RESPONSE or len(p) != 64:
        raise ValueError('invalid measurement response')
    if any(v not in (0,1) for v in p[:4]) or p[18:20] != b'\0\0' or any(p[56:]):
        raise ValueError('invalid measurement flags or reserved fields')
    count, lo, hi, mean, vpp, rms = struct.unpack_from('<IhhhHH',p,4)
    total, squares, period, frequency, duty, periods = struct.unpack_from('<qQQIII',p,20)
    if (p[0] != 1 or count != 16384 or not -2048 <= lo <= mean <= hi <= 2047
            or vpp != hi-lo or rms > 2048 or periods > count or duty > 1000000
            or frequency > frame.sample_rate//2 or bool(p[1]) != bool(periods)
            or bool(p[2]) != bool(periods) or (p[1] and (not period or not frequency))):
        raise ValueError('invalid frozen measurement geometry')
    return {'stats_valid': bool(p[0]),'period_valid': bool(p[1]),'duty_valid': bool(p[2]),'error': bool(p[3]),
                'count': count,'minimum': lo,'maximum': hi,'mean': mean,'vpp': vpp,'rms': rms,'sum': total,
                'square_sum': squares,'period_q16': period,'frequency': frequency,'duty_ppm': duty,'periods': periods}

def decode_spectrum(frame):
    """Fixed 1024-point periodic Hann FFT; amplitude is peak ADC units Q16."""
    p = frame.payload
    if frame.kind != 0xb3 or frame.flags != RESPONSE or len(p) != 96:
        raise ValueError('invalid spectrum response')
    if p[0] != 1 or p[1] & ~3 or p[2] or p[3] or p[6:8] != b'\1\0' or any(p[14:16]):
        raise ValueError('invalid spectrum flags/window')
    n, = struct.unpack_from('<H',p,4)
    offset, peak = struct.unpack_from('<IH',p,8)
    frequency, amplitude, rms, dc = struct.unpack_from('<IIIi',p,16)
    if (n != 1024 or offset != 0 or peak > 510 or not 0 < frame.sample_rate <= 125000000
            or frequency != (peak*frame.sample_rate+512)//1024):
        raise ValueError('invalid spectrum geometry')
    harmonics = []
    for h in range(2,6):
        order,valid,k,hz,aq,reserved = struct.unpack_from('<BBHIII',p,32+(h-2)*16)
        if (order != h or valid not in (0,1) or reserved or bool(valid) != (peak >= 4 and h*peak < 511)
                or (valid and (abs(k-h*peak)>1 or hz != (k*frame.sample_rate+512)//1024))):
            raise ValueError('invalid harmonic summary')
        harmonics.append({'order': h,'valid': bool(valid),'bin': k,'frequency': hz,'amplitude': aq/65536})
    return {'valid': bool(p[1]&1),'clipped': bool(p[1]&2),'n': n,'offset': offset,'peak_bin': peak,
                'frequency': frequency,'amplitude': amplitude/65536,'rms': rms/65536,'dc': dc/65536,
                'harmonics': harmonics}
ENVELOPE_PREFIX = struct.Struct('<IIHH')
ENVELOPE_BUCKET = struct.Struct('<hhB')

class EnvelopeAssembler:
    """Strict compact-envelope reassembly; every packet describes one frozen frame."""
    def __init__(self, sequence, buckets, record_length):
        if not 1 <= buckets <= 800 or not 1 <= record_length <= 16384:
            raise ValueError('invalid envelope request')
        self.next_sequence = sequence
        self.expected_buckets = min(buckets, record_length)
        self.record_length = record_length
        self.buckets = []
        self.identity = None
        self.complete = False

    def accept(self, frame):
        if self.complete or frame.kind != 0xb2 or len(frame.payload) < 17:
            raise ValueError('invalid envelope payload')
        offset, total, count, encoding = ENVELOPE_PREFIX.unpack_from(frame.payload)
        data = frame.payload[ENVELOPE_PREFIX.size:]
        if (len(data) % ENVELOPE_BUCKET.size or len(data) > 202*ENVELOPE_BUCKET.size
                or total != self.record_length or count != self.expected_buckets or encoding != 1):
            raise ValueError('invalid envelope geometry or encoding')
        if offset != len(self.buckets) or frame.sequence != self.next_sequence:
            raise ValueError('envelope gap or sequence')
        size = len(data)//ENVELOPE_BUCKET.size
        last = offset+size == count
        expected_flags = RESPONSE | (FIRST if offset == 0 else 0) | (LAST if last else MORE)
        identity = (frame.timestamp, frame.sample_rate, frame.trigger_index)
        if (offset+size > count or frame.flags != expected_flags or
                not 0 < frame.sample_rate <= 125000000 or not 0 <= frame.trigger_index < total):
            raise ValueError('invalid envelope flags or metadata')
        if self.identity is not None and identity != self.identity:
            raise ValueError('envelope metadata changed')
        entries = list(ENVELOPE_BUCKET.iter_unpack(data))
        if any(not -2048 <= lo <= hi <= 2047 or otr not in (0,1) for lo,hi,otr in entries):
            raise ValueError('invalid envelope sample or OTR')
        self.identity = identity
        self.buckets.extend(entries)
        self.next_sequence = (self.next_sequence+1)&65535
        self.complete = last
        return self.buckets.copy() if last else None
def crc16(data):return binascii.crc_hqx(data,0xffff)
@dataclass(frozen=True)
class Frame:
    kind:int
    sequence:int=0
    timestamp:int=0
    sample_rate:int=0
    trigger_index:int=0
    flags:int=0
    payload:bytes=b''
def encode(f):
    if len(f.payload)>MAX_PAYLOAD:raise ValueError('payload exceeds 1024 bytes')
    h=HEADER.pack(MAGIC,VERSION,f.kind,f.sequence,len(f.payload),f.timestamp,f.sample_rate,f.trigger_index,f.flags)
    return h+f.payload+struct.pack('<H',crc16(h[2:]+f.payload))
class Parser:
    def __init__(self):
        self.buffer=bytearray();self.errors={'crc': 0,'length': 0,'version': 0,'timeout': 0};self.good_frames=0
    def feed(self,data=b''):
        self.buffer.extend(data);result=[]
        while True:
            start=self.buffer.find(MAGIC)
            if start<0:
                self.buffer[:]=self.buffer[-1:] if self.buffer.endswith(b'\x55') else b''
                break
            if start:del self.buffer[:start]
            if len(self.buffer)<HEADER.size:break
            _,version,kind,seq,n,timestamp,rate,trig,flags=HEADER.unpack_from(self.buffer)
            if version!=VERSION:
                self.errors['version']+=1;del self.buffer[0];continue
            if n>MAX_PAYLOAD:
                self.errors['length']+=1;del self.buffer[0];continue
            total=HEADER.size+n+2
            if len(self.buffer)<total:break
            expected=struct.unpack_from('<H',self.buffer,total-2)[0]
            if crc16(self.buffer[2:total-2])!=expected:
                self.errors['crc']+=1;del self.buffer[0];continue
            result.append(Frame(kind,seq,timestamp,rate,trig,flags,bytes(self.buffer[HEADER.size:total-2])))
            self.good_frames+=1;del self.buffer[:total]
        return result
    def expire(self):
        """One idle-gap expiry, only after all available bytes were parsed."""
        result=self.feed()
        if self.buffer and self.buffer[0]==0x55:
            self.errors['timeout']+=1;del self.buffer[0];result+=self.feed()
        return result
class WaveAssembler:
    def __init__(self):self.reset()
    def reset(self):self.words=[];self.active=False;self.next_offset=0;self.next_sequence=0
    def accept(self,f):
        if f.kind!=0xb0 or len(f.payload)<10 or len(f.payload)%2:raise ValueError('invalid wave payload')
        offset,total=struct.unpack_from('<II',f.payload);words=list(struct.unpack('<'+'H'*((len(f.payload)-8)//2),f.payload[8:]))
        if offset+len(words)>total or total>16384:raise ValueError('wave range')
        if f.flags&FIRST:
            self.reset();self.active=True;self.next_offset=offset;self.next_sequence=f.sequence
            self.total=total;self.base=(f.timestamp-offset)&((1<<64)-1);self.trigger=f.trigger_index;self.rate=f.sample_rate
        if not self.active or offset!=self.next_offset or f.sequence!=self.next_sequence:raise ValueError('wave gap or sequence')
        if total!=self.total or f.timestamp!=((self.base+offset)&((1<<64)-1)) or f.trigger_index!=self.trigger or f.sample_rate!=self.rate:raise ValueError('wave metadata')
        if bool(f.flags&MORE)==bool(f.flags&LAST):raise ValueError('wave completion flags')
        self.words.extend(words);self.next_offset+=len(words);self.next_sequence=(self.next_sequence+1)&65535
        if f.flags&LAST:self.active=False;return self.words.copy()
        return None
