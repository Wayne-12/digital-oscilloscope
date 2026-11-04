# Read-only verification; run after booting from Flash, without JTAG loading.
set panel [file normalize [file dirname [info script]]]
set release [file join $panel release]
set f [open [file join $release latest_flash_report.txt] r];set report_name [string trim [read $f]];close $f
if {![regexp {^hardware_[0-9]{8}_[0-9]{6}$} $report_name]} {error {Invalid flash report directory}}
set argv [list [file join $release $report_name]]
# Read-only cold-boot validation: never programs/reconfigures the FPGA.
if {[llength $argv] != 1} {puts stderr {Expected report directory}; exit 1}
set report [file normalize [lindex $argv 0]]
if {[catch {
  open_hw_manager
  connect_hw_server -url localhost:3121
  set targets [get_hw_targets -quiet *1234-tulA]
  if {[llength $targets] != 1} {error "Expected one EGO1 target: $targets"}
  open_hw_target [lindex $targets 0]
  set devices [get_hw_devices -quiet xc7a35t_0]
  if {[llength $devices] != 1} {error "Unexpected FPGA devices: $devices"}
  set device [lindex $devices 0]
  if {[string tolower [get_property IDCODE_HEX $device]] ne {0362d093}} {error {Wrong FPGA}}
  report_property $device -file $report/cold_boot_fpga.rpt
  set mode {}
  foreach i {2 1 0} {
    set bit_name [format {REGISTER.CONFIG_STATUS.BIT%02d_MODE_PIN_M[%d]} [expr {8+$i}] $i]
    append mode [get_property $bit_name $device]
  }
  set done [get_property REGISTER.CONFIG_STATUS.BIT14_DONE_PIN $device]
  set eos [get_property REGISTER.CONFIG_STATUS.BIT04_END_OF_STARTUP_(EOS)_STATUS $device]
  set crc [get_property REGISTER.CONFIG_STATUS.BIT00_CRC_ERROR $device]
  puts "FLASH_BOOT_MODE $mode"
  puts "FLASH_BOOT_DONE $done EOS $eos CRC_ERROR $crc"
  if {$mode ne {001} || $done ne {1} || $eos ne {1} || $crc ne {0}} {
    error {Expected Master SPI mode 001, DONE=1, EOS=1 and CRC_ERROR=0}
  }
  close_hw_target
  disconnect_hw_server
  close_hw_manager
  puts {FLASH_COLD_BOOT_REGISTERS_PASS}
  puts {PANEL_FLASH_BOOT_PASS}
} detail options]} {
  puts stderr "FLASH_COLD_BOOT_FAIL $detail"
  puts stderr [dict get $options -errorinfo]
  catch {close_hw_target}
  catch {disconnect_hw_server}
  catch {close_hw_manager}
  exit 1
}
exit 0
