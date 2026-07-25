/*
 * Copyright (c) 2026 Daniel Tyukov
 * SPDX-License-Identifier: Apache-2.0
 *
 * The enable stage of a ring oscillator: one NAND instead of one inverter.
 *
 * Two jobs. It lets the oscillator be powered down, and it gives the loop a
 * defined starting state. An inverter ring whose nodes begin at x stays at x
 * forever in a simulator, because ~x is x. With en low this output is a hard 1
 * and the whole chain resolves, so releasing en starts oscillation from a known
 * state rather than from an unresolvable one.
 *
 * Separate (* keep_hierarchy *) module for the same reason as ring_inv: so the
 * mapper cannot merge it into the chain.
 */

`default_nettype none

/* verilator lint_off UNOPTFLAT */
/* verilator lint_off UNUSEDPARAM */
// UNOPTFLAT: this cell is part of a deliberate combinational cycle.
// UNUSEDPARAM: SIM_DELAY is referenced only inside the `ifdef SIM branch.
(* keep_hierarchy *)
module ring_gate #(
    parameter integer SIM_DELAY = 3
) (
    input  wire a,
    input  wire en,
    output wire z
);
`ifdef SIM
  assign #SIM_DELAY z = ~(a & en);
`else
  assign z = ~(a & en);
`endif
endmodule
/* verilator lint_on UNUSEDPARAM */
/* verilator lint_on UNOPTFLAT */
