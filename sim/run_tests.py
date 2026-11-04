"""Run host regression against a disposable copy of the delivered source tree."""
from pathlib import Path
import os,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'build'))
from stage_workspace import main
work=main()
env=dict(os.environ,QT_QPA_PLATFORM='offscreen',PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8',PYTHONUTF8='1')
result=subprocess.run([sys.executable,'-m','unittest','discover','-s','pc/tests','-v'],cwd=work,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace')
log=ROOT/'sim/results/submission_pc_tests.log'
log.parent.mkdir(parents=True,exist_ok=True)
log.write_text(result.stdout+result.stderr,encoding='utf-8')
print((result.stdout+result.stderr)[-3500:])
raise SystemExit(result.returncode)
