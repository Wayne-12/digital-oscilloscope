# Explicitly patch the linked C program into the placed BRAM locations.
# Opening a DCP in a fresh session does not preserve source-file ELF associations.
set root [file normalize [file join [file dirname [info script]] ..]]
set binary [file normalize [file join [file dirname [info nameofexecutable]] .. ..]]
set args [list -force -meminfo [file join $root reports implementation cpu_memory.mmi] \
 -data [file join $root build scope_cpu.elf] -bit [file join $root build scope_cpu_test.bit] \
 -proc uart/cpu/inst/microblaze_I -out [file join $root build scope_cpu_runtime.bit]]
puts [exec [file join $binary updatemem.bat] {*}$args 2>@1]
puts {CPU_ELF_EMBED_PASS}
exit
