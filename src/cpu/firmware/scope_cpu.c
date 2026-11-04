#include "scope_cpu.h"
#include <string.h>
static void put16(uint8_t *p, uint16_t v) { p[0]=(uint8_t)v; p[1]=(uint8_t)(v>>8); }
static void put32(uint8_t *p, uint32_t v) {
    unsigned i; for(i=0;i<4;i++) p[i]=(uint8_t)(v>>(8*i));
}
uint16_t scope_crc16(const uint8_t *p, size_t n) {
    uint16_t crc=0xffff; unsigned b;
    while(n--) { crc^=(uint16_t)*p++<<8;
        for(b=0;b<8;b++) crc=(uint16_t)((crc<<1)^((crc&0x8000)?0x1021:0));
    } return crc;
}
size_t scope_request(uint8_t *out, size_t cap, uint8_t cmd,
                     uint16_t seq, const uint8_t *payload, size_t n) {
    if(!out || n>1024 || cap<n+28 || (n && !payload) || cmd>=0x80) return 0;
    memset(out,0,26); out[0]=0x55; out[1]=0xaa; out[2]=1; out[3]=cmd;
    put16(out+4,seq); put16(out+6,(uint16_t)n);
    if(n) memcpy(out+26,payload,n);
    put16(out+26+n,scope_crc16(out+2,24+n)); return 28+n;
}
int scope_request_valid(const uint8_t *p, size_t n) {
    size_t len; uint16_t crc;
    if(!p || n<28 || p[0]!=0x55 || p[1]!=0xaa || p[2]!=1 || p[3]>=0x80 || p[24] || p[25]) return 0;
    len=(size_t)p[6]+((size_t)p[7]<<8);
    if(len>1024 || n!=len+28) return 0;
    crc=(uint16_t)(p[n-2]|((uint16_t)p[n-1]<<8));
    return crc==scope_crc16(p+2,n-4);
}
int scope_record_payload(uint8_t out[8], uint32_t ratio) {
    if(!out || ratio>1000000) return 0;
    put32(out,16384); put32(out+4,ratio); return 1;
}
int scope_dds_payload(uint8_t out[16], unsigned wave, unsigned enable,
                      uint32_t hz, uint32_t phase, uint16_t amp, int32_t offset) {
    if(!out || wave>3 || enable>1 || hz>12500000 || amp>16383 || offset< -131072 || offset>131071) return 0;
    out[0]=(uint8_t)wave; out[1]=(uint8_t)enable; put32(out+2,hz);
    put32(out+6,phase); put16(out+10,amp); put32(out+12,(uint32_t)offset); return 1;
}
unsigned scope_cpu_poll(scope_cpu *c) {
    uint32_t status=c->read(c->context,SCOPE_STATUS); unsigned moved=0;
    /* Both directions get a turn, even during a full-record transfer or STOP.
       Do not parse/drop damaged packets here: the existing RTL parser owns
       resynchronization, timeout and the UI-visible error counters. */
    if((status&(HOST_RX_VALID|HW_TX_READY))==(HOST_RX_VALID|HW_TX_READY)) {
        c->write(c->context,SCOPE_HW_TX,c->read(c->context,SCOPE_HOST_RX)&255);
        c->host_bytes++; moved++;
    }
    if((status&(HW_RX_VALID|HOST_TX_READY))==(HW_RX_VALID|HOST_TX_READY)) {
        c->write(c->context,SCOPE_HOST_TX,c->read(c->context,SCOPE_HW_RX)&255);
        c->hardware_bytes++; moved++;
    }
    if((++c->polls&0xffff)==0) c->write(c->context,SCOPE_HEARTBEAT,c->polls);
    return moved;
}
