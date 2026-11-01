"""Amplitude-independent, read-only echo probe; no retries of control commands."""
from pathlib import Path
import importlib.util
import json
import sys
import time
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('bridge_client',ROOT/'软核/scripts/hardware_client.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
out=ROOT/'PC/reports/final_acceptance_20261101'/sys.argv[1]
c=m.Client();report={'samples':[],'errors':[]}
try:
    report['before']=m.baseline(c)
    start=time.perf_counter()
    for i in range(400):
        sent=time.perf_counter()
        try:
            frame=c.request(1,b'BRIDGE_PROBE',timeout=.3)
            assert frame.payload==b'BRIDGE_PROBE'
            report['samples'].append([i,sent-start,time.perf_counter()-sent])
        except Exception as exc:report['errors'].append([i,sent-start,repr(exc)])
    report['after']=m.baseline(c)
    report['parser_errors']=c.parser.errors
finally:
    c.close();out.write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({'requests':400,'errors':report['errors'],'before':report['before'],'after':report.get('after')},indent=2),flush=True)
