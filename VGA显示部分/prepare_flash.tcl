# Generate power-on SPI images from the accepted routed design and final ELF.
set panel [file normalize [file dirname [info script]]]
set out [file join $panel output]
set release [file join $panel release]
file mkdir $release
open_checkpoint [file join $out cpu_vga_routed.dcp]
if {[get_property PART [current_design]] ne {xc7a35tcsg324-1}} {error {Unexpected FPGA}}
set_property CONFIG_MODE SPIx1 [current_design]
set_property BITSTREAM.CONFIG.SPI_BUSWIDTH 1 [current_design]
set_property BITSTREAM.CONFIG.CONFIGRATE 3 [current_design]
set_property BITSTREAM.STARTUP.STARTUPCLK CCLK [current_design]
report_property [current_design] -file [file join $release flash_design_properties.rpt]
set raw [file join $release display_flash_unpatched.bit]
set final [file join $release display_final.bit]
write_bitstream -force $raw
set binary [file normalize [file join [file dirname [info nameofexecutable]] .. ..]]
puts [exec [file join $binary updatemem.bat] -force -meminfo [file join $out cpu_memory.mmi] \
 -data [file join $out panel.elf] -bit $raw -proc uart/cpu/inst/microblaze_I -out $final 2>@1]
foreach format {mcs bin} {
 write_cfgmem -force -format $format -size 8 -interface SPIx1 \
  -loadbit [list up 0x00000000 $final] -file [file join $release display_final.$format]
}
file delete $raw
puts {PANEL_FLASH_PREPARE_PASS}
exit 0
