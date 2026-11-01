# Run in the ASCII staging directory prepared by build_scope_board.py.
set output [file normalize artifacts]
file mkdir $output
if {[catch {
  create_project -in_memory -part xc7a35tcsg324-1
  set_property target_language Verilog [current_project]
  set ::scope_fft_output_root [file normalize ip]
  source ensure_scope_fft_ip.tcl
  synth_ip [get_ips scope_fft_1024]
  foreach path [lsort [glob src/*.sv]] {read_verilog -sv $path}
  foreach path [glob clock/*.v] {read_verilog $path}
  read_xdc scope_board_25m.xdc
  set uart_baud 115200
  if {[info exists ::env(SCOPE_UART_BAUD)]} {set uart_baud $::env(SCOPE_UART_BAUD)}
  if {$uart_baud ni {115200 921600}} {error "UNSUPPORTED_UART_BAUD $uart_baud"}
  synth_design -top scope_board_top -part xc7a35tcsg324-1 -generic UART_BAUD=$uart_baud
  set require_iob [expr {[info exists ::env(SCOPE_REQUIRE_IOB)] && $::env(SCOPE_REQUIRE_IOB) eq "1"}]
  if {$require_iob} {
    set adc_input_registers [get_cells -hier -filter {NAME =~ input_capture/raw_iob_reg* || NAME =~ input_capture/otr_iob_reg*}]
    if {[llength $adc_input_registers] != 13} {error "ADC_INPUT_REGISTER_COUNT [llength $adc_input_registers]"}
    set_property IOB TRUE $adc_input_registers
  }
  write_checkpoint -force $output/synth.dcp
  report_utilization -file $output/synth_utilization.rpt
  report_timing_summary -file $output/synth_timing.rpt
  opt_design
  place_design
  phys_opt_design
  route_design
  write_checkpoint -force $output/routed.dcp
  report_utilization -file $output/utilization.rpt
  report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose -file $output/timing.rpt
  report_clock_interaction -file $output/clock_interaction.rpt
  report_cdc -details -file $output/cdc.rpt
  report_drc -file $output/drc.rpt
  report_methodology -file $output/methodology.rpt
  report_io -file $output/io.rpt
  report_clocks -file $output/clocks.rpt
  if {$require_iob} {
    set adc_input_registers [get_cells -hier -filter {NAME =~ input_capture/raw_iob_reg* || NAME =~ input_capture/otr_iob_reg*}]
    if {[llength $adc_input_registers] != 13} {error {Post-route ADC register count differs}}
    set iob_file [open $output/adc_iob_placement.tsv w]
    puts $iob_file "cell\tref_name\tLOC\tBEL\tsite_type\tIOB"
    foreach register [lsort $adc_input_registers] {
      set location [get_property LOC $register]
      set bel [get_property BEL $register]
      set site_type [get_property SITE_TYPE [get_sites $location]]
      puts $iob_file "$register\t[get_property REF_NAME $register]\t$location\t$bel\t$site_type\t[get_property IOB $register]"
      if {![string match ILOGIC* $site_type]} {error "ADC_NOT_IN_INPUT_IOB $register $location $site_type"}
    }
    close $iob_file
    report_timing -from [get_ports {adc_data[*] adc_otr}] -to $adc_input_registers -delay_type max -max_paths 20 -file $output/adc_input_setup.rpt
    report_timing -from [get_ports {adc_data[*] adc_otr}] -to $adc_input_registers -delay_type min -max_paths 20 -file $output/adc_input_hold.rpt
    puts {ADC_INPUT_IOB_PLACEMENT_PASS registers=13}
  }
  set bad_drc [get_drc_violations -quiet -filter {SEVERITY == Error || SEVERITY == {Critical Warning}}]
  if {[llength $bad_drc]} {error "DRC_BLOCKERS $bad_drc"}
  set setup [get_timing_paths -quiet -delay_type max -slack_lesser_than 0 -max_paths 10]
  set hold [get_timing_paths -quiet -delay_type min -slack_lesser_than 0 -max_paths 10]
  if {[llength $setup] || [llength $hold]} {error "TIMING_FAILED setup=[llength $setup] hold=[llength $hold]"}
  puts {BOARD_IMPLEMENTATION_PASS}
  write_bitstream -force $output/scope_board_25m.bit
  puts {BOARD_BITSTREAM_PASS}
} detail options]} {
  puts stderr "BOARD_BUILD_FAIL $detail"
  puts stderr [dict get $options -errorinfo]
  exit 1
}
exit 0
