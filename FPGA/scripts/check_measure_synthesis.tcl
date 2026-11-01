# OOC synthesis only: no pin assignment, board preset, or implementation claim.
if {[llength $argv]!=2} {error {expected report_directory staged_fpga_root}}
set out [file normalize [lindex $argv 0]]
set root [file normalize [lindex $argv 1]]
if {[catch {
    set records {}
    foreach top {measurement_core trigger_core bram_capture} {
        create_project -in_memory -part xc7a35tcsg324-1
        foreach rel {rtl/common/scope_pkg.sv rtl/trigger/trigger_edge.sv rtl/trigger/trigger_core.sv rtl/capture/capture_bram.sv rtl/capture/bram_capture.sv rtl/measure/measure_udiv.sv rtl/measure/measurement_core.sv} {
            read_verilog -sv [file join $root $rel]
        }
        if {$top eq {bram_capture}} {
            synth_design -top $top -generic USE_EXTENDED_TRIGGER=1 -part xc7a35tcsg324-1 -mode out_of_context
        } else {
            synth_design -top $top -part xc7a35tcsg324-1 -mode out_of_context
        }
        report_utilization -file [file join $out ${top}_utilization.txt]
        set latches [llength [get_cells -quiet -hier -filter {REF_NAME =~ LD*}]]
        set lut [llength [get_cells -quiet -hier -filter {REF_NAME =~ LUT*}]]
        set ff [llength [get_cells -quiet -hier -filter {REF_NAME =~ FD*}]]
        set dsp [llength [get_cells -quiet -hier -filter {REF_NAME =~ DSP*}]]
        set b36 [llength [get_cells -quiet -hier -filter {REF_NAME =~ RAMB36*}]]
        set b18 [llength [get_cells -quiet -hier -filter {REF_NAME =~ RAMB18*}]]
        set lutram [llength [get_cells -quiet -hier -filter {REF_NAME =~ RAM* && REF_NAME !~ RAMB*}]]
        if {$latches!=0} {error "Latch inferred in $top"}
        if {$top eq {bram_capture} && (2*$b36+$b18!=13 || $lutram!=0)} {error {Extended capture BRAM inference mismatch}}
        lappend records [format {{"top":"%s","lut":%d,"ff":%d,"dsp":%d,"bram36":%d,"bram18":%d,"lutram":%d,"latches":%d}} $top $lut $ff $dsp $b36 $b18 $lutram $latches]
        puts "MEASURE_OOC_TOP_PASS top=$top lut=$lut ff=$ff dsp=$dsp bram36=$b36 bram18=$b18 latches=$latches"
        close_project
    }
    set fd [open [file join $out resources.json] w]
    puts $fd [format {[%s]} [join $records ,]]
    close $fd
    puts {MEASURE_OOC_SYNTH_PASS tops=3 latches=0}
} message options]} {
    puts stderr "MEASURE_OOC_SYNTH_FAIL $message"
    puts stderr [dict get $options -errorinfo]
    catch {close_project}
    exit 1
}
exit 0
