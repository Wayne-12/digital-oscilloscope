# Offline preparation only: no hardware connection or flash mutation.
if {[llength $argv] ni {2 3 4}} {
  puts stderr {Usage: prepare_scope_flash.tcl routed_checkpoint output_directory [size_MiB] [image_basename]}
  exit 1
}
set checkpoint [file normalize [lindex $argv 0]]
set output [file normalize [lindex $argv 1]]
set size_mib 4
if {[llength $argv] >= 3} {set size_mib [lindex $argv 2]}
set basename scope_board_25m_flash
if {[llength $argv] == 4} {set basename [lindex $argv 3]}
if {![regexp {^[A-Za-z0-9_-]+$} $basename]} {error {Invalid image basename}}
if {$size_mib ni {4 8}} {puts stderr {Supported sizes are 4 or 8 MiB}; exit 1}
if {[catch {
  file mkdir $output
  open_hw_manager
  set model n25q[expr {$size_mib * 8}]-3.3v-spi-x1_x2_x4
  set parts [get_cfgmem_parts -quiet $model]
  if {![llength $parts]} {error "Unsupported flash model $model"}
  puts "FLASH_CANDIDATES $parts"
  report_property [lindex $parts 0]
  close_hw_manager
  open_checkpoint $checkpoint
  puts "FLASH_DESIGN_PART [get_property PART [current_design]]"
  if {[get_property PART [current_design]] ne {xc7a35tcsg324-1}} {error {Unexpected design part}}
  puts "FLASH_ORIGINAL_STARTUPCLK [get_property BITSTREAM.STARTUP.STARTUPCLK [current_design]]"
  set_property CONFIG_MODE SPIx1 [current_design]
  set_property BITSTREAM.CONFIG.SPI_BUSWIDTH 1 [current_design]
  set_property BITSTREAM.CONFIG.CONFIGRATE 3 [current_design]
  set_property BITSTREAM.STARTUP.STARTUPCLK CCLK [current_design]
  report_property [current_design] -file $output/design_properties.rpt
  write_bitstream -force $output/$basename.bit
  write_cfgmem -force -format mcs -size $size_mib -interface SPIx1 \
    -loadbit [list up 0x00000000 $output/$basename.bit] \
    -file $output/$basename.mcs
  write_cfgmem -force -format bin -size $size_mib -interface SPIx1 \
    -loadbit [list up 0x00000000 $output/$basename.bit] \
    -file $output/$basename.bin
  puts {FLASH_PREPARE_PASS}
} detail options]} {
  puts stderr "FLASH_PREPARE_FAIL $detail"
  puts stderr [dict get $options -errorinfo]
  exit 1
}
exit 0
