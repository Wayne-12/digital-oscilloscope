"""Independent, parameterized software references; no board or transport imports."""
import cmath
import math


def vector(data):
    if not isinstance(data, list) or not data:
        raise ValueError("input must be a nonempty numeric array")
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in data):
        raise ValueError("samples must be finite numbers")
    return data


def identity(data, **params):
    return vector(data)[:]


def affine(data, scale=1.0, offset=0.0):
    return [x * scale + offset for x in vector(data)]


def statistics(data):
    x = vector(data)
    return {"count": len(x), "minimum": min(x), "maximum": max(x),
            "mean": math.fsum(x) / len(x),
            "rms": math.sqrt(math.fsum(v * v for v in x) / len(x)),
            "vpp": max(x) - min(x)}


def envelope(data, buckets):
    """Floor-partitioned min/max; first occurrence wins ties. Inclusive last index."""
    x = vector(data)
    if isinstance(buckets, bool) or not isinstance(buckets, int) or buckets <= 0:
        raise ValueError("buckets must be a positive integer")
    n, b = len(x), min(len(x), buckets)
    result = []
    for i in range(b):
        lo, end = i * n // b, (i + 1) * n // b
        part = x[lo:end]
        mn, mx = min(part), max(part)
        result.append(dict(first=lo, last=end - 1, count=end - lo, minimum=mn, maximum=mx,
                           min_index=lo + part.index(mn), max_index=lo + part.index(mx)))
    return result


def fir(data, taps):
    """Causal FIR, zero initial state, output length equals input length; no drain."""
    x, h = vector(data), vector(taps)
    return [math.fsum(h[k] * x[n-k] for k in range(min(n+1, len(h)))) for n in range(len(x))]


def dft(data, window="rectangular", normalization="none"):
    """Direct O(N²) forward DFT, negative exponent, full complex spectrum as pairs.

    Periodic Hann; no implicit ADC shift, quantization, gain compensation or padding.
    """
    x = vector(data)
    if window not in ("rectangular", "hann") or normalization not in ("none", "forward"):
        raise ValueError("invalid window/normalization")
    n = len(x)
    if n > 4096:
        raise ValueError("direct DFT limited to 4096 samples; provide a custom model for larger transforms")
    y = [v * (0.5 - 0.5 * math.cos(2*math.pi*i/n) if window == "hann" else 1)
         for i, v in enumerate(x)]
    roots = [cmath.exp(-2j*math.pi*i/n) for i in range(n)]
    factor = n if normalization == "forward" else 1
    bins = [sum((v * roots[k*i % n] for i, v in enumerate(y)), 0j) / factor for k in range(n)]
    return [[z.real, z.imag] for z in bins]


MODELS = {f.__name__: f for f in (identity, affine, statistics, envelope, fir, dft)}
