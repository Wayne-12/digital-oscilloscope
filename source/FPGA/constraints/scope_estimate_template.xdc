# ESTIMATE ONLY: provisional xc7a35tcsg324-1, not board timing signoff.
# No PACKAGE_PIN, IOSTANDARD, board preset, ADC/DAC false paths or IO delays.
# Active only for the existing scope_hw_top shell (100 MHz -> MMCM -> 25 MHz).
create_clock -name sys_clk_100 -period 10.000 [get_ports sys_clk_100]
# The Clocking Wizard supplies its MMCM clock relationships. Do not invent a
# second independent clock on its output. Final ADC/DAC generated-clock and
# input/output delays require verified part, pinout, wiring and module timing.
