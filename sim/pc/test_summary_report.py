from pathlib import Path
from unittest.mock import patch
import csv,hashlib,json,sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'protocol'))
import summary_report as report

class SummaryReportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.package=self.root/'FPGA/output/current';self.impl=self.package/'implementation';self.impl.mkdir(parents=True)
        (self.package/'image.bit').write_bytes(b'accepted artifact')
        self.digest=report.sha(self.package/'image.bit')
        (self.package/'release_manifest.json').write_text(json.dumps(dict(build='0xA4261027',bitstream='image.bit',bitstream_sha256=self.digest,hardware_verdict='PASS',flash_programmed=False)))
        (self.impl/'timing.rpt').write_text('WNS(ns) summary\n 8.234 0.000 0 36000 0.017 0.000 0 36000 3.000 0.000 0 10000\n')
        (self.impl/'utilization.rpt').write_text('\n'.join(f'| {name} | {used} | 0 | 0 | {total} | {percent} |' for name,used,total,percent in
            [('Slice LUTs',100,20800,.48),('Slice Registers',200,41600,.48),('Block RAM Tile',13.5,50,27),('DSPs',42,90,46.67),('Bonded IOB',39,210,18.57)]))
        self.live=dict(build=0xA4261027,capabilities=63,port='COM12',baud=921600,device_id='same-device',sample_rate=25000000,counters=[0,0,0,0,0,5,0,0,120],pc_errors=dict(crc=0,length=0,version=0,timeout=0))
    def save_evidence(self,name,build,digest,device='same-device'):
        p=self.root/'pc/acceptance_runs'/name/'report.json';p.parent.mkdir(parents=True)
        p.write_text(json.dumps(dict(source='hardware-uart',build=hex(build),firmware_sha256=digest,baud=921600,device_id=device,
            started_at=name,verdict='PASS',qualified_bauds=[921600],restored=True,echo_payload_bytes=13418616,echo_seconds=600.03)))
    def test_actual_timing_and_fractional_bram(self):
        rows=report.collect(self.root,self.live);values={r['metric']:r['value'] for r in rows}
        self.assertEqual(values['setup_wns'],8.234);self.assertEqual(values['hold_whs'],.017)
        self.assertEqual(values['bram_used'],13.5);self.assertEqual(values['fpga_command_rejected'],5)
        self.assertFalse(values['current_image_formal_uart'])
        self.assertEqual(next(r['status'] for r in rows if r['metric']=='bit_error_rate'),'NOT_MEASURED')
    def test_historical_pass_does_not_qualify_new_image(self):
        self.save_evidence('old',0xA0261026,'oldsha')
        rows=report.collect(self.root,self.live)
        self.assertTrue(all(r['scope']=='historical-other-image' for r in rows if r['category']=='uart-test'))
        self.assertFalse(next(r['value'] for r in rows if r['metric']=='current_image_formal_uart'))
        self.save_evidence('wrong-device',0xA4261027,self.digest,'another-board')
        self.assertFalse(next(r['value'] for r in report.collect(self.root,self.live) if r['metric']=='current_image_formal_uart'))
        self.save_evidence('same',0xA4261027,self.digest)
        self.assertTrue(next(r['value'] for r in report.collect(self.root,self.live) if r['metric']=='current_image_formal_uart'))
    def test_no_false_zero_for_missing_or_foreign_evidence(self):
        (self.impl/'timing.rpt').unlink()
        rows=report.collect(self.root,self.live,dict(source='硬件 UART',firmware_build=0xA1261026))
        self.assertEqual(next(r['status'] for r in rows if r['category']=='measurement'),'UNAVAILABLE')
        self.assertEqual(next(r['value'] for r in rows if r['metric']=='routed_report'),'')
    def test_external_reference_metadata_and_display_are_distinct_from_nominal(self):
        measurement=dict(source='硬件 UART',firmware_build=0xA4261027,
            voltage_calibration=dict(mode='external-reference-dc',status='VERIFIED_DC_POINTS',
                scope='DC checked points only',profile_sha256='accepted-fixture-profile'),
            pc=dict(mean=.1),display_pc=dict(mean=.099))
        rows=report.collect(self.root,self.live,measurement)
        mode=next(r for r in rows if r['category']=='voltage-calibration' and r['metric']=='mode')
        self.assertEqual(mode['value'],'external-reference-dc')
        self.assertIn('no AC',mode['notes'])
        self.assertEqual(next(r['value'] for r in rows if r['category']=='display-measurement' and r['metric']=='mean'),.099)
        self.assertEqual(next(r['value'] for r in rows if r['metric']=='pc.mean'),.1)
    def test_tampered_image_refused(self):
        (self.package/'image.bit').write_bytes(b'modified')
        with self.assertRaises(ValueError):report.collect(self.root,self.live)
    def test_atomic_utf8_export(self):
        path=self.root/'汇总.csv';report.export(path,self.root,self.live)
        self.assertTrue(path.read_bytes().startswith(b'\xef\xbb\xbf'))
        with path.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
        self.assertEqual(set(rows[0]),set(report.FIELDS));before=path.read_bytes()
        with patch.object(report.os,'replace',side_effect=PermissionError('locked file')):
            with self.assertRaises(PermissionError):report.export(path,self.root,self.live)
        self.assertEqual(path.read_bytes(),before);self.assertFalse(list(self.root.glob('.scope-summary-*')))

if __name__=='__main__':unittest.main()
