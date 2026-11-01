"""Independent PC-side scoreboard for one Step 14 connected system case."""
from __future__ import annotations

import argparse
import binascii
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "PC" / "protocol"))
from scope_protocol import Parser, RESPONSE, FIRST, LAST
from generate_measure_vectors import stats


class AuditError(Exception):
    def __init__(self, code: str, time_ns: int, detail: str = ""):
        super().__init__(f"{code} time_ns={time_ns} {detail}")
        self.code, self.time_ns, self.detail = code, time_ns, detail


def check(ok: bool, code: str, time_ns: int, detail: str = "") -> None:
    if not ok:
        raise AuditError(code, time_ns, detail)


def audit(vectors: Path, traces: Path) -> dict:
    cfg = json.loads((vectors / "config.json").read_text(encoding="utf-8"))
    raw_bytes = bytes.fromhex((traces / "system_uart.hex").read_text(encoding="ascii"))
    parser = Parser()
    frames = parser.feed(raw_bytes)
    check(len(frames) == 9 and not parser.buffer and not any(parser.errors.values()),
          "PC_FRAME_PARSE", 0, f"frames={len(frames)} errors={parser.errors}")
    live: dict[int, int] = {}
    previous = None
    live_gaps = 0
    for row in (traces / "system_live.csv").read_text(encoding="ascii").splitlines():
        ts_text, raw_text, otr_text = row.split(",")
        ts, raw, otr = int(ts_text), int(raw_text, 16), int(otr_text)
        check(0 <= raw <= 4095 and otr in (0, 1), "LIVE_ENCODING", ts)
        if previous is not None and cfg["case"] != 7:
            check(ts == previous + 1, "LIVE_TIMESTAMP_GAP", ts,
                  f"previous={previous}")
        elif previous is not None:
            check(ts > previous, "LIVE_TIMESTAMP_ORDER", ts)
        if previous is not None and ts != previous + 1:
            live_gaps += 1
        check(ts not in live, "LIVE_TIMESTAMP_DUPLICATE", ts)
        live[ts] = raw | (otr << 15)
        previous = ts
    check(len(live) > cfg["record_length"], "LIVE_TOO_SHORT", previous or 0,
          f"samples={len(live)}")
    check((live_gaps > 0) == (cfg["case"] == 7),
          "EMERGENCY_GAP_COVERAGE", previous or 0,
          f"gaps={live_gaps}")
    expected_kinds = (0x81, 0xC0, 0x90, 0x91, 0xA0, 0x83, 0xB1, 0xB0, 0xA1)
    for i, (frame, kind) in enumerate(zip(frames, expected_kinds)):
        check(frame.kind == kind and frame.sequence == 100 + i,
              "PC_RESPONSE_ORDER", frame.timestamp,
              f"index={i} kind={frame.kind:02x} seq={frame.sequence}")
        check(frame.flags & RESPONSE and not (frame.flags & 2),
              "PC_RESPONSE_ERROR", frame.timestamp, f"index={i}")
        check(frame.sample_rate == cfg["sample_rate_hz"],
              "PC_SAMPLE_RATE", frame.timestamp, f"index={i}")
    check(frames[0].payload == b"step14", "PC_PING", 0)
    for i in (1, 2, 3, 4, 8):
        check(frames[i].payload == b"\x00", "PC_COMMAND_ACK", frames[i].timestamp,
              f"index={i} payload={frames[i].payload.hex()}")
    status = frames[5]
    first_ts = status.timestamp
    check(len(status.payload) == 48 and status.payload[0] & 0x06 == 0x06,
          "PC_STATUS_FRAME", first_ts)
    check(struct.unpack_from("<I", status.payload, 4)[0] == cfg["record_length"] and
          struct.unpack_from("<I", status.payload, 8)[0] == cfg["pre_samples"],
          "PC_STATUS_CONFIG", first_ts)
    check(status.trigger_index == cfg["pre_samples"], "PC_TRIGGER_INDEX", first_ts)
    measure = frames[6]
    measurement_count = cfg['record_length']
    check(len(measure.payload) == 64 and measure.payload[0] == 1 and
          struct.unpack_from("<I", measure.payload, 4)[0] == measurement_count,
          "PC_MEASUREMENT_VALID", measure.timestamp)
    accepted = [row.split(',') for row in (traces/'system_measure.csv').read_text(encoding='ascii').splitlines()]
    times = [int(r[0]) for r in accepted]
    words_measured = [int(r[1],16) | (int(r[2])<<15) for r in accepted]
    check(len(accepted)==measurement_count, 'MEASUREMENT_STREAM_LENGTH', measure.timestamp)
    check(all(live.get(t)==w for t,w in zip(times,words_measured)), 'MEASUREMENT_STREAM_SOURCE', measure.timestamp)
    golden = stats([2047-(w&4095) for w in words_measured],times,cfg['sample_rate_hz'],0,8)
    actual = [struct.unpack_from(fmt,measure.payload,offset)[0] for fmt,offset in
              (('<I',4),('<h',8),('<h',10),('<h',12),('<H',14),('<H',16),('<q',20),('<Q',28),
               ('<I',52),('<Q',36),('<I',44),('<I',48),('<B',3),('<B',1))]
    check(actual==golden and measure.payload[2]==golden[-1], 'MEASUREMENT_INTEGER_SCOREBOARD',
          times[0]*1000000000//cfg['sample_rate_hz'], f'expected={golden} actual={actual}')
    measured_frequency = struct.unpack_from("<I", measure.payload, 44)[0]
    pp = struct.unpack_from("<H", measure.payload, 14)[0]
    if cfg["case"] == 0:
        check(measure.payload[1] == 0 and pp == 0 and
              struct.unpack_from("<h", measure.payload, 12)[0] == 0,
              "MID_ZERO_MEASUREMENT", measure.timestamp)
    elif cfg["case"] != 5:
        check(measure.payload[1] == 1 and
              abs(measured_frequency - cfg["frequency_hz"]) <=
              max(3, cfg["frequency_hz"] // 100),
              "SINE_FREQUENCY", measure.timestamp,
              f"expected={cfg['frequency_hz']} actual={measured_frequency}")
    wave = frames[7]
    offset, total = struct.unpack_from("<II", wave.payload)
    check(offset == cfg["wave_offset"] and total == cfg["record_length"] and
          len(wave.payload) == 8 + 2 * cfg["wave_count"] and
          wave.flags & FIRST and wave.flags & LAST,
          "PC_WAVE_HEADER", wave.timestamp)
    check(wave.timestamp == first_ts + offset and
          wave.trigger_index == cfg["pre_samples"],
          "PC_WAVE_TIMESTAMP", wave.timestamp)
    words = struct.unpack_from("<" + "H" * cfg["wave_count"], wave.payload, 8)
    for i, word in enumerate(words):
        ts = wave.timestamp + i
        check(word == live.get(ts), "PC_WAVE_SAMPLE", ts,
              f"index={offset+i} expected={live.get(ts)} actual={word}")
    otr_count = sum(word >> 15 for word in live.values())
    check((otr_count > 0) == (cfg["case"] == 6), "OTR_PATH", first_ts,
          f"count={otr_count}")
    if cfg["case"] == 6:
        check(any(word & 0x8000 for word in words), "OTR_WAVE_MISSING", wave.timestamp)
    if cfg["case"] == 5:
        signed = [2047 - (w & 4095) for w in words]
        check(max(signed) >= 1900 and min(signed) <= -1900,
              "SINGLE_POINT_SPIKES", wave.timestamp)
    if cfg["case"] == 0:
        check(all(2047 - (w & 4095) == 0 for w in words),
              "MID_WAVE_ZERO", wave.timestamp)
    return dict(verdict="PASS", case=cfg["case"], seed=cfg["seed"],
                config=cfg, output_frames=len(frames), output_bytes=len(raw_bytes),
                live_samples=len(live), frame_length=total,
                trigger_index=wave.trigger_index, first_timestamp=first_ts,
                wave_compared=len(words), otr_samples=otr_count,
                live_gaps=live_gaps,
                peak_to_peak=pp, measured_frequency_hz=measured_frequency,
                measurement_golden=golden, measurement_input_first_timestamp=times[0],
                measurement_input_last_timestamp=times[-1], measurement_input_samples=len(times),
                first_error_time_ns=None)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--vectors", type=Path, required=True)
    p.add_argument("--traces", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    try:
        report = audit(a.vectors, a.traces)
    except AuditError as exc:
        report = dict(verdict="FAIL", first_error_time_ns=exc.time_ns,
                      error_code=exc.code, detail=exc.detail)
    except Exception as exc:
        report = dict(verdict="FAIL", first_error_time_ns=None,
                      error_code=type(exc).__name__, detail=str(exc))
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
    if report["verdict"] != "PASS":
        print(f"SYSTEM_AUDIT_FAIL {report['error_code']} time_ns={report['first_error_time_ns']} {report['detail']}")
        sys.exit(1)
    print(f"SYSTEM_AUDIT_PASS case={report['case']} seed={report['seed']} "
          f"compared={report['wave_compared']} live={report['live_samples']} "
          f"length={report['frame_length']}")


if __name__ == "__main__":
    main()
