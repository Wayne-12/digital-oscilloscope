"""Independently audit saved raw evidence and plot the discrete loopback survey."""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import os

import numpy as np
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pyqtgraph as pg
from pyqtgraph.exporters import ImageExporter
from PySide6 import QtGui, QtWidgets


def check(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    a = parser.parse_args()
    folder = a.run.resolve()
    report = json.loads((folder/'report.json').read_text(encoding='utf-8'))
    check(report['verdict'] == 'SURVEY_COMPLETE' and report['restored'], 'Incomplete survey or failed restoration')
    check(report['configuration_before_hex'] == report['configuration_after_hex'], 'Configuration differs')
    check(not any(report['error_deltas']) and not any(report['parser_errors'].values()), 'Transport errors')
    timestamps = set()
    for row in report['frames']:
        path = (folder/row['file']).resolve()
        check(path.parent == folder and row['verified'], 'Invalid frame path or unverified frame')
        check(hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256'], 'Raw frame hash differs')
        words = np.load(path, allow_pickle=False)
        check(words.shape == (16384,) and words.dtype == np.dtype('uint16'), 'Frame format differs')
        check(not np.any(words & 0xf000), 'OTR or reserved bit')
        raw = words & 4095
        check(not np.any((raw == 0) | (raw == 4095)), 'Unexpected saturated input')
        check(row['saturation'] == {'count':16384, 'saturated_samples':0, 'events':0, 'diagnostic':False}, 'Wrong saturation summary')
        signed = 2047-raw.astype(np.int64)
        m = row['measurement']
        check((m['count'],m['minimum'],m['maximum'],m['sum'],m['square_sum']) ==
              (16384,int(signed.min()),int(signed.max()),int(signed.sum()),int((signed*signed).sum())), 'Moment mismatch')
        check(row['timestamp'] not in timestamps, 'Repeated frozen frame')
        timestamps.add(row['timestamp'])
    for relative, digest in report['source_sha256'].items():
        check(hashlib.sha256((folder/'source'/relative).read_bytes()).hexdigest() == digest, 'Source snapshot hash differs')
    grouped = {}
    for row in report['frames']:
        if row['case'] == 'survey':
            grouped.setdefault((row['wave'],row['frequency_hz'],row['phase_degrees']),[]).append(row)
    table = []
    names = ('sine','square','triangle')
    for (wave, frequency, phase), rows in sorted(grouped.items()):
        analyses = [row['analysis'] for row in rows]
        item = {'wave':names[wave], 'frequency_hz':frequency, 'phase_degrees':phase, 'frames':len(rows),
                'status':analyses[0]['status'], 'observed_vpp_codes_min':min(v['vpp_adc_codes'] for v in analyses),
                'observed_vpp_codes_max':max(v['vpp_adc_codes'] for v in analyses)}
        for source, target in (('fitted_peak_adc_codes','peak_adc_codes'),
                               ('relative_to_100khz_db','relative_db'),
                               ('fundamental_residual_ratio','sine_basis_residual_ratio')):
            values = [v[source] for v in analyses if source in v]
            item[target+'_min'] = min(values) if values else ''
            item[target+'_max'] = max(values) if values else ''
        table.append(item)
    with (folder/'frequency_points.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream,fieldnames=list(table[0]))
        writer.writeheader()
        writer.writerows(table)
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    fonts = Path(os.environ.get('SystemRoot', 'C:/Windows'))/'Fonts'
    for name in ('segoeui.ttf','arial.ttf'):
        if (fonts/name).is_file():
            QtGui.QFontDatabase.addApplicationFont(str(fonts/name))
    app.setFont(QtGui.QFont('Segoe UI',10))
    pg.setConfigOptions(antialias=True, background='w', foreground='#263547')
    widget = pg.GraphicsLayoutWidget()
    widget.resize(1500, 660)
    widget.addLabel('Physical loopback survey | 25 MSPS | peak code 819 | fixed knob', colSpan=2)
    widget.nextRow()
    left = widget.addPlot(title='DAC + cable + ADC response')
    right = widget.addPlot(title='12.5 MHz boundary only')
    left.addLegend(offset=(15, 15))
    right.addLegend(offset=(15, 15))
    left.setLogMode(x=True)
    left.setLabel('bottom', 'Requested DDS frequency', units='Hz')
    left.getAxis('bottom').enableAutoSIPrefix(False)
    left.setLabel('bottom', 'Requested DDS frequency (MHz)')
    left.getAxis('bottom').setTicks([[(4,'0.01'),(5,'0.1'),(6,'1'),(float(np.log10(5000000)),'5'),(7,'10')]])
    left.setLabel('left', 'Fitted fundamental relative to 100 kHz', units='dB')
    left.setYRange(-6.3, 3.5)
    left.showGrid(x=True, y=True, alpha=.2)
    for level in (-3, 3):
        left.addItem(pg.InfiniteLine(pos=level, angle=0, pen=pg.mkPen('#a89010', width=1.2)))
    right.setLabel('bottom', 'Programmed phase', units='degrees')
    right.setLabel('left', 'Observed ADC peak-to-peak codes')
    right.getAxis('bottom').setTicks([[(v, str(v)) for v in (0,45,90,135)]])
    right.showGrid(x=True, y=True, alpha=.2)
    colors = ('#087f8c','#d17a00','#7851a9')
    for wave, name in enumerate(names):
        frequency_groups = {}
        for row in report['frames']:
            if row['case']=='survey' and row['wave']==wave and 'relative_to_100khz_db' in row['analysis']:
                frequency_groups.setdefault(row['frequency_hz'],[]).append(row['analysis']['relative_to_100khz_db'])
        frequencies = sorted(frequency_groups)
        median = [float(np.median(frequency_groups[f])) for f in frequencies]
        left.plot(frequencies, median, pen=pg.mkPen(colors[wave],width=1.5), symbol='o',
                  symbolSize=7, symbolBrush=colors[wave], name=name)
        values = [np.mean([row['analysis']['vpp_adc_codes'] for row in grouped[(wave,12500000,phase)]])
                  for phase in (0,45,90,135)]
        right.plot((0,45,90,135), values, pen=pg.mkPen(colors[wave],width=1.5),symbol='o',
                   symbolSize=7,symbolBrush=colors[wave],name=name)
    widget.nextRow()
    widget.addLabel('Measured points; connecting lines are guides. Gold lines: +/-3 dB screen.',colSpan=2)
    widget.nextRow()
    widget.addLabel('No continuous bandwidth, absolute voltage, or independent DAC quality qualification.',colSpan=2)
    widget.show()
    app.processEvents()
    exporter = ImageExporter(widget.scene())
    exporter.parameters()['width'] = 1800
    exporter.export(str(folder/'frequency_response.png'))
    widget.close()
    audit = {'verdict':'PASS_RAW_EVIDENCE_INTEGRITY_ONLY','frames':len(report['frames']),
             'samples':len(report['frames'])*16384,'digital_limit_hz':12500000,
             'real_dac_quality_qualification':False,'configuration_restored':True,
             'report_sha256':hashlib.sha256((folder/'report.json').read_bytes()).hexdigest()}
    (folder/'independent_audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
    print(json.dumps(audit,indent=2))


if __name__ == '__main__':
    main()
