"""Transactional 1024-point normalized arbitrary-waveform tables."""
import csv
import io
import math
import struct
from pathlib import Path
import scope_protocol as p

POINTS=1024
BEGIN,CHUNK,COMMIT,READ,STATUS,SELECT=range(0x15,0x1b)
CAPABILITY=32

def encode_table(values):
    values=list(values)
    if len(values)!=POINTS or any(type(v) is not int or not -32767<=v<=32767 for v in values):
        raise ValueError('波形表必须为1024个 -32767～32767 的整数')
    return struct.pack('<1024h',*values)

def load_table(path):
    """One normalized [-1,1] value per line; optional header 'value'."""
    text=Path(path).read_text(encoding='utf-8-sig')
    rows=list(csv.reader(io.StringIO(text)))
    if rows and rows[0]==['value']:rows=rows[1:]
    values=[]
    for index,row in enumerate(rows,1):
        if len(row)!=1:raise ValueError(f'第{index}行需要单列归一化数值')
        try:value=float(row[0])
        except ValueError:raise ValueError(f'第{index}行不是数值') from None
        if not math.isfinite(value) or not -1<=value<=1:raise ValueError(f'第{index}行必须在 -1～1 之间')
        values.append(int(math.copysign(math.floor(abs(value)*32767+.5),value)))
    encode_table(values)
    return values

def status(link,restoring=False):
    f=link.exchange(STATUS,restoring=True) if restoring else link.exchange(STATUS)
    if f.kind!=STATUS|128 or f.flags!=p.RESPONSE or len(f.payload)!=16:
        raise ValueError('波形表状态响应无效')
    version,flags,reserved,points,received,active_crc,staging_crc,padding=struct.unpack('<BBHHHHHI',f.payload)
    if version!=1 or flags&~7 or reserved or padding or points!=POINTS or received>POINTS:
        raise ValueError('波形表状态字段无效')
    return dict(valid=bool(flags&1),uploading=bool(flags&2),selected=bool(flags&4),received=received,
                active_crc=active_crc,staging_crc=staging_crc)

def read_table(link):
    data=bytearray()
    for offset in range(0,POINTS,256):
        header=struct.pack('<HH',offset,256);f=link.exchange(READ,header)
        if f.kind!=READ|128 or f.flags!=p.RESPONSE or len(f.payload)!=516 or f.payload[:4]!=header:
            raise ValueError('波形表读回范围或响应无效')
        data.extend(f.payload[4:])
    values=list(struct.unpack('<1024h',data));encode_table(values)
    return values

def ack(link,kind,payload=b'',restoring=False):
    f=link.exchange(kind,payload,restoring=True) if restoring else link.exchange(kind,payload)
    if f.kind!=kind|128 or f.flags!=p.RESPONSE or f.payload!=b'\0':raise ValueError('波形表命令未确认')

def upload(link,values,progress=lambda value:None):
    """Caller must stop acquisition and disable DDS first; output stays disabled."""
    # Preserve the exact transaction image, including one-pass iterables and
    # caller-owned lists that a progress callback can modify during transfer.
    values=list(values)
    data=encode_table(values)
    ack(link,BEGIN,struct.pack('<I',POINTS))
    for offset in range(0,POINTS,256):
        ack(link,CHUNK,struct.pack('<H',offset)+data[offset*2:(offset+256)*2])
        progress((offset+256)*80//POINTS)
    crc=p.crc16(data)
    ack(link,COMMIT,struct.pack('<H',crc))
    if read_table(link)!=values:raise ValueError('波形表板端读回与原始文件不一致')
    result=status(link)
    if not result['valid'] or result['uploading'] or result['active_crc']!=crc:
        raise ValueError('波形表提交校验失败')
    progress(100)
    return result
