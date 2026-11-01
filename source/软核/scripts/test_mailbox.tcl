set root [file normalize [file join [file dirname [info script]] ..]]
set binary [file normalize [file join [file dirname [info nameofexecutable]] .. ..]]
cd [file join $root build]
foreach {tool args} [list xvlog [list -sv ../integration/rtl/uart_proto/byte_fifo.sv ../rtl/scope_cpu_mailbox.sv ../tests/tb_mailbox.sv] xelab [list tb_mailbox -s mailbox_sim] xsim [list mailbox_sim -runall]] {
 set command [linsert $args 0 [file join $binary ${tool}.bat]]
 if {[catch {exec {*}$command 2>@1} result]} {puts $result;error "SIM_TOOL_FAILED $tool"}
 set f [open [file join $root reports ${tool}_mailbox.txt] w];puts $f $result;close $f
 if {$tool eq "xsim" && ![string match {*MAILBOX_TEST_PASS*} $result]} {error "MAILBOX_TEST_FAILED"}
 puts "OFFLINE_PASS $tool"
}
exit
