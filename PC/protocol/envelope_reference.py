"""Integer reference for frozen-frame envelope/ROI; no dependency on RTL."""
MAX_SAMPLES=16384
MAX_BUCKETS=800
MASK64=(1<<64)-1

def boundaries(sample_count,requested_buckets=800):
    if not 1<=sample_count<=MAX_SAMPLES or not 1<=requested_buckets<=MAX_BUCKETS:
        raise ValueError('invalid frame/bucket count')
    count=min(sample_count,requested_buckets)
    return [(i*sample_count//count,(i+1)*sample_count//count-1) for i in range(count)]

def roi_bounds(sample_count,trigger_index,requested=1024):
    if not 1<=sample_count<=MAX_SAMPLES or not 0<=trigger_index<sample_count:
        raise ValueError('invalid trigger/frame')
    if requested==0:return (0,0,0)
    if not 512<=requested<=2048:raise ValueError('ROI length must be 0 or 512..2048')
    count=min(requested,sample_count)
    first=min(max(trigger_index-count//2,0),sample_count-count)
    return first,count,trigger_index-first

def summarize(words,trigger_index,requested_buckets=800,requested_roi=1024):
    n=len(words);bs=boundaries(n,requested_buckets);roi=roi_bounds(n,trigger_index,requested_roi)
    if any(not 0<=w<=65535 or w&0x7000 for w in words):raise ValueError('invalid stored sample')
    signed=[2047-(w&4095) for w in words];result=[]
    for i,(lo,hi) in enumerate(bs):
        values=signed[lo:hi+1];mn=min(values);mx=max(values)
        result.append((i,lo,hi,len(values),mn,mx,lo+values.index(mn),lo+values.index(mx),int(any(w&0x8000 for w in words[lo:hi+1]))))
    return result,roi
