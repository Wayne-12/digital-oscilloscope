# Upgrade the existing project in place after the caller has backed it up.
# Arguments: report_directory [revision_control_helper_tcl]
if {[llength $argv] < 1 || [llength $argv] > 2} {
    puts stderr {Usage: migrate_vivado_2025_2.tcl report_directory [helper_scripts.tcl]}
    exit 1
}
set report_directory [file normalize [lindex $argv 0]]
file mkdir $report_directory
if {[catch {
    if {[version -short] ne {2025.2}} { error {Migration requires Vivado 2025.2} }
    if {[llength [get_parts -quiet xc7a35tcsg324-1]] != 1} {
        error {The temporary Artix-7 part xc7a35tcsg324-1 is not installed}
    }
    set ::scope_project_defer_configure 1
    source [file join [file dirname [info script]] create_smoke_project.tcl]
    open_project $smoke_project::project_file
    set design_top [get_property TOP [get_filesets sources_1]]
    set simulation_top [get_property TOP [get_filesets sim_1]]
    set_property target_simulator XSim [current_project]
    update_compile_order -fileset sources_1
    update_compile_order -fileset sim_1
    smoke_project::audit [file join $report_directory project_audit.txt]
    if {[llength $argv] == 2} {
        source [file normalize [lindex $argv 1]]
        capture_project_settings [file join $report_directory project_settings.tcl]
    }
    write_project_tcl -force [file join $report_directory recreate_project.tcl]
    close_project
    # Reopen the saved XPR to check persisted settings, rather than session state.
    open_project $smoke_project::project_file
    if {[get_property TOP [get_filesets sources_1]] ne $design_top ||
        [get_property TOP [get_filesets sim_1]] ne $simulation_top} {
        error {Project top modules changed while saving the upgraded project}
    }
    if {[get_property PART [current_project]] ne {xc7a35tcsg324-1} ||
        [get_property BOARD_PART [current_project]] ne {}} {
        error {Temporary part or board selection changed}
    }
    smoke_project::audit [file join $report_directory reopened_project_audit.txt]
    puts "PROJECT_MIGRATION_PASS vivado=[version -short] design_top=$design_top simulation_top=$simulation_top"
    close_project
} message options]} {
    puts stderr "PROJECT_MIGRATION_FAIL $message"
    puts stderr [dict get $options -errorinfo]
    catch {close_project}
    exit 1
}
exit 0
