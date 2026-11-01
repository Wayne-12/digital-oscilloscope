if {[llength $argv]!=4} {error {expected report vectors traces seed}}
set report [file normalize [lindex $argv 0]];set traces [file normalize [lindex $argv 2]]
if {[catch {
    source [file join [file dirname [info script]] create_smoke_project.tcl]
    set ::scope_clock_plain_hdl 1
    source [file join [file dirname [info script]] ensure_scope_clock_ip.tcl]
    source [file join [file dirname [info script]] ensure_scope_fft_ip.tcl]
    set_property top scope_hw_top [get_filesets sources_1]
    set options [format {-sv_seed %s -testplusarg "SEED=%s" -testplusarg "VECTOR_DIR=%s"} [lindex $argv 3] [lindex $argv 3] [file normalize [lindex $argv 1]]]
    set_property -name xsim.simulate.xsim.more_options -value $options -objects [get_filesets sim_1]
    file mkdir $traces
    set tops {tb_innovation_units tb_innovation_health tb_innovation_bram tb_innovation_control}
    foreach backend {bram} {foreach profile {0 1 2 3} {lappend tops tb_innovation_${backend}_channel${profile}}}
    foreach top $tops {
        set_property top $top [get_filesets sim_1];set_property xsim.simulate.runtime 200ms [get_filesets sim_1]
        smoke_project::refresh_compile_order -fileset sources_1;smoke_project::refresh_compile_order -fileset sim_1
        launch_simulation -simset sim_1 -mode behavioral;close_sim
        set simdir [file join $smoke_project::project_dir scope_smoke.sim sim_1 behav xsim]
        foreach name {xvlog.log elaborate.log simulate.log} {file copy -force [file join $simdir $name] [file join $report ${top}.${name}]}
        set f [open [file join $report ${top}.simulate.log] r];set log [read $f];close $f
        if {![regexp -line {^TEST_PASS tb_innovation.*errors=0} $log] || [regexp -line {^\s*(ERROR:|Fatal:|TEST_FAIL)} $log]} {error "Incomplete PASS: $top"}
    }
    foreach pattern {health_*.csv innovation_*_jobs.csv innovation_*_source.csv innovation_*_job*_uart.hex innovation_*_job*_container.hex} {
        foreach path [glob -nocomplain -directory $simdir $pattern] {file copy -force $path [file join $traces [file tail $path]]}
    }
    set_property top tb_innovation_health [get_filesets sim_1]
    smoke_project::audit [file join $report project_audit.txt]
    puts {INNOVATION_PROJECT_PASS tops=13 errors=0};close_project
} message options]} {
    puts stderr "INNOVATION_PROJECT_FAIL $message";puts stderr [dict get $options -errorinfo];catch {close_sim};catch {close_project};exit 1
}
exit 0
