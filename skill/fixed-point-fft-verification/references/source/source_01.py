"""ctypes adapter for the installed FFT IP's official bit-accurate C model.

The model is an offline verification dependency, never part of the PC UI.
The structure definitions and fixed-point scaling follow the header shipped
with the exact Vivado-generated FFT IP (xfft_v9_1_bitacc_cmodel.h).
"""
import ctypes as c
import os
from pathlib import Path

class Generics(c.Structure):
    _fields_=[(n,c.c_int) for n in ('nfft','arch','has_nfft','float_point','input_width',
        'twiddle_width','scaling','bfp','rounding','nssr','inverse')]

DoublePointer=c.POINTER(c.c_double)
class Inputs(c.Structure):
    _fields_=[('nfft',c.c_int),('real',DoublePointer),('real_size',c.c_int),
        ('imag',DoublePointer),('imag_size',c.c_int),('scaling',c.POINTER(c.c_int)),
        ('scaling_size',c.c_int),('direction',c.c_int)]

class Outputs(c.Structure):
    _fields_=[('real',DoublePointer),('real_size',c.c_int),('imag',DoublePointer),
        ('imag_size',c.c_int),('exponent',c.c_int),('overflow',c.c_int)]

def fft_integer(samples,model_directory):
    if len(samples)!=1024 or any(type(x) is not int or not -32768<=x<=32767 for x in samples):
        raise ValueError('Expected 1024 signed16 preprocessed FFT inputs')
    directory=Path(model_directory).resolve()
    with os.add_dll_directory(str(directory)):
        dll=c.CDLL(str(directory/'libIp_xfft_v9_1_bitacc_cmodel.dll'))
        create=dll.xilinx_ip_xfft_v9_1_create_state
        create.argtypes=[Generics];create.restype=c.c_void_p
        simulate=dll.xilinx_ip_xfft_v9_1_bitacc_simulate
        simulate.argtypes=[c.c_void_p,Inputs,c.POINTER(Outputs)];simulate.restype=c.c_int
        destroy=dll.xilinx_ip_xfft_v9_1_destroy_state
        destroy.argtypes=[c.c_void_p];destroy.restype=None
        state=create(Generics(10,2,0,0,16,24,0,0,1,1,0))
        if not state:raise RuntimeError('FFT C model could not create state')
        real=(c.c_double*1024)(*(x/32768 for x in samples))
        imag=(c.c_double*1024)();outreal=(c.c_double*1024)();outimag=(c.c_double*1024)()
        scaling=(c.c_int*10)()
        inputs=Inputs(10,real,1024,imag,1024,scaling,10,1)
        outputs=Outputs(outreal,1024,outimag,1024,0,0)
        try:
            if simulate(state,inputs,c.byref(outputs)):
                raise RuntimeError('FFT C model failed')
            assert outputs.real_size==outputs.imag_size==1024
            result=[complex(round(outreal[k]*32768),round(outimag[k]*32768)) for k in range(1024)]
            assert all(z.real==outreal[k]*32768 and z.imag==outimag[k]*32768 for k,z in enumerate(result))
            return result
        finally:
            destroy(state)
