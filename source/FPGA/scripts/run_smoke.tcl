# Arguments: report_directory seed random_cycles
if {[llength $argv] != 3} {
    puts stderr {Usage: run_smoke.tcl report_directory seed random_cycles}
    exit 1
}
set report_directory [file normalize [lindex $argv 0]]
set seed [lindex $argv 1]
set random_cycles [lindex $argv 2]
file mkdir $report_directory
if {[catch {
    source [file join [file dirname [info script]] create_smoke_project.tcl]
    smoke_project::audit [file join $report_directory project_audit.txt]
    # Retain quotes around plusargs through Vivado's generated Windows .bat.
    set options [format {-sv_seed %s -testplusarg "SEED=%s" -testplusarg "RANDOM_CYCLES=%s"} \
                        $seed $seed $random_cycles]
    set_property -name xsim.simulate.xsim.more_options -value $options -objects [get_filesets sim_1]
    launch_simulation -simset sim_1 -mode behavioral
    close_sim

    set xsim_directory [file join $smoke_project::project_dir scope_smoke.sim sim_1 behav xsim]
    foreach name {xvlog.log elaborate.log simulate.log compile.bat elaborate.bat simulate.bat tb_smoke.tcl} {
        set path [file join $xsim_directory $name]
        if {[file exists $path]} { file copy -force $path [file join $report_directory $name] }
    }
    set runtime_log [file join $report_directory simulate.log]
    if {![file exists $runtime_log]} { error {Simulation transcript not found} }
    set channel [open $runtime_log r]
    set transcript [read $channel]
    close $channel
    if {![regexp -line {^TEST_PASS tb_smoke .*} $transcript terminal_pass]} {
        error {Behavioral simulation did not reach TEST_PASS}
    }
    if {[regexp -nocase -line {^\s*(ERROR:|Fatal:|TEST_FAIL)} $transcript]} {
        error {Unexpected error/fatal in simulation transcript}
    }
    puts $terminal_pass
    puts {BEHAVIORAL_SIMULATION_PASS}
    close_project
} error_message error_options]} {
    puts stderr "STEP1_FAIL $error_message"
    puts stderr [dict get $error_options -errorinfo]
    catch {close_sim}
    catch {close_project}
    exit 1
}
exit 0
