# Vivado 2025.2 native OOC analysis. No implementation or board pin constraints.
if {[llength $argv] != 3} {error {expected top output_directory staged_fpga_root}}
lassign $argv top out root
file mkdir $out
proc collect_sv {directory} {
    set result {}
    foreach p [lsort [glob -nocomplain -directory $directory *]] {
        if {[file isdirectory $p]} {set result [concat $result [collect_sv $p]]
        } elseif {[file extension $p] eq {.sv}} {lappend result $p}
    }
    return $result
}
if {[catch {
    set_param general.maxThreads 4
    create_project -in_memory -part xc7a35tcsg324-1
    set_property target_language Verilog [current_project]
    if {$top eq {scope_hw_top}} {
        set ::scope_clock_output_root [file join $root ip]
        set ::scope_clock_generate_products 1
        set ::scope_clock_plain_hdl 1
        source [file join $root scripts ensure_scope_clock_ip.tcl]
    }
    if {$top eq {spectrum_analyzer}} {
        set ::scope_fft_output_root [file join $root ip]
        source [file join $root scripts ensure_scope_fft_ip.tcl]
        synth_ip [get_ips scope_fft_1024]
    }
    set packages {}
    foreach n {scope_pkg protocol_pkg multires_pkg fft_window_pkg spectrum_pkg innovation_pkg} {
        set p [file join $root rtl common ${n}.sv]
        read_verilog -sv $p
        lappend packages $p
    }
    foreach p [collect_sv [file join $root rtl]] {
        if {$p ni $packages} {read_verilog -sv $p}
    }
    set generics {}
    if {$top eq {bram_capture}} {set generics {USE_EXTENDED_TRIGGER=1}}
    if {$top eq {scope_dds_rate_adapter}} {set generics {DAC_RATE_HZ=10000000}}
    set args [list -top $top -part xc7a35tcsg324-1 -mode out_of_context -flatten_hierarchy rebuilt]
    if {[llength $generics]} {lappend args -generic $generics}
    synth_design {*}$args
    if {$top eq {scope_hw_top}} {
        read_xdc [file join $root constraints scope_estimate_template.xdc]
    } else {
        # Independent domains are intentionally not declared synchronous or
        # hidden by set_clock_groups/false paths. CDC remains visible.
        foreach name {clk clk_sys clk_sample clk_adc clk_dac clk_memory write_clk read_clk} {
            set p [get_ports -quiet $name]
            if {[llength $p]} {
                set period 10.000
                if {$name in {clk_sample clk_adc clk_dac write_clk}} {set period 40.000}
                create_clock -name $name -period $period $p
            }
        }
    }
    report_utilization -file [file join $out utilization.rpt]
    report_utilization -hierarchical -file [file join $out hierarchy.rpt]
    report_clocks -file [file join $out clocks.rpt]
    report_clock_interaction -file [file join $out clock_interaction.rpt]
    report_cdc -details -file [file join $out cdc.rpt]
    report_methodology -file [file join $out methodology.rpt]
    report_timing_summary -report_unconstrained -file [file join $out timing_estimate.rpt]
    set checks [get_drc_checks -quiet {MDRV-1 LUTLP-1}]
    if {[llength $checks] != 2} {error {Required MDRV/LUTLP structural checks unavailable}}
    report_drc -checks $checks -file [file join $out structural_drc.rpt]
    set violations [get_drc_violations -quiet]
    set latches [llength [get_cells -quiet -hier -filter {REF_NAME =~ LD*}]]
    set blackboxes [llength [get_cells -quiet -hier -filter {IS_BLACKBOX == 1}]]
    set clock_bad {}
    set fd [open [file join $out clock_drivers.tsv] w]
    puts $fd "clock_pin\tnet\tdriver\tref_name"
    foreach pin [get_pins -quiet -hier -filter {IS_CLOCK == 1 && DIRECTION == IN}] {
        set net [get_nets -quiet -of_objects $pin]
        foreach driver [get_pins -quiet -leaf -of_objects $net -filter {DIRECTION == OUT}] {
            set cell [get_cells -quiet -of_objects $driver]
            set ref [get_property REF_NAME $cell]
            puts $fd "$pin\t$net\t$driver\t$ref"
            if {[string match LUT* $ref] || [string match FD* $ref]} {lappend clock_bad $pin}
        }
    }
    close $fd
    set f [open [file join $out resources.json] w]
    puts $f [format {{"top":"%s","lut_logic_cells":%d,"ff":%d,"dsp":%d,"bram36":%d,"bram18":%d,"lutram_cells":%d,"latches":%d,"blackboxes":%d,"structural_drc":%d,"fabric_clock_drivers":%d,"synchronizer_flops":%d}} $top \
        [llength [get_cells -quiet -hier -filter {REF_NAME =~ LUT*}]] \
        [llength [get_cells -quiet -hier -filter {REF_NAME =~ FD*}]] \
        [llength [get_cells -quiet -hier -filter {REF_NAME =~ DSP*}]] \
        [llength [get_cells -quiet -hier -filter {REF_NAME =~ RAMB36*}]] \
        [llength [get_cells -quiet -hier -filter {REF_NAME =~ RAMB18*}]] \
        [llength [get_cells -quiet -hier -filter {REF_NAME =~ RAM* && REF_NAME !~ RAMB*}]] \
        $latches $blackboxes [llength $violations] [llength $clock_bad] \
        [llength [get_cells -quiet -hier -filter {ASYNC_REG == TRUE}]]]
    close $f
    write_checkpoint -force [file join $out ${top}.dcp]
    write_xdc -force -exclude_physical [file join $out applied_estimate.xdc]
    if {$latches || $blackboxes || [llength $violations] || [llength $clock_bad]} {
        error "STRUCTURE_FAIL latch=$latches blackbox=$blackboxes drc=[llength $violations] fabric_clock=[llength $clock_bad]"
    }
    puts "PROVISIONAL_OOC_PASS top=$top"
    close_project
} message options]} {
    puts stderr "PROVISIONAL_OOC_FAIL top=$top $message"
    puts stderr [dict get $options -errorinfo]
    catch {close_project}
    exit 1
}
exit 0
