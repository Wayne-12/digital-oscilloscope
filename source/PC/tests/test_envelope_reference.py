import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'protocol'))
from envelope_reference import boundaries,roi_bounds,summarize

class EnvelopeTests(unittest.TestCase):
    def test_nondivisible_partition_and_short_frames(self):
        for n,b in ((1,800),(799,800),(801,800),(16384,800),(16384,800),(16000,800),(16383,127)):
            pairs=boundaries(n,b);seen=[0]*n
            for lo,hi in pairs:
                self.assertLessEqual(lo,hi)
                for i in range(lo,hi+1):seen[i]+=1
            self.assertEqual(seen,[1]*n)
    def test_all_small_integer_partitions(self):
        for n in range(1,129):
            for b in range(1,129):
                pairs=boundaries(n,b)
                self.assertEqual(pairs[0][0],0);self.assertEqual(pairs[-1][1],n-1)
                self.assertTrue(all(a[1]+1==c[0] for a,c in zip(pairs,pairs[1:])))
    def test_all_impulse_positions_and_both_signs(self):
        for n,b in ((7,800),(31,7),(101,17),(801,800)):
            for position in range(n):
                for x in (-2048,2047):
                    words=[2047]*n;words[position]=2047-x
                    env,_=summarize(words,min(n-1,n//2),b)
                    hit=[row for row in env if row[1]<=position<=row[2]]
                    self.assertEqual(len(hit),1);self.assertEqual(hit[0][4 if x<0 else 5],x)
    def test_roi_clamps_and_trigger_index(self):
        for n in (1,511,512,799,16384,16384):
            for t in (0,n//2,n-1):
                for requested in (512,513,1024,2047,2048):
                    start,count,trigger=roi_bounds(n,t,requested)
                    self.assertEqual(count,min(n,requested));self.assertEqual(start+trigger,t)
                    self.assertTrue(0<=start<=t<start+count<=n)
        self.assertEqual(roi_bounds(16384,8192,2048),(7168,2048,1024))
    def test_invalid_config_and_ties(self):
        for n,b in ((0,800),(16385,800),(4,0),(4,801)):
            with self.assertRaises(ValueError):boundaries(n,b)
        with self.assertRaises(ValueError):roi_bounds(10,10)
        with self.assertRaises(ValueError):roi_bounds(10,0,511)
        env,_=summarize([2047,2047,2047],0,1)
        self.assertEqual(env[0],(0,0,2,3,0,0,0,0,0))

if __name__=='__main__':unittest.main()
