"""Read status, release the PC lease, and observe real autonomous CPU progress."""
from pathlib import Path
import json,struct,time
from hardware_client import Client
root=Path(__file__).resolve().parents[2]
out=root/'软核/reports/version_sync_20261030/autonomous.json'
r=dict(result='FAIL',scope='autonomous command progress without PC requests for 7 seconds; no video observation')
c=None
try:
 c=Client();assert c.identity()==0xA7261029
 before=c.request(3).payload;r['before_commands']=struct.unpack_from('<I',before,44)[0]
 c.close();c=None
 time.sleep(7)
 c=Client();after=c.request(3).payload;r['after_commands']=struct.unpack_from('<I',after,44)[0]
 r['autonomous_command_delta']=(r['after_commands']-r['before_commands'])&0xffffffff
 assert r['autonomous_command_delta']>=8,'No autonomous progress: check SW0 ON, SW1 and SW7 OFF'
 assert before[12:44]==after[12:44],'communication error counters changed'
 assert not any(c.parser.errors.values())
 r['result']='PASS'
except Exception as exc:r['error']=repr(exc)
finally:
 if c:c.close()
 out.write_text(json.dumps(r,indent=2),encoding='utf-8')
print(json.dumps(r,indent=2))
raise SystemExit(r['result']!='PASS')
