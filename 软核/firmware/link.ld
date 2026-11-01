ENTRY(_start)
MEMORY { ram (rwx) : ORIGIN = 0, LENGTH = 32K }
SECTIONS {
 .vectors.reset 0 : { KEEP(*(.vectors.reset)) } > ram
 .text 0x50 : { *(.text.start) *(.text*) } > ram
 .rodata : { *(.rodata*) } > ram
 .data : { *(.data*) *(.sdata*) } > ram
 .bss (NOLOAD) : { __bss_start = .; *(.bss*) *(.sbss*) *(COMMON) __bss_end = .; } > ram
 . = ALIGN(16);
 _end = .;
 _stack = ORIGIN(ram) + LENGTH(ram) - 16;
 ASSERT(_end < _stack - 4096, "Firmware leaves less than 4KB stack")
}
