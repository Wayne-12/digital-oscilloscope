# Native Vivado flow. Upgrade the staged XCI before regenerating its products.
# The default hardware build remains 25 MHz; ideal-clock tests cover other rates.
if {[info exists ::scope_clock_output_root]} {
    set scope_ip_directory [file normalize $::scope_clock_output_root]
} else {
    set scope_ip_directory [file normalize [file join [file dirname [info script]] .. ip]]
}
set scope_clock_xci [file join $scope_ip_directory scope_clk_wiz scope_clk_wiz.xci]
file mkdir $scope_ip_directory
set scope_clock_hdl_files [list \
    [file join $scope_ip_directory scope_clk_wiz scope_clk_wiz_clk_wiz.v] \
    [file join $scope_ip_directory scope_clk_wiz scope_clk_wiz.v]]
if {[info exists ::scope_clock_plain_hdl] && $::scope_clock_plain_hdl} {
    foreach hdl_file $scope_clock_hdl_files {
        set existing_file [get_files -quiet $hdl_file]
        if {[llength $existing_file] != 0 && [llength [get_ips -quiet scope_clk_wiz]] == 0} {
            remove_files $existing_file
        }
    }
}
if {[llength [get_ips -quiet scope_clk_wiz]] == 0} {
    if {[file exists $scope_clock_xci]} {
        read_ip $scope_clock_xci
    } else {
        if {[llength [get_ipdefs -all xilinx.com:ip:clk_wiz:6.0]] != 1} {
            error {Required Clocking Wizard 6.0 is unavailable in this installation}
        }
        create_ip -name clk_wiz -vendor xilinx.com -library ip -version 6.0 \
                  -module_name scope_clk_wiz -dir $scope_ip_directory
    }
}
set scope_clock_ip [get_ips scope_clk_wiz]
if {[info exists ::scope_clock_generate_products] && $::scope_clock_generate_products} {
    report_ip_status -file [file join $scope_ip_directory ip_status_before_upgrade.txt]
    if {[get_property IS_LOCKED $scope_clock_ip]} {
        upgrade_ip $scope_clock_ip
        set scope_clock_ip [get_ips scope_clk_wiz]
    }
    if {[get_property IS_LOCKED $scope_clock_ip]} {
        error {Clocking Wizard is still locked after upgrade}
    }
}
set scope_clock_requirements [list \
    CONFIG.PRIM_IN_FREQ 100.000 \
    CONFIG.CLKOUT1_REQUESTED_OUT_FREQ 25.000 \
    CONFIG.USE_RESET true \
    CONFIG.RESET_TYPE ACTIVE_HIGH \
    CONFIG.USE_LOCKED true]
set scope_changed_settings {}
foreach {property requested} $scope_clock_requirements {
    set observed [get_property $property $scope_clock_ip]
    if {![string equal -nocase $observed $requested]} {
        lappend scope_changed_settings $property $requested
    }
}
if {[llength $scope_changed_settings] != 0} {
    set_property -dict $scope_changed_settings $scope_clock_ip
}
foreach {property requested} $scope_clock_requirements {
    set observed [get_property $property $scope_clock_ip]
    if {[string is double -strict $requested]} {
        if {abs(double($observed)-double($requested)) > 0.000001} {
            error "Clocking Wizard readback mismatch: $property=$observed expected=$requested"
        }
    } elseif {![string equal -nocase $observed $requested]} {
        error "Clocking Wizard readback mismatch: $property=$observed expected=$requested"
    }
    puts "CLOCK_IP_READBACK $property=$observed"
}
if {[info exists ::scope_clock_generate_products] && $::scope_clock_generate_products} {
    generate_target all [get_files $scope_clock_xci]
    report_ip_status -file [file join $scope_ip_directory ip_status_after_upgrade.txt]
} elseif {![file exists [file join $scope_ip_directory scope_clk_wiz scope_clk_wiz.v]]} {
    error {Clocking Wizard products missing; run check_safe_project.ps1 to stage generation in an ASCII TEMP path}
}
puts {CLOCK_IP_CONFIG_PASS input=100MHz output=25MHz reset=ACTIVE_HIGH locked=enabled}
if {[info exists ::scope_clock_plain_hdl] && $::scope_clock_plain_hdl} {
    # Keep the reproducible XCI on disk; consume generated HDL directly so the
    # project does not regenerate IP in the problematic non-ASCII path.
    remove_files [get_files $scope_clock_xci]
    foreach hdl_file $scope_clock_hdl_files {
        if {![file exists $hdl_file]} { error "Missing generated clock HDL: $hdl_file" }
        add_files -norecurse -fileset sources_1 [list $hdl_file]
    }
    puts {CLOCK_IP_HDL_IMPORT_PASS generated_modules=2}
}
