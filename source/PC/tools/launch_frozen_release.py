"""Verify a frozen release before launching its UI or explicit acceptance mode."""
import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def verify(root):
    manifest = json.loads((root/'release_manifest.json').read_text(encoding='utf-8'))
    for relative, expected in manifest['files_sha256'].items():
        path = (root/relative).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError('Missing or invalid release file: '+relative)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Release file changed: '+relative)
    return manifest


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--mode', choices=('verify', 'ui', 'short', 'soak'), default='verify')
    cli.add_argument('--port', default='COM12')
    cli.add_argument('--conditions', help='Actual connection, supply, gain position and ambient observations')
    cli.add_argument('--dry-run', action='store_true', help='Print the command without opening hardware')
    args = cli.parse_args()
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        manifest = verify(ROOT)
    except (OSError, ValueError, KeyError) as error:
        print('Release integrity check failed: '+str(error), file=sys.stderr)
        return 1
    print(f"Release verified: {manifest['release_id']} / {len(manifest['files_sha256'])} files", flush=True)
    if args.mode == 'verify':
        return 0
    if args.mode == 'ui':
        command = [sys.executable, str(ROOT/'PC/ui/launch_scope.py'), '--linked', '--baud', '921600', '--port', args.port]
    else:
        conditions = args.conditions
        if not conditions and not args.dry_run:
            try:
                conditions = input('请输入本次实际接线、电源、旋钮位置及环境观察（记录到报告）：\n').strip()
            except EOFError:
                cli.error('Provide --conditions with the actual setup observations')
            if not conditions:
                cli.error('Actual setup observations cannot be empty')
        # Runtime results live in their own directory and never overwrite frozen evidence.
        run_id = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d_%H%M%S_%f')
        output = ROOT/'PC/acceptance_runs'/f'{run_id}_{args.mode}'
        command = [sys.executable, '-u', str(ROOT/'PC/tools/run_uart_acceptance.py'),
                   '--hardware', '--port', args.port, '--baud', '921600',
                   '--device-id', 'EGO1-FTDI-1234-COM12', '--expected-build', '0xA0261026',
                   '--firmware', str(ROOT/'firmware/scope_analysis_1024_25m.bit'),
                   '--conditions', conditions or 'DRY_RUN_ONLY', '--output-dir', str(output)]
        if args.mode == 'short':
            command += ['--duration', '30', '--uart-duration', '2', '--min-echo-bytes', '4096']
        else:
            command += ['--duration', '7200', '--uart-duration', '600', '--min-echo-bytes', '1048576']
        print('Mode: '+('30-second functional check' if args.mode == 'short' else
                        'At least 10-minute UART echo + uninterrupted 2-hour capture'), flush=True)
    if args.dry_run:
        print(json.dumps(command, ensure_ascii=False, indent=2))
        return 0
    return subprocess.run(command, cwd=ROOT, check=False).returncode


if __name__ == '__main__':
    raise SystemExit(main())
