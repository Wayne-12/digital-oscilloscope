# Constructs a separate project and checks integrated RTL. Never programs hardware.

set root $::env(SCOPE_CPU_ROOT)

set vga [file normalize [file dirname [info script]]]

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

  if {[file tail $path] eq "frozen_frame_analysis.sv"} {continue}
  read_verilog -sv $path

 }

}

read_verilog -sv [file join $vga scope_cpu_mailbox.sv]

read_verilog -sv [file join $vga scope_cpu_endpoint.sv]

read_verilog -sv [file join $root rtl scope_core.sv]

read_verilog -sv [file join $vga scope_cpu_vga_top.sv]

foreach p [glob [file join $root integration clock *.v]] {read_verilog $p}

read_xdc [file join $root integration scope_board_25m.xdc]

add_files -norecurse [file join $vga output panel.elf]

set elf [get_files panel.elf]

set_property SCOPED_TO_REF scope_cpu_endpoint $elf

set_property SCOPED_TO_CELLS {cpu/inst/microblaze_I} $elf

set_property include_dirs [list $vga] [current_fileset]

foreach name {panel_inputs.sv panel_pixel_clock.sv panel_stats.sv panel_wave_memory.sv panel_interpolator.sv panel_analysis.sv panel_screen.sv} {

 read_verilog -sv [file join $vga $name]

}

read_xdc [file join $vga vga.xdc]

set_property top scope_cpu_vga_top [current_fileset]

update_compile_order -fileset sources_1

synth_ip [get_ips]

synth_design -top scope_cpu_vga_top -part xc7a35tcsg324-1



write_checkpoint -force [file join $vga output cpu_vga_synth.dcp]



set out [file join $vga output]

opt_design

place_design

phys_opt_design

report_timing -max_paths 20 -file [file join $out placed_paths.rpt]

write_checkpoint -force [file join $out cpu_vga_placed.dcp]

route_design

report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose -file [file join $out timing.rpt]

report_drc -file [file join $out drc.rpt]

report_cdc -details -file [file join $out cdc.rpt]
report_methodology -file [file join $out methodology.rpt]

report_utilization -file [file join $out utilization.rpt]

report_route_status -file [file join $out route.rpt]

set setup [get_timing_paths -quiet -delay_type max -slack_lesser_than 0]

set hold [get_timing_paths -quiet -delay_type min -slack_lesser_than 0]

if {![llength [get_timing_paths -quiet -delay_type max]] || [llength $setup] || [llength $hold]} {error {VGA_TIMING_FAILED}}

if {[llength [get_drc_violations -quiet -filter {SEVERITY == Error || SEVERITY == {Critical Warning}}]]} {error {VGA_DRC_FAILED}}

set fd [open [file join $out cdc.rpt] r]; set cdc [read $fd]; close $fd

if {[regexp -line {^[ \t]*CDC-[0-9]+[ \t]+Critical[ \t]+[1-9][0-9]*} $cdc]} {error {VGA_CDC_CRITICAL}}

set adc_regs [get_cells -hier -filter {NAME =~ input_capture/raw_iob_reg* || NAME =~ input_capture/otr_iob_reg*}]

if {[llength $adc_regs]!=13} {error {ADC_IOB_COUNT}}

foreach c $adc_regs {if {![string match ILOGIC* [get_property LOC $c]]} {error {ADC_IOB_LOCATION}}}

write_checkpoint -force [file join $out cpu_vga_routed.dcp]

write_mem_info -force [file join $out cpu_memory.mmi]

write_bitstream -force [file join $out cpu_vga_unpatched.bit]

set binary [file normalize [file join [file dirname [info nameofexecutable]] .. ..]]

puts [exec [file join $binary updatemem.bat] -force -meminfo [file join $out cpu_memory.mmi] -data [file join $vga output panel.elf] -bit [file join $out cpu_vga_unpatched.bit] -proc uart/cpu/inst/microblaze_I -out [file join $out cpu_vga_runtime.bit] 2>@1]

puts {PANEL_BUILD_PASS}

exit

