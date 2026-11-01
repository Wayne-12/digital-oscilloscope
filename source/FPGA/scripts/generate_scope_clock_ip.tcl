# Isolated native IP generation avoids the observed 2024.2 template writer
# failure in a non-ASCII output directory. Products are copied back by PS.
if {[llength $argv] != 1} { puts stderr {Usage: generate_scope_clock_ip.tcl ascii_build_directory}; exit 1 }
set build_directory [file normalize [lindex $argv 0]]
if {[regexp {[^\x00-\x7f]} $build_directory]} { puts stderr {IP build path must be ASCII}; exit 1 }
if {[catch {
    create_project -in_memory -part xc7a35tcsg324-1
    set ::scope_clock_output_root [file join $build_directory ip]
    set ::scope_clock_generate_products 1
    source [file join [file dirname [info script]] ensure_scope_clock_ip.tcl]
    puts {CLOCK_IP_GENERATION_PASS}
    close_project
} error_message error_options]} {
    puts stderr "CLOCK_IP_GENERATION_FAIL $error_message"
    puts stderr [dict get $error_options -errorinfo]
    catch {close_project}
    exit 1
}
exit 0
