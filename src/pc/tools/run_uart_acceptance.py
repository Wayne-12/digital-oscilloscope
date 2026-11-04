"""Offline preparation / explicit physical UART and two-hour soak acceptance."""
from datetime import datetime
from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'pc/protocol'))
from uart_acceptance import BAUDS, run_acceptance


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    mode = cli.add_mutually_exclusive_group(required=True)
    mode.add_argument('--offline', action='store_true', help='virtual time, no serial dependency or hardware access')
    mode.add_argument('--hardware', action='store_true', help='open exactly the requested port and baud; no fallback')
    cli.add_argument('--baud', type=int, choices=BAUDS, required=True)
    cli.add_argument('--port')
    cli.add_argument('--device-id', default='')
    cli.add_argument('--conditions', default='', help='module/loopback/gain position/supply/ambient observations')
    cli.add_argument('--firmware', type=Path, help='artifact actually loaded on the board, hashed into report')
    cli.add_argument('--expected-build', type=lambda v: int(v, 0), default=0xA0261026)
    cli.add_argument('--duration', type=float, default=7200, help='uninterrupted soak seconds, excluding recovery')
    cli.add_argument('--uart-duration', type=float, default=600, help='echo stage minimum seconds')
    cli.add_argument('--min-echo-bytes', type=int, default=1048576, help='minimum verified one-way echo payload bytes')
    cli.add_argument('--seed', type=int, default=20261026)
    cli.add_argument('--output-dir', type=Path)
    args = cli.parse_args()
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if args.hardware and not (args.port and args.device_id and args.conditions and args.firmware and args.firmware.is_file()):
        cli.error('--hardware requires --port, --device-id, --conditions and an existing --firmware file')
    output = args.output_dir or ROOT/'pc/acceptance_runs'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    try:
        report = run_acceptance(output, args.baud, offline=args.offline, port=args.port,
                                device_id=args.device_id, conditions=args.conditions, firmware=args.firmware,
                                expected_build=args.expected_build, duration=args.duration,
                                uart_duration=args.uart_duration, min_bytes=args.min_echo_bytes, seed=args.seed)
    except (ValueError, OSError) as error:
        cli.error(str(error))
    print(f"{report['verdict']} — report: {output.resolve()/'report.json'}")
    print('可宣传的实测稳定档位: ' + str(report['qualified_bauds']))
    return 0 if report['verdict'] in ('PASS', 'SHORT_PASS', 'OFFLINE_PASS') else 1


if __name__ == '__main__':
    raise SystemExit(main())
