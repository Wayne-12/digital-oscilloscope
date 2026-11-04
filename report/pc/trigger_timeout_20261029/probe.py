"""Reproduce trigger wait and compare AUTO using the production UART worker."""
import ctypes  # Initialize the system runtime before loading venv packages.
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / '.venv-ui/Lib/site-packages'))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
spec = importlib.util.spec_from_file_location('scope_probe_ui', ROOT/'示波器显示界面.py')
ui = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ui
spec.loader.exec_module(ui)
p = ui.proto
out = Path(__file__).resolve().parent
w = ui.SerialWorker('COM12', 921600)
report = {'source': 'hardware-uart', 'flash_written': False, 'pc_release': ui.PC_RELEASE}
try:
    w.open_link()
    before = w.exchange(p.GET_CONFIG).payload
    mode = w.exchange(p.GET_CAPTURE_CONFIG).payload
    report['before_config_hex'] = before.hex()
    report['before_mode_hex'] = mode.hex()
    report['before_status'] = w.read_status()
    w.exchange(p.STOP)
    started = time.monotonic()
    try:
        frame = w.capture(1, acquisition_mode=2)
        report['single'] = {'result': 'TRIGGERED', 'timestamp': frame.timestamp}
    except TimeoutError as exc:
        report['single'] = {'result': type(exc).__name__, 'message': str(exc)}
    report['single']['elapsed'] = time.monotonic()-started
    frames = []
    for i in range(3):
        frame = w.capture(2, acquisition_mode=0)
        ui.np.save(out/f'auto_{i}.npy', frame.words)
        frames.append({'timestamp': frame.timestamp, 'samples': len(frame.words),
                       'measurement': frame.fpga_measurement,
                       'min_volts': float(frame.volts().min()), 'max_volts': float(frame.volts().max())})
    report['auto_frames'] = frames
    report['after_status'] = w.read_status()
    report['parser_errors'] = dict(w.parser.errors)
    report['result'] = 'PASS' if len({f['timestamp'] for f in frames}) == 3 else 'FAIL'
finally:
    if w.link is not None:
        try:
            w.exchange(p.STOP)
            if 'mode' in locals():
                w.exchange(p.SET_CAPTURE_MODE, mode)
            report['after_config_hex'] = w.exchange(p.GET_CONFIG).payload.hex()
            report['configuration_unchanged'] = report['after_config_hex'] == report.get('before_config_hex')
        finally:
            w.link.close()
    (out/f'probe_{ui.PC_RELEASE}.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=True))
