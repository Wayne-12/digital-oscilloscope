# Non-project resource proof; never changes the user's board project/XDC.
if {[llength $argv]!=2} {error {expected report_directory fpga_root}}
set out [file normalize [lindex $argv 0]]
set root [file normalize [lindex $argv 1]]
proc ram_counts {} {
    set b36 [llength [get_cells -quiet -hier -filter {REF_NAME =~ RAMB36*}]]
    set b18 [llength [get_cells -quiet -hier -filter {REF_NAME =~ RAMB18*}]]
    set lut [llength [get_cells -quiet -hier -filter {REF_NAME =~ RAM* && REF_NAME !~ RAMB*}]]
    return [list $b36 $b18 $lut]
}
if {[catch {
    create_project -in_memory -part xc7a35tcsg324-1
    foreach rel {rtl/common/scope_pkg.sv rtl/trigger/trigger_edge.sv rtl/capture/capture_bram.sv rtl/capture/bram_capture.sv} {
        read_verilog -sv [file join $root $rel]
    }
    synth_design -top bram_capture -part xc7a35tcsg324-1 -mode out_of_context
    report_utilization -file [file join $out utilization.txt]
    lassign [ram_counts] core36 core18 corelut
    # 12 raw bits + OTR are dynamic; three reserved zero columns are optimized.
    if {2*$core36+$core18!=13 || $corelut!=0} {error {capture core dynamic BRAM columns mismatch}}
    close_project
    create_project -in_memory -part xc7a35tcsg324-1
    foreach rel {rtl/common/scope_pkg.sv rtl/capture/capture_bram.sv} {
        read_verilog -sv [file join $root $rel]
    }
    synth_design -top capture_bram -part xc7a35tcsg324-1 -mode out_of_context
    report_utilization -file [file join $out ram_template_utilization.txt]
    lassign [ram_counts] ram36 ram18 ramlut
    if {2*$ram36+$ram18!=16 || $ramlut!=0} {error {standalone 16384x16 BRAM template mismatch}}
    set fd [open [file join $out resources.json] w]
    puts $fd [format {{"logical_depth":16384,"logical_width":16,"core_dynamic_bits":13,"core":{"bram36":%d,"bram18":%d,"lutram":%d},"ram_template":{"bram36":%d,"bram18":%d,"lutram":%d}}} $core36 $core18 $corelut $ram36 $ram18 $ramlut]
    close $fd
    puts "CAPTURE_BRAM_SYNTH_PASS core_bram36=$core36 core_bram18=$core18 ram_bram36=$ram36 ram_bram18=$ram18 lutram=0"
    close_project
} message options]} {
    puts stderr "CAPTURE_BRAM_SYNTH_FAIL $message"
    puts stderr [dict get $options -errorinfo]
    catch {close_project}
    exit 1
}
exit 0
