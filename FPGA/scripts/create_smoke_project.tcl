# Create/open the RTL project; the configured toolchain is Vivado 2025.2.
namespace eval smoke_project {
    variable fpga_root [file normalize [file join [file dirname [info script]] ..]]
    variable project_dir [file join $fpga_root project scope_smoke]
    if {[info exists ::env(SCOPE_NATIVE_PROJECT_DIR)]} {
        set project_dir [file normalize $::env(SCOPE_NATIVE_PROJECT_DIR)]
    }
    variable project_file [file join $project_dir scope_smoke.xpr]

    proc collect_hdl {directory} {
        set result {}
        foreach child [lsort [glob -nocomplain -directory $directory *]] {
            if {[file isdirectory $child]} {
                set result [concat $result [collect_hdl $child]]
            } elseif {[file extension $child] in {.sv .v}} {
                lappend result [file normalize $child]
            }
        }
        return $result
    }

    proc add_missing {fileset paths} {
        set existing {}
        foreach item [get_files -quiet -of_objects [get_filesets $fileset]] {
            lappend existing [file normalize $item]
        }
        set missing {}
        set systemverilog {}
        foreach path $paths {
            if {$path ni $existing} {
                lappend missing $path
            }
            if {[file extension $path] eq {.sv}} {
                lappend systemverilog $path
            }
        }
        if {[llength $missing]} {add_files -norecurse -fileset $fileset $missing}
        if {[llength $systemverilog]} {set_property file_type SystemVerilog [get_files $systemverilog]}
    }

    proc configure {} {
        variable fpga_root
        variable project_dir
        variable project_file
        if {[file exists $project_file]} {
            open_project $project_file
        } else {
            create_project scope_smoke $project_dir -part xc7a35tcsg324-1
        }
        if {[get_property PART [current_project]] ne {xc7a35tcsg324-1}} {
            error {Unexpected project part; temporary part must be xc7a35tcsg324-1}
        }
        if {[get_property BOARD_PART [current_project]] ne {}} {
            error {Board presets must not be selected}
        }
        set_property target_language Verilog [current_project]
        set_property simulator_language Mixed [current_project]
        set_property target_simulator XSim [current_project]
        # Batch regressions choose each top explicitly. Do not let an old IDE
        # hierarchy cache clear that selection before XSim compiles the files.
        set_property source_mgmt_mode None [current_project]

        set rtl_files [collect_hdl [file join $fpga_root rtl]]
        set package_paths {}
        foreach name {scope_pkg protocol_pkg multires_pkg fft_window_pkg spectrum_pkg innovation_pkg} {
            set path [file join $fpga_root rtl common ${name}.sv]
            if {[file exists $path]} {lappend package_paths $path}
        }
        set ordered_rtl $package_paths
        foreach path $rtl_files {if {$path ni $package_paths} {lappend ordered_rtl $path}}
        set rtl_files $ordered_rtl
        set sim_files [concat [collect_hdl [file join $fpga_root sim models]] \
                              [collect_hdl [file join $fpga_root sim tb]]]
        add_missing sources_1 $rtl_files
        add_missing sim_1 $sim_files
        foreach path $sim_files {
            set_property used_in_synthesis false [get_files $path]
            set_property used_in_implementation false [get_files $path]
            set_property used_in_simulation true [get_files $path]
        }
        set_property top smoke_counter [get_filesets sources_1]
        set_property top tb_smoke [get_filesets sim_1]
        set_property top_lib xil_defaultlib [get_filesets sim_1]
        # Finite upper bound; testbench also has a 50us fatal watchdog.
        set_property xsim.simulate.runtime 60us [get_filesets sim_1]
        audit
    }

    proc refresh_compile_order {args} {
        # Explicit package order was established in configure. Invoking the
        # automatic graph updater here can erase a deliberately selected test
        # top when unrelated roots/IP are also present in this multi-top project.
        if {[llength $args] != 2 || [lindex $args 0] ne {-fileset}} {
            error {refresh_compile_order expects -fileset <name>}
        }
        if {[llength [get_filesets -quiet [lindex $args 1]]] != 1} {
            error {Unknown compile-order fileset}
        }
        set_property source_mgmt_mode None [current_project]
    }

    proc audit {{output_file {}}} {
        variable fpga_root
        set design_files [get_files -quiet -of_objects [get_filesets sources_1]]
        set simulation_files [get_files -quiet -of_objects [get_filesets sim_1]]
        set constraints [get_files -quiet -of_objects [get_filesets constrs_1]]
        if {[llength $constraints] != 0} { error {Step 1 must not contain constraints} }
        if {[get_property DESIGN_MODE [get_filesets sources_1]] ne {RTL}} {
            error {Design mode must be RTL}
        }
        foreach path $design_files {
            set path [file normalize $path]
            if {![string match "[file join $fpga_root rtl]/*" $path] &&
                ![string match "[file join $fpga_root ip]/*" $path]} {
                error "Non-design file in Design Sources: $path"
            }
        }
        foreach path $simulation_files {
            if {[get_property USED_IN_SYNTHESIS $path] ||
                [get_property USED_IN_IMPLEMENTATION $path]} {
                error "Simulation-only file enabled for synthesis/implementation: $path"
            }
        }
        set synthesis_order [get_files -compile_order sources -used_in synthesis]
        foreach path $synthesis_order {
            if {![string match "[file join $fpga_root rtl]/*" [file normalize $path]] &&
                ![string match "[file join $fpga_root ip]/*" [file normalize $path]]} {
                error "Synthesis depends on simulation file: $path"
            }
        }
        if {$output_file ne {}} {
            set channel [open $output_file w]
            fconfigure $channel -encoding utf-8
            puts $channel "vivado_version=[version -short]"
            puts $channel "project=$smoke_project::project_file"
            puts $channel "part=[get_property PART [current_project]] (temporary)"
            puts $channel "board_part=[get_property BOARD_PART [current_project]]"
            puts $channel "design_mode=[get_property DESIGN_MODE [get_filesets sources_1]]"
            puts $channel "target_simulator=[get_property target_simulator [current_project]]"
            puts $channel "design_top=[get_property TOP [get_filesets sources_1]]"
            puts $channel "simulation_top=[get_property TOP [get_filesets sim_1]]"
            puts $channel "constraints=[llength $constraints]"
            puts $channel "DESIGN_SOURCES\n[join $design_files \n]"
            puts $channel "SIMULATION_ONLY_SOURCES\n[join $simulation_files \n]"
            puts $channel "SYNTHESIS_COMPILE_ORDER\n[join $synthesis_order \n]"
            close $channel
        }
        puts "PROJECT_AUDIT_PASS rtl=[llength $design_files] sim_only=[llength $simulation_files] constraints=0"
    }
}
if {![info exists ::scope_project_defer_configure] || !$::scope_project_defer_configure} {
    smoke_project::configure
}
