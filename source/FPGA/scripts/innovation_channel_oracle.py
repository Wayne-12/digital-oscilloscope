"""Independent integer channel/ADC timeline for connected innovation captures.

Uses observed input DAC codes checked against the test stimulus, never the
model's ideal output as a golden input. All divisions round nearest, ties away.
"""
import csv


def rnd(n, d):
    return (-1 if n < 0 else 1) * ((abs(n) + d // 2) // d)


def advance(s):
    s ^= (s << 13) & 0xffffffff
    s ^= s >> 17
    return (s ^ (s << 5)) & 0xffffffff


def channel_words(path, profile, n):
    gain = (16384,24576,12288,32768)[profile]
    offset = (0,37,-23,0)[profile]
    delay, fraction, noise, alpha = (2,16384,3,32768) if profile == 2 else (0,0,0,65536)
    history=[]; filt=0; state=12345; inputs=[]; captured=[]; clipped=0
    with path.open(encoding='ascii') as f:
        for k,r in enumerate(csv.DictReader(f)):
            r={key:int(value) for key,value in r.items()}
            x=-600+10*(k%128) if k%256<128 else 600-10*(k%128)
            if k%113==17: x=5000
            elif k%127==29: x=-5000
            assert r['cycle']==k and r['dac']==8192+x, ('channel stimulus',profile,k,r)
            history.insert(0,x)
            cv=len(history)>=delay+1+bool(fraction)
            if cv:
                y=rnd((65536-fraction)*history[delay]+fraction*(history[delay+1] if fraction else 0),65536)
                y=rnd(y*gain,65536)*(-1 if profile==2 else 1)
                state=advance(state); y+=offset+state%(2*noise+1)-noise
                filt+=rnd((y*65536-filt)*alpha,65536)
                ideal=rnd(filt,65536)
                clip=int(profile==3 and not -700<=ideal<=700)
                if profile==3: ideal=max(-700,min(700,ideal))
                fe=int(k==128+n//2); fv=1
            else:
                ideal=0; clip=0; fe=0; fv=0
            history=history[:delay+2]
            assert (r['ideal'],r['channel_valid'],r['clipped'],r['force_enable'],r['force_value'])==(ideal,int(cv),clip,fe,fv), ('channel model',profile,k,r,ideal,cv,clip,fe,fv)
            otr=fv if fe else int(not -2048<=ideal<=2047)
            inputs.append((otr<<15)|(2047-max(-2048,min(2047,ideal))))
            expected=inputs[k-8] if k>=8 else 2047
            assert r['capture_valid']==int(k>=8) and r['timestamp']==max(0,k-8) and (r['otr']<<15)|r['raw']==expected, ('ADC pipeline',profile,k,r,expected)
            if 136<=k<136+n: captured.append(expected)
            clipped+=clip
    assert len(captured)==n and sum(w>>15 for w in captured)==1
    assert captured[n//2]>>15==1
    assert (clipped>0)==(profile==3)
    return captured, dict(profile=profile,gain_q16=gain,offset=offset,invert=profile==2,
                         noise_lsb=noise,delay=delay,fraction_q16=fraction,alpha_q16=alpha,
                         clipping=profile==3,clipped_samples=clipped,forced_otr_index=n//2,
                         adc_delay_edges=8,compared=n)
