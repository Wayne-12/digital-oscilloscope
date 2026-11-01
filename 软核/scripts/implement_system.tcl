set root [file normalize [file join [file dirname [info script]] ..]]
set out [file join $root reports implementation]
file mkdir $out
open_checkpoint [file join $root build scope_cpu_synth.dcp]
report_clocks -file [file join $out clocks_before.rpt]
report_methodology -file [file join $out methodology_before.rpt]
write_xdc -force -exclude_physical [file join $out constraints_before.xdc]
opt_design
place_design
phys_opt_design
route_design
write_checkpoint -force [file join $root build scope_cpu_routed.dcp]
report_utilization -file [file join $out utilization.rpt]
report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose -file [file join $out timing.rpt]
report_methodology -file [file join $out methodology.rpt]
report_drc -file [file join $out drc.rpt]
report_route_status -file [file join $out route_status.rpt]
report_cdc -details -file [file join $out cdc.rpt]
set cdc_channel [open [file join $out cdc.rpt] r]
set cdc_text [read $cdc_channel]
close $cdc_channel
if {[regexp -line {^[ \t]*CDC-[0-9]+[ \t]+Critical[ \t]+[1-9][0-9]*} $cdc_text]} {
 error {CDC_CRITICAL_REMAINS: no download image may be released}
}
report_clock_interaction -file [file join $out clock_interaction.rpt]
set setup [get_timing_paths -delay_type max -slack_lesser_than 0 -max_paths 10]
set hold [get_timing_paths -delay_type min -slack_lesser_than 0 -max_paths 10]
set timed [get_timing_paths -delay_type max -max_paths 1]
if {![llength $timed]} {error {NO_TIMED_PATHS: cannot sign off timing}}
if {[llength $setup] || [llength $hold]} {error "TIMING_FAILED setup=[llength $setup] hold=[llength $hold]"}
set blockers [get_drc_violations -filter {SEVERITY == Error || SEVERITY == {Critical Warning}}]
if {[llength $blockers]} {error "DRC_BLOCKERS $blockers"}
write_mem_info -force [file join $out cpu_memory.mmi]
write_bitstream -force [file join $root build scope_cpu_test.bit]
puts {CPU_IMPLEMENTATION_PASS}
close_design
exit
