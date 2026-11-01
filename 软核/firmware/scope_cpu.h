#ifndef SCOPE_CPU_H
#define SCOPE_CPU_H
#include <stdint.h>
#include <stddef.h>
/* MicroBlaze MCS external I/O bus, PG116. All registers are 32-bit. */
#define SCOPE_IO_BASE UINT32_C(0xc0000000)
enum { SCOPE_ID=0, SCOPE_STATUS=4, SCOPE_HOST_RX=8, SCOPE_HW_TX=12,
       SCOPE_HW_RX=16, SCOPE_HOST_TX=20, SCOPE_HEARTBEAT=24 };

/* Current integrated panel MMIO extension (0xA7261029).
   Keep local C scheduling and the hardware mailbox on one shared contract. */
enum { PANEL_INPUT=28, PANEL_STATUS=32, PANEL_CONTROL=36, PANEL_MS=40,
       PANEL_FRAME=44, PANEL_VPP=48, PANEL_HZ=52 };
enum { HOST_RX_VALID=1, HW_TX_READY=2, HW_RX_VALID=4, HOST_TX_READY=8 };
#define SCOPE_IO_ID UINT32_C(0x53435031)
typedef uint32_t (*scope_read_fn)(void *, uint32_t);
typedef void (*scope_write_fn)(void *, uint32_t, uint32_t);
typedef struct {
    void *context;
    scope_read_fn read;
    scope_write_fn write;
    uint32_t host_bytes, hardware_bytes, polls;
} scope_cpu;
/* One bounded, bidirectional service round. No blocking or allocation. */
unsigned scope_cpu_poll(scope_cpu *cpu);
uint16_t scope_crc16(const uint8_t *bytes, size_t count);
/* Creates a protocol-v1 request, with explicit little-endian serialization. */
size_t scope_request(uint8_t *out, size_t capacity, uint8_t command,
                     uint16_t sequence, const uint8_t *payload, size_t length);
int scope_request_valid(const uint8_t *packet, size_t length);
int scope_record_payload(uint8_t out[8], uint32_t pre_ratio_ppm);
int scope_dds_payload(uint8_t out[16], unsigned wave, unsigned enable,
                      uint32_t hz, uint32_t phase, uint16_t amplitude, int32_t offset);
#endif
