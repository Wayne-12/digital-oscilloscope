"""Compare summaries from the physical UART pins with independent ADC traces."""
from pathlib import Path
import math
import struct
import sys
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'PC/protocol'))
import scope_protocol as proto
import spectrum_reference as reference

def audit(folder,exact_fft=None):
    folder=Path(folder)
    parser=proto.Parser()
    packets=parser.feed(bytes.fromhex((folder/'uart.hex').read_text()))
    assert not parser.buffer and not any(parser.errors.values())
    by_seq={f.sequence:f for f in packets if f.kind!=0xb0}
    assert by_seq[12].payload==struct.pack('<IHH',15,800,2048)
    assert by_seq[13].payload==by_seq[15].payload
    assert by_seq[14].payload==by_seq[16].payload
    live={int(t):int(raw,16)|(int(otr)<<15) for t,raw,otr in
          (line.split(',') for line in (folder/'live.csv').read_text().splitlines())}
    for name,mi,si in [('frozen.hex',13,14),('frozen2.hex',19,20)]:
        m,s=by_seq[mi],by_seq[si]
        proto.decode_measurement(m)
        proto.decode_spectrum(s)
        words=np.array([int(x,16) for x in (folder/name).read_text().split()],dtype=np.int64)
        assert m.timestamp==s.timestamp and m.sample_rate==s.sample_rate==25000000
        assert words.tolist()==[live[m.timestamp+i] for i in range(16384)]
        x=2047-(words&4095)
        p=m.payload
        assert len(p)==64 and p[:4]==b'\1\1\1\0'
        count,lo,hi,mean,vpp,rms=struct.unpack_from('<IhhhHH',p,4)
        assert (count,lo,hi,vpp)==(16384,int(x.min()),int(x.max()),int(np.ptp(x)))
        assert mean==int(np.sign(x.mean())*math.floor(abs(x.mean())+.5))
        assert rms==math.floor(math.sqrt(float(np.mean(x*x)))+.5)
        assert struct.unpack_from('<qQ',p,20)==(int(x.sum()),int((x*x).sum()))
        rises=[];falls=[];level=None
        for i,v in enumerate(x):
            if level is None:
                if v<=-8:level=False
                elif v>=8:level=True
            elif not level and v>8:rises.append(i);level=True
            elif level and v<-8:falls.append(i);level=False
        frequency=struct.unpack_from('<I',p,44)[0]
        periods=len(rises)-1
        elapsed=rises[-1]-rises[0]
        high=sum(next(f for f in falls if f>r)-r for r in rises[:-1])
        assert struct.unpack_from('<Q',p,36)[0]==(elapsed*65536+periods//2)//periods
        assert frequency==(25000000*periods+elapsed//2)//elapsed
        assert struct.unpack_from('<I',p,48)[0]==(high*1000000+elapsed//2)//elapsed
        assert struct.unpack_from('<I',p,52)[0]==periods
        # Honor the existing, independently specified integer Q3/Q16 window
        # front-end. Ideal floating windowing can reorder sub-LSB harmonics.
        z=np.fft.rfft(reference.preprocess(x[:1024].tolist(),1))
        amplitude_tolerance=reference.AMPLITUDE_TOLERANCE_Q16/65536
        power=np.abs(z)**2
        exact=None
        if exact_fft is not None:
            exact=np.asarray(exact_fft(reference.preprocess(x[:1024].tolist(),1)))
            assert len(exact)==1024
            # Keep the pre-existing independent DFT component bound, and add
            # exact equality to every RTL FFT output from the official C model.
            full_dft=np.fft.fft(reference.preprocess(x[:1024].tolist(),1))
            assert np.max(np.abs(exact.real-full_dft.real))<=reference.COMPONENT_TOLERANCE
            assert np.max(np.abs(exact.imag-full_dft.imag))<=reference.COMPONENT_TOLERANCE
            rows=[tuple(map(int,line.split(','))) for line in (folder/'fft_bins.csv').read_text().splitlines()]
            rows=[row for row in rows if row[0]==m.timestamp]
            assert len(rows)==1024 and [row[1] for row in rows]==list(range(1024))
            assert all(complex(re,im)==exact[k] for _,k,re,im in rows)
        peak=int(np.argmax(power[2:511])+2)
        q=s.payload
        assert len(q)==96 and q[0]==1 and q[1]&1 and q[2:4]==b'\0\0'
        assert struct.unpack_from('<H',q,4)[0]==1024 and q[6:8]==b'\1\0'
        assert struct.unpack_from('<H',q,12)[0]==peak
        assert struct.unpack_from('<I',q,16)[0]==(peak*25000000+512)//1024
        assert abs(struct.unpack_from('<I',q,20)[0]/65536-abs(z[peak])/2048)<amplitude_tolerance
        for h in range(2,6):
            order,valid,k,hz,amp,reserved=struct.unpack_from('<BBHIII',q,32+(h-2)*16)
            assert order==h and reserved==0
            assert valid==int(peak>=4 and h*peak<511)
            assert hz==(k*25000000+512)//1024
            if valid:
                harmonic_power=power if exact is None else np.asarray(
                    [int(v.real)**2+int(v.imag)**2 for v in exact],dtype=np.int64)
                expected=int(np.argmax(harmonic_power[h*peak-1:h*peak+2])+h*peak-1)
                assert k==expected,(name,h,k,expected,harmonic_power[h*peak-1:h*peak+2].tolist())
                if exact is not None:
                    value=int(exact[k].real)**2+int(exact[k].imag)**2
                    root=math.isqrt(value<<10)
                    root+=int((value<<10)-root*root>root)
                    assert amp==root
                assert abs(amp/65536-abs(z[k])/2048)<amplitude_tolerance
        assert not m.flags&proto.ERROR and not s.flags&proto.ERROR
    assert by_seq[13].timestamp!=by_seq[19].timestamp
    return {'analysis_simulation': 'PASS','analysis_frames': 2,'analysis_samples_compared': 32768,
                'analysis_checks': 'ADC identity, exact stats/period/frequency/duty, integer-window 1024 Hann FFT, exact H2-H5 peak bins, immutable repeat, next frame'}
