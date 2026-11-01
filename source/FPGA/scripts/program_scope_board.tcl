# Explicit user-authorized, volatile JTAG programming. No flash erase/write.
if {[llength $argv]!=1} {puts stderr {Usage: program_scope_board.tcl bitstream};exit 1}
set bitstream [file normalize [lindex $argv 0]]
if {![file exists $bitstream]} {puts stderr {Bitstream not found};exit 1}
if {[catch {
  open_hw_manager
  connect_hw_server -url localhost:3121
  set targets [get_hw_targets -quiet *1234-tulA]
  if {[llength $targets]!=1} {error "Expected the previously identified EGO1 target: $targets"}
  open_hw_target [lindex $targets 0]
  set devices [get_hw_devices -quiet xc7a35t_0]
  if {[llength $devices]!=1} {error "Expected one xc7a35t_0 device: $devices"}
  set device [lindex $devices 0]
  if {[string tolower [get_property IDCODE_HEX $device]] ne {0362d093}} {error {Unexpected FPGA IDCODE}}
  puts "BOARD_PROGRAM_FILE $bitstream"
  set_property PROGRAM.FILE $bitstream $device
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
  exit 1
}
puts {BOARD_PROGRAM_PASS}
exit 0
