from pathlib import Path
from html import escape
from PIL import Image, ImageDraw, ImageFont
import math

ROOT = Path(__file__).resolve().parent
W, H = 2200, 1370
im = Image.new('RGB', (W, H), 'white')
d = ImageDraw.Draw(im)
svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}"><rect width="100%" height="100%" fill="white"/>']
INK, DATA, CLOCK, POWER, ANALOG = '#20384B', '#216EAA', '#8553A5', '#B65031', '#247A65'

def text(x, y, s, size=30, color=INK, bold=False):
    font = ImageFont.truetype('C:/Windows/Fonts/msyhbd.ttc' if bold else 'C:/Windows/Fonts/msyh.ttc', size)
    d.text((x, y), s, font=font, fill=color, anchor='mm')
    svg.append(f'<text x="{x}" y="{y}" text-anchor="middle" dominant-baseline="central" font-family="Microsoft YaHei, sans-serif" font-size="{size}" font-weight="{700 if bold else 400}" fill="{color}">{escape(s)}</text>')

def box(x, y, w, h, lines):
    d.rounded_rectangle((x,y,x+w,y+h), radius=12, fill='#F1F6FA', outline=INK, width=3)
    svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="#F1F6FA" stroke="{INK}" stroke-width="3"/>')
    for i,s in enumerate(lines):
        text(x+w/2,y+h/2+(i-(len(lines)-1)/2)*47,s,31,bold=i==0)

def arrow(points, color=DATA, both=False):
    d.line(points, fill=color, width=4)
    svg.append('<polyline points="'+' '.join(f'{x},{y}' for x,y in points)+f'" fill="none" stroke="{color}" stroke-width="4"/>')
    def head(a,b):
        ag=math.atan2(b[1]-a[1],b[0]-a[0]); n=17
        p=[b,(b[0]-n*math.cos(ag-.48),b[1]-n*math.sin(ag-.48)),(b[0]-n*math.cos(ag+.48),b[1]-n*math.sin(ag+.48))]
        d.polygon(p,fill=color)
        svg.append('<polygon points="'+' '.join(f'{x},{y}' for x,y in p)+f'" fill="{color}"/>')
    head(points[-2],points[-1])
    if both: head(points[1],points[0])

text(1100,45,'系统硬件连接与关键输入、输出信号',47,bold=True)
arrow([(1870,440),(1870,135),(190,135),(190,440)],ANALOG)
text(1100,105,'SMA 模拟回环：OUTA → IN（自检 / 校准时连接）',30,ANALOG)
box(840,205,520,140,['DC-DC 电源模块','外部直流输入 6～30 V','5 V 输出 / GND'])
arrow([(840,275),(330,275),(330,440)],POWER)
arrow([(1360,275),(1740,275),(1740,440)],POWER)
text(560,245,'5 V 供电',29,POWER);text(1550,245,'5 V 供电',29,POWER)
box(60,440,430,240,['AD9226 采集模块','IN → 模拟前端 → ADC','12 位 / 25 MSPS','CLK 输入；D / OTR 输出'])
box(790,440,620,240,['EGO1 / XC7A35T FPGA','采集 / 触发 / 存储 / 测量 / FFT','MicroBlaze 控制与波形发生','板载 SYS_CLK：100 MHz'])
box(1670,440,470,240,['AD9767 输出模块','DAC → 滤波 / 放大 → OUTA','14 位 A 通道 / 25 MHz','DA / ACLK / WR1 输入'])
arrow([(490,510),(790,510)],DATA)
text(640,480,'D[11:0]、OTR',28,DATA)
arrow([(790,610),(490,610)],CLOCK)
text(640,580,'CLK：25 MHz',28,CLOCK)
arrow([(1410,510),(1670,510)],DATA)
text(1540,480,'DA[13:0]',29,DATA)
arrow([(1410,610),(1670,610)],CLOCK)
text(1540,580,'ACLK、WR1',29,CLOCK)
text(1100,1188,'EGO1 通过自身电源接口供电；各模块共地；数字接口 LVCMOS33',28)
box(60,915,530,185,['显示连接','VGA → 有源转换器 → HDMI','外接显示器：1024 × 600'])
box(1610,915,530,185,['电脑通信连接','板载 USB-UART → 电脑','921600 bit/s，8N1'])
box(800,1005,600,150,['本地输入与控制','S0～S4：方向 / 确认按键','SW0：模块使能；SW7：控制权'])
arrow([(890,680),(890,825),(325,825),(325,915)],DATA)
text(520,792,'R/G/B[3:0]、HSYNC、VSYNC',27,DATA)
arrow([(1310,680),(1310,825),(1875,825),(1875,915)],DATA,both=True)
text(1690,792,'FPGA TX：T4；RX：N5',27,DATA)
arrow([(1100,1005),(1100,680)],CLOCK)
text(1240,927,'按键 / 拨码输入',27,CLOCK)
text(1100,1230,'方向以箭头为准：蓝色为数字数据 / 视频 / 通信，紫色为时钟 / 控制，棕红为供电，绿色为模拟回环',27)
text(1100,1290,'本图按项目连接与约束文件整理；模块内部电路见对应原理图。',27)
svg.append('</svg>')
(ROOT/'01_硬件总体连接与信号方向.svg').write_text('\n'.join(svg),encoding='utf-8')
im.save(ROOT/'01_硬件总体连接与信号方向.png',dpi=(240,240))
