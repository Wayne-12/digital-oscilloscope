if {[llength $argv]!=2} {error {expected output_directory staged_root}}
set out [file normalize [lindex $argv 0]];set root [file normalize [lindex $argv 1]]
set records {}
if {[catch {
    foreach top {relative_calibrator calibration_apply health_compare capture_moments capture_result_stream capture_result_uart} {
        create_project -in_memory -part xc7a35tcsg324-1
        foreach rel {rtl/common/scope_pkg.sv rtl/common/multires_pkg.sv rtl/common/protocol_pkg.sv rtl/common/innovation_pkg.sv rtl/measure/measure_udiv.sv rtl/uart_proto/frame_tx.sv rtl/innovation/relative_calibrator.sv rtl/innovation/calibration_apply.sv rtl/innovation/health_compare.sv rtl/innovation/capture_moments.sv rtl/innovation/capture_result_stream.sv rtl/innovation/capture_result_uart.sv} {read_verilog -sv [file join $root $rel]}
        synth_design -top $top -part xc7a35tcsg324-1 -mode out_of_context
        report_utilization -file [file join $out ${top}_utilization.txt]
        set latches [llength [get_cells -quiet -hier -filter {REF_NAME =~ LD*}]]
        set blackboxes [llength [get_cells -quiet -hier -filter {IS_BLACKBOX == 1}]]
        set lut [llength [get_cells -quiet -hier -filter {REF_NAME =~ LUT*}]]
        set ff [llength [get_cells -quiet -hier -filter {REF_NAME =~ FD*}]]
        set dsp [llength [get_cells -quiet -hier -filter {REF_NAME =~ DSP*}]]
        set ram [llength [get_cells -quiet -hier -filter {REF_NAME =~ RAM*}]]
        if {$latches!=0 || $blackboxes!=0} {error "Invalid netlist $top"}
        lappend records [format {{"top":"%s","lut":%d,"ff":%d,"dsp":%d,"ram":%d,"latches":0,"blackboxes":0}} $top $lut $ff $dsp $ram]
        puts "INNOVATION_OOC_TOP_PASS top=$top lut=$lut ff=$ff dsp=$dsp ram=$ram latches=0 blackboxes=0"
        close_project
    }
    set f [open [file join $out resources.json] w];puts $f "\[[join $records ,]\]";close $f
    puts {INNOVATION_OOC_SYNTH_PASS tops=6 latches=0 blackboxes=0}
} message options]} {
    puts stderr "INNOVATION_OOC_SYNTH_FAIL $message";puts stderr [dict get $options -errorinfo];catch {close_project};exit 1
}
exit 0
