#include "scope_cpu.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
typedef struct { uint32_t status; uint8_t a,b,x,y; unsigned reads,writes; } mock;
static uint32_t rd(void *ctx,uint32_t reg) {
 mock *m=ctx;
 if(reg==SCOPE_STATUS) return m->status;
 m->reads++;
 if(reg==SCOPE_HOST_RX) return m->a;
 assert(reg==SCOPE_HW_RX); return m->b;
}
static void wr(void *ctx,uint32_t reg,uint32_t v) {
 mock *m=ctx; m->writes++;
 if(reg==SCOPE_HW_TX) m->x=(uint8_t)v;
 else if(reg==SCOPE_HOST_TX) m->y=(uint8_t)v;
 else assert(reg==SCOPE_HEARTBEAT);
}
int main(void) {
 uint8_t p[1052],payload[1024],dds[16],record[8]; size_t n; unsigned s,i;
 mock m={0}; scope_cpu c={&m,rd,wr,0,0,0};
 assert(scope_crc16((const uint8_t *)"123456789",9)==0x29b1);
 assert(scope_crc16(0,0)==0xffff);
 for(i=0;i<1024;i++) payload[i]=(uint8_t)i;
 for(i=0;i<=1024;i++) {
  n=scope_request(p,sizeof p,1,65535,payload,i); assert(n==i+28);
  assert(scope_request_valid(p,n)); p[n-1]^=1; assert(!scope_request_valid(p,n));
 }
 assert(!scope_request(p,sizeof p,1,0,payload,1025));
 assert(!scope_request(p,27,1,0,0,0));
 assert(scope_record_payload(record,1000000)); assert(!scope_record_payload(record,1000001));
 assert(scope_dds_payload(dds,3,1,12500000,0xffffffff,16383,-131072));
 assert(!scope_dds_payload(dds,4,1,0,0,0,0));
 assert(!scope_dds_payload(dds,0,1,12500001,0,0,0));
 assert(!scope_dds_payload(dds,0,1,0,0,0,131072));
 /* Every possible availability combination: never pop a blocked source. */
 for(s=0;s<16;s++) {
  m.status=s; m.a=0x55; m.b=0xaa; m.reads=m.writes=0;
  unsigned expected=((s&3)==3)+((s&12)==12);
  assert(scope_cpu_poll(&c)==expected); assert(m.reads==expected && m.writes==expected);
  if((s&3)==3) assert(m.x==0x55);
  if((s&12)==12) assert(m.y==0xaa);
 }
 puts("C_TEST_PASS CRC, all payload lengths, malformed CRC, bounds, 16 backpressure states");
 return 0;
}
