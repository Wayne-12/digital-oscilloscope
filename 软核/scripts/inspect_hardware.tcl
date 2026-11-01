open_hw_manager
connect_hw_server -url localhost:3121
set targets [get_hw_targets]
puts "HW_TARGETS $targets"
foreach target $targets {
 open_hw_target $target
 foreach d [get_hw_devices] {
  puts "HW_DEVICE $d IDCODE=[get_property IDCODE_HEX $d]"
  report_property $d
 }
 close_hw_target
}
disconnect_hw_server
close_hw_manager
puts {HARDWARE_INSPECTION_DONE}
exit
