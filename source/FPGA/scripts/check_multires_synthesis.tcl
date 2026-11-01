if {[llength $argv]!=2} {error {expected output_directory staged_fpga_root}}
set out [file normalize [lindex $argv 0]];set root [file normalize [lindex $argv 1]]
if {[catch {
    create_project -in_memory -part xc7a35tcsg324-1
    foreach rel {rtl/common/scope_pkg.sv rtl/common/multires_pkg.sv rtl/measure/measure_udiv.sv rtl/multires/multires_envelope.sv} {read_verilog -sv [file join $root $rel]}
    synth_design -top multires_envelope -part xc7a35tcsg324-1 -mode out_of_context
    report_utilization -file [file join $out multires_envelope_utilization.txt]
    set latches [llength [get_cells -quiet -hier -filter {REF_NAME =~ LD*}]]
    set lut [llength [get_cells -quiet -hier -filter {REF_NAME =~ LUT*}]]
    set ff [llength [get_cells -quiet -hier -filter {REF_NAME =~ FD*}]]
    set dsp [llength [get_cells -quiet -hier -filter {REF_NAME =~ DSP*}]]
    set ram [llength [get_cells -quiet -hier -filter {REF_NAME =~ RAM*}]]
    set index_pins [llength [get_ports -quiet {sample_index[*]}]]
    if {$latches!=0 || $dsp!=0 || $ram!=0 || $index_pins!=18} {error {Unexpected latch, multiplier, frame storage or narrow read index}}
    set f [open [file join $out resources.json] w]
    puts $f [format {[{"top":"multires_envelope","lut":%d,"ff":%d,"dsp":%d,"ram":%d,"latches":%d,"index_bits":%d}]} $lut $ff $dsp $ram $latches $index_pins];close $f
    puts "MULTIRES_OOC_TOP_PASS top=multires_envelope lut=$lut ff=$ff dsp=0 ram=0 latches=0 index_bits=18"
    close_project;puts {MULTIRES_OOC_SYNTH_PASS tops=1 latches=0}
} message options]} {
    puts stderr "MULTIRES_OOC_SYNTH_FAIL $message";puts stderr [dict get $options -errorinfo];catch {close_project};exit 1
}
exit 0
