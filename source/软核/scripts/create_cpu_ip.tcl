# Offline only. No hardware-manager, programming, or flash operations.
set root [file normalize [file join [file dirname [info script]] ..]]
set output [file join $root build cpu_ip]
file mkdir $output
create_project scope_cpu [file join $output project] -part xc7a35tcsg324-1 -force
set existing [file join $output scope_microblaze scope_microblaze.xci]
if {[file exists $existing]} {read_ip $existing} else {
 create_ip -name microblaze_mcs -vendor xilinx.com -library ip -module_name scope_microblaze -dir $output
}
set wanted [list CONFIG.FREQ {25} CONFIG.MEMSIZE {32768} CONFIG.USE_IO_BUS {1} CONFIG.DEBUG_ENABLED {0} CONFIG.USE_UART_RX {0} CONFIG.USE_UART_TX {0}]
set_property -dict $wanted [get_ips scope_microblaze]
set receipt [open [file join $root reports cpu_ip_readback.txt] w]
foreach {key value} $wanted {
 set actual [get_property $key [get_ips scope_microblaze]]
 puts $receipt "$key requested=$value actual=$actual"
 if {$actual != $value} {error "CONFIG_READBACK_FAILED $key"}
}
close $receipt
generate_target all [get_ips scope_microblaze]
write_ip_tcl -force [get_ips scope_microblaze] [file join $root build recreate_cpu_ip.tcl]
puts {CPU_IP_GENERATED_OFFLINE}
close_project
exit
