"""Independently audit whole-record saturation and existing analysis outputs."""
from pathlib import Path
import math
import struct
import sys
import zipfile
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'PC/protocol'))
import scope_protocol as p
import spectrum_reference as reference
from fft_bitaccurate_reference import fft_integer

def counts(words):
    mask=[(int(word)&4095) in (0,4095) for word in words]
    return sum(mask),sum(hit and (index==0 or not mask[index-1]) for index,hit in enumerate(mask))

def audit(folder,model_archive,expected_build=0xA2261027,expected_capabilities=31):
    folder=Path(folder);parser=p.Parser()
    frames=parser.feed(bytes.fromhex((folder/'uart.hex').read_text()))
    assert len(frames)==38 and not parser.buffer and not any(parser.errors.values())
    packets={f.sequence:f for f in frames}
    assert len(packets)==38 and not any(f.flags&p.ERROR for f in frames)
    assert packets[1].payload==b'\1\0\0\0'+struct.pack('<I',expected_build)
    assert packets[13].payload==struct.pack('<IHH',expected_capabilities,800,2048)
    model=folder/'cmodel';model.mkdir(exist_ok=True)
    with zipfile.ZipFile(model_archive) as z:z.extractall(model)
    trace=[tuple(map(int,line.split(','))) for line in (folder/'fft_bins.csv').read_text().splitlines()]
    live={int(t):int(raw,16)|(int(otr)<<15) for t,raw,otr in
          (line.split(',') for line in (folder/'live.csv').read_text().splitlines())}
    results=[]
    for mode in range(4):
        base=15+mode*8
        words=[int(value,16) for value in (folder/f'saturation_frame_{mode}.hex').read_text().split()]
        assert len(words)==16384 and not any(word&0x7000 for word in words)
        summary=packets[base+2];again=packets[base+3]
        assert summary.payload==again.payload and summary.timestamp==again.timestamp
        stat=p.decode_saturation(summary);samples,events=counts(words)
        assert (stat['count'],stat['saturated_samples'],stat['events'],stat['diagnostic'])==(16384,samples,events,mode!=0)
        if mode==0:
            assert words==[live[summary.timestamp+i] for i in range(16384)]
            assert samples==events==0
        else:
            for i,word in enumerate(words):
                phase=(summary.timestamp+i)%16
                expected=(4095 if mode==2 else 2047 if mode==3 else
                    0 if phase in (0,1,2,15) else 4095 if phase==7 else 2047)
                assert word&4095==expected
            if mode==2:assert samples==16384 and events==1
            if mode==3:assert samples==events==0
        measured=packets[base+4];spectrum=packets[base+5]
        assert measured.timestamp==spectrum.timestamp==summary.timestamp
        assert measured.sample_rate==spectrum.sample_rate==summary.sample_rate==25000000
        m=p.decode_measurement(measured);spec=p.decode_spectrum(spectrum)
        x=np.asarray([2047-(word&4095) for word in words],dtype=np.int64)
        assert m['sum']==int(x.sum()) and m['square_sum']==int((x*x).sum())
        assert (m['minimum'],m['maximum'],m['vpp'])==(int(x.min()),int(x.max()),int(np.ptp(x)))
        assert m['rms']==math.floor(math.sqrt(float(np.mean(x*x)))+.5) and not m['error']
        expected_fft=fft_integer(reference.preprocess(x[:1024].tolist(),1),model)
        rows=[row for row in trace if row[0]==summary.timestamp]
        assert len(rows)==1024 and [row[1] for row in rows]==list(range(1024))
        assert all(complex(re,im)==expected_fft[k] for _,k,re,im in rows)
        assembly=p.WaveAssembler();roi=assembly.accept(packets[base+6])
        assert roi==words[8192:8320] and assembly.base==summary.timestamp
        results.append({'mode':mode,'saturated_samples':samples,'events':events,'timestamp':summary.timestamp})
    assert len({row['timestamp'] for row in results})==4
    return {'saturation_simulation':'PASS','complete_frames':4,'raw_words_checked':65536,
        'fft_bins_exactly_compared':4096,'roi_words_checked':512,'cases':results}
