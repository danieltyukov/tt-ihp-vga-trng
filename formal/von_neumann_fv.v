/*
 * Copyright (c) 2026 Daniel Tyukov
 * SPDX-License-Identifier: Apache-2.0
 *
 * Formal verification harness for the von Neumann debiaser.
 *
 * test.py checks the debiaser against one hand written stream and one 20000
 * sample random stream. That is good evidence about two sequences. This checks
 * every sequence: SymbiYosys bounded model checking proves that no input
 * sequence of up to 40 cycles from reset can violate any property below, and the
 * cover task proves the properties are not vacuous. The state machine has a
 * period of two input samples, so 40 cycles covers every pairing, alignment and
 * discard case many times over.
 *
 * Bounded rather than unbounded, and see von_neumann.sby for why: z3 4.8.12 is
 * the version on this machine and it does not converge on the induction step.
 *
 * The property that matters is number 2. Von Neumann debiasing works because for
 * independent samples P(01) = P(10) = p(1-p) whatever p is, so a debiaser that
 * emits 0 on exactly 01 and 1 on exactly 10 is unbiased by construction. That
 * exact symmetry claim is what is checked here. The statistical conclusion then
 * follows from the input samples being independent, which is an assumption about
 * the noise source and not something any tool can prove about this module.
 */

`default_nettype none

module von_neumann_fv (
    input wire clk,
    input wire rst_n,
    input wire in_bit,
    input wire in_stb
);

  wire out_bit, out_stb;

  von_neumann dut (
      .clk    (clk),
      .rst_n  (rst_n),
      .in_bit (in_bit),
      .in_stb (in_stb),
      .out_bit(out_bit),
      .out_stb(out_stb)
  );

  // ---- independent record of the input pairing -----------------------------
  // This tracks only the INPUT side: which two samples form a pair, and what they
  // were. It deliberately does not model the DUT's outputs.
  //
  // The first version of this harness also carried an expected out_stb and
  // out_bit and asserted cycle for cycle equivalence, which is a miter of two
  // copies of the same state machine. z3 4.8.12 did not converge on that in ten
  // minutes, while the identical property written inside a single module proved by
  // induction in one second. Asserting the specification directly against the
  // recorded input pair is both cheaper and a more direct statement of the
  // theorem: properties 1 to 3 pin the output down completely, so the equivalence
  // assertion added nothing.
  reg       sh_have;
  reg       sh_first;
  reg [1:0] pair;        // the pair that completed on this edge
  reg       pair_valid;

  always @(posedge clk) begin
    if (!rst_n) begin
      sh_have    <= 1'b0;
      sh_first   <= 1'b0;
      pair       <= 2'b00;
      pair_valid <= 1'b0;
    end else begin
      pair_valid <= 1'b0;
      if (in_stb) begin
        if (!sh_have) begin
          sh_have  <= 1'b1;
          sh_first <= in_bit;
        end else begin
          sh_have    <= 1'b0;
          pair       <= {sh_first, in_bit};
          pair_valid <= 1'b1;
        end
      end
    end
  end

  // The trace has to start with a reset. Flip-flops power up at an arbitrary
  // value and a formal tool models that faithfully, so without this the solver is
  // free to start the DUT and this harness in inconsistent states, which says
  // nothing about the design. One cycle of rst_n low aligns them, since the reset
  // is synchronous.
  reg init_done = 1'b0;
  always @(posedge clk) init_done <= 1'b1;
  always @(posedge clk) if (!init_done) assume (!rst_n);

  // Shadow of the previous cycle's out_stb, for the throughput property below.
  reg prev_out_stb;
  always @(posedge clk) begin
    if (!rst_n) prev_out_stb <= 1'b0;
    else prev_out_stb <= out_stb;
  end

  always @(posedge clk) begin
    if (rst_n) begin
      // 1. Nothing is emitted without a completed pair.
      if (out_stb) assert (pair_valid);

      // 2. Exact symmetry, the property the unbiasedness argument rests on:
      //    01 emits 0, 10 emits 1, and equal pairs emit nothing.
      if (pair_valid) begin
        case (pair)
          2'b01: begin
            assert (out_stb);
            assert (out_bit == 1'b0);
          end
          2'b10: begin
            assert (out_stb);
            assert (out_bit == 1'b1);
          end
          default: assert (!out_stb);  // 00 and 11 are discarded
        endcase
      end

      // 3. Throughput. Two consecutive output strobes are impossible, because a
      //    pair takes two input samples to complete. That is the local form of
      //    "never more than one output bit per two input bits", and it makes the
      //    yield bound structural rather than something observed in one run.
      //
      //    The global counting version, n_out <= n_in / 2 over saturating
      //    counters, was tried first and is not k-inductive: from an arbitrary
      //    state the solver can pick n_out greater than n_in / 2, and ruling that
      //    out needs the auxiliary invariant 2*n_out + sh_have <= n_in, which the
      //    saturation then breaks. The local property is equivalent for this
      //    purpose and checks in seconds.
      if (out_stb) assert (!prev_out_stb);
    end
  end

  // Non-vacuity: the solver has to demonstrate that output really can happen,
  // otherwise a debiaser that emits nothing at all would satisfy everything above.
  always @(posedge clk) begin
    if (rst_n) begin
      cover (out_stb && out_bit == 1'b0);
      cover (out_stb && out_bit == 1'b1);
      cover (pair_valid && pair == 2'b00 && !out_stb);
      cover (pair_valid && pair == 2'b11 && !out_stb);
    end
  end

endmodule
