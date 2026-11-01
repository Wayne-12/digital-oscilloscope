#include "scope_cpu.h"
#include "panel_model.h"
#include "panel_font.h"
#include "panel_knob.h"
#include "panel_knob_scale.h"
/* Bounded mailbox transactions. All backend commands share this owner with
   the PC bridge; PC ownership is selected explicitly with physical SW7. */
#ifdef PANEL_HOST
extern uint32_t panel_host_read(uint32_t a);
extern void panel_host_write(uint32_t a,uint32_t v);
static uint32_t rd(void *p,uint32_t a){(void)p;return panel_host_read(a);}
static void wr(void *p,uint32_t a,uint32_t v){(void)p;panel_host_write(a,v);}
#else
static uint32_t rd(void *p,uint32_t a){(void)p;return *(volatile uint32_t *)(uintptr_t)(SCOPE_IO_BASE+a);}
static void wr(void *p,uint32_t a,uint32_t v){(void)p;*(volatile uint32_t *)(uintptr_t)(SCOPE_IO_BASE+a)=v;}
#endif
static uint8_t tx[64],host_reply[29];
static unsigned tx_count,tx_pos,waiting,error,command_kind,reply_pos,reply_count;
static uint16_t seq=0xe000;static uint32_t sent;
static unsigned test_active,test_commands;
typedef struct {uint16_t pos,length,sequence,crc,wire_crc,flags;uint8_t kind,payload;} wire_frame;
static wire_frame host_frame,backend_frame;
static unsigned owner_pc,handoff,handoff_stop;
static uint32_t host_activity,backend_activity,handoff_started;
static unsigned frame_byte(wire_frame *f,unsigned b){
 unsigned n=f->pos,i;
 if(n==0){if(b==0x55)f->pos=1;return 0;}
 if(n==1){f->pos=b==0xaa?2:b==0x55?1:0;f->crc=0xffff;return 0;}
 if(n==2 && b!=1){f->pos=0;return 0;}
 if(n==3)f->kind=(uint8_t)b;
 if(n==4)f->sequence=(uint16_t)b;
 if(n==5)f->sequence|=(uint16_t)(b<<8);
 if(n==6)f->length=(uint16_t)b;
 if(n==7){f->length|=(uint16_t)(b<<8);if(f->length>1024){f->pos=0;return 0;}}
 if(n==24)f->flags=(uint16_t)b;
 if(n==25)f->flags|=(uint16_t)(b<<8);
 if(n==26)f->payload=(uint8_t)b;
 if(n<26u+f->length){
  f->crc^=(uint16_t)(b<<8);
  for(i=0;i<8;i++)f->crc=(uint16_t)((f->crc<<1)^((f->crc&0x8000)?0x1021:0));
 }else if(n==26u+f->length)f->wire_crc=(uint16_t)b;
 else {f->wire_crc|=(uint16_t)(b<<8);f->pos=0;return f->wire_crc==f->crc?1:2;}
 f->pos++;return 0;
}
static void local_reply(void){
 uint8_t code=6;uint16_t crc;
 if(reply_pos<reply_count || host_frame.kind>=128 || host_frame.flags)return;
 reply_count=(unsigned)scope_request(host_reply,sizeof host_reply,host_frame.kind,host_frame.sequence,&code,1);
 host_reply[3]|=128;host_reply[24]=3;
 crc=scope_crc16(host_reply+2,25);host_reply[27]=(uint8_t)crc;host_reply[28]=(uint8_t)(crc>>8);reply_pos=0;
}
static void host_service(uint32_t now){
 unsigned quota=32;
 if(host_frame.pos && (uint32_t)(now-host_activity)>25)host_frame.pos=0;
 while(quota-- && (rd(0,4)&HOST_RX_VALID)){
  host_activity=now;if(frame_byte(&host_frame,rd(0,8)&255)==1)local_reply();
 }
 quota=32;
 while(reply_pos<reply_count && quota-- && (rd(0,4)&HOST_TX_READY))wr(0,20,host_reply[reply_pos++]);
}
static unsigned panel_bridge_poll(scope_cpu *c){
 uint32_t status=c->read(c->context,SCOPE_STATUS);unsigned moved=0,b;
 if((status&(HOST_RX_VALID|HW_TX_READY))==(HOST_RX_VALID|HW_TX_READY)){
  b=c->read(c->context,SCOPE_HOST_RX)&255;c->write(c->context,SCOPE_HW_TX,b);
  (void)frame_byte(&host_frame,b);host_activity=c->read(c->context,40);c->host_bytes++;moved++;
 }
 if((status&(HW_RX_VALID|HOST_TX_READY))==(HW_RX_VALID|HOST_TX_READY)){
  b=c->read(c->context,SCOPE_HW_RX)&255;c->write(c->context,SCOPE_HOST_TX,b);
  (void)frame_byte(&backend_frame,b);backend_activity=c->read(c->context,40);c->hardware_bytes++;moved++;
 }
 return moved;
}
/* Page formatting must not starve the transparent PC byte bridge. The RTL
   receiver times out a partial request after 4 ms at 25 MHz. */
static scope_cpu *draw_bridge;
static void draw_service(void){
 unsigned quota=32;
 if(!draw_bridge || waiting)return;
 while(quota-- && panel_bridge_poll(draw_bridge)){}
}
static void issue(unsigned kind,const uint8_t *payload,unsigned length,uint32_t now){
 if(test_active)test_commands=1;
 tx_count=(unsigned)scope_request(tx,sizeof tx,(uint8_t)kind,++seq,payload,length);
 tx_pos=0;waiting=1;command_kind=kind;sent=now;
 if(!tx_count){error=1;waiting=0;}
}
static void service(uint32_t now){
 unsigned quota=32;
 while(waiting && tx_pos<tx_count && quota-- && (rd(0,4)&HW_TX_READY))wr(0,12,tx[tx_pos++]);
 quota=32;
 while(waiting && quota-- && (rd(0,4)&HW_RX_VALID)){
  backend_activity=now;
  unsigned complete=frame_byte(&backend_frame,rd(0,16)&255);
  if(complete && backend_frame.kind==(command_kind|128) && backend_frame.sequence==seq){
   if(complete!=1 || backend_frame.flags!=1 || backend_frame.length!=1 || backend_frame.payload)error=3;
   waiting=0;
  }
 }
 if(waiting && (uint32_t)(now-sent)>2000){waiting=0;error=4;}
}
/* Finish the current request and response packet before taking the byte bridge
   away. STOP then cancels acquisition/streaming; foreign replies are drained by
   the framed receiver instead of being mistaken for local ACKs. */
static unsigned owner_step(unsigned pc,uint32_t now,scope_cpu *bridge){
 unsigned quota,b;
 if(!handoff && pc!=owner_pc){handoff=1;handoff_stop=0;handoff_started=now;}
 if(!handoff){if(!owner_pc)host_service(now);return 1;}
 if(!owner_pc)host_service(now);
 if(!handoff_stop){
  if(owner_pc){
   if(host_frame.pos && (uint32_t)(now-host_activity)<=25){
    quota=32;
    while(host_frame.pos && quota-- && (rd(0,4)&(HOST_RX_VALID|HW_TX_READY))==(HOST_RX_VALID|HW_TX_READY)){
     b=rd(0,8)&255;wr(0,12,b);(void)frame_byte(&host_frame,b);host_activity=now;
    }
    return 0;
   }
   host_frame.pos=0;
   if(backend_frame.pos && (uint32_t)(now-handoff_started)<1500){
    quota=32;
    while(backend_frame.pos && quota-- && (rd(0,4)&(HW_RX_VALID|HOST_TX_READY))==(HW_RX_VALID|HOST_TX_READY)){
     b=rd(0,16)&255;wr(0,20,b);(void)frame_byte(&backend_frame,b);backend_activity=now;
    }
    return 0;
   }
   local_reply();
  }
  if(waiting)return 0;
  error=0;issue(0x21,0,0,now);handoff_stop=1;return 0;
 }
 host_service(now);
 if(waiting)return 0;
 if(error){handoff_stop=0;handoff_started=now;backend_frame.pos=0;return 0;}
 quota=32;
 while(quota-- && (rd(0,4)&HW_RX_VALID)){(void)frame_byte(&backend_frame,rd(0,16)&255);backend_activity=now;}
 if((rd(0,4)&HW_RX_VALID) || reply_pos<reply_count || (uint32_t)(now-backend_activity)<20)return 0;
 (void)bridge;owner_pc=pc;handoff=0;error=0;return 1;
}
/* Ten display bits per cell: low byte plus packed two-bit attributes. */
static uint8_t screen_low[1600],screen_high[400];
static unsigned screen_get(unsigned i){return screen_low[i]|((unsigned)(screen_high[i>>2]>>(2*(i&3)))&3)<<8;}
static void screen_set(unsigned i,unsigned value){
 unsigned shift=2*(i&3);
 screen_low[i]=(uint8_t)value;
 screen_high[i>>2]=(uint8_t)((screen_high[i>>2]&~(3u<<shift))|((value>>8&3)<<shift));
}
static panel_navigation navigation;
enum {TEST_NONE,TEST_OK,TEST_DISABLED,TEST_PC,TEST_COMM,TEST_TIMEOUT,
 TEST_DATA,TEST_FREQUENCY,TEST_AMPLITUDE,TEST_SATURATION,TEST_OTR,TEST_ANALYSIS};
static struct {unsigned complete,ready,counts_valid,comm_valid,cause;
 uint32_t saturated,overrange,comm_error;} test_result;
static unsigned finish_selftest(unsigned ready,unsigned pc,unsigned comm,unsigned commands,unsigned fresh){
 unsigned flags=rd(0,64),cause=TEST_OK;
 test_result.complete=1;test_result.ready=ready;
 test_result.counts_valid=fresh && (flags&16);test_result.comm_valid=commands && (!waiting || comm);
 test_result.saturated=rd(0,68);test_result.overrange=rd(0,72);test_result.comm_error=comm;
 if(!ready)cause=TEST_DISABLED;
 else if(pc)cause=TEST_PC;
 else if(comm || !commands)cause=TEST_COMM;
 else if(!fresh)cause=TEST_TIMEOUT;
 else if(flags&32)cause=TEST_ANALYSIS;
 else if((flags&17)!=17)cause=TEST_DATA;
 else if(rd(0,48)<=200)cause=TEST_AMPLITUDE;
 else if(!(flags&2) || rd(0,52)<=950000 || rd(0,52)>=1050000)cause=TEST_FREQUENCY;
 else if(test_result.saturated)cause=TEST_SATURATION;
 else if(test_result.overrange)cause=TEST_OTR;
 test_result.cause=cause;return cause==TEST_OK?1:2;
}
static const char *selftest_reason(void){
 switch(test_result.cause){
  case TEST_OK:return "检测正常";
  case TEST_DISABLED:return "模块未启用";
  case TEST_PC:return "电脑控制中";
  case TEST_COMM:return test_result.comm_error==4?"通信超时":"命令通信错误";
  case TEST_TIMEOUT:return "未收到新采样";
  case TEST_DATA:return "采样数据无效";
  case TEST_FREQUENCY:return "频率不符";
  case TEST_AMPLITUDE:return "回环幅度过低";
  case TEST_SATURATION:return "存在饱和点";
  case TEST_OTR:return "ADC超量程";
  case TEST_ANALYSIS:return "分析异常";
  default:return "绿色通过  红色失败";
 }
}
static uint32_t control_word(const panel_model *m){
 unsigned state=m->selftest==2?3:m->result;
 return m->running|(m->timebase<<2)|(m->gain<<6)|(m->y1<<8)|(m->y2<<17)|
  ((m->page==5 && navigation.focus==3)?1u<<26:0)|(state<<27)|
  ((m->page==0 && navigation.focus==5)?1u<<30:0);
}
static unsigned last_knob_position;
static uint32_t knob_word(unsigned valid,uint32_t mv){
 if(valid)last_knob_position=panel_knob_position(mv);
 return (uint32_t)panel_knob[last_knob_position]|65536u;
}
static void text(unsigned row,unsigned col,const char *s){
 unsigned a=row*64+col;
 while(*s && a<1600 && col<64){
  draw_service();
  unsigned code=(uint8_t)*s++,i;
  if(code<128){screen_set(a++,code);col++;continue;}
  if((code&0xf0)==0xe0 && s[0] && s[1]){code=((code&15)<<12)|(((uint8_t)s[0]&63)<<6)|((uint8_t)s[1]&63);s+=2;}
  else {screen_set(a++,'?');col++;continue;}
  for(i=0;i<PANEL_CJK_COUNT;i++){
   if(!(i&15))draw_service();
   if(panel_cjk[i]==code)break;
  }
  if(i<PANEL_CJK_COUNT && col<63){screen_set(a++,128+i*2);screen_set(a++,129+i*2);col+=2;}
 }
}
static void number(unsigned r,unsigned c,int32_t v){
 char b[12];unsigned i=0,k=0;uint32_t u;
 if(v<0){text(r,c++,"-");u=0u-(uint32_t)v;}else u=(uint32_t)v;
 do{b[i++]=(char)('0'+u%10);u/=10;}while(u && i<10);
 while(i){char ch[2];ch[0]=b[--i];ch[1]=0;text(r,c+k++,ch);}
}
static void frequency(unsigned r,unsigned c,uint32_t hz){
 uint32_t whole=hz/1000,part=hz%1000;char frac[5];unsigned digits=3;
 number(r,c,(int32_t)whole);
 if(!part)return;
 do{c++;whole/=10;}while(whole);
 frac[0]='.';frac[1]=(char)('0'+part/100);frac[2]=(char)('0'+part/10%10);frac[3]=(char)('0'+part%10);frac[4]=0;
 while(digits>0 && frac[digits]=='0')frac[digits--]=0;
 text(r,c,frac);
}
static unsigned numeric_string(char *b,int32_t v){
 char reverse[12];unsigned n=0,k=0;uint32_t u=v<0?0u-(uint32_t)v:(uint32_t)v;
 if(v<0)b[k++]='-';
 do{reverse[n++]=(char)('0'+u%10);u/=10;}while(u);
 while(n)b[k++]=reverse[--n];
 b[k]=0;return k;
}
static void centered_number(unsigned row,unsigned left,unsigned right,int32_t value){
 char b[12];unsigned n=numeric_string(b,value);text(row,left+(right-left-n)/2,b);
}
static void percent_number(unsigned row,unsigned end,uint32_t harmonic,uint32_t base){
 char b[16];unsigned n;uint32_t percent;uint64_t scaled;
 if(!base){text(row,end-2,"--");return;}
 scaled=((uint64_t)harmonic*10000+base/2)/base;
 if(scaled>999999){text(row,end-8,"9999.99+");return;}
 percent=(uint32_t)scaled;
 n=numeric_string(b,(int32_t)(percent/100));
 b[n++]='.';b[n++]=(char)('0'+percent/10%10);b[n++]=(char)('0'+percent%10);b[n]=0;
 text(row,end-n,b);
}
static void reading(unsigned row,int32_t v,unsigned valid,unsigned khz){
 char b[16];unsigned n;
 if(!valid){text(row,56,"--");return;}
 if(!khz)n=numeric_string(b,v);
 else {
  uint32_t part=(uint32_t)v%1000;n=numeric_string(b,(int32_t)((uint32_t)v/1000));
  if(part){
   b[n++]='.';b[n++]=(char)('0'+part/100);b[n++]=(char)('0'+part/10%10);b[n++]=(char)('0'+part%10);
   while(b[n-1]=='0')n--;
   b[n]=0;
  }
 }
 text(row,58-n,b);
}
static const panel_model *draw_model;
static void item(unsigned row,unsigned field,const char *label,int32_t value,const char *unit){
 unsigned selected=navigation.focus>=3 && panel_field_index(draw_model,navigation.focus-3)==field;
 text(row,3,selected?(navigation.editing?"*":">"):" ");text(row,5,label);
 if(value!=INT32_MIN)number(row,draw_model->page==2?22:25,value);
 text(row,draw_model->page==2?32:39,unit);
}
static void scale_item(unsigned row,unsigned field,const char *label,unsigned value,const char *unit){
 text(row,3,navigation.focus==field+3?(navigation.editing?"*":">"):" ");
 text(row,5,label);number(row,22,(int32_t)value);text(row,32,unit);
}
static const char *modes[]={"自动","正常","单次"};
static const char *kinds[]={"上升沿","下降沿","窗口进入","窗口离开","正脉宽","负脉宽","欠幅","过幅","超量程"};
static const char *waves[]={"正弦波","方波","三角波","直流"};
static const char *pages[]={"波形","触发","信号源","光标","频谱","自检"};
static const unsigned ns[]={640,2560,10240,40960,65536},mvdiv[]={2240,560,280,140};
static void draw(panel_model *active,unsigned pc){
 panel_model *m=navigation.editing?&navigation.draft:active;
 draw_model=m;
 unsigned i;uint32_t flags=rd(0,64),vpp=rd(0,48),hz=rd(0,52),fund=rd(0,76),amp=rd(0,80);
 for(i=0;i<1600;i++){if(!(i&31))draw_service();screen_set(i,' ');}
 for(i=0;i<6;i++){
  unsigned c=2+i*10;text(1,c,(navigation.focus==0 && navigation.target_page==i)?">":" ");
  text(1,c+1,pages[i]);
 }
 text(3,3,"采集");
 text(3,10,navigation.focus==1?">":" ");text(3,12,active->single?"取消单次":active->running?"暂停":"运行");
 text(3,22,navigation.focus==2?">":" ");text(3,24,"单次采集");text(3,45,"状态");
 text(3,51,handoff?"等待":!(rd(0,32)&4)?"未启用":pc?"电脑控制":error?"命令失败":active->single?"等待触发":active->running?"运行中":"已暂停");
 if(m->page==0 || m->page==3 || m->page==4){
  text(5,2,m->page==4?"频谱":"时基");
  if(m->page!=4){number(5,7,(int32_t)ns[m->timebase]);text(5,13,"ns/div");number(5,23,(int32_t)mvdiv[m->gain]);text(5,28,"mV/div");}
  text(6,44,"频率");reading(6,(int32_t)hz,flags&2,1);text(6,59,"kHz");
  text(9,44,"峰峰值");reading(9,(int32_t)vpp,flags&1,0);text(9,59,"mV");
  text(12,44,"有效值");reading(12,(int32_t)rd(0,56),flags&1,0);text(12,59,"mV");
  text(15,44,"平均值");reading(15,(int32_t)rd(0,60),flags&1,0);text(15,59,"mV");
  if(m->page==0){
   scale_item(19,0,"时基",ns[m->timebase],"ns/div");
   scale_item(21,1,"垂直刻度",mvdiv[m->gain],"mV/div");
   text(20,45,navigation.focus==5?">":" ");text(20,47,"自动校准量程");
  }else if(m->page==3){
   int dx=(int)m->x2-(int)m->x1,dy=(int)m->y1-(int)m->y2;
   int dt=dx*(int)(ns[m->timebase]/64),dv=dy*(int)mvdiv[m->gain]/40;
   for(i=0;i<4;i++){
    unsigned c=i==0?3:i==1?17:i==2?33:47;
    int value=i<2?(int)(i?m->x2:m->x1)*(int)(ns[m->timebase]/64):
      (140-(int)(i==2?m->y1:m->y2))*(int)mvdiv[m->gain]/40;
    text(19,c,navigation.focus==3+i?(navigation.editing?"*":">"):" ");
    text(19,c+1,i==0?"时间一":i==1?"时间二":i==2?"电压一":"电压二");
    number(19,c+8,value);
   }
   text(21,4,"时间差");centered_number(21,10,25,dt);text(21,25,"ns");
   text(21,34,"电压差");centered_number(21,40,55,dv);text(21,55,"mV");
  }else{
   text(19,4,"基波 H1");if(rd(0,116)&0x100)frequency(19,14,fund);else text(19,14,"--");text(19,24,"kHz");
   for(i=0;i<4;i++){
    unsigned a=i==0?84:i==1?88:i==2?92:112;
    text(21,4+i*15,"H");number(21,5+i*15,(int32_t)i+2);
    if(amp && (rd(0,116)&0x100) && fund>=97656 && (uint64_t)fund*(i+2)<12475586)
     percent_number(21,15+i*15,rd(0,a),amp);
    else text(21,13+i*15,"--");
   }
   text(19,35,"谐波占比");text(19,45,"(%)");
  }
 }else if(m->page==1){
  item(5,0,"采集模式",INT32_MIN,"");text(5,25,modes[m->mode]);
  item(7,1,"触发类型",INT32_MIN,"");text(7,25,kinds[m->kind]);
  item(9,2,"触发电平",m->level,"码");item(11,3,"迟滞",(int)m->hysteresis,"码");
  item(13,10,"预触发",(int)m->pre,"%");
  if(m->kind==2 || m->kind==3){item(15,4,"窗口下限",m->low,"码");item(17,5,"窗口上限",m->high,"码");}
  else if(m->kind==4 || m->kind==5){item(15,6,"最小脉宽",(int)m->width_min,"采样周期");item(17,7,"最大脉宽",(int)m->width_max,"采样周期");}
  else if(m->kind==6 || m->kind==7){item(15,8,"幅度门限",(int)m->limit,"码");item(17,9,"观测长度",(int)m->observation,"点");}
 }else if(m->page==2){
  item(5,0,"输出开关",INT32_MIN,"");text(5,22,m->enable?"开启":"关闭");
  item(7,1,"波形",INT32_MIN,"");text(7,22,waves[m->wave]);item(9,2,"频率",INT32_MIN,"kHz");frequency(9,22,m->hz);
  item(11,3,"相位",(int)m->phase,"度");item(13,4,"幅度",(int)m->amplitude,"峰值码");
  item(15,5,"偏置",m->offset,"码");
  text(6,48,"幅度旋钮");
  text(18,44,"回环峰峰值");
  if(flags&1){char b[12];unsigned n=numeric_string(b,(int32_t)vpp);text(18,59-n,b);}
  else text(18,57,"--");
  // Keep both unit cells inside the compact area's normal-font suppression.
  text(18,60,"mV");
 }else{
  text(5,3,"回环自检");text(7,3,"DAC OUTA 接 ADC IN");
  text(9,5,navigation.focus==3?">":" ");text(9,8,"开始自检");
  text(9,25,"检查回环信号");
  text(11,m->selftest==2 || !m->result?9:8,m->selftest==2?"检测中":m->result==1?"自检通过":m->result==2?"自检失败":"未检测");
  text(11,25,m->selftest==2?"等待有效采样":selftest_reason());
  text(13,3,"模块状态");text(13,21,test_result.complete?(test_result.ready?"已启用":"未启用"):"\x7f");
  text(15,3,"饱和点数");text(17,3,"超量程点数");text(19,3,"错误代码");
  if(test_result.counts_valid){number(15,21,(int32_t)test_result.saturated);number(17,21,(int32_t)test_result.overrange);}
  else {text(15,21,"\x7f");text(17,21,"\x7f");}
  if(test_result.comm_valid)number(19,21,(int32_t)test_result.comm_error);else text(19,21,"\x7f");
  text(13,29,"模块启用状态");text(15,29,"是否有采样点触及饱和阈值");
  text(17,29,"是否检测到 ADC 超量程标志");text(19,29,"是否有命令通信错误");
 }
 if(m->page==0 || m->page==3 || m->page==4)text(17,45,(flags&8)?"电压校正已应用":"标称电压");
 if(m->page!=5){
  if(rd(0,68))text(22,26,"饱和");
  if(rd(0,72))text(22,36,"超量程");
  if(flags&32)text(22,48,"分析异常");
 }
 if(m->page==4)text(23,2,"H2-H5:二至五次谐波相对于H1的比例");
 text(23,navigation.editing?34:38,navigation.editing?"左右微调  上下粗调  中心确认":"方向键移动预选  中心确认");
 for(i=0;i<1600;i++){
  if(!(i&31))draw_service();
  if(screen_get(i)=='>' || screen_get(i)=='*'){
  unsigned end=(i/64)*64+62,j;
  if(i/64==1)end=i+9;
  else if(i/64==3)end=i+12;
  else if(m->page==0 && (i/64==19 || i/64==21) && i%64<40)end=(i/64)*64+40;
  else if(m->page==3 && i/64==19)end=i+14;
  else if(m->page==2 && i/64>=5 && i/64<=15)end=(i/64)*64+40;
  else if(m->page==5 && i/64==9)end=(i/64)*64+19;
  for(j=i;j<end && j<1600;j++)screen_set(j,screen_get(j)|512);
  }
 }
}
int main(void){
 panel_model m,saved;scope_cpu bridge={0,rd,wr,0,0,0};
 uint32_t previous=0,last_draw=0,last_frame=0,test_started=0,revision=0;
 unsigned phase=0,render=1600,render_pending=0,keys_ready=0;
 panel_init(&m);
 if(rd(0,0)!=SCOPE_IO_ID)for(;;){}
 for(;;){
  uint32_t now=rd(0,40),pins=rd(0,28),edges=pins&~previous,status=rd(0,32),frame=rd(0,44);
  unsigned pc=!!(pins&(1u<<12)),i,was_handoff=handoff,ready;
  service(now);
  ready=owner_step(pc,now,&bridge);
  if(handoff || was_handoff){
   keys_ready=0;navigation.editing=0;m.single=0;
   if(ready){m.dirty=1;phase=0;revision=m.revision;navigation.target_page=m.page;}
  }
  if(!(pins&31) && ready)keys_ready=1;
  if(!pc && ready && keys_ready && m.selftest!=2){
   /* EGO1 layout from the board manual: S4 up, S1 down,
      S3 left, S0 right, S2 center. */
   static const unsigned mapping[5]={KEY_RIGHT,KEY_DOWN,KEY_OK,KEY_LEFT,KEY_UP};
   for(i=0;i<5;i++)if(edges&(1u<<i)){
    if(mapping[i]==KEY_OK && error){error=0;m.dirty=1;m.revision++;}
    panel_move(&m,&navigation,mapping[i]);
   }
  }
  previous=pins;
  if(m.selftest==3){panel_autoscale(&m,rd(0,48),rd(0,52));m.selftest=0;}
  if(m.selftest==1 && !waiting){
   test_result.complete=test_result.counts_valid=test_result.comm_valid=test_result.cause=0;
   test_commands=0;test_active=0;
   if(!(status&4) || pc){m.selftest=0;m.result=finish_selftest(!!(status&4),pc,0,0,0);}
   else {
   saved=m;m.selftest=2;m.result=0;m.running=1;m.single=0;m.mode=0;m.kind=0;m.level=0;
   m.wave=0;m.enable=1;m.hz=1000000;m.phase=0;m.amplitude=4096;m.offset=0;
   m.dirty=1;m.revision++;test_started=now;last_frame=frame;error=0;test_active=1;
   }
  }
  if(m.selftest==2 && ((phase==9 && frame!=last_frame && !waiting) || error || pc || !(status&4) || (uint32_t)(now-test_started)>5000)){
   unsigned result=finish_selftest(!!(status&4),pc,error,test_commands,phase==9 && frame!=last_frame);
   test_active=0;m=saved;m.selftest=0;m.result=result;m.dirty=1;m.revision++;error=0;
  }
  /* Text and display settings use a separate acknowledged page bank. */
  if(render==1600 && !render_pending && !rd(0,100) && (uint32_t)(now-last_draw)>=100){
   draw_bridge=pc && owner_pc && ready && !waiting?&bridge:0;
   draw(&m,pc);draw_bridge=0;render=0;last_draw=now;
  }
  if(render<1600 && !rd(0,100)){
   for(i=0;i<16 && render<1600;i++,render++)wr(0,96,(render<<10)|screen_get(render));
   if(render==1600){
    wr(0,36,control_word(&m));
    wr(0,104,m.x1|(m.x2<<16));wr(0,108,m.page);
    wr(0,136,knob_word(rd(0,64)&1,rd(0,48)));
    wr(0,100,1);render_pending=1;
   }
  }
  if(render_pending && !rd(0,100))render_pending=0;
  if(!ready || waiting)continue;
  if(pc){
   (void)panel_bridge_poll(&bridge);continue;
  }
  if(!(status&4)){m.dirty=1;continue;}
  if(error)continue;
  if(m.dirty){m.dirty=0;phase=0;revision=m.revision;}
  if(revision!=m.revision){phase=0;revision=m.revision;}
  if(phase==0){issue(0x21,0,0,now);phase=1;continue;}
  if(phase<8 && (status&2))continue;
  if(phase==1){uint8_t b[8]={0};b[0]=(uint8_t)(m.single?2:m.mode);panel_put32(b+4,2500000);issue(0x12,b,8,now);phase=2;}
  else if(phase==2){uint8_t b[24];panel_trigger(&m,b);issue(0x11,b,24,now);phase=3;}
  else if(phase==3){uint8_t b[8];scope_record_payload(b,m.pre*10000);issue(0x10,b,8,now);phase=4;}
  else if(phase==4){uint8_t b[16];scope_dds_payload(b,m.wave,0,m.hz,(uint32_t)(((uint64_t)m.phase<<32)/360),(uint16_t)m.amplitude,m.offset);issue(0x40,b,16,now);phase=5;}
  else if(phase==5){uint8_t standard=0;issue(0x1a,&standard,1,now);phase=6;}
  else if(phase==6){uint8_t b[16];scope_dds_payload(b,m.wave,m.enable,m.hz,(uint32_t)(((uint64_t)m.phase<<32)/360),(uint16_t)m.amplitude,m.offset);issue(0x40,b,16,now);phase=7;}
  else if(phase==7){
   if(m.running || m.single){issue(m.single?0x20:0x22,0,0,now);last_frame=frame;phase=9;}
   else phase=8;
  }else if(phase==9 && (status&1) && frame!=last_frame){
   if(m.single || m.mode==2){m.single=0;m.running=0;issue(0x21,0,0,now);phase=8;}
   else if((uint32_t)(now-last_draw)<20){last_frame=frame;issue(0x23,0,0,now);}
  }
 }
}
