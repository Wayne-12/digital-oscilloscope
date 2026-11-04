#define _CRT_SECURE_NO_WARNINGS
#include <stdio.h>
#include <stdlib.h>
#include <assert.h>
#undef assert
#define assert(c) do{if(!(c)){fprintf(stderr,"CHECK FAILED line %d: %s\n",__LINE__,#c);exit(1);}}while(0)
#define PANEL_HOST
#define main panel_firmware_main
#include "panel_main.c"
#undef main
static uint32_t regs[64];
static uint8_t reply[128],requests[64];static unsigned reply_size,reply_pos,request_size;
uint32_t panel_host_read(uint32_t a){
 if(a==4)return regs[1]|(reply_pos<reply_size?HW_RX_VALID:0);
 if(a==16 && reply_pos<reply_size)return reply[reply_pos++];
 return regs[a/4];
}
void panel_host_write(uint32_t a,uint32_t v){
 if(a==12 && request_size<sizeof requests)requests[request_size++]=(uint8_t)v;
 else regs[a/4]=v;
}
static void ack(unsigned corrupt){
 uint16_t crc;unsigned i;
 for(i=0;i<28;i++)reply[i]=requests[i];
 reply[3]|=0x80;reply[6]=1;reply[24]=1;reply[26]=0;
 crc=scope_crc16(reply+2,25);reply[27]=(uint8_t)crc;reply[28]=(uint8_t)(crc>>8);
 if(corrupt)reply[27]^=1;
 reply_pos=0;reply_size=29;
}
static void command_test(void){
 regs[1]=0;error=0;reply_pos=reply_size=request_size=0;
 issue(0x21,0,0,100);service(101);assert(waiting && tx_pos==0);
 regs[1]=HW_TX_READY;service(102);assert(waiting && request_size==28 && scope_request_valid(requests,28));
 ack(0);service(103);assert(!waiting && !error);
 request_size=0;issue(0x22,0,0,104);service(105);ack(1);service(106);assert(!waiting && error==3);
 error=0;request_size=0;reply_pos=reply_size=0;issue(0x21,0,0,107);service(2200);assert(!waiting && error==4);
 error=0;regs[1]=0;
 puts("COMMAND_TEST_PASS");
}
static void navigation_test(void){
 panel_model m;panel_navigation n={0};unsigned i,j;
 panel_init(&m);
 panel_move(&m,&n,KEY_RIGHT);assert(m.page==0 && n.target_page==1);
 panel_move(&m,&n,KEY_OK);assert(m.page==1);
 panel_move(&m,&n,KEY_DOWN);assert(n.focus==1);
 panel_move(&m,&n,KEY_RIGHT);assert(n.focus==2);
 panel_move(&m,&n,KEY_LEFT);assert(n.focus==1);
 panel_move(&m,&n,KEY_DOWN);assert(n.focus==3);
 panel_move(&m,&n,KEY_DOWN);panel_move(&m,&n,KEY_DOWN);
 assert(n.focus==5);panel_move(&m,&n,KEY_OK);assert(n.editing);
 panel_move(&m,&n,KEY_RIGHT);assert(m.level==0 && n.draft.level==1);
 m.running=0; /* A single capture can finish while an editor is open. */
 panel_move(&m,&n,KEY_OK);assert(!n.editing && m.level==1 && m.dirty);
 assert(!m.running);
 for(i=0;i<100;i++)panel_move(&m,&n,KEY_UP);assert(n.focus==0);
 n.focus=1;panel_move(&m,&n,KEY_OK);assert(m.running==1);
 n.focus=2;panel_move(&m,&n,KEY_OK);assert(m.single && !m.running);
 n.focus=1;panel_move(&m,&n,KEY_OK);assert(!m.single && !m.running);
 for(i=0;i<6;i++)for(j=0;j<panel_fields(i);j++){
  unsigned k;m.page=i;m.field=j;
  for(k=0;k<1000;k++)panel_key(&m,4,1,1);
  assert(m.low+(int)m.hysteresis<m.high-(int)m.hysteresis);
  assert(m.width_min && m.width_max>=m.width_min && m.pre<=100 && m.hz<=12500000);
  for(k=0;k<1000;k++)panel_key(&m,4,-1,1);
  assert(m.low+(int)m.hysteresis<m.high-(int)m.hysteresis);
  assert(m.width_min && m.width_max>=m.width_min && m.pre<=100 && m.x1<=639 && m.y2<=279);
 }
 panel_init(&m);m.page=1;m.kind=8;{uint8_t b[24];panel_trigger(&m,b);assert(b[0]==8 && panel_get32(b+20)==256);}
 panel_init(&m);m.page=1;n.focus=4;n.editing=0;
 panel_move(&m,&n,KEY_OK);assert(n.editing && n.draft.kind==0);
 panel_move(&m,&n,KEY_LEFT);assert(n.draft.kind==8 && m.kind==0);
 panel_move(&m,&n,KEY_OK);assert(!n.editing && m.kind==8);
 panel_move(&m,&n,KEY_OK);
 panel_move(&m,&n,KEY_RIGHT);assert(n.draft.kind==0 && m.kind==8);
 for(i=0;i<9;i++){assert(n.draft.kind==i);panel_move(&m,&n,KEY_RIGHT);}
 assert(n.draft.kind==0);
 for(i=0;i<9;i++){panel_move(&m,&n,KEY_LEFT);assert(n.draft.kind==8-i);}
 panel_move(&m,&n,KEY_OK);assert(!n.editing && m.kind==0);
 puts("TRIGGER_CYCLE_TEST_PASS");
 puts("NAVIGATION_TEST_PASS");
 panel_init(&m);n.focus=3;n.editing=0;
 panel_move(&m,&n,KEY_DOWN);assert(n.focus==4);
 panel_move(&m,&n,KEY_RIGHT);assert(n.focus==5);
 panel_move(&m,&n,KEY_LEFT);assert(n.focus==3);
 n.focus=5;panel_move(&m,&n,KEY_OK);assert(m.selftest==3);
}
static void selftest_report_test(void){
 panel_model m;panel_init(&m);m.page=5;
 regs[64/4]=31;regs[52/4]=1000000;regs[48/4]=840;regs[68/4]=regs[72/4]=0;
 m.result=finish_selftest(0,0,0,0,0);assert(m.result==2 && test_result.cause==TEST_DISABLED);
 assert(test_result.complete && !test_result.ready && !test_result.counts_valid && !test_result.comm_valid);
 draw(&m,0);assert(screen_get(15*64+21)==127 && screen_get(17*64+21)==127 && screen_get(19*64+21)==127);
 finish_selftest(1,0,0,1,0);assert(test_result.cause==TEST_TIMEOUT && !test_result.counts_valid && test_result.comm_valid);
 finish_selftest(1,0,4,1,0);assert(test_result.cause==TEST_COMM && test_result.comm_error==4);
 m.result=finish_selftest(1,0,0,1,1);assert(m.result==1 && test_result.cause==TEST_OK && test_result.counts_valid);
 regs[68/4]=13;regs[72/4]=2;draw(&m,0);
 assert(screen_get(15*64+21)=='0' && screen_get(17*64+21)=='0');
 finish_selftest(1,0,0,1,1);assert(test_result.cause==TEST_SATURATION && test_result.saturated==13);
 regs[68/4]=0;finish_selftest(1,0,0,1,1);assert(test_result.cause==TEST_OTR);
 regs[72/4]=0;regs[52/4]=700000;finish_selftest(1,0,0,1,1);assert(test_result.cause==TEST_FREQUENCY);
 regs[48/4]=40;finish_selftest(1,0,0,1,1);assert(test_result.cause==TEST_AMPLITUDE);
 regs[64/4]=3;finish_selftest(1,0,0,1,1);assert(test_result.cause==TEST_DATA && !test_result.counts_valid);
 regs[64/4]=63;finish_selftest(1,0,0,1,1);assert(test_result.cause==TEST_ANALYSIS);
 finish_selftest(1,1,0,1,0);assert(test_result.cause==TEST_PC);
 waiting=1;finish_selftest(1,1,0,1,0);assert(!test_result.comm_valid);waiting=0;
 memset(&test_result,0,sizeof test_result);draw(&m,0);assert(screen_get(13*64+21)==127);
 memset(regs,0,sizeof regs);puts("SELFTEST_DIAGNOSIS_PASS");
}
static unsigned bridge_tx,bridge_rx;
static uint32_t bridge_read(void *context,uint32_t a){
 (void)context;
 if(a==SCOPE_STATUS)return HOST_RX_VALID|HW_TX_READY|HW_RX_VALID|HOST_TX_READY;
 return a==SCOPE_HOST_RX?0xa5:0x5a;
}
static void bridge_write(void *context,uint32_t a,uint32_t v){
 (void)context;
 if(a==SCOPE_HW_TX){assert(v==0xa5);bridge_tx++;}
 else if(a==SCOPE_HOST_TX){assert(v==0x5a);bridge_rx++;}
}
static void draw_bridge_test(void){
 panel_model m;scope_cpu bridge={0,bridge_read,bridge_write,0,0,0};
 unsigned page;
 panel_init(&m);waiting=0;draw_bridge=&bridge;
 for(page=0;page<6;page++){
  unsigned previous_tx=bridge_tx; m.page=page;draw(&m,1);
  assert(bridge_tx>previous_tx && bridge_tx==bridge_rx);
 }
 waiting=1;page=bridge_tx;draw(&m,1);assert(bridge_tx==page);
 waiting=0;draw_bridge=0;draw(&m,0);assert(bridge_tx==page);
 puts("DRAW_BRIDGE_FAIRNESS_TEST_PASS");
}
static void handoff_test(void){
 unsigned i;wire_frame parsed={0};uint8_t packet[1052],data[1024];
 uint16_t crc;
 for(i=0;i<1024;i++)data[i]=(uint8_t)i;
 assert(scope_request(packet,sizeof packet,0x30,99,data,1024)==1052);
 packet[3]|=128;packet[24]=1;crc=scope_crc16(packet+2,1048);
 packet[1050]=(uint8_t)crc;packet[1051]=(uint8_t)(crc>>8);
 for(i=0;i<1051;i++)assert(frame_byte(&parsed,packet[i])==0);
 assert(frame_byte(&parsed,packet[1051])==1 && parsed.sequence==99 && parsed.length==1024);
 for(i=0;i<1600;i++)screen_set(i,(i*17)&1023);
 for(i=0;i<1600;i++)assert(screen_get(i)==((i*17)&1023));
 request_size=reply_size=reply_pos=0;regs[1]=HW_TX_READY|HOST_TX_READY;
 host_frame.pos=12;host_frame.flags=0;host_frame.kind=0x30;host_frame.sequence=321;
 backend_frame.pos=0;host_activity=100;backend_activity=0;
 owner_pc=1;handoff=waiting=error=tx_count=0;
 assert(!owner_step(0,101,0) && !waiting && tx_count==0);
 assert(!owner_step(0,127,0) && waiting && command_kind==0x21);
 service(128);ack(0);service(129);assert(!waiting && !error);
 reply_pos=reply_count;
 assert(owner_step(0,155,0) && !owner_pc && !handoff && !error);
 host_frame.kind=1;host_frame.sequence=77;host_frame.flags=0;local_reply();
 memset(&parsed,0,sizeof parsed);
 for(i=0;i<29;i++)(void)frame_byte(&parsed,host_reply[i]);
 assert(parsed.kind==0x81 && parsed.sequence==77 && parsed.flags==3 && parsed.payload==6);
 reply_pos=reply_count;request_size=reply_size=reply_pos=0;regs[1]=0;
 memset(&host_frame,0,sizeof host_frame);memset(&backend_frame,0,sizeof backend_frame);
 puts("HANDOFF_PACKET_DRAIN_AND_PACKED_SCREEN_PASS");
}
int main(void){
 handoff_test();
 draw_bridge_test();
 panel_model m;unsigned p,i;FILE *f;
 selftest_report_test();
 panel_init(&m);m.page=2;m.field=1;m.wave=3;
 for(i=1;i<=8;i++){panel_key(&m,4,1,0);assert(m.wave==((3u-i)&3u));}
 for(i=1;i<=8;i++){panel_key(&m,4,-1,0);assert(m.wave==((3u+i)&3u));}
 {panel_navigation wave_nav={0};wave_nav.focus=4;
  panel_move(&m,&wave_nav,KEY_OK);assert(wave_nav.editing);
  panel_move(&m,&wave_nav,KEY_LEFT);assert(m.wave==3 && wave_nav.draft.wave==0);
  panel_move(&m,&wave_nav,KEY_RIGHT);assert(wave_nav.draft.wave==3);
  panel_move(&m,&wave_nav,KEY_RIGHT);assert(wave_nav.draft.wave==2);
  panel_move(&m,&wave_nav,KEY_OK);assert(!wave_nav.editing && m.wave==2);
 }
 puts("WAVE_CYCLE_TEST_PASS");
 panel_init(&m);m.page=1;m.field=2;panel_key(&m,4,1,0);assert(m.level==1);
 panel_key(&m,4,-1,0);assert(m.level==0);panel_key(&m,4,1,1);assert(m.level==100);
 m.field=4;panel_key(&m,4,1,0);assert(m.low==-99);
 m.field=5;panel_key(&m,4,1,0);assert(m.high==101);
 m.field=7;panel_key(&m,4,1,0);assert(m.width_max==25001);
 m.field=8;panel_key(&m,4,1,0);assert(m.limit==101);
 m.field=9;panel_key(&m,4,1,0);assert(m.observation==257);
 panel_init(&m);m.page=2;m.field=4;panel_key(&m,4,1,0);assert(m.amplitude==4097);
 panel_key(&m,4,-1,0);assert(m.amplitude==4096);
 m.field=5;panel_key(&m,4,-1,0);assert(m.offset==-1);
 m.field=2;panel_key(&m,4,1,0);assert(m.hz==1001000);
 panel_init(&m);m.page=5;navigation.focus=3;
 assert(((control_word(&m)>>26)&7)==1);
 m.result=1;assert(((control_word(&m)>>27)&3)==1);
 m.result=2;assert(((control_word(&m)>>27)&3)==2);
 m.selftest=2;assert(((control_word(&m)>>27)&3)==3);
 assert(((control_word(&m)>>17)&511)==m.y2);
 puts("FINE_STEP_SELFTEST_STATE_PASS");
 assert(panel_knob_position(0)==0 && panel_knob_position(108)==0);
 assert(panel_knob_position(2212)==360 && panel_knob_position(UINT32_MAX)==360);
 assert(panel_knob_position(1160)==180);
 assert(sizeof panel_knob/sizeof panel_knob[0]==PANEL_KNOB_STEPS+1);
 for(i=109;i<=2212;i++){
  unsigned before=panel_knob_position(i-1),after=panel_knob_position(i);
  assert(after>=before && after<=before+1 && after<=PANEL_KNOB_STEPS);
 }
 assert(panel_knob[0]==(uint16_t)0x2dd3 && panel_knob[180]==(uint16_t)0xc000 && panel_knob[360]==(uint16_t)0x2d2d);
 assert(knob_word(0,2212)==((uint32_t)panel_knob[0]|65536u));
 assert(knob_word(1,1160)==((uint32_t)panel_knob[180]|65536u));
 assert(knob_word(0,108)==((uint32_t)panel_knob[180]|65536u));
 assert(knob_word(1,2212)==((uint32_t)panel_knob[360]|65536u));
 assert(knob_word(0,0)==((uint32_t)panel_knob[360]|65536u));
 last_knob_position=0;
 puts("KNOB_ALWAYS_VISIBLE_TEST_PASS");
 puts("KNOB_CALIBRATION_TEST_PASS");
 navigation_test();command_test();panel_init(&m);regs[32/4]=5;regs[64/4]=31;regs[48/4]=840;regs[52/4]=1000000;
 regs[56/4]=297;regs[60/4]=0;regs[76/4]=1000977;regs[80/4]=11272192;
 regs[84/4]=101450;regs[88/4]=33816;regs[92/4]=11272;regs[112/4]=5636;regs[116/4]=0x101;
 for(p=0;p<6;p++){
  char path[64];m.page=p;navigation.focus=0;navigation.target_page=p;navigation.editing=0;
  if(p==1)m.kind=2;
  draw(&m,0);snprintf(path,sizeof path,"output/page_%u.mem",p);f=fopen(path,"w");assert(f);
  for(i=0;i<1600;i++)fprintf(f,"%03x\n",screen_get(i));fclose(f);
 }
 for(p=1;p<=2;p++){
  m.page=5;m.result=finish_selftest(p==1,0,0,p==1,p==1);navigation.focus=3;draw(&m,0);
  f=fopen(p==1?"output/page_5_pass.mem":"output/page_5_fail.mem","w");assert(f);
  for(i=0;i<1600;i++)fprintf(f,"%03x\n",screen_get(i));fclose(f);
 }
 assert(screen_get(15*64+21)==127 && screen_get(15*64+29)>=128);
 assert(screen_get(17*64+21)==127 && screen_get(19*64+21)==127);
 m.page=0;draw(&m,0);
 assert(screen_get(6*64+54)=='1' && screen_get(6*64+57)=='0' && screen_get(6*64+58)==' ' && screen_get(6*64+59)=='k');
 regs[60/4]=(uint32_t)-100;draw(&m,0);
 assert(screen_get(15*64+54)=='-' && screen_get(15*64+57)=='0' && screen_get(15*64+58)==' ' && screen_get(15*64+59)=='m');
 m.page=2;navigation.focus=5;draw(&m,0);
 assert((screen_get(9*64+22)&511)=='1' && (screen_get(9*64+32)&511)=='k');
 assert((screen_get(9*64+39)&512) && !(screen_get(9*64+40)&512));
 assert(screen_get(18*64+56)=='8' && screen_get(18*64+60)=='m' && screen_get(18*64+61)=='V');
 assert(screen_get(18*64+62)==' ' && screen_get(18*64+63)==' ');
 assert(screen_get(18*64+44)>=128 && screen_get(18*64+53)>=128);
 m.page=3;m.x1=0;m.x2=639;m.timebase=4;navigation.focus=3;draw(&m,0);
 assert((screen_get(19*64+25)&511)=='6' && (screen_get(19*64+30)&511)=='6');
 assert((screen_get(19*64+16)&512) && !(screen_get(19*64+17)&512));
 assert(screen_get(21*64+25)=='n' && screen_get(21*64+55)=='m');
 assert(screen_get(21*64+14)=='6' && screen_get(21*64+19)=='6' && screen_get(21*64+24)==' ');
 m.x1=639;m.x2=0;draw(&m,0);
 assert(screen_get(21*64+14)=='-' && screen_get(21*64+20)=='6' && screen_get(21*64+24)==' ');
 m.page=4;navigation.focus=0;draw(&m,0);
 assert(screen_get(21*64+4)=='H' && screen_get(21*64+5)=='2' && screen_get(21*64+11)=='0' && screen_get(21*64+12)=='.' && screen_get(21*64+13)=='9' && screen_get(21*64+14)=='0');
 assert(screen_get(21*64+19)=='H' && screen_get(21*64+20)=='3' && screen_get(21*64+28)=='3' && screen_get(21*64+29)=='0');
 assert(screen_get(19*64+9)=='H' && screen_get(19*64+10)=='1' && screen_get(19*64+46)=='%');
 assert(screen_get(19*64+11)==' ' && screen_get(19*64+12)==' ' && screen_get(19*64+13)==' ' && screen_get(19*64+14)=='1');
 assert(screen_get(21*64+34)=='H' && screen_get(21*64+49)=='H');
 assert(screen_get(23*64+2)=='H' && screen_get(23*64+3)=='2' && screen_get(23*64+5)=='H' && screen_get(23*64+6)=='5');
 assert(screen_get(23*64+38)>=128 && screen_get(23*64+37)==' ' && screen_get(23*64+62)==' ' && screen_get(23*64+63)==' ');
 percent_number(0,10,1,1);
 assert(screen_get(4)=='1' && screen_get(7)=='.' && screen_get(8)=='0' && screen_get(9)=='0');
 percent_number(0,10,0,1);assert(screen_get(6)=='0' && screen_get(7)=='.' && screen_get(9)=='0');
 percent_number(0,10,1,0);assert(screen_get(8)=='-' && screen_get(9)=='-');
 percent_number(0,10,UINT32_MAX,1);assert(screen_get(9)=='+');
 puts("PANEL_C_TEST_PASS");return 0;
}

