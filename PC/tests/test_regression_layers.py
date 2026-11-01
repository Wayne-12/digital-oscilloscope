"""The orchestration must fail closed before entering a higher layer."""
import sys,unittest,json,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'FPGA/scripts'))
import run_system_regression as runner

class LayerOrderTests(unittest.TestCase):
    def state(self):
        return dict(foundation=[],connected=[],phase_history=[])

    def passing_units(self):
        return [dict(report='fixture',tests=['safe_seq','adc_capture','dds_dac','capture_bram'])]

    def test_unit_then_integration_then_system(self):
        m=self.state();events=[]
        def prior(a,r,selected):
            events.append('base_units' if 'smoke' in selected else 'integration');return []
        with patch.object(runner,'prior_suites',side_effect=prior), \
             patch.object(runner,'unit_suites',side_effect=lambda *x:events.append('units') or self.passing_units()), \
             patch.object(runner,'connected_cases',side_effect=lambda *x:events.append('system')):
            runner.execute_layers(SimpleNamespace(system_only=False,seeds=[42]),Path('.'),Path('.'),m)
        self.assertEqual(events,['base_units','units','integration','system'])
        self.assertEqual(m['phase_history'],['unit','integration','system'])

    def test_unit_failure_blocks_integration_and_system(self):
        m=self.state()
        with patch.object(runner,'prior_suites',return_value=[]) as prior, \
             patch.object(runner,'unit_suites',side_effect=runner.RegressionFailure('UNIT_LAYER','test')), \
             patch.object(runner,'connected_cases') as system:
            with self.assertRaises(runner.RegressionFailure):
                runner.execute_layers(SimpleNamespace(system_only=False,seeds=[42]),Path('.'),Path('.'),m)
        self.assertEqual(prior.call_count,1);system.assert_not_called()
        self.assertEqual(m['phase_history'],['unit'])

    def test_integration_failure_blocks_system(self):
        m=self.state()
        with patch.object(runner,'prior_suites',side_effect=[[],runner.RegressionFailure('SUITE_uart','test')]), \
             patch.object(runner,'unit_suites',return_value=self.passing_units()),patch.object(runner,'connected_cases') as system:
            with self.assertRaises(runner.RegressionFailure):
                runner.execute_layers(SimpleNamespace(system_only=False,seeds=[42]),Path('.'),Path('.'),m)
        system.assert_not_called();self.assertEqual(m['phase_history'],['unit','integration'])

    def test_partial_unit_report_cannot_open_gate(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td)
            payload=dict(verdict='PASS',layer='unit',seeds=[42],tests=['uart_phy'],source_sha256={},
                         results=[dict(test='uart_phy',seed=42,verdict='PASS')])
            (d/'manifest.json').write_text(json.dumps(payload),encoding='utf-8')
            with self.assertRaises(runner.RegressionFailure) as error:
                runner.unit_suites(SimpleNamespace(unit_reports=[d],seeds=[42]),d)
            self.assertEqual(error.exception.code,'UNIT_COVERAGE')

    def test_changed_source_invalidates_unit_report(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td)
            payload=dict(verdict='PASS',layer='unit',seeds=[42],tests=[],results=[],
                         source_sha256={'rtl/common/scope_pkg.sv':'0'*64})
            (d/'manifest.json').write_text(json.dumps(payload),encoding='utf-8')
            with self.assertRaises(runner.RegressionFailure) as error:
                runner.unit_suites(SimpleNamespace(unit_reports=[d],seeds=[42]),d)
            self.assertEqual(error.exception.code,'UNIT_SOURCE_CHANGED')

if __name__=='__main__':unittest.main()
