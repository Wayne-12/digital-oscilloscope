# Explicit 2026-10-28 user authorization: temporary FPGA configuration only.
# This script never creates, erases, programs or verifies a configuration-memory device.
set root [file normalize [file join [file dirname [info script]] ..]]
set image [file join $root build scope_cpu_runtime.bit]
if {![file exists $image]} {error {Missing routed CPU test image}}
foreach dependency [list [file join $root build scope_cpu.elf] [file join $root build scope_cpu_test.bit] [file join $root build scope_cpu_routed.dcp] [file join $root reports implementation cpu_memory.mmi]] {
 if {[file mtime $image] < [file mtime $dependency]} {error "Stale embedded CPU image: $dependency"}
}
open_hw_manager
connect_hw_server -url localhost:3121
set targets [get_hw_targets *1234-tulA]
if {[llength $targets]!=1} {error {Unexpected or ambiguous JTAG target}}
open_hw_target [lindex $targets 0]
set devices [get_hw_devices xc7a35t_0]
if {[llength $devices]!=1} {error {Expected one XC7A35T}}
set d [lindex $devices 0]
if {[string tolower [get_property IDCODE_HEX $d]] ne "0362d093"} {error {Unexpected device IDCODE}}
set_property PROGRAM.FILE $image $d
puts "TEMPORARY_FPGA_IMAGE $image"
program_hw_devices $d
refresh_hw_device $d
if {[get_property REGISTER.CONFIG_STATUS.BIT14_DONE_PIN $d] ne "1"} {error {DONE did not assert}}
close_hw_target
disconnect_hw_server
close_hw_manager
puts {VOLATILE_CPU_PROGRAM_PASS_NO_FLASH}
exit
