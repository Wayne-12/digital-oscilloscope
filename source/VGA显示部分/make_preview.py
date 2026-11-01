"""Render firmware-exported cells using the exact generated FPGA font ROM.
Trace and spectrum in these previews are illustrative, not measured data.
"""
from pathlib import Path
from PIL import Image,ImageDraw,ImageColor
import math
import json
import re
p=Path(__file__).resolve().parent
font=[int(x,16) for x in (p/'font.mem').read_text().split()]
small_font=[int(x,16) for x in (p/'small_font.mem').read_text().split()]
small_map=json.loads((p/'output/small_font_map.json').read_text())
ticks=[int(v,16) for v in (p/'knob_ticks.mem').read_text().split()]
images=[]
for page,variant in [(i,None) for i in range(6)]+[(5,'pass'),(5,'fail')]:
    suffix='_'+variant if variant else ''
    cells=[int(x,16) for x in (p/f'output/page_{page}{suffix}.mem').read_text().split()]
    im=Image.new('RGB',(1024,600),'#111122');dr=ImageDraw.Draw(im)
    dr.rectangle((0,0,1023,55),fill='#112244')
    dr.rectangle((32,64,991,103),fill='#112233',outline='#334455')
    if page in (0,3,4):
        for i in range(4):dr.rectangle((704,112+i*72,991,175+i*72),fill='#112233')
    if page==0:dr.rectangle((704,448,991,535),fill='#112233',outline='#445566')
    if page==3:
        for x in (32,520):dr.rectangle((x,448,x+471,535),fill='#112233',outline='#445566')
    if page==4:
        dr.rectangle((32,448,991,535),fill='#112233',outline='#445566')
        for x in (112,352,592,832):dr.rectangle((x,496,x+135,531),fill='#111122',outline='#445566')
    if page==5:
        selected=bool(cells[9*64+5]&512)
        dr.rectangle((64,208,319,247),fill='#224455' if selected else '#112233',outline='#99bbcc' if selected else '#445566')
        dr.rectangle((64,256,319,295),fill='#117733' if variant=='pass' else '#881111' if variant=='fail' else '#112233',outline='#55bb77' if variant=='pass' else '#cc6666' if variant=='fail' else '#445566')
    if page==2:
        calibration=(p/'panel_knob_scale.h').read_text()
        lo=int(re.search(r'PANEL_KNOB_MIN_MV (\d+)u',calibration).group(1))
        hi=int(re.search(r'PANEL_KNOB_MAX_MV (\d+)u',calibration).group(1))
        steps=int(re.search(r'PANEL_KNOB_STEPS (\d+)u',calibration).group(1))
        position=max(0,min(steps,((840-lo)*steps+(hi-lo)//2)//(hi-lo)))
        a=math.radians(135+position*270/steps)
        pointer_x=round(64*math.cos(a));pointer_y=round(64*math.sin(a))
        for y in range(176,401):
            for x in range(720,945):
                dx=x-832;dy=y-288;r2=dx*dx+dy*dy;s=dx+dy
                tick=ticks[abs(dy)*128+abs(dx)] if dy<=abs(dx) else 0
                color='#445566' if tick==1 else '#8899aa' if tick==2 else None
                if r2-12*dx-14*dy+85<=6724:color='#000011'
                if r2<=6724:color='#112233'
                if r2<=6400:color='#667788' if s<0 else '#223344'
                if r2<6084:color='#44bbdd'
                if r2<5625:color='#112233'
                if r2<5184:color='#223344'
                dot=dx*pointer_x+dy*pointer_y;cross=dx*pointer_y-dy*pointer_x
                if r2<4900 and 2560<=dot<=4096 and abs(cross)*8<=(4096-dot)*3:color='#445566'
                if r2<16:color='#334455'
                if color:im.putpixel((x,y),ImageColor.getrgb(color))
    if page in (0,3,4):
        dr.rectangle((32,144,672,424),fill='#000011')
        for x in range(32,673,64):
            for y in range(144,425,8):dr.point((x,y),fill='#333344')
        for y in range(144,425,40):
            for x in range(32,673,8):dr.point((x,y),fill='#333344')
        dr.line((32,284,672,284),fill='#555566');dr.line((352,144,352,424),fill='#555566')
        dr.rectangle((32,144,672,424),outline='#555566')
        if page==4:
            for x in range(640):
                index=x*4//5
                h=max(0,175-abs(index-41)*20,75-abs(index-82)*15,35-abs(index-123)*15)
                if h:dr.line((32+x,423,32+x,423-h),fill='#66bbff')
        else:
            dr.line([(32+x,284-round(120*math.sin(x*math.tau/100))) for x in range(640)],fill='#ffee55',width=2)
        if page==3:
            for x in (192,512):dr.line((x,144,x,424),fill='#99ccff')
            for y in (264,344):dr.line((32,y,672,y),fill='#99ccff')
    for a,c in enumerate(cells):
        x0=(a%64)*16;y0=(a//64)*24
        if ((page in (0,3,4) and a//64 in (6,9,12,15)) or (page==2 and a//64==18)) and a%64>=44:
            x0=720+(a%64-44)*12;y0=432 if page==2 else 132+((a//64-6)//3)*72
            small=small_map.get(str(c&511),0)
            for y in range(24):
                for x in range(12):
                    if small_font[small*32+y] & (2048>>x):im.putpixel((x0+x,y0+y),(204,221,238))
            continue
        if c&512:dr.rectangle((x0,y0,x0+15,y0+23),fill='#224455')
        for y in range(24):
            for x in range(16):
                if font[(c&511)*32+y] & (32768>>x):im.putpixel((x0+x,y0+y),(255,255,238) if c&512 else (204,221,238))
    im.save(p/f'output/page_{page}{suffix}.png')
    if not variant:images.append(im)
sheet=Image.new('RGB',(1024,900))
for i,im in enumerate(images):sheet.paste(im.resize((512,300)),((i%2)*512,(i//2)*300))
sheet.save(p/'output/pages.png')
print('PREVIEW_READY')
