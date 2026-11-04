"""Apply the saved nonzero DDS through the UI/worker ACK path, then capture."""
import ctypes
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / '.venv-ui/Lib/site-packages'))
sys.path.insert(0, str(ROOT / 'PC/tests'))
from test_scope_ui import ui

p = ui.proto
out = Path(__file__).resolve().parent
app = ui.QtWidgets.QApplication.instance() or ui.QtWidgets.QApplication([])
window = ui.ScopeWindow()
window.timer.stop()
window.source.setCurrentIndex(1)
window.hardware_connected = True
window.device_capabilities = 63
worker = ui.SerialWorker('COM12', 921600)
window.worker = worker
worker.command_confirmed.connect(window.remember_confirmed_command)
worker.dds_configuration_ready.connect(window.receive_dds_configuration)
worker.command_done.connect(worker.shutdown.set)
faults = []
worker.fault.connect(faults.append)
# The previous acknowledged profile is 100 kHz sine, 10%, zero offset.
window.dds_wave.setCurrentIndex(0)
window.dds_freq.setValue(100)
window.dds_amplitude.setValue(10)
window.dds_offset.setValue(0)
window.dds_phase.setValue(0)
window.dds_enable.setChecked(True)
window.apply_dds()
worker.run()
window.worker = None
assert not faults, faults
assert ui.read_hardware_profile(window.profile_path)['dds']['amplitude'] == .1
window.close()

w = ui.SerialWorker('COM12', 921600)
record = {'pc_release': ui.PC_RELEASE, 'source': 'hardware-uart', 'flash_written': False,
          'dds_configuration_verified_and_saved': True, 'frames': []}
try:
    w.open_link()
    record['configuration_hex'] = w.exchange(p.GET_CONFIG).payload.hex()
    record['before_status'] = w.read_status()
    for mode in (2, 2, 2, 0, 0, 0):
        frame = w.capture(2, acquisition_mode=mode)
        index = len(record['frames'])
        ui.np.save(out/f'restored_{index}.npy', frame.words)
        record['frames'].append({'mode': mode, 'timestamp': frame.timestamp,
                                 'samples': len(frame.words), 'measurement': frame.fpga_measurement})
    record['after_status'] = w.read_status()
    assert record['before_status']['counters'][:8] == record['after_status']['counters'][:8]
    assert len({f['timestamp'] for f in record['frames']}) == 6
    assert all(f['measurement']['period_valid'] and 99000 < f['measurement']['frequency'] < 101000
               for f in record['frames'])
    assert not any(w.parser.errors.values())
    record['result'] = 'PASS'
finally:
    if w.link is not None:
        try:
            w.exchange(p.STOP)
        finally:
            w.link.close()
    record['parser_errors'] = w.parser.errors
    (out/'restored_hardware.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(record, ensure_ascii=True))
