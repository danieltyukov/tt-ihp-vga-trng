/*
 * Copyright (c) 2026 Daniel Tyukov
 * SPDX-License-Identifier: Apache-2.0
 *
 * Enable gated ring oscillator: one ring_gate followed by STAGES-1 ring_inv,
 * output fed back to the gate.
 *
 * Protecting it from synthesis
 * ----------------------------
 * This is the part that is easy to get wrong, and getting it wrong is silent.
 * Each stage is a separate (* keep_hierarchy *) module so no inverter pair can
 * be cancelled across the chain, and (* keep *) on the chain wires stops
 * opt_clean removing the loop as unobservable. src/ring_inv.v explains what
 * happens without that: both oscillators collapse to one inverter, their
 * frequencies become identical, and the XOR that feeds the sampler becomes a
 * constant. scripts/synth_report.sh checks that all 12 stages of the two rings
 * survive mapping.
 *
 * Static timing will report a combinational loop here. That is correct and
 * expected for a ring oscillator: the loop is deliberately not on the clock tree
 * and its only consumer is the two stage synchroniser in entropy_source.v. The
 * check step in scripts/synth_report.sh confirms every loop Yosys reports is
 * inside a ring and nowhere else.
 *
 * In simulation the stage delays give the loop a defined period. That period is
 * exact and jitter free, which is precisely why nothing about randomness is
 * tested through this path. See src/entropy_source.v and test/tb_ring.v.
 */

`default_nettype none

/* verilator lint_off UNOPTFLAT */
// UNOPTFLAT: the combinational cycle is the whole point of a ring oscillator.
(* keep *)
module ring_osc #(
    parameter integer STAGES    = 5,  // must be odd
    parameter integer SIM_DELAY = 3   // per stage delay, simulation only
) (
    input  wire en,
    output wire osc
);
  (* keep *) wire [STAGES-1:0] chain;

  ring_gate #(
      .SIM_DELAY(SIM_DELAY)
  ) u_gate (
      .a (chain[STAGES-1]),
      .en(en),
      .z (chain[0])
  );

  genvar i;
  generate
    for (i = 1; i < STAGES; i = i + 1) begin : g_stage
      ring_inv #(
          .SIM_DELAY(SIM_DELAY)
      ) u_inv (
          .a(chain[i-1]),
          .z(chain[i])
      );
    end
  endgenerate

  assign osc = chain[STAGES-1];
endmodule
/* verilator lint_on UNOPTFLAT */
