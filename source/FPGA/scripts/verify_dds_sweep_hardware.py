"""Discrete physical loopback survey, keeping the original 12.5MHz digital limit."""
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
    a = cli.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    spec = importlib.util.spec_from_file_location('dds_survey_ui', ROOT/'示波器显示界面.py')
    ui = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = ui
    spec.loader.exec_module(ui)
    import dds_sweep
    paths = (Path(__file__), ROOT/'PC/protocol/dds_sweep.py', ROOT/'PC/protocol/analog_acceptance.py',
             ROOT/'示波器显示界面.py', ROOT/'FPGA/rtl/dac_dds/scope_board_dds.sv',
             ROOT/'FPGA/rtl/dac_dds/dds_sine_lut.sv')
    sources = {path: path.read_bytes() for path in paths}
    worker = ui.SerialWorker(a.port, 921600)
    try:
        worker.open_link()
        report = dds_sweep.run(worker, a.output_dir, progress=lambda message: print(message, flush=True))
        report['source_sha256'] = {str(path.relative_to(ROOT)): hashlib.sha256(data).hexdigest()
                                  for path, data in sources.items()}
        for path, data in sources.items():
            dest = a.output_dir/'source'/path.relative_to(ROOT)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        if any(path.read_bytes() != data for path, data in sources.items()):
            report.update(verdict='FAIL', source_error='测试期间源码发生改变')
        (a.output_dir/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        print(json.dumps({key: report[key] for key in ('verdict', 'restored', 'summary')}, ensure_ascii=False, indent=2), flush=True)
        return 0 if report['verdict'] == 'SURVEY_COMPLETE' and report['restored'] else 1
    finally:
        if worker.link is not None:
            worker.link.close()


if __name__ == '__main__':
    raise SystemExit(main())
