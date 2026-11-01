# Args: report_directory vector_directory expected_directory trace_directory seed
if {[llength $argv] != 5} {puts stderr {MEASURE_PROJECT_FAIL expected five arguments}; exit 1}
set report_directory [file normalize [lindex $argv 0]]
if {[catch {
    source [file join [file dirname [info script]] create_smoke_project.tcl]
    set ::scope_clock_plain_hdl 1
    source [file join [file dirname [info script]] ensure_scope_clock_ip.tcl]
    set_property top scope_hw_top [get_filesets sources_1]
    set_property xsim.simulate.runtime 100ms [get_filesets sim_1]
    # Write relative to XSim's working directory. Absolute TEMP CSV writes
    # failed in project mode on this host; Tcl archives the completed files.
    set run_options [format {-sv_seed %s -testplusarg "SEED=%s" -testplusarg "VECTOR_DIR=%s" -testplusarg "EXPECTED_DIR=%s" -testplusarg "TRACE_DIR=%s"} \
        [lindex $argv 4] [lindex $argv 4] [file normalize [lindex $argv 1]] \
        [file normalize [lindex $argv 2]] {.}]
    set_property -name xsim.simulate.xsim.more_options -value $run_options -objects [get_filesets sim_1]
    set combined {}
    set compile_log {}
    set elaborate_log {}
    foreach top {tb_trigger tb_measure tb_measure_capture} {
        set_property top $top [get_filesets sim_1]
        smoke_project::refresh_compile_order -fileset sources_1
        smoke_project::refresh_compile_order -fileset sim_1
        launch_simulation -simset sim_1 -mode behavioral
        close_sim
        set simulation_directory [file join $smoke_project::project_dir scope_smoke.sim sim_1 behav xsim]
        set f [open [file join $simulation_directory simulate.log] r]
        set part [read $f];close $f
        if {![regexp -line "^TEST_PASS $top " $part]} {error "Missing independent PASS: $top"}
        append combined $part "\n"
        foreach trace [glob -nocomplain -directory $simulation_directory *.csv] {
            file mkdir [file normalize [lindex $argv 3]]
            file copy -force $trace [file join [file normalize [lindex $argv 3]] [file tail $trace]]
        }
        foreach name {xvlog.log elaborate.log simulate.log compile.bat elaborate.bat simulate.bat} {
            set path [file join $simulation_directory $name]
            if {[file exists $path]} {
                file copy -force $path [file join $report_directory ${top}.${name}]
                if {$name in {xvlog.log elaborate.log}} {
                    set log [open $path r];set text [read $log];close $log
                    if {$name eq {xvlog.log}} {append compile_log $text "\n"} else {append elaborate_log $text "\n"}
                } elseif {$name ne {simulate.log}} {file copy -force $path [file join $report_directory $name]}
            }
        }
    }
    set f [open [file join $report_directory simulate.log] w];puts $f $combined;close $f
    set f [open [file join $report_directory xvlog.log] w];puts $f $compile_log;close $f
    set f [open [file join $report_directory elaborate.log] w];puts $f $elaborate_log;close $f
    set channel [open [file join $report_directory simulate.log] r]
    set transcript [read $channel]
    close $channel
    if {![regexp -line {^TEST_PASS tb_measure stage=0 .*errors=0} $transcript] ||
        [regexp -all -line {^FEATURE_PASS } $transcript] != 7 ||
        [regexp -all -line {^MEASURE_CAPTURE_PASS } $transcript] != 9 ||
        [regexp -all -line {^MEASURE_RESET_PASS } $transcript] != 13 ||
        ![regexp -line {^MEASURE_CAPTURE_CONFIG_PASS invalid_arms=4 errors=0} $transcript] ||
        [regexp -line {^\s*(ERROR:|Fatal:|TEST_FAIL)} $transcript]} {error {Incomplete MEASURE project PASS}}
    smoke_project::audit [file join $report_directory project_audit.txt]
    puts {MEASURE_PROJECT_PASS features=7 frames=9 errors=0}
    close_project
} message options]} {
    puts stderr "MEASURE_PROJECT_FAIL $message"
    puts stderr [dict get $options -errorinfo]
    catch {close_sim}
    catch {close_project}
    exit 1
}
exit 0
