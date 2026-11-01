"""Independent unbounded-integer ADC oracle; no RTL/package function calls."""
import argparse
import json
import random
from pathlib import Path

MASK32 = (1 << 32) - 1


def noise_step(value):
    value ^= (value * (1 << 13)) & MASK32
    value ^= value // (1 << 17)
    return (value ^ ((value * (1 << 5)) & MASK32)) & MASK32


def profile_settings(profile):
    return {
        "gain_q16": 98304 if profile == 1 else (69632 if profile == 4 else 65536),
        "offset_lsb": -3 if profile == 1 else (7 if profile == 4 else 0),
        "noise_lsb": 3 if profile == 2 else (2 if profile == 4 else 0),
        "missing_enable": profile in (3, 4),
        "missing_code": 2040 if profile == 4 else 2048,
        "replacement": 2041 if profile == 4 else 2049,
    }


def round_gain(sample, gain):
    product = sample * gain
    quotient, remainder = divmod(abs(product), 65536)
    magnitude = quotient + (remainder >= 32768)
    return magnitude if product >= 0 else -magnitude


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-output", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--random-samples", type=int, default=12000)
    args = parser.parse_args()
    if not 10000 <= args.random_samples <= 100000 or not 0 <= args.seed < (1 << 31):
        parser.error("Require 10000..100000 random samples and a 31-bit nonnegative seed")
    args.output.mkdir(parents=True, exist_ok=False)
    args.expected_output.mkdir(parents=True, exist_ok=False)
    rng = random.Random(args.seed)
    samples = []

    def append(value, phase, forced=None):
        index = len(samples)
        if forced is None:
            forced = 1 if index % 97 == 0 else (0 if index % 149 == 0 else None)
        samples.append((value, int(forced is not None), int(forced or 0), phase))

    for value in [-(1 << 31), -8192, -2049, -2048, -2047, -1024, -1, 0,
                  1, 1024, 2046, 2047, 2048, 8192, (1 << 31) - 1]:
        append(value, 0)
    for code in [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 0x555, 0xAAA]:
        append(2047 - code, 0)
    for value, forced in [(0, 1), (0, 0), (8192, 0), (-8192, 1)]:
        append(value, 0, forced)
    ramp_start = len(samples)
    for value in range(-2048, 2048):
        append(value, 1)
    zero_start = len(samples)
    for _ in range(256):
        append(0, 2)
    random_start = len(samples)
    for _ in range(args.random_samples):
        append(rng.randrange(-4096, 4096), 3)
    for _ in range(16):
        append(0, 4)
    total = len(samples)
    (args.output / "adc_meta.txt").write_text(
        f"{args.seed} {total} {ramp_start} {zero_start} {random_start} {args.random_samples}\n",
        encoding="ascii")
    stimulus = [((value & MASK32) << 32) | (enabled << 31) | (forced << 30) | (phase << 27)
                for value, enabled, forced, phase in samples]
    (args.output / "adc_stim.mem").write_text("".join(f"{word:016x}\n" for word in stimulus), encoding="ascii")
    profiles = []
    for profile in range(5):
        config = profile_settings(profile)
        state = (args.seed ^ 0xA9226000 ^ ((profile * 0x9E3779B9) & MASK32)) & MASK32
        state = state or 1
        initial_state = state
        expected = []
        missing_hits = auto_otr_hits = forced_high = forced_low = 0
        for value, enabled, forced, phase in samples:
            state = noise_step(state)
            noise = state % (2 * config["noise_lsb"] + 1) - config["noise_lsb"]
            adjusted = round_gain(value, config["gain_q16"]) + config["offset_lsb"] + noise
            auto_otr = int(adjusted < -2048 or adjusted > 2047)
            raw = 2047 - max(-2048, min(2047, adjusted))
            missing = int(config["missing_enable"] and raw == config["missing_code"])
            if missing:
                raw = config["replacement"]
            decoded = 2047 - raw
            otr = forced if enabled else auto_otr
            expected.append(raw | ((decoded & 0x1FFF) << 12) | (otr << 25) |
                            (auto_otr << 26) | (missing << 27))
            missing_hits += missing
            auto_otr_hits += auto_otr
            forced_high += int(enabled and forced and not auto_otr)
            forced_low += int(enabled and not forced and auto_otr)
        assert forced_high and forced_low and auto_otr_hits
        assert not config["missing_enable"] or missing_hits
        if profile == 0:
            assert {word & 0xFFF for word in expected[ramp_start:zero_start]} == set(range(4096))
            assert all(((word >> 12) & 0x1FFF) == 0 for word in expected[zero_start:random_start])
        (args.expected_output / f"adc_expected_p{profile}.mem").write_text(
            "".join(f"{word:08x}\n" for word in expected), encoding="ascii")
        profiles.append(dict(profile=profile, noise_seed=initial_state, missing_hits=missing_hits,
                             auto_otr_hits=auto_otr_hits, forced_high=forced_high,
                             forced_low=forced_low, **config))
    metadata = dict(seed=args.seed, total_samples=total, random_samples=args.random_samples,
                    ramp_start=ramp_start, ramp_count=4096, zero_start=zero_start,
                    zero_count=256, random_start=random_start, profiles=profiles,
                    encoding="raw = 2047 - clamp(adjusted, -2048, 2047)",
                    rounding="Q16 nearest integer; ties away from zero",
                    model_latency_periods=7, capture_extra_periods=1, total_latency_periods=8)
    (args.expected_output / "oracle_manifest.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"ORACLE_PASS seed={args.seed} total={total} random={args.random_samples} profiles=5")


if __name__ == "__main__":
    main()
