# User-authorized volatile JTAG update. No configuration-memory operations.
set panel [file normalize [file dirname [info script]]]
set image [file join $panel output cpu_vga_runtime.bit]
if {![file exists $image]} {error {Verified runtime bitstream missing}}
if {[catch {
 open_hw_manager
 connect_hw_server -url localhost:3121
 set targets [get_hw_targets -quiet *1234-tulA]
 if {[llength $targets]!=1} {error "Expected one known EGO1 JTAG target: $targets"}
 open_hw_target [lindex $targets 0]
 set devices [get_hw_devices -quiet xc7a35t_0]
 if {[llength $devices]!=1} {error "Expected one XC7A35T: $devices"}
 set device [lindex $devices 0]
 if {[string tolower [get_property IDCODE_HEX $device]] ne {0362d093}} {error {Unexpected FPGA IDCODE}}
 set_property PROGRAM.FILE $image $device
 puts "BOARD_PROGRAM_FILE $image"
 program_hw_devices $device
 refresh_hw_device $device
 set done [get_property REGISTER.CONFIG_STATUS.BIT14_DONE_PIN $device]
 puts "BOARD_PROGRAM_DONE $done"
 if {$done ne {1}} {error {FPGA DONE did not assert}}
 close_hw_target
 disconnect_hw_server
 close_hw_manager
} detail options]} {
 puts stderr "BOARD_PROGRAM_FAIL $detail"
 puts stderr [dict get $options -errorinfo]
 catch {close_hw_target};catch {disconnect_hw_server};catch {close_hw_manager}
 exit 1
}
puts {BOARD_PROGRAM_PASS}
exit 0
