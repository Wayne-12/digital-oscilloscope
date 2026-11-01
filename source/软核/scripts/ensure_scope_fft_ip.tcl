# Native 2025.2 configuration. The installed ip-configurator helper requires
# 2026.1, so this file uses only native IP catalog APIs and exact readbacks.
if {[info exists ::scope_fft_output_root]} {
    set scope_fft_directory [file normalize $::scope_fft_output_root]
} else {set scope_fft_directory [file normalize [file join [file dirname [info script]] .. ip]]}
set scope_fft_xci [file join $scope_fft_directory scope_fft_1024 scope_fft_1024.xci]
file mkdir $scope_fft_directory
if {[llength [get_ips -quiet scope_fft_1024]]==0} {
    if {[file exists $scope_fft_xci]} {read_ip $scope_fft_xci} else {
        if {[llength [get_ipdefs -all xilinx.com:ip:xfft:9.1]]!=1} {error {FFT 9.1 definition is unavailable}}
        create_ip -name xfft -vendor xilinx.com -library ip -version 9.1 -module_name scope_fft_1024 -dir $scope_fft_directory
    }
}
set fft_ip [get_ips scope_fft_1024]
if {[get_property IS_LOCKED $fft_ip]} {error {The FFT IP is locked; explicit version diagnosis is required}}
set fft_contract [list CONFIG.channels 1 CONFIG.transform_length 1024 CONFIG.target_clock_frequency 100 \
    CONFIG.implementation_options radix_2_burst_io CONFIG.run_time_configurable_transform_length false \
    CONFIG.data_format fixed_point CONFIG.input_width 16 CONFIG.phase_factor_width 24 CONFIG.scaling_options unscaled \
    CONFIG.rounding_modes convergent_rounding CONFIG.aclken false CONFIG.aresetn true CONFIG.ovflo false CONFIG.xk_index true \
    CONFIG.throttle_scheme nonrealtime CONFIG.output_ordering natural_order CONFIG.cyclic_prefix_insertion false \
    CONFIG.memory_options_data block_ram CONFIG.memory_options_phase_factors block_ram CONFIG.memory_options_reorder block_ram]
set changed {}
foreach {p value} $fft_contract {
    if {![string equal -nocase [get_property $p $fft_ip] $value]} {lappend changed $p $value}
}
if {[llength $changed]} {set_property -dict $changed $fft_ip}
foreach {p value} $fft_contract {
    if {![string equal -nocase [get_property $p $fft_ip] $value]} {error "FFT_CONFIG_READBACK_FAIL $p=[get_property $p $fft_ip], required=$value"}
}
generate_target all $fft_ip
set f [open [file join $scope_fft_directory fft_contract_readback.txt] w]
puts $f "vivado_version=[version -short]"
puts $f "ip=[get_property IPDEF $fft_ip] core_revision=[get_property CORE_REVISION $fft_ip]"
foreach {p value} $fft_contract {puts $f "$p=[get_property $p $fft_ip]"}
close $f
puts "FFT_IP_CONFIG_PASS version=[version -short] n=1024 input_width=16 phase_width=24 unscaled=1 natural_order=1"
