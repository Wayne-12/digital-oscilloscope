# Physical wiring: project plan sections 6.2 and 6.3, confirmed by user.
# External timing assumes <=2 ns per-direction wiring/board skew budget.
# This budget must be re-evaluated before using longer wires or faster clocks.
set_property -dict {PACKAGE_PIN P17 IOSTANDARD LVCMOS33} [get_ports sys_clk_100]
set_property -dict {PACKAGE_PIN P15 IOSTANDARD LVCMOS33 PULLUP TRUE} [get_ports reset_n]
# SW0 as named in the hardware manual (the vendor XDC reverses its array order).
set_property -dict {PACKAGE_PIN R1 IOSTANDARD LVCMOS33} [get_ports module_switch]
set_property -dict {PACKAGE_PIN N5 IOSTANDARD LVCMOS33 PULLUP TRUE} [get_ports fpga_uart_rx_n5]
set_property -dict {PACKAGE_PIN T4 IOSTANDARD LVCMOS33 SLEW SLOW DRIVE 8} [get_ports fpga_uart_tx_t4]
set_property -dict {PACKAGE_PIN B16 IOSTANDARD LVCMOS33} [get_ports {adc_data[0]}]
set_property -dict {PACKAGE_PIN B17 IOSTANDARD LVCMOS33} [get_ports {adc_data[1]}]
set_property -dict {PACKAGE_PIN A15 IOSTANDARD LVCMOS33} [get_ports {adc_data[2]}]
set_property -dict {PACKAGE_PIN A16 IOSTANDARD LVCMOS33} [get_ports {adc_data[3]}]
set_property -dict {PACKAGE_PIN A13 IOSTANDARD LVCMOS33} [get_ports {adc_data[4]}]
set_property -dict {PACKAGE_PIN A14 IOSTANDARD LVCMOS33} [get_ports {adc_data[5]}]
set_property -dict {PACKAGE_PIN B18 IOSTANDARD LVCMOS33} [get_ports {adc_data[6]}]
set_property -dict {PACKAGE_PIN A18 IOSTANDARD LVCMOS33} [get_ports {adc_data[7]}]
set_property -dict {PACKAGE_PIN F13 IOSTANDARD LVCMOS33} [get_ports {adc_data[8]}]
set_property -dict {PACKAGE_PIN F14 IOSTANDARD LVCMOS33} [get_ports {adc_data[9]}]
set_property -dict {PACKAGE_PIN B13 IOSTANDARD LVCMOS33} [get_ports {adc_data[10]}]
set_property -dict {PACKAGE_PIN B14 IOSTANDARD LVCMOS33} [get_ports {adc_data[11]}]
set_property -dict {PACKAGE_PIN D14 IOSTANDARD LVCMOS33} [get_ports adc_otr]
set_property -dict {PACKAGE_PIN C14 IOSTANDARD LVCMOS33 DRIVE 8 SLEW FAST} [get_ports adc_clk]
set_property -dict {PACKAGE_PIN B11 IOSTANDARD LVCMOS33 DRIVE 8 SLEW FAST} [get_ports {dac_da[0]}]
set_property -dict {PACKAGE_PIN A11 IOSTANDARD LVCMOS33 DRIVE 8 SLEW FAST} [get_ports {dac_da[1]}]
set_property -dict {PACKAGE_PIN E15 IOSTANDARD LVCMOS33 DRIVE 8 SLEW FAST} [get_ports {dac_da[2]}]
set_property -dict {PACKAGE_PIN E16 IOSTANDARD LVCMOS33 DRIVE 8 SLEW FAST} [get_ports {dac_da[3]}]
set_property -dict {PACKAGE_PIN H16 IOSTANDARD LVCMOS33 DRIVE 8 SLEW FAST} [get_ports {dac_da[4]}]
set_property -dict {PACKAGE_PIN G16 IOSTANDARD LVCMOS33 DRIVE 8 SLEW FAST} [get_ports {dac_da[5]}]
set_property -dict {PACKAGE_PIN F15 IOSTANDARD LVCMOS33 DRIVE 8 SLEW FAST} [get_ports {dac_da[6]}]
set_property -dict {PACKAGE_PIN F16 IOSTANDARD LVCMOS33 DRIVE 8 SLEW FAST} [get_ports {dac_da[7]}]
set_property -dict {PACKAGE_PIN H14 IOSTANDARD LVCMOS33 DRIVE 8 SLEW FAST} [get_ports {dac_da[8]}]
set_property -dict {PACKAGE_PIN G14 IOSTANDARD LVCMOS33 DRIVE 8 SLEW FAST} [get_ports {dac_da[9]}]
set_property -dict {PACKAGE_PIN E17 IOSTANDARD LVCMOS33 DRIVE 8 SLEW FAST} [get_ports {dac_da[10]}]
set_property -dict {PACKAGE_PIN D17 IOSTANDARD LVCMOS33 DRIVE 8 SLEW FAST} [get_ports {dac_da[11]}]
set_property -dict {PACKAGE_PIN K13 IOSTANDARD LVCMOS33 DRIVE 8 SLEW FAST} [get_ports {dac_da[12]}]
set_property -dict {PACKAGE_PIN J13 IOSTANDARD LVCMOS33 DRIVE 8 SLEW FAST} [get_ports {dac_da[13]}]
set_property -dict {PACKAGE_PIN D15 IOSTANDARD LVCMOS33 DRIVE 8 SLEW FAST} [get_ports dac_aclk]
set_property -dict {PACKAGE_PIN C15 IOSTANDARD LVCMOS33 DRIVE 8 SLEW FAST} [get_ports dac_wr1]
set_property -dict {PACKAGE_PIN K3 IOSTANDARD LVCMOS33 DRIVE 4 SLEW SLOW} [get_ports {status_led[0]}]
set_property -dict {PACKAGE_PIN M1 IOSTANDARD LVCMOS33 DRIVE 4 SLEW SLOW} [get_ports {status_led[1]}]
set_property -dict {PACKAGE_PIN L1 IOSTANDARD LVCMOS33 DRIVE 4 SLEW SLOW} [get_ports {status_led[2]}]
set_property -dict {PACKAGE_PIN K6 IOSTANDARD LVCMOS33 DRIVE 4 SLEW SLOW} [get_ports {status_led[3]}]
create_clock -name sys_clk_100 -period 10.000 [get_ports sys_clk_100]
# The imported, generated Clocking Wizard HDL contains an MMCM and BUFG;
# Vivado derives its 25 MHz clock. Forward it through each real output path.
create_generated_clock -name adc_external -source [get_pins adc_oddr/C] -divide_by 1 [get_ports adc_clk]
create_generated_clock -name dac_external -source [get_pins dac_oddr/C] -divide_by 1 [get_ports dac_aclk]
create_generated_clock -name wr_external -source [get_pins wr1_oddr/C] -divide_by 1 [get_ports dac_wr1]
# AD9226 tCO 3.5..7 ns, expanded conservatively by the skew budget.
set_input_delay -clock adc_external -max 9.000 [get_ports {adc_data[*] adc_otr}]
set_input_delay -clock adc_external -min 1.500 [get_ports {adc_data[*] adc_otr}]
# AD9767 setup >=2 ns, hold >=1.5 ns, plus skew budget. Check both latches.
set_output_delay -clock dac_external -max 4.000 [get_ports {dac_da[*]}]
set_output_delay -clock dac_external -min -3.500 [get_ports {dac_da[*]}]
set_output_delay -clock wr_external -max 4.000 -add_delay [get_ports {dac_da[*]}]
set_output_delay -clock wr_external -min -3.500 -add_delay [get_ports {dac_da[*]}]
# Only genuinely asynchronous user controls / UART synchronizer first stages.
set_false_path -from [get_ports fpga_uart_rx_n5] -to [get_pins -hier -filter {NAME =~ *rx_meta_reg/D}]
# The mechanical switch has no phase relationship; assertion is debounced,
# withdrawal also uses the safety core's asynchronous clear input.
set_false_path -from [get_ports module_switch]
set_false_path -from [get_ports reset_n]
# These asynchronous external endpoints have no external capture clock. The
# UART register-to-register baud logic remains fully timed at 25 MHz.
set_false_path -to [get_ports {fpga_uart_tx_t4 status_led[*]}]
set_property CFGBVS VCCO [current_design]
set_property CONFIG_VOLTAGE 3.3 [current_design]
set_property BITSTREAM.CONFIG.UNUSEDPIN Pullnone [current_design]
