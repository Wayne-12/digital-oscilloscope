if {[llength $argv]!=2} {error {expected output_directory staged_fpga_root}}
set out [file normalize [lindex $argv 0]];set root [file normalize [lindex $argv 1]]
if {[catch {
    create_project -in_memory -part xc7a35tcsg324-1
    set_property target_language Verilog [current_project]
    set ::scope_fft_output_root [file join $root ip]
    source [file join $root scripts ensure_scope_fft_ip.tcl]
    synth_ip [get_ips scope_fft_1024]
    foreach rel {rtl/common/fft_window_pkg.sv rtl/common/spectrum_pkg.sv rtl/measure/fft_hann_lut.sv rtl/measure/fft_ip_wrapper.sv rtl/measure/spectrum_isqrt.sv rtl/measure/spectrum_analyzer.sv} {read_verilog -sv [file join $root $rel]}
    synth_design -top spectrum_analyzer -part xc7a35tcsg324-1 -mode out_of_context
    report_utilization -file [file join $out spectrum_analyzer_utilization.txt]
    set latches [llength [get_cells -quiet -hier -filter {REF_NAME =~ LD*}]]
    set lut [llength [get_cells -quiet -hier -filter {REF_NAME =~ LUT*}]]
    set ff [llength [get_cells -quiet -hier -filter {REF_NAME =~ FD*}]]
    set dsp [llength [get_cells -quiet -hier -filter {REF_NAME =~ DSP*}]]
    set ram [llength [get_cells -quiet -hier -filter {REF_NAME =~ RAM*}]]
    set blackboxes [llength [get_cells -quiet -hier -filter {IS_BLACKBOX == 1}]]
    if {$latches!=0 || $blackboxes!=0 || $dsp==0 || $ram==0} {error "Unexpected implementation: latches=$latches blackboxes=$blackboxes dsp=$dsp ram=$ram"}
    write_checkpoint -force [file join $out spectrum_analyzer.dcp]
    set f [open [file join $out resources.json] w]
    puts $f [format {{"top":"spectrum_analyzer","lut":%d,"ff":%d,"dsp":%d,"ram":%d,"latches":%d,"blackboxes":%d}} $lut $ff $dsp $ram $latches $blackboxes];close $f
    puts "SPECTRUM_OOC_SYNTH_PASS lut=$lut ff=$ff dsp=$dsp ram=$ram latches=0 blackboxes=0"
    close_project
} message options]} {
    puts stderr "SPECTRUM_OOC_SYNTH_FAIL $message";puts stderr [dict get $options -errorinfo];catch {close_project};exit 1
}
exit 0
