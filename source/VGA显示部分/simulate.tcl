set root $::env(SCOPE_CPU_ROOT)
set panel [file normalize [file dirname [info script]]]
set binary [file normalize [file join [file dirname [info nameofexecutable]] .. ..]]
set out [file join $panel output sim]
file mkdir $out
foreach name {font.mem small_font.mem knob_ticks.mem output/page_0.mem output/page_2.mem output/page_5.mem} {file copy -force [file join $panel $name] [file join $out [file tail $name]]}
cd $out
set sources [list [file join $root integration rtl common scope_pkg.sv]]
foreach name {panel_stats.sv panel_wave_memory.sv panel_interpolator.sv panel_screen.sv tb_interpolator.sv tb_panel.sv} {lappend sources [file join $panel $name]}
set fd [open run.tcl w];puts $fd "run 300 ms\nquit";close $fd
foreach {tool args} [list xvlog [concat -sv -i $panel $sources] xelab [list tb_panel -s panel_sim] xsim [list panel_sim -tclbatch run.tcl]] {
 if {[catch {exec [file join $binary ${tool}.bat] {*}$args 2>@1} result]} {puts $result;error "PANEL_TOOL_FAIL $tool"}
 set fd [open ${tool}.txt w];puts $fd $result;close $fd
 puts $result
 if {$tool eq "xsim" && ![string match {*PANEL_RTL_TEST_PASS*} $result]} {error {PANEL_TEST_FAILED}}
 if {$tool eq "xsim" && ![string match {*INTERPOLATION_TEST_PASS*} $result]} {error {INTERPOLATION_TEST_FAILED}}
}
puts {PANEL_SIMULATION_PASS}
exit
