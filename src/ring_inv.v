/*
 * Copyright (c) 2026 Daniel Tyukov
 * SPDX-License-Identifier: Apache-2.0
 *
 * One inverter stage of a ring oscillator.
 *
 * This exists as a separate (* keep_hierarchy *) module for one reason: an
 * optimiser will otherwise cancel inverter pairs across the chain. Written as a
 * single expression inside ring_osc, a 5 stage and a 7 stage ring both collapse
 * to one inverter and one AND gate, both oscillators end up identical, and the
 * XOR of two identical oscillators is a constant. Measured with Yosys 0.33 and
 * the sg13g2 library: 2 surviving cells instead of 12. keep_hierarchy is
 * honoured by Yosys' flatten pass, so the stages stay distinct.
 *
 * SIM_DELAY exists only for simulation, where a zero delay inverter loop would
 * deadlock the timewheel.
 */

`default_nettype none

/* verilator lint_off UNOPTFLAT */
/* verilator lint_off UNUSEDPARAM */
// UNOPTFLAT: this cell is part of a deliberate combinational cycle.
// UNUSEDPARAM: SIM_DELAY is referenced only inside the `ifdef SIM branch.
(* keep_hierarchy *)
module ring_inv #(
    parameter integer SIM_DELAY = 3
) (
    input  wire a,
    output wire z
);
`ifdef SIM
  assign #SIM_DELAY z = ~a;
`else
  assign z = ~a;
`endif
endmodule
/* verilator lint_on UNUSEDPARAM */
/* verilator lint_on UNOPTFLAT */
