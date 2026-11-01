# Args: report_directory vector_directory trace_directory seed
if {[llength $argv]!=4} {puts stderr {UART_PROJECT_FAIL expected four arguments};exit 1}
set report [file normalize [lindex $argv 0]]
if {[catch {
    source [file join [file dirname [info script]] create_smoke_project.tcl]
    set ::scope_clock_plain_hdl 1
    source [file join [file dirname [info script]] ensure_scope_clock_ip.tcl]
    set_property top scope_hw_top [get_filesets sources_1]
    set options [format {-sv_seed %s -testplusarg "SEED=%s" -testplusarg "VECTOR_DIR=%s" -testplusarg "TRACE_DIR=."} [lindex $argv 3] [lindex $argv 3] [file normalize [lindex $argv 1]]]
    set_property -name xsim.simulate.xsim.more_options -value $options -objects [get_filesets sim_1]
    file mkdir [file normalize [lindex $argv 2]]
    foreach top {tb_uart_bits tb_uart_bytes} {
        set_property top $top [get_filesets sim_1]
        set_property xsim.simulate.runtime 1s [get_filesets sim_1]
        smoke_project::refresh_compile_order -fileset sources_1
        smoke_project::refresh_compile_order -fileset sim_1
        launch_simulation -simset sim_1 -mode behavioral
        close_sim
        set simdir [file join $smoke_project::project_dir scope_smoke.sim sim_1 behav xsim]
        foreach name {xvlog.log elaborate.log simulate.log} {
            file copy -force [file join $simdir $name] [file join $report ${top}.${name}]
        }
        set f [open [file join $report ${top}.simulate.log] r];set transcript [read $f];close $f
        if {![regexp -line "^TEST_PASS $top .*errors=0" $transcript] || [regexp -line {^\s*(ERROR:|Fatal:|TEST_FAIL)} $transcript]} {error "Incomplete PASS: $top"}
        set trace [expr {$top eq {tb_uart_bits}?{uart_bits.hex}:{uart_bytes.hex}}]
        file copy -force [file join $simdir $trace] [file join [file normalize [lindex $argv 2]] $trace]
    }
    smoke_project::audit [file join $report project_audit.txt]
    puts {UART_PROJECT_PASS tops=2 errors=0}
    close_project
} message options]} {
    puts stderr "UART_PROJECT_FAIL $message";puts stderr [dict get $options -errorinfo]
    catch {close_sim};catch {close_project};exit 1
}
exit 0
