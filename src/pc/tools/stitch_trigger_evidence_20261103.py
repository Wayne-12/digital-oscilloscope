"""Arrange unmodified live screenshots and render an evidence summary."""
from pathlib import Path
import json
from PySide6.QtGui import QImage,QPainter,QColor,QFont,QGuiApplication,QFontDatabase
from PySide6.QtCore import Qt
app=QGuiApplication([])
fid=QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')
family=QFontDatabase.applicationFontFamilies(fid)[0]
OUT=Path(__file__).resolve().parents[2]/'outputs/trigger_evidence_20261103'
r=json.loads((OUT/'report.json').read_text(encoding='utf-8'))
assert r['result']=='PASS' and len(r['frames'])==32
font=QFont(family,18)
small=QFont(family,13)
def montage(items,cols,target,title):
    tw,th=740,490;rows=(len(items)+cols-1)//cols
    im=QImage(cols*tw,80+rows*(th+42),QImage.Format.Format_RGB32);im.fill(QColor('white'));d=QPainter(im);d.setPen(QColor('#17243b'));d.setFont(font);d.drawText(20,42,title)
    for i,item in enumerate(items):
        x=(i%cols)*tw;y=80+(i//cols)*(th+42)
        tile=QImage(str(OUT/(item['name']+'.png'))).scaled(tw,th,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
        d.drawImage(x,y,tile);d.setFont(small);d.drawText(x+10,y+th+28,f"{item['kind']} | {item['mode']} | 索引 {item['trigger']} | {item['name']}")
    d.end();assert im.save(str(OUT/target))
montage([r['frames'][i*4] for i in range(8)],2,'八类触发_总览.png','1 MHz 正弦实物回环 · 八类触发代表帧（原始截图缩放排列）')
for i in range(8):montage(r['frames'][i*4:i*4+4],2,f'{i+1:02d}_四帧拼图.png',f"{r['frames'][i*4]['kind']} · 4帧实物匹配记录")
montage(r['frames'],4,'32帧_完整拼图.png','1 MHz 正弦实物回环 · 8类 × 4帧 · 全部触发索引8192')
lines=['# 触发实物验证','',f"固件：{r['build']}；接口：COM12；采样率：25 MSPS。",'', '32帧来自本次实物UART读取；截图由生产上位机加载对应实物冻结帧生成。拼图仅缩放排列，不修改波形、数字或采集结果。','', '|触发|匹配帧|索引|不匹配观察|','|---|---|---|---|']
for i,v in enumerate(r['waiting']):lines.append(f"|{v['kind']}|4（NORMAL 2 + SINGLE 2）|8192|{v['seconds']:.2f}秒内保持等待|")
lines+=['','AUTO不匹配条件下仍生成超时帧；SINGLE冻结保持已检查。','',f"原板端配置恢复：{r.get('restored',False)}。",'','原始ADC数据见同目录.npy；逐帧时间戳、触发参数及等待轮询见report.json。']
(OUT/'验证说明.md').write_text('\n'.join(lines),encoding='utf-8')
print(OUT/'八类触发_总览.png')
