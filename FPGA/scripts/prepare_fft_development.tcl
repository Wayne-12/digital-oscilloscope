if {[llength $argv]!=2} {error {expected ASCII_build_directory source_fpga_root}}
set stage [file normalize [lindex $argv 0]];set root [file normalize [lindex $argv 1]]
if {[catch {
    create_project -in_memory -part xc7a35tcsg324-1
    set_property target_language Verilog [current_project]
    set_property simulator_language Mixed [current_project]
    set ::scope_fft_output_root [file join $stage ip]
    source [file join $root scripts ensure_scope_fft_ip.tcl]
    report_property -all [get_ips scope_fft_1024] -file [file join $stage fft_properties.txt]
    export_simulation -of_objects [get_ips scope_fft_1024] -simulator xsim -directory [file join $stage export] -force
    report_ip_status -file [file join $stage fft_ip_status.txt]
    puts {FFT_PREPARE_PASS};close_project
} message options]} {
    puts stderr "FFT_PREPARE_FAIL $message";puts stderr [dict get $options -errorinfo];catch {close_project};exit 1
}
exit 0
