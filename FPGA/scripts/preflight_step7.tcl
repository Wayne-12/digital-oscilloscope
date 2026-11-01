open_project [file normalize [file join [file dirname [info script]] ../project/scope_smoke/scope_smoke.xpr]]
puts "STEP7_PREFLIGHT version=[version -short] part=[get_property PART [current_project]] board=[get_property BOARD_PART [current_project]] simulator=[get_property target_simulator [current_project]]"
foreach fs {sources_1 sim_1} {puts "$fs top=[get_property TOP [get_filesets $fs]] files=[llength [get_files -of_objects [get_filesets $fs]]]"}
puts "constraints=[llength [get_files -quiet -of_objects [get_filesets constrs_1]]]"
close_project
exit

