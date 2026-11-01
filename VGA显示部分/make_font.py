"""Bake Chinese SimSun and Latin Times New Roman into the FPGA glyph ROM."""
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import json
import math
import re
root=Path(__file__).resolve().parent
source=(root/'panel_main.c').read_text(encoding='utf-8')
chars=sorted({c for c in source if '\u4e00'<=c<='\u9fff'})
assert 128+2*len(chars)<=512, len(chars)
def load(paths,size):
    for path in paths:
        if Path(path).exists():return ImageFont.truetype(path,size),path
    return ImageFont.load_default(), 'Pillow default'
cn,cn_path=load(['C:/Windows/Fonts/simsun.ttc','C:/Windows/Fonts/msyh.ttc'],24)
latin,latin_path=load(['C:/Windows/Fonts/times.ttf','C:/Windows/Fonts/arial.ttf'],22)
rows=[0]*(512*32)
for code in range(32,127):
    glyph='\u2212' if code==45 else chr(code)
    width=max(16,latin.getbbox(glyph,anchor='ls')[2])
    im=Image.new('1',(width,24));dr=ImageDraw.Draw(im)
    dr.text((max(0,(16-int(latin.getlength(glyph)))//2),19),glyph,font=latin,fill=1,anchor='ls')
    if width>16:im=im.resize((16,24),Image.Resampling.NEAREST)
    for y in range(24):rows[code*32+y]=sum(int(im.getpixel((x,y)))<<(15-x) for x in range(16))
for i,c in enumerate(chars):
    im=Image.new('1',(32,24));ImageDraw.Draw(im).text((4,21),c,font=cn,fill=1,anchor='ls')
    for half in range(2):
        for y in range(24):rows[(128+i*2+half)*32+y]=sum(int(im.getpixel((half*16+x,y)))<<(15-x) for x in range(16))
# Paired short dashes share one cell; their central gap aligns with digit 0.
rows[127*32+11]=rows[127*32+12]=0x7e7e
(root/'font.mem').write_text(''.join(f'{n:04x}\n' for n in rows),encoding='ascii')
(root/'panel_font.h').write_text('#define PANEL_CJK_COUNT '+str(len(chars))+'\nstatic const unsigned short panel_cjk[]={'+','.join(str(ord(c)) for c in chars)+'};\n',encoding='ascii')
knob=[]
steps=int(re.search(r'#define PANEL_KNOB_STEPS (\d+)u',(root/'panel_knob_scale.h').read_text()).group(1))
for i in range(steps+1):
    angle=math.radians(135+i*270/steps)
    x=round(64*math.cos(angle));y=round(64*math.sin(angle))
    knob.append((x&255)|((y&255)<<8))
(root/'panel_knob.h').write_text('static const unsigned short panel_knob[]={'+','.join(str(x) for x in knob)+'};\n',encoding='ascii')
(root/'output').mkdir(exist_ok=True)
small_cn,_=load(['C:/Windows/Fonts/simsun.ttc','C:/Windows/Fonts/msyh.ttc'],20)
small_latin,_=load(['C:/Windows/Fonts/times.ttf','C:/Windows/Fonts/arial.ttf'],18)
small_rows=[0]*(64*32);small_map={};small_count=0
for c in sorted(set(' 0123456789.-kHzmV')):
    glyph='\u2212' if c=='-' else c
    width=max(12,small_latin.getbbox(glyph,anchor='ls')[2])
    im=Image.new('1',(width,24))
    ImageDraw.Draw(im).text((max(0,(12-int(small_latin.getlength(glyph)))//2),20),glyph,font=small_latin,fill=1,anchor='ls')
    if width>12:im=im.resize((12,24),Image.Resampling.NEAREST)
    small_map[ord(c)]=small_count
    for y in range(24):small_rows[small_count*32+y]=sum(int(im.getpixel((x,y)))<<(11-x) for x in range(12))
    small_count+=1
for c in sorted(set('频率峰值有效平均回环')):
    im=Image.new('1',(24,24));ImageDraw.Draw(im).text((2,20),c,font=small_cn,fill=1,anchor='ls')
    for half in range(2):
        small_map[128+chars.index(c)*2+half]=small_count
        for y in range(24):small_rows[small_count*32+y]=sum(int(im.getpixel((half*12+x,y)))<<(11-x) for x in range(12))
        small_count+=1
assert small_count<=64
(root/'small_font.mem').write_text(''.join(f'{n:03x}\n' for n in small_rows),encoding='ascii')
mapping='function automatic [5:0] small_glyph(input [8:0] code);\n case(code)\n'
mapping+=''.join(f"  9'd{k}:small_glyph=6'd{v};\n" for k,v in sorted(small_map.items()))
mapping+='  default:small_glyph=0;\n endcase\nendfunction\n'
(root/'panel_small_font.svh').write_text(mapping,encoding='ascii')
(root/'output/small_font_map.json').write_text(json.dumps(small_map),encoding='ascii')
(root/'output/fonts.json').write_text(json.dumps({'Chinese':cn_path,'LatinDigits':latin_path,'characters':len(chars)},ensure_ascii=False,indent=2),encoding='utf-8')
print('FONT_READY',cn_path,latin_path,len(chars))
# Mirrored 5-degree ticks; the renderer limits them to the 270-degree sweep.
ticks=[]
for y in range(128):
    for x in range(128):
        value=0
        for deg in range(0,91,5):
            a=math.radians(deg);along=x*math.cos(a)+y*math.sin(a)
            across=abs(y*math.cos(a)-x*math.sin(a))
            major=deg%45==0
            if (90 if major else 96)<=along<=(108 if major else 103) and across<=(0.9 if major else 0.6):
                value=2 if major else 1
        ticks.append(value)
(root/'knob_ticks.mem').write_text(''.join(f'{v:x}\n' for v in ticks),encoding='ascii')
