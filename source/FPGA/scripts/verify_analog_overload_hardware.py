"""Real DAC->ADC range/overload acceptance; no diagnostic injection or Flash writes."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--port', default='COM12')
    cli.add_argument('--output-dir', type=Path, required=True)
    cli.add_argument('--source', choices=('dac-loopback', 'adc-input'), default='dac-loopback',
                     help='adc-input only observes an already configured analog input')
    a = cli.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    spec = importlib.util.spec_from_file_location('analog_acceptance_ui', ROOT/'示波器显示界面.py')
    ui = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = ui
    spec.loader.exec_module(ui)
    import analog_acceptance
    source_bytes = {path: path.read_bytes() for path in
                    (Path(__file__), ROOT/'PC/protocol/analog_acceptance.py', ROOT/'示波器显示界面.py')}
    worker = ui.SerialWorker(a.port, 921600)
    try:
        worker.open_link()
        report = analog_acceptance.run(worker, a.output_dir, source=a.source,
                                       progress=lambda message: print(message, flush=True))
        report['tool_sha256'] = {str(path.relative_to(ROOT)): hashlib.sha256(data).hexdigest()
                                 for path, data in source_bytes.items()}
        for path, data in source_bytes.items():
            snapshot = a.output_dir/'source'/path.relative_to(ROOT)
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            snapshot.write_bytes(data)
        if any(path.read_bytes() != data for path, data in source_bytes.items()):
            report.update(verdict='FAIL', source_error='验收期间源码发生改变')
        (a.output_dir/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({k: report[k] for k in ('verdict', 'restored', 'coverage', 'missing')},
                         ensure_ascii=False, indent=2), flush=True)
        return 0 if report['verdict'] == 'PASS' else 2 if report['verdict'] == 'INCOMPLETE' else 1
    finally:
        if worker.link is not None:
            worker.link.close()


if __name__ == '__main__':
    raise SystemExit(main())
