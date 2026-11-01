set root [file normalize [file join [file dirname [info script]] ..]]
set binary [file normalize [file join [file dirname [info nameofexecutable]] .. ..]]
cd [file join $root build]
set core ../rtl/scope_core.sv
if {[info exists ::env(SCOPE_CDC_BASELINE)] && $::env(SCOPE_CDC_BASELINE) eq "1"} {set core ../integration/rtl/top/scope_core.sv}
set sources [list ../integration/rtl/common/scope_pkg.sv ../integration/rtl/clock_reset/scope_reset_sync.sv \
 ../integration/rtl/clock_reset/scope_enable_sync.sv ../integration/rtl/clock_reset/scope_safe_ctrl.sv $core ../tests/tb_cdc_safety.sv]
lappend sources [file join [file dirname $binary] data verilog src glbl.v]
foreach {tool args} [list xvlog [concat -sv $sources] xelab [list tb_cdc_safety glbl -L unisims_ver -s cdc_safety_sim] xsim [list cdc_safety_sim -runall]] {
 if {[catch {exec [file join $binary ${tool}.bat] {*}$args 2>@1} result]} {puts $result;error "SIM_TOOL_FAILED $tool"}
 set f [open [file join $root reports ${tool}_cdc_safety.txt] w];puts $f $result;close $f
 if {$tool eq "xsim" && ![string match {*CDC_SAFETY_TEST_PASS*} $result]} {error "CDC_SAFETY_TEST_FAILED see xsim_cdc_safety.txt"}
 puts "CDC_SAFETY_STAGE_PASS $tool"
}
exit
