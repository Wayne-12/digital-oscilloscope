"""Software DUT examples, independent from goldencheck.models; NOT hardware results.

Interface: dut_program.py {fir|fft} input.json output.json
Replace this program with a simulator, executable, or board readback adapter.
"""
import cmath
import json
from pathlib import Path
import sys


def streaming_fir(samples):
    # Shift register implementation, unlike the reference's direct indexing.
    delay = [0.0, 0.0, 0.0]
    output = []
    for sample in samples:
        delay = [sample] + delay[:-1]
        output.append(delay[0] * 0.25 + delay[1] * 0.5 + delay[2] * 0.25)
    return output


def radix2_fft(samples):
    n = len(samples)
    if n == 0 or n & (n - 1):
        raise ValueError("radix-2 FFT requires a nonzero power-of-two length")
    a = [complex(x) for x in samples]
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j ^= bit
        if i < j:
            a[i], a[j] = a[j], a[i]
    width = 2
    while width <= n:
        root = cmath.exp(-2j * cmath.pi / width)
        for start in range(0, n, width):
            w = 1 + 0j
            for k in range(width // 2):
                even, odd = a[start+k], w * a[start+k+width//2]
                a[start+k], a[start+k+width//2] = even+odd, even-odd
                w *= root
        width *= 2
    return [[x.real, x.imag] for x in a]


if __name__ == "__main__":
    mode, inp, out = sys.argv[1:]
    data = json.loads(Path(inp).read_text(encoding="utf-8"))
    result = {"fir": streaming_fir, "fft": radix2_fft}[mode](data)
    Path(out).write_text(json.dumps(result, allow_nan=False), encoding="utf-8")
