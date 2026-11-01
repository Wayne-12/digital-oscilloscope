# Args: report vectors expected traces seed
if {[llength $argv]!=5} {error {expected report vectors expected traces seed}}
set report [file normalize [lindex $argv 0]]
if {[catch {
    source [file join [file dirname [info script]] create_smoke_project.tcl]
    set ::scope_clock_plain_hdl 1
    source [file join [file dirname [info script]] ensure_scope_clock_ip.tcl]
    source [file join [file dirname [info script]] ensure_scope_fft_ip.tcl]
    set_property top scope_hw_top [get_filesets sources_1]
    set options [format {-sv_seed %s -testplusarg "SEED=%s" -testplusarg "VECTOR_DIR=%s" -testplusarg "EXPECTED_DIR=%s"} [lindex $argv 4] [lindex $argv 4] [file normalize [lindex $argv 1]] [file normalize [lindex $argv 2]]]
    set_property -name xsim.simulate.xsim.more_options -value $options -objects [get_filesets sim_1]
    file mkdir [file normalize [lindex $argv 3]]
    foreach top {tb_fft_wrapper tb_spectrum tb_spectrum_capture tb_spectrum_control tb_spectrum_isqrt} {
        set_property top $top [get_filesets sim_1]
        set_property xsim.simulate.runtime 100ms [get_filesets sim_1]
        smoke_project::refresh_compile_order -fileset sources_1;smoke_project::refresh_compile_order -fileset sim_1
        launch_simulation -simset sim_1 -mode behavioral
        close_sim
        set simdir [file join $smoke_project::project_dir scope_smoke.sim sim_1 behav xsim]
        foreach name {xvlog.log elaborate.log simulate.log} {file copy -force [file join $simdir $name] [file join $report ${top}.${name}]}
        set f [open [file join $report ${top}.simulate.log] r];set log [read $f];close $f
        if {![regexp -line {^TEST_PASS tb_(fft_wrapper|spectrum).*errors=0} $log] || [regexp -line {^\s*(ERROR:|Fatal:|TEST_FAIL)} $log]} {error "Incomplete PASS: $top"}
    }
    foreach name {fft_raw.csv spectrum_bins.csv spectrum_results.csv spectrum_capture_bins.csv spectrum_capture_results.csv spectrum_capture_roi.csv} {
        file copy -force [file join $simdir $name] [file join [file normalize [lindex $argv 3]] $name]
    }
    set_property top tb_spectrum [get_filesets sim_1]
    smoke_project::audit [file join $report project_audit.txt]
    report_ip_status -file [file join $report ip_status.txt]
    puts {SPECTRUM_PROJECT_PASS tops=5 errors=0};close_project
} message options]} {
    puts stderr "SPECTRUM_PROJECT_FAIL $message";puts stderr [dict get $options -errorinfo];catch {close_sim};catch {close_project};exit 1
}
exit 0
