# Timing constraints for tt_um_danieltyukov_vga_trng.
#
# Written because LibreLane otherwise warns "'PNR_SDC_FILE' is not defined. Using
# generic fallback SDC", and slack numbers from a generic fallback are not worth
# quoting. Both PNR_SDC_FILE and SIGNOFF_SDC_FILE in hardening/config.json point
# here.
#
# Every number below is stated with its reason. Nothing is a default that happened
# to work.

# ---------------------------------------------------------------------------
# Clock
# ---------------------------------------------------------------------------
# 640x480 at 59.94 Hz needs 800 * 525 * 59.9405 = 25.175 MHz, so 39.7220 ns.
# This is the value info.yaml declares as clock_hz 25175000.
set clk_period 39.7220
create_clock -name clk -period $clk_period [get_ports clk]

# The Tiny Tapeout harness distributes one clock across the whole die to every
# user tile, so the clock arriving here has picked up jitter and skew that this
# tile does not control. 0.25 ns of uncertainty is 0.63% of the period.
set_clock_uncertainty 0.25 [get_clocks clk]

# Transition time on the clock pin as it enters the tile.
set_clock_transition 0.15 [get_clocks clk]

# ---------------------------------------------------------------------------
# Boundary timing
# ---------------------------------------------------------------------------
# ui_in and uio_in reach this tile through the harness input mux, and uo_out
# leaves through the output mux. Budgeting 25% of the period at each boundary
# leaves half the period for the tile itself. That is deliberately stricter than
# assuming zero external delay: it is the constraint a tile has to meet to be
# usable in the real harness, and there is enough margin to afford it (post
# synthesis STA in docs/sta/ shows 33.8 ns of slack at the slow corner).
set io_budget [expr $clk_period * 0.25]

set_input_delay $io_budget -clock clk [get_ports rst_n]
set_input_delay $io_budget -clock clk [get_ports ena]
set_input_delay $io_budget -clock clk [get_ports {ui_in[*]}]
set_input_delay $io_budget -clock clk [get_ports {uio_in[*]}]

set_output_delay $io_budget -clock clk [get_ports {uo_out[*]}]
set_output_delay $io_budget -clock clk [get_ports {uio_out[*]}]
set_output_delay $io_budget -clock clk [get_ports {uio_oe[*]}]

# ---------------------------------------------------------------------------
# Drive and load at the boundary
# ---------------------------------------------------------------------------
# The harness drives tile inputs from ordinary standard cells and its input mux
# presents an ordinary standard cell load, so model both with the smallest
# inverter in the library rather than an ideal source and a zero load.
set_driving_cell -lib_cell sg13g2_inv_1 -pin Y [all_inputs]
# Input capacitance of sg13g2_inv_1 in the typical corner, as the load an output
# of this tile has to drive.
set_load 0.0034 [all_outputs]

# ---------------------------------------------------------------------------
# Design rule limits
# ---------------------------------------------------------------------------
# Keep the mapper from building a single net that fans out across the tile.
set_max_fanout 10 [current_design]
set_max_transition 1.5 [current_design]
