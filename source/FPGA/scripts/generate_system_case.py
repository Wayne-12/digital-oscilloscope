"""Independent PC command vectors for the Step 14 byte-level system harness."""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "PC" / "protocol"))
from scope_protocol import (Frame, encode, PING, SET_DDS, SET_RECORD,
                            SET_TRIGGER, SINGLE, GET_STATUS, READ_MEASURE,
                            READ_WAVE, STOP)


def make(case: int, seed: int) -> tuple[list[bytes], dict]:
    if case not in range(8):
        raise ValueError("case must be 0..7")
    frequency = {0: 0, 1: 10_000, 2: 100_000, 3: 100_000,
                 4: 1_000_977, 5: 100_000, 6: 100_000,
                 7: 10_000}[case]
    amplitude = {0: 0, 1: 6000, 2: 2000, 3: 6000,
                 4: 6000, 5: 6000, 6: 6000,
                 7: 6000}[case]
    record_length = 16384
    pre_fraction_ppm = 500000
    pre = ((record_length - 1) * pre_fraction_ppm + 500000) // 1000000
    trigger_kind = 8 if case == 6 else 0
    threshold = 1750 if case == 5 else 0
    config = dict(case=case, seed=seed, frequency_hz=frequency,
                  amplitude=amplitude, record_length=record_length,
                  pre_samples=pre, sample_rate_hz=25_000_000,
                  trigger_kind=trigger_kind, trigger_threshold=threshold,
                  wave_offset=max(0, pre - 64), wave_count=128)
    trigger = struct.pack("<BBhHhhIIHI", trigger_kind, 0, threshold, 8,
                          -200, 200, 1, 1000, 1000, 2)
    assert len(trigger) == 24
    commands = [(PING, b"step14"),
                (SET_DDS, struct.pack("<BBIIHi", 3 if case == 0 else 0, 1,
                                      frequency, 0, amplitude, 0)),
                (SET_RECORD, struct.pack("<II", record_length, pre_fraction_ppm)),
                (SET_TRIGGER, trigger), (SINGLE, b""),
                (GET_STATUS, b""), (READ_MEASURE, b""),
                (READ_WAVE, struct.pack("<II", config["wave_offset"], 128)),
                (STOP, b"")]
    return [encode(Frame(kind=kind, sequence=100 + i, payload=payload))
            for i, (kind, payload) in enumerate(commands)], config


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--case", type=int, required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    frames, config = make(a.case, a.seed)
    a.out.mkdir(parents=True, exist_ok=True)
    for i, frame in enumerate(frames):
        (a.out / f"cmd_{i}.hex").write_text(
            "".join(f"{b:02x}\n" for b in frame), encoding="ascii")
    (a.out / "lengths.txt").write_text(
        "\n".join(str(len(f)) for f in frames) + "\n", encoding="ascii")
    (a.out / "config.json").write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"SYSTEM_VECTORS_PASS case={a.case} seed={a.seed} commands={len(frames)}")


if __name__ == "__main__":
    main()
