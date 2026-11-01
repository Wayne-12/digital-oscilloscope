# Use only after external module 5V is OFF and SW0 is OFF, board/JTAG powered.
set panel [file normalize [file dirname [info script]]]
set release [file join $panel release]
set report_name hardware_[clock format [clock seconds] -format {%Y%m%d_%H%M%S}]
set report [file join $release $report_name]
set f [open [file join $release latest_flash_report.txt] w];puts $f $report_name;close $f
set argv [list [file join $release display_final.mcs] [file join $release display_final.bin] $report]
# User-authorized QSPI deployment. Modules 5V off, SW0 off, board powered.
# Back up the full detected flash. Erase/program only if the desired image differs.
if {[llength $argv]!=3} {puts stderr {Expected image.mcs image.bin new_report_directory};exit 1}
set image [file normalize [lindex $argv 0]]
set expected [file normalize [lindex $argv 1]]
set report [file normalize [lindex $argv 2]]
if {[catch {
  if {![file isfile $image] || ![file isfile $expected]} {error {Missing prepared image}}
  if {[file exists $report]} {error {Use a new report directory to preserve backups}}
  file mkdir $report
  set f [open $expected rb];set expected_data [read $f];close $f
  open_hw_manager
  connect_hw_server -url localhost:3121
  set targets [get_hw_targets -quiet *1234-tulA]
  if {[llength $targets]!=1} {error "Unexpected targets: $targets"}
  open_hw_target [lindex $targets 0]
  set devices [get_hw_devices -quiet xc7a35t_0]
  if {[llength $devices]!=1} {error "Unexpected devices: $devices"}
  set device [lindex $devices 0]
  current_hw_device $device
  if {[string tolower [get_property IDCODE_HEX $device]] ne {0362d093}} {error {Unexpected FPGA IDCODE}}
  set mode {}
  foreach i {2 1 0} {
    set name [format {REGISTER.CONFIG_STATUS.BIT%02d_MODE_PIN_M[%d]} [expr {8+$i}] $i]
    append mode [get_property $name $device]
  }
  if {$mode ne {001}} {error "Master SPI mode 001 required before deployment; observed $mode"}
  report_property $device -file $report/fpga_before.rpt
  set parts [get_cfgmem_parts -quiet n25q64-3.3v-spi-x1_x2_x4]
  if {![llength $parts]} {error {Verified N25Q64 flash definition unavailable}}
  set part [lindex $parts 0]
  if {[get_property MEM_DENSITY $part]!=64} {error {Unexpected flash density}}
  if {[file size $expected]>8388608} {error {Image exceeds flash capacity}}
  puts "QSPI_PART $part"
  create_hw_cfgmem -hw_device $device -mem_dev $part
  set mem [get_property PROGRAM.HW_CFGMEM $device]
  set_property PROGRAM.FILES [list $image] $mem
  set_property PROGRAM.ADDRESS_RANGE use_file $mem
  set_property PROGRAM.UNUSED_PIN_TERMINATION pull-none $mem
  foreach p {ERASE BLANK_CHECK CFG_PROGRAM VERIFY} {set_property PROGRAM.$p 0 $mem}
  create_hw_bitstream -hw_device $device [get_property PROGRAM.HW_CFGMEM_BITFILE $device]
  program_hw_devices $device
  readback_hw_cfgmem -all -format bin -file $report/flash_before.bin $mem
  if {[file size $report/flash_before.bin]!=8388608} {error {Incomplete full-flash backup; refusing erase}}
  puts {QSPI_FULL_BACKUP_PASS bytes=8388608}
  set f [open $report/flash_before.bin rb];set before_data [read $f];close $f
  set prefix [string range $before_data 0 [expr {[string length $expected_data]-1}]]
  if {$prefix eq $expected_data} {
    set action RETAINED_IDENTICAL_IMAGE
    puts {QSPI_ALREADY_CURRENT_ERASE_PROGRAM_SKIPPED}
  } else {
    foreach p {ERASE BLANK_CHECK CFG_PROGRAM VERIFY} {set_property PROGRAM.$p 1 $mem}
    program_hw_cfgmem $mem
    set action PROGRAMMED_AND_VERIFIED
    puts {QSPI_PROGRAM_VERIFY_PASS}
  }
  readback_hw_cfgmem -offset 0 -datacount [file size $expected] -format bin -file $report/flash_after.bin $mem
  set f [open $report/flash_after.bin rb];set actual_data [read $f];close $f
  if {$actual_data ne $expected_data} {error {Independent flash binary readback differs from target}}
  puts {QSPI_INDEPENDENT_READBACK_COMPARE_PASS}
  report_property $mem -file $report/flash_after.rpt
  set f [open $report/action.txt w];puts $f $action;close $f
  # Boot from mode pins, rather than loading the user image via volatile JTAG.
  set boot_result [boot_hw_device -timeout 30 $device]
  refresh_hw_device $device
  set done [get_property REGISTER.CONFIG_STATUS.BIT14_DONE_PIN $device]
  set eos [get_property REGISTER.CONFIG_STATUS.BIT04_END_OF_STARTUP_(EOS)_STATUS $device]
  set crc [get_property REGISTER.CONFIG_STATUS.BIT00_CRC_ERROR $device]
  puts "QSPI_BOOT result=$boot_result MODE=$mode DONE=$done EOS=$eos CRC_ERROR=$crc"
  if {$done ne {1} || $eos ne {1} || $crc ne {0}} {error {QSPI boot register checks failed}}
  report_property $device -file $report/fpga_after_qspi_boot.rpt
  close_hw_target
  disconnect_hw_server
  close_hw_manager
  puts "QSPI_DEPLOYMENT_PASS action=$action"
  puts {PANEL_FLASH_PROGRAM_PASS}
} message options]} {
  puts stderr "QSPI_DEPLOYMENT_FAIL $message"
  puts stderr [dict get $options -errorinfo]
  catch {close_hw_target};catch {disconnect_hw_server};catch {close_hw_manager}
  exit 1
}
exit 0
