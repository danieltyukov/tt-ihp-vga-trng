# OpenSTA script for tt_um_danieltyukov_vga_trng.
#
# Sourced by a generated wrapper that sets pdk, lib, netlist and period.
# scripts/run_sta.sh writes that wrapper. The openroad wrapper on this machine is
# Docker backed and does not forward the environment into the container, so the
# values have to arrive as Tcl, not as env vars.
#
# Everything is written to stdout and run_sta.sh redirects it into the report
# file. Two traps here, both hit while writing this:
#   - report_checks and report_design_area print to OpenSTA's report stream
#     rather than returning a string, so capturing them with [ ] yields nothing.
#   - that stream and Tcl's stdout are buffered separately, so section headings
#     written with plain puts land in the wrong place. Hence the flush in 'hdr'.
#
# The tech LEF and the stdcell LEF must both be read before read_verilog or
# OpenROAD errors with "[ERROR ORD-2010] no technology has been read".

foreach v {pdk lib netlist period} {
  if {![info exists $v]} {
    puts "sta.tcl: '$v' is not set. Run it through scripts/run_sta.sh."
    exit 1
  }
}
set top tt_um_danieltyukov_vga_trng

# Heading plus flush, so Tcl output and the STA report stream stay in order.
proc hdr {args} {
  foreach line $args { puts $line }
  flush stdout
}

read_lef $pdk/libs.ref/sg13g2_stdcell/lef/sg13g2_tech.lef
read_lef $pdk/libs.ref/sg13g2_stdcell/lef/sg13g2_stdcell.lef
read_liberty $lib
read_verilog $netlist
link_design $top

# 25.175 MHz pixel clock. The period is passed in so the same script can sweep.
create_clock -name clk -period $period [get_ports clk]

# The Tiny Tapeout harness registers the user inputs and outputs, so the tile
# sees them at the clock edge. Zero external delay is the same assumption the
# tt-gds flow's generated SDC makes.
#
# clk is listed out of get_ports explicitly rather than subtracted from
# all_inputs: remove_from_collection does not exist in this OpenSTA build.
set_input_delay 0.0 -clock clk [get_ports {rst_n ena ui_in uio_in}]
set_output_delay 0.0 -clock clk [get_ports {uo_out uio_out uio_oe}]

hdr "OpenSTA report for $top" \
    "liberty : [file tail $lib]" \
    "netlist : [file tail $netlist]" \
    "period  : $period ns ([format %.4f [expr {1000.0 / $period}]] MHz)" \
    ""

hdr "=== setup, worst path ==="
report_checks -path_delay max -digits 4
hdr "" "=== setup, five worst endpoints ==="
report_checks -path_delay max -group_path_count 5 -digits 4
hdr "" "=== hold, worst path ==="
report_checks -path_delay min -digits 4
hdr "" "=== area ==="
report_design_area
hdr ""

set ws_max [sta::worst_slack -max]
set ws_min [sta::worst_slack -min]
set fmax [expr {1000.0 / ($period - $ws_max)}]

hdr "=== summary ===" \
    [format "worst setup slack : %.4f ns" $ws_max] \
    [format "worst hold slack  : %.4f ns" $ws_min] \
    "total negative slack (setup) : [sta::total_negative_slack_cmd max]" \
    "total negative slack (hold)  : [sta::total_negative_slack_cmd min]" \
    [format "fmax from the setup critical path : %.4f MHz" $fmax] \
    [format "margin over the 25.1750 MHz target : %.2fx" [expr {$fmax / 25.175}]] \
    ""

# Tagged lines for scripts/parse_sta.py.
puts "PERIOD $period"
puts [format "WORST_SETUP %.4f" $ws_max]
puts [format "WORST_HOLD %.4f" $ws_min]
puts [format "FMAX_MHZ %.4f" $fmax]
puts "TNS_MAX [sta::total_negative_slack_cmd max]"
