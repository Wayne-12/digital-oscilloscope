# VGA observer: same 25 MHz clock as production acquisition.
set_property -dict {PACKAGE_PIN D7 IOSTANDARD LVCMOS33} [get_ports vga_hsync]
set_property -dict {PACKAGE_PIN C4 IOSTANDARD LVCMOS33} [get_ports vga_vsync]
set_property -dict {PACKAGE_PIN F5 IOSTANDARD LVCMOS33} [get_ports {vga_r[0]}]
set_property -dict {PACKAGE_PIN C6 IOSTANDARD LVCMOS33} [get_ports {vga_r[1]}]
set_property -dict {PACKAGE_PIN C5 IOSTANDARD LVCMOS33} [get_ports {vga_r[2]}]
set_property -dict {PACKAGE_PIN B7 IOSTANDARD LVCMOS33} [get_ports {vga_r[3]}]
set_property -dict {PACKAGE_PIN B6 IOSTANDARD LVCMOS33} [get_ports {vga_g[0]}]
set_property -dict {PACKAGE_PIN A6 IOSTANDARD LVCMOS33} [get_ports {vga_g[1]}]
set_property -dict {PACKAGE_PIN A5 IOSTANDARD LVCMOS33} [get_ports {vga_g[2]}]
set_property -dict {PACKAGE_PIN D8 IOSTANDARD LVCMOS33} [get_ports {vga_g[3]}]
set_property -dict {PACKAGE_PIN C7 IOSTANDARD LVCMOS33} [get_ports {vga_b[0]}]
set_property -dict {PACKAGE_PIN E6 IOSTANDARD LVCMOS33} [get_ports {vga_b[1]}]
set_property -dict {PACKAGE_PIN E5 IOSTANDARD LVCMOS33} [get_ports {vga_b[2]}]
set_property -dict {PACKAGE_PIN E7 IOSTANDARD LVCMOS33} [get_ports {vga_b[3]}]
set_property SLEW SLOW [get_ports {vga_hsync vga_vsync vga_r[*] vga_g[*] vga_b[*]}]
set_property DRIVE 8 [get_ports {vga_hsync vga_vsync vga_r[*] vga_g[*] vga_b[*]}]
set_output_delay -clock [get_clocks -of_objects [get_pins video_clock/mmcm/CLKOUT0]] -max 10.0 [get_ports {vga_hsync vga_vsync vga_r[*] vga_g[*] vga_b[*]}]
set_output_delay -clock [get_clocks -of_objects [get_pins video_clock/mmcm/CLKOUT0]] -min 0.0 [get_ports {vga_hsync vga_vsync vga_r[*] vga_g[*] vga_b[*]}]
set_property -dict {PACKAGE_PIN N4 IOSTANDARD LVCMOS33} [get_ports {vga_switches[0]}]
set_property -dict {PACKAGE_PIN M4 IOSTANDARD LVCMOS33} [get_ports {vga_switches[1]}]
set_property -dict {PACKAGE_PIN R2 IOSTANDARD LVCMOS33} [get_ports {vga_switches[2]}]
set_property -dict {PACKAGE_PIN P2 IOSTANDARD LVCMOS33} [get_ports {vga_switches[3]}]
set_false_path -from [get_ports {vga_switches[*]}]
set_property -dict {PACKAGE_PIN P5 IOSTANDARD LVCMOS33} [get_ports {vga_switches[4]}]
set_property -dict {PACKAGE_PIN R11 IOSTANDARD LVCMOS33} [get_ports {panel_buttons[0]}]
set_property -dict {PACKAGE_PIN R17 IOSTANDARD LVCMOS33} [get_ports {panel_buttons[1]}]
set_property -dict {PACKAGE_PIN R15 IOSTANDARD LVCMOS33} [get_ports {panel_buttons[2]}]
set_property -dict {PACKAGE_PIN V1 IOSTANDARD LVCMOS33} [get_ports {panel_buttons[3]}]
set_property -dict {PACKAGE_PIN U4 IOSTANDARD LVCMOS33} [get_ports {panel_buttons[4]}]
set_false_path -from [get_ports {panel_buttons[*]}]
# Toggle synchronizers: only cut each first metastability-catching stage.
# The second stage remains timed at its destination clock.
set toggle_first_stages [get_pins -hier -regexp {screen/(req_sync|ack_sync|ui_req_sync|ui_ack_sync)_reg\[0\]/D}]
set_false_path -to $toggle_first_stages

# Bundled record metadata is immutable before request and until ack returns.
# Require physical arrival within one 49 MHz period, before the synchronized
# request can enable a frame-boundary latch. No blanket asynchronous clock cut.
set_max_delay -datapath_only 18.0 -from [get_cells -hier -filter {NAME =~ screen/saved*_reg*}] -to [get_cells -hier -filter {NAME =~ screen/shown*_reg*}]

