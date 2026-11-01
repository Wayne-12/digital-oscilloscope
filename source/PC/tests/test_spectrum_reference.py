import math,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'protocol'))
from spectrum_reference import *

class SpectrumTests(unittest.TestCase):
    def test_dft_known_constant_impulse_and_inverse(self):
        self.assertAlmostEqual(dft([2]*16)[0].real,32)
        self.assertTrue(all(abs(z-3)<1e-10 for z in dft([3]+[0]*15)))
        xs=[complex(i-8,3-i) for i in range(16)];back=dft(dft(xs),True)
        self.assertTrue(all(abs(z/16-x)<1e-9 for z,x in zip(back,xs)))
    def test_coherent_complex_sign_and_bin(self):
        x=[complex(math.cos(2*math.pi*3*i/32),math.sin(2*math.pi*3*i/32)) for i in range(32)]
        self.assertEqual(max(range(32),key=lambda k:abs(dft(x)[k])),3)
        self.assertEqual(max(range(32),key=lambda k:abs(dft(x,True)[k])),29)
    def test_window_gain_and_frontend_rounding(self):
        self.assertEqual(sum(HANN),N*32768)
        self.assertEqual(preprocess([-4096]*N,0),[-32768]*N)
        self.assertEqual(preprocess([4095]*N,0),[32760]*N)
        self.assertEqual(preprocess([4095]*N,1)[N//2],32760)
        self.assertEqual(preprocess([4095]*N,1)[0],0)
    def test_coherent_amplitude_parseval_and_silence(self):
        x=[round_away(1000*math.sin(2*math.pi*37*i/N)) for i in range(N)]
        z=dft(preprocess(x));s=summary(z,25000000)
        self.assertEqual(s['peak_bin'],37);self.assertLess(abs(s['amplitude_q16']/65536-1000),0.1)
        self.assertLess(abs(sum(one_sided_power(z))-sum(v*v for v in x)/N),1e-6)
        for window in (0,1):
            zero=summary(dft(preprocess([0]*N,window)),25000000,window)
            self.assertEqual((zero['valid'],zero['peak_bin'],zero['frequency'],zero['amplitude_q16']),(0,0,0,0))
    def test_hann_reduces_far_leakage(self):
        x=[round_away(1000*math.sin(2*math.pi*37.25*i/N+0.17)) for i in range(N)]
        spectra=[dft(preprocess(x,w)) for w in (0,1)]
        far=[sum(one_sided_power(z,w)[k] for k in range(513) if not 35<=k<=40) for w,z in enumerate(spectra)]
        self.assertLess(far[1],far[0]*0.05)

if __name__=='__main__':unittest.main()
