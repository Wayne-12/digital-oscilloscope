    .section .vectors.reset,"ax"
    .global _start
    bri _start
    .section .text.start,"ax"
_start:
    la r1,r0,_stack
    la r5,r0,__bss_start
    la r6,r0,__bss_end
1:  cmpu r7,r5,r6
    beqi r7,2f
    sbi r0,r5,0
    addik r5,r5,1
    bri 1b
2:  bralid r15,main
    nop
3:  bri 3b
