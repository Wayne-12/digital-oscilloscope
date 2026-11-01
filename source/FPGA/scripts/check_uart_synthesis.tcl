if {[llength $argv]!=2} {error {expected output_directory staged_fpga_root}}
set out [file normalize [lindex $argv 0]];set root [file normalize [lindex $argv 1]]
if {[catch {
    set records {}
    foreach top {uart_transport scope_uart_endpoint} {
        create_project -in_memory -part xc7a35tcsg324-1
        foreach rel {rtl/common/scope_pkg.sv rtl/common/multires_pkg.sv rtl/common/protocol_pkg.sv rtl/measure/measure_udiv.sv rtl/multires/multires_envelope.sv} {read_verilog -sv [file join $root $rel]}
        foreach p [lsort [glob [file join $root rtl uart_proto *.sv]]] {read_verilog -sv $p}
        synth_design -top $top -part xc7a35tcsg324-1 -mode out_of_context
        report_utilization -file [file join $out ${top}_utilization.txt]
        set latches [llength [get_cells -quiet -hier -filter {REF_NAME =~ LD*}]]
        set lut [llength [get_cells -quiet -hier -filter {REF_NAME =~ LUT*}]]
        set ff [llength [get_cells -quiet -hier -filter {REF_NAME =~ FD*}]]
        set b36 [llength [get_cells -quiet -hier -filter {REF_NAME =~ RAMB36*}]]
        set b18 [llength [get_cells -quiet -hier -filter {REF_NAME =~ RAMB18*}]]
        set lutram [llength [get_cells -quiet -hier -filter {REF_NAME =~ RAM* && REF_NAME !~ RAMB*}]]
        if {$latches!=0} {error "Latch inferred in $top"}
        lappend records [format {{"top":"%s","lut":%d,"ff":%d,"bram36":%d,"bram18":%d,"lutram":%d,"latches":%d}} $top $lut $ff $b36 $b18 $lutram $latches]
        puts "UART_OOC_TOP_PASS top=$top lut=$lut ff=$ff latches=$latches"
        close_project
    }
    set f [open [file join $out resources.json] w];puts $f [format {[%s]} [join $records ,]];close $f
    puts {UART_OOC_SYNTH_PASS tops=2 latches=0}
} message options]} {
    puts stderr "UART_OOC_SYNTH_FAIL $message";puts stderr [dict get $options -errorinfo];catch {close_project};exit 1
}
exit 0
