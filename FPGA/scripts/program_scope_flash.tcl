# Nonvolatile programming, authorized by the user. Run only after the user
# confirms module 5 V is OFF, SW0 is low, and board/JTAG power is maintained.
# A flash definition must match Vivado's JEDEC detection; never bypass its check.
# Usage: program_scope_flash.tcl image.mcs expected.bin report_directory [flash_part]
if {[llength $argv] ni {3 4}} {
  puts stderr {Usage: program_scope_flash.tcl image.mcs expected.bin report_directory [flash_part]}
  exit 1
}
set image [file normalize [lindex $argv 0]]
set expected [file normalize [lindex $argv 1]]
set report [file normalize [lindex $argv 2]]
set model n25q32-3.3v-spi-x1_x2_x4
if {[llength $argv] == 4} {set model [lindex $argv 3]}
if {$model ni {n25q32-3.3v-spi-x1_x2_x4 n25q64-3.3v-spi-x1_x2_x4}} {
  puts stderr {Unsupported flash definition}; exit 1
}
if {[catch {
  if {![file isfile $image] || ![file isfile $expected]} {error {Missing prepared image}}
  if {[file exists $report]} {error {Use a new report directory to preserve flash backups}}
  file mkdir $report
  open_hw_manager
  connect_hw_server -url localhost:3121
  set targets [get_hw_targets -quiet *1234-tulA]
  if {[llength $targets] != 1} {error "Unexpected JTAG targets: $targets"}
  open_hw_target [lindex $targets 0]
  set devices [get_hw_devices -quiet xc7a35t_0]
  if {[llength $devices] != 1} {error "Unexpected FPGA devices: $devices"}
  set device [lindex $devices 0]
  current_hw_device $device
  if {[string tolower [get_property IDCODE_HEX $device]] ne {0362d093}} {
    error {Unexpected FPGA IDCODE}
  }
  report_property $device -file $report/fpga_before.rpt
  set parts [get_cfgmem_parts -quiet $model]
  if {![llength $parts]} {error "No matching flash definition: $model"}
  set part [lindex $parts 0]
  set density [get_property MEM_DENSITY $part]
  if {$density ni {32 64}} {error {Unexpected flash density}}
  set capacity [expr {$density * 131072}]
  if {[file size $expected] > $capacity} {error {Image exceeds flash capacity}}
  puts "FLASH_PART $part"
  create_hw_cfgmem -hw_device $device -mem_dev $part
  set mem [get_property PROGRAM.HW_CFGMEM $device]
  set_property PROGRAM.FILES [list $image] $mem
  set_property PROGRAM.ADDRESS_RANGE use_file $mem
  set_property PROGRAM.UNUSED_PIN_TERMINATION pull-none $mem
  set_property PROGRAM.ERASE 0 $mem
  set_property PROGRAM.BLANK_CHECK 0 $mem
  set_property PROGRAM.CFG_PROGRAM 0 $mem
  set_property PROGRAM.VERIFY 0 $mem
  report_property $mem -file $report/flash_before.rpt
  create_hw_bitstream -hw_device $device [get_property PROGRAM.HW_CFGMEM_BITFILE $device]
  program_hw_devices $device
  # Save the entire existing flash before any nonvolatile write.
  readback_hw_cfgmem -all -format bin -file $report/flash_before.bin $mem
  if {[file size $report/flash_before.bin] != $capacity} {
    error {Full flash backup has an unexpected size; refusing erase}
  }
  puts {FLASH_BACKUP_PASS}
  set_property PROGRAM.ERASE 1 $mem
  set_property PROGRAM.BLANK_CHECK 1 $mem
  set_property PROGRAM.CFG_PROGRAM 1 $mem
  set_property PROGRAM.VERIFY 1 $mem
  program_hw_cfgmem $mem
  puts {FLASH_PROGRAM_VERIFY_PASS}
  readback_hw_cfgmem -offset 0 -datacount [file size $expected] -format bin \
    -file $report/flash_after.bin $mem
  set input [open $expected rb]
  set expected_data [read $input]
  close $input
  set input [open $report/flash_after.bin rb]
  set actual_data [read $input]
  close $input
  if {$expected_data ne $actual_data} {error {Flash binary readback differs from prepared image}}
  puts {FLASH_BINARY_COMPARE_PASS}
  report_property $mem -file $report/flash_after.rpt
  close_hw_target
  disconnect_hw_server
  close_hw_manager
  puts {FLASH_PROGRAM_PASS_BOOT_TEST_PENDING}
} detail options]} {
  puts stderr "FLASH_PROGRAM_FAIL $detail"
  puts stderr [dict get $options -errorinfo]
  catch {close_hw_target}
  catch {disconnect_hw_server}
  catch {close_hw_manager}
  exit 1
}
exit 0
