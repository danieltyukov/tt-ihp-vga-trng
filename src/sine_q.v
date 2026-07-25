/*
 * Copyright (c) 2026 Daniel Tyukov
 * SPDX-License-Identifier: Apache-2.0
 *
 * Quarter wave sine table: 5 bit phase in, 4 bit unsigned sine out.
 *
 * A full 32 entry table would be 128 bits of ROM. Storing only the rising
 * quarter wave as eight 3 bit entries and recovering the other three quadrants
 * by folding the phase costs about twenty gates per instance instead.
 *
 *   phase[4] selects the lower half of the wave, phase[3] mirrors the index
 *   inside each half, and the case block is the rising quarter.
 *
 * Sweeping phase 0 .. 31 gives amp 8..15 rising, 15..8 falling, 7..0 falling,
 * 0..7 rising, which is continuous at both wrap points: amp(15) = 8 next to
 * amp(16) = 7, and amp(31) = 7 next to amp(0) = 8.
 */

`default_nettype none

module sine_q (
    input  wire [4:0] phase,
    output wire [3:0] amp
);
  wire [2:0] f = phase[3] ? ~phase[2:0] : phase[2:0];

  reg [2:0] q;
  always @(*) begin
    case (f)
      3'd0:    q = 3'd0;
      3'd1:    q = 3'd2;
      3'd2:    q = 3'd3;
      3'd3:    q = 3'd5;
      3'd4:    q = 3'd6;
      3'd5:    q = 3'd7;
      3'd6:    q = 3'd7;
      default: q = 3'd7;
    endcase
  end

  assign amp = phase[4] ? {1'b0, 3'd7 - q} : {1'b1, q};
endmodule
