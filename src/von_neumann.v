/*
 * Copyright (c) 2026 Daniel Tyukov
 * SPDX-License-Identifier: Apache-2.0
 *
 * Von Neumann debiaser.
 *
 * Raw samples are taken in non overlapping pairs. A pair of unequal bits emits
 * the first bit of the pair; an equal pair is discarded. If the source is
 * biased but its samples are independent, P(01) = P(10) = p(1-p) regardless of
 * p, so the emitted bit is exactly unbiased. The price is throughput: the
 * expected yield is p(1-p) output bits per input bit, which is 0.25 for an
 * unbiased source and falls off quadratically as the bias grows.
 *
 * The convention here is "emit the first bit of the pair", so 10 emits 1 and
 * 01 emits 0. The Python reference model in test/model.py uses the same
 * convention and the two are compared bit for bit.
 *
 * What this does not fix: von Neumann removes static bias, not serial
 * correlation. A source with correlated adjacent samples stays correlated
 * after debiasing. That is one reason the LFSR conditioner is downstream and
 * the repetition count test is upstream.
 */

`default_nettype none

module von_neumann (
    input  wire clk,
    input  wire rst_n,
    input  wire in_bit,
    input  wire in_stb,
    output reg  out_bit,
    output reg  out_stb
);
  reg have_first;  // 1 when first_bit holds the first sample of a pair
  reg first_bit;

  always @(posedge clk) begin
    if (!rst_n) begin
      have_first <= 1'b0;
      first_bit  <= 1'b0;
      out_bit    <= 1'b0;
      out_stb    <= 1'b0;
    end else begin
      out_stb <= 1'b0;
      if (in_stb) begin
        if (!have_first) begin
          have_first <= 1'b1;
          first_bit  <= in_bit;
        end else begin
          have_first <= 1'b0;
          if (first_bit != in_bit) begin
            out_bit <= first_bit;
            out_stb <= 1'b1;
          end
        end
      end
    end
  end
endmodule
