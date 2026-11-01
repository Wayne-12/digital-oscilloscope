# Arguments: report_directory. Native XSim behavioral simulation only.
if {[llength $argv] != 1} { puts stderr {Usage: check_safe_project.tcl report_directory}; exit 1 }
set report_directory [file normalize [lindex $argv 0]]
file mkdir $report_directory
proc safe_project_simulate {top_name runtime output_directory} {
    file mkdir $output_directory
    set_property top $top_name [get_filesets sim_1]
    set_property xsim.simulate.runtime $runtime [get_filesets sim_1]
    smoke_project::refresh_compile_order -fileset sim_1
    launch_simulation -simset sim_1 -mode behavioral
    close_sim
    set xsim_directory [file join $smoke_project::project_dir scope_smoke.sim sim_1 behav xsim]
    foreach name [list xvlog.log elaborate.log simulate.log compile.bat elaborate.bat simulate.bat "${top_name}.tcl"] {
        set path [file join $xsim_directory $name]
        if {[file exists $path]} { file copy -force $path [file join $output_directory $name] }
    }
    set channel [open [file join $output_directory simulate.log] r]
    set transcript [read $channel]
    close $channel
    if {![regexp -line "^TEST_PASS $top_name .*" $transcript terminal_pass]} {
        error "$top_name did not reach TEST_PASS"
    }
    if {[regexp -nocase -line {^\s*(ERROR:|Fatal:|TEST_FAIL)} $transcript]} {
        error "$top_name reported an error/fatal"
    }
    puts $terminal_pass
}
if {[catch {
    source [file join [file dirname [info script]] create_smoke_project.tcl]
    set ::scope_clock_plain_hdl 1
    source [file join [file dirname [info script]] ensure_scope_clock_ip.tcl]
    set_property top scope_hw_top [get_filesets sources_1]
    set_property -name xsim.simulate.xsim.more_options \
                 -value {-sv_seed 20261020 -testplusarg "SEED=20261020"} -objects [get_filesets sim_1]
    smoke_project::refresh_compile_order -fileset sources_1
    safe_project_simulate tb_safe 5ms [file join $report_directory core]
    safe_project_simulate tb_hw_safe 110us [file join $report_directory wrapper]
    set_property top tb_safe [get_filesets sim_1]
    set_property xsim.simulate.runtime 5ms [get_filesets sim_1]
    smoke_project::refresh_compile_order -fileset sim_1
    smoke_project::audit [file join $report_directory project_audit.txt]
    puts {SAFE_PROJECT_PASS core=PASS wrapper=PASS}
    close_project
} error_message error_options]} {
    puts stderr "SAFE_PROJECT_FAIL $error_message"
    puts stderr [dict get $error_options -errorinfo]
    catch {close_sim}
    catch {close_project}
    exit 1
}
exit 0
