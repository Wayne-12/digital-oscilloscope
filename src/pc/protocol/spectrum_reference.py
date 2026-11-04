"""Direct floating DFT + explicit integer front-end, independent of Xilinx FFT."""
import cmath,math
N=1024
INPUT_SHIFT=3
COMPONENT_TOLERANCE=128  # FFT integer units, fixed before the first IP simulation.
AMPLITUDE_TOLERANCE_Q16=8192  # 0.125 ADC LSB.

def round_away(x):return math.floor(x+0.5) if x>=0 else -math.floor(-x+0.5)
def hann_coefficients(n=N):return [round_away(65536*(0.5-0.5*math.cos(2*math.pi*i/n))) for i in range(n)]
HANN=hann_coefficients()
assert sum(HANN)==N*32768
def preprocess(samples,window=0):
    if window not in (0,1):raise ValueError('window')
    coeff=HANN if window else [65536]*N
    if len(samples)!=N or any(not -4096<=x<=4095 for x in samples):raise ValueError('signed13 frame')
    result=[]
    for x,w in zip(samples,coeff):
        p=(x<<INPUT_SHIFT)*w
        value=(abs(p)+32768)//65536
        result.append(-value if p<0 else value)
    assert all(-32768<=v<=32767 for v in result)
    return result

_ROOTS={}
def dft(samples,inverse=False):
    """O(N^2) definition; inverse is deliberately UNNORMALIZED like the IP."""
    n=len(samples);key=(n,inverse)
    if key not in _ROOTS:
        sign=1 if inverse else -1
        _ROOTS[key]=[cmath.exp(sign*2j*math.pi*i/n) for i in range(n)]
    roots=_ROOTS[key]
    return [sum((x*roots[(k*i)%n] for i,x in enumerate(samples)),0j) for k in range(n)]

def amplitude(z,window=0,endpoint=False):
    gain=0.5 if window else 1.0
    return abs(z)*(1 if endpoint else 2)/(8*N*gain)
def one_sided_power(bins,window=0):
    coeff=HANN if window else [65536]*N
    energy=sum(w*w for w in coeff)/(65536**2*N)
    return [abs(bins[k])**2*(1 if k in (0,N//2) else 2)/(64*N*N*energy) for k in range(N//2+1)]
def summary(bins,rate,window=0,threshold_q16=2<<16):
    # A periodic Hann spreads DC/Nyquist into their adjacent bins; guard those
    # bins from the dominant-AC search. The full spectrum is still exported.
    first,last=(2,N//2-2) if window else (1,N//2-1)
    k=max(range(first,last+1),key=lambda i:(abs(bins[i])**2,-i))
    aq=round_away(amplitude(bins[k],window)*65536)
    valid=abs(bins[k])>0 and aq>=threshold_q16
    return dict(valid=int(valid),peak_bin=k if valid else 0,frequency=(k*rate+N//2)//N if valid else 0,
        amplitude_q16=aq if valid else 0,rms_q16=round_away(amplitude(bins[k],window)*65536/math.sqrt(2)) if valid else 0,
        dc_q16=round_away(bins[0].real*(16 if window else 8)),search_first=first,search_last=last)
