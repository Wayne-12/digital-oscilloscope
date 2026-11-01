if {[llength $argv]!=1} {error {expected report_directory}}
set out [file normalize [lindex $argv 0]]
open_project [file normalize [file join [file dirname [info script]] ../project/scope_smoke/scope_smoke.xpr]]
puts "STEP11_PREFLIGHT version=[version -short] part=[get_property PART [current_project]] board=[get_property BOARD_PART [current_project]] simulator=[get_property target_simulator [current_project]]"
foreach fs {sources_1 sim_1} {puts "$fs top=[get_property TOP [get_filesets $fs]] files=[llength [get_files -of_objects [get_filesets $fs]]]"}
puts "constraints=[llength [get_files -quiet -of_objects [get_filesets constrs_1]]]"
set defs [get_ipdefs -all xilinx.com:ip:xfft:9.1]
if {[llength $defs]!=1} {error {FFT 9.1 IP definition not uniquely available}}
report_property -all [lindex $defs 0] -file [file join $out fft_catalog.txt]
puts "STEP11_FFT_CATALOG_PASS ip=[lindex $defs 0]"
close_project
exit 0
