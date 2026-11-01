#include "scope_cpu.h"
static uint32_t read_io(void *unused, uint32_t reg) {
    (void)unused; return *(volatile uint32_t *)(uintptr_t)(SCOPE_IO_BASE+reg);
}
static void write_io(void *unused, uint32_t reg, uint32_t v) {
    (void)unused; *(volatile uint32_t *)(uintptr_t)(SCOPE_IO_BASE+reg)=v;
}
int main(void) {
    scope_cpu cpu={0,read_io,write_io,0,0,0};
    if(read_io(0,SCOPE_ID)!=SCOPE_IO_ID) for(;;) {} /* fail closed */
    for(;;) (void)scope_cpu_poll(&cpu);
}
