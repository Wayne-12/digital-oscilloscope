"""Current AWG fit utility extracted unchanged from the legacy board verifier."""
import numpy as np

def fit_table(raw,table,frequency):
    y=2047-(raw[:4096]&4095).astype(float);y-=y.mean()
    inc=round(frequency*2**32/25000000)
    phase=np.arange(len(y),dtype=np.uint64)*inc
    best=None
    for offset in range(1024):
        indices=(((phase+offset*2**22)&0xffffffff)>>22).astype(int)
        x=np.asarray(table,dtype=float)[indices];x-=x.mean()
        gain=float(x@y/(x@x));prediction=x*gain
        error=float(np.sqrt(np.mean((y-prediction)**2))/np.std(y))
        if best is None or error<best['normalized_rms_error']:
            best=dict(phase_index=offset,gain=gain,normalized_rms_error=error,
                correlation=float(np.corrcoef(x,y)[0,1]),adc_vpp=float(np.ptp(y)))
    return best
