# Constructs a separate project and checks integrated RTL. Never programs hardware.
set root [file normalize [file join [file dirname [info script]] ..]]
create_project -in_memory -part xc7a35tcsg324-1
set_property target_language Verilog [current_project]
set candidates [glob [file join $root build cpu_ip */scope_microblaze.xci]]
if {![llength $candidates]} {error {Generate the CPU IP first}}
# Generated duplicates are equivalent; choose the first retained IP.
read_ip [lindex [lsort $candidates] 0]
set ::scope_fft_output_root [file join $root build fft_ip]
source -notrace [file join $root scripts ensure_scope_fft_ip.tcl]
foreach name {scope_pkg protocol_pkg spectrum_pkg multires_pkg fft_window_pkg} {
 read_verilog -sv [file join $root integration rtl common ${name}.sv]
}
foreach dir [glob -types d [file join $root integration rtl *]] {
 # Experimental innovation/SRAM blocks are outside the delivered top's
 # dependency tree. Keep them in the provenance snapshot, not this build.
 if {[file tail $dir] in {innovation sram_ctrl}} {continue}
 foreach path [glob -nocomplain [file join $dir *.sv]] {
  if {[file tail $dir] eq "common" && [string match *_pkg.sv [file tail $path]]} {continue}
  if {[file tail $dir] eq "top" && [file tail $path] in {scope_core.sv scope_board_top.sv}} {continue}
  read_verilog -sv $path
 }
}
read_verilog -sv [file join $root rtl scope_cpu_mailbox.sv]
read_verilog -sv [file join $root rtl scope_cpu_endpoint.sv]
read_verilog -sv [file join $root rtl scope_core.sv]
read_verilog -sv [file join $root rtl scope_cpu_board_top.sv]
foreach p [glob [file join $root integration clock *.v]] {read_verilog $p}
read_xdc [file join $root integration scope_board_25m.xdc]
add_files -norecurse [file join $root build scope_cpu.elf]
set elf [get_files scope_cpu.elf]
set_property SCOPED_TO_REF scope_cpu_endpoint $elf
set_property SCOPED_TO_CELLS {cpu/inst/microblaze_I} $elf
set_property top scope_cpu_board_top [current_fileset]
update_compile_order -fileset sources_1
synth_ip [get_ips]
synth_design -top scope_cpu_board_top -part xc7a35tcsg324-1
report_utilization -file [file join $root reports integrated_utilization.rpt]
report_timing_summary -file [file join $root reports integrated_synth_timing.rpt]
file mkdir [file join $root reports cdc_repair]
report_cdc -details -file [file join $root reports cdc_repair after_synth_cdc.rpt]
report_methodology -file [file join $root reports cdc_repair after_synth_methodology.rpt]
write_checkpoint -force [file join $root build scope_cpu_synth.dcp]
puts {INTEGRATED_SYNTHESIS_PASS}
close_design
close_project
exit
