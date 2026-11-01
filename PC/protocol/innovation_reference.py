"""Step 12 integer contracts for combined-chain relative simulation calibration."""
import struct,zlib,math
from scope_protocol import Parser,FIRST,LAST,MORE
Q20=1<<20
GAIN_ERROR_LIMIT_Q20=525  # 0.000501 ADC code / DAC code, fixed before simulation.
OFFSET_ERROR_LIMIT_Q16=16384  # 0.25 ADC code.
def rnd(n,d):
    if d<=0:raise ValueError('positive denominator required')
    return (-1 if n<0 else 1)*((abs(n)+d//2)//d)
def fit(points,nominal=Q20//4):
    n=len(points)
    if not 2<=n<=32 or not 0<nominal<=Q20 or any(not -134217728<=y<=134152192 or not -8192<=x<=8191 for x,y in points):return None
    sx=sum(x for x,y in points);sy=sum(y for x,y in points);sxx=sum(x*x for x,y in points);sxy=sum(x*y for x,y in points)
    den=n*sxx-sx*sx
    if den<=0:return None
    g=rnd((n*sxy-sx*sy)<<4,den)
    if not 16384<=abs(g)<=4194304:return None
    b=rnd((sy<<4)-g*sx,n<<4)
    if abs(b)>134217728:return None
    c=rnd(nominal<<20,abs(g))*(-1 if g<0 else 1)
    if abs(c)>67108864:return None
    return g,b,c
def apply(word,offset,correction,valid=True):
    y=2047-(word&4095)
    result=rnd(((y<<16)-offset)*correction,1<<20) if valid else y<<16
    return max(-(1<<31),min((1<<31)-1,result)),int(not -(1<<31)<=result<(1<<31))
def classify(base,cur,limits):
    flags=[abs(cur['offset']-base['offset'])>limits['zero'],abs(abs(cur['gain'])-abs(base['gain']))>limits['gain'],
      cur['noise']-base['noise']>limits['noise'],cur['compression']-base['compression']>limits['compression'] or cur['otr']-base['otr']>limits['otr'],
      cur['harmonic']-base['harmonic']>limits['harmonic'],(cur['gain']<0)!=(base['gain']<0),not(base['valid'] and cur['valid'] and base['gain'] and cur['gain'])]
    mask=sum(int(f)<<i for i,f in enumerate(flags));priority=[(6,7),(5,6),(3,4),(2,3),(1,2),(0,1),(4,5)]
    return mask,next((value for bit,value in priority if flags[bit]),0)
LIMITS=dict(zero=4<<16,gain=10486,noise=4<<16,compression=50000,harmonic=100,otr=0)
def source_words(n):
    values=[(i*37+123)%17-8 for i in range(n)]
    for b in range(800):
        lo=b*n//800;hi=(b+1)*n//800-1;p=(lo,(lo+hi)//2,hi)[b%3];q=hi if p==lo else lo
        values[p]=2047;values[q]=-2048
    return [((int(i==n//2 or (i>n//2 and i%257==17)))<<15)|(2047-x) for i,x in enumerate(values)]
def moments(words):
    x=[2047-(w&4095) for w in words]
    return dict(count=len(x),sum=sum(x),square_sum=sum(v*v for v in x),minimum=min(x),maximum=max(x),otr=sum(w>>15 for w in words),crc=zlib.crc32(struct.pack('<'+'H'*len(words),*words)))
def decode_result(data):
    if len(data)<137 or data[:8]!=b'SCAP\x01'+bytes([data[5]])+b'\x80\x00' or data[5]!=0:raise ValueError('SCAP header')
    u16=lambda o:struct.unpack_from('<H',data,o)[0]
    u32=lambda o:struct.unpack_from('<I',data,o)[0]
    u64=lambda o:struct.unpack_from('<Q',data,o)[0]
    n,t=u32(12),u32(16);b,r=u16(56),u16(58);start=u32(60);first=u64(32);mask=(1<<64)-1
    if not 0<n<=16384 or t>=n or not 0<b<=min(800,n) or start+r>n or not u32(28):raise ValueError('SCAP range')
    if u32(20)!=t or u32(24)!=n-t-1 or u64(40)!=(first+t)&mask or u64(48)!=(first+n-1)&mask or u32(68)!=n:raise ValueError('SCAP metadata')
    if data[96]!=1 or any(data[97:128]):raise ValueError('SCAP summary flags/reserved')
    buckets=[];roi=[];pos=128
    while pos<len(data):
        tag=data[pos]
        if tag==0x42:
            if pos+14>len(data):raise ValueError('truncated bucket')
            k,mn,mx=struct.unpack_from('<Hhh',data,pos+1);mi=int.from_bytes(data[pos+7:pos+10],'little');ma=int.from_bytes(data[pos+10:pos+13],'little');otr=data[pos+13]
            lo=k*n//b;hi=(k+1)*n//b-1
            if k!=len(buckets) or k>=b or not lo<=mi<=hi or not lo<=ma<=hi or mn>mx or otr>1:raise ValueError('SCAP bucket')
            buckets.append(dict(index=k,first=lo,last=hi,min=mn,max=mx,min_index=mi,max_index=ma,otr=otr));pos+=14
        elif tag==0x52:
            if pos+3>len(data) or len(roi)>=r:raise ValueError('SCAP ROI')
            word=u16(pos+1);i=start+len(roi)
            if word&0x7000:raise ValueError('reserved raw bits')
            roi.append(dict(index=i,word=word,timestamp=(first+i)&mask));pos+=3
        elif tag==0x46:
            if pos+9!=len(data) or u32(pos+1)!=zlib.crc32(data[:pos]) or u16(pos+5)!=b or u16(pos+7)!=r or len(buckets)!=b or len(roi)!=r:raise ValueError('SCAP trailer/CRC/counts')
            return dict(result_id=u32(8),storage=data[5],count=n,trigger=t,first=first,rate=u32(28),roi_start=start,buckets=buckets,roi=roi,
              moments=dict(count=u32(68),sum=struct.unpack_from('<q',data,72)[0],square_sum=u64(80),minimum=struct.unpack_from('<h',data,88)[0],maximum=struct.unpack_from('<h',data,90)[0],otr=u32(92),crc=u32(64)))
        else:raise ValueError('SCAP tag')
    raise ValueError('SCAP missing footer')
def assemble_uart(wire):
    p=Parser();frames=p.feed(wire)
    if any(p.errors.values()) or p.buffer or not frames:raise ValueError('UART parser')
    result=bytearray();seq=frames[0].sequence;metadata=(frames[0].timestamp,frames[0].sample_rate,frames[0].trigger_index)
    for i,f in enumerate(frames):
        offset=struct.unpack_from('<I',f.payload)[0]
        if f.kind!=0xb2 or offset!=len(result) or f.sequence!=(seq+i)&65535 or (f.timestamp,f.sample_rate,f.trigger_index)!=metadata:raise ValueError('result segment identity')
        expected=1|(FIRST if i==0 else 0)|(LAST if i==len(frames)-1 else MORE)
        if f.flags!=expected or not 4<len(f.payload)<=1024:raise ValueError('result segment flags')
        result.extend(f.payload[4:])
    decoded=decode_result(bytes(result))
    if (decoded['first'],decoded['rate'],decoded['trigger'])!=metadata:raise ValueError('result outer metadata')
    return decoded,bytes(result),len(frames)
