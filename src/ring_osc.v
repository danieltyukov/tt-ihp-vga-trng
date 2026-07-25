/*
 * Copyright (c) 2026 Daniel Tyukov
 * SPDX-License-Identifier: Apache-2.0
 *
 * Enable gated ring oscillator, built from individually protected stages.
 *
 * Stage 0 is a NAND against en instead of a plain inverter. That serves two
 * purposes: it lets the loop be powered down, and it gives the loop a defined
 * starting state. An inverter ring whose nodes begin at x stays at x forever in
 * a simulator, because ~x is x. With en low the NAND output is a hard 1 and the
 * whole chain resolves, so releasing en starts oscillation from a known state.
 *
 * Protecting it from synthesis
 * ----------------------------
 * This is the part that is easy to get wrong, and getting it wrong is silent.
 * Writing the chain as a plain expression inside one module does not work: the
 * mapper collapses an odd inverter chain to a single inverter, so a 5 stage and
 * a 7 stage oscillator both come out as one inverter and one AND gate, they end
 * up with identical frequencies, and the XOR of two identical oscillators is a
 * constant. Measured with Yosys 0.33 and the sg13g2 library, that is exactly
 * what happens: 2 cells survive instead of 12.
 *
 * So each stage is its own (* keep_hierarchy *) module. Yosys' flatten pass
 * honours that attribute, so the stages stay distinct cells through synthesis
 * and no inverter pair can be cancelled across a boundary. (* keep *) on the
 * chain wires additionally stops opt_clean removing the loop as unobservable.
 *
 * Static timing will report a combinational loop here. That is correct and
 * expected for a ring oscillator: the loop is deliberately not on the clock
 * tree and its only consumer is the two stage synchroniser in
 * entropy_source.v. The 'check' step in scripts/synth_report.sh confirms that
 * every loop Yosys reports is inside this module and nowhere else.
 *
 * For simulation each stage carries an inertial delay so Icarus gives the loop
 * a defined period instead of deadlocking at zero delay. That period is exact
 * and jitter free, which is precisely why nothing about randomness is tested
 * through this path. See src/entropy_source.v.
 */

`default_nettype none

/* verilator lint_off UNUSEDPARAM */
// SIM_DELAY is referenced only inside the `ifdef SIM branch, so it is genuinely
// unused in a synthesis build. The waiver is scoped to this file.

// One inverter stage.
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

// The enable gate, one NAND. Doubles as the stage that breaks the x deadlock.
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
