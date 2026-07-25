/*
 * Copyright (c) 2026 Daniel Tyukov
 * SPDX-License-Identifier: Apache-2.0
 *
 * Pattern 2: Sierpinski bit fractal.
 *
 * (x & y) == 0 draws the Sierpinski gasket, a closed form result of Kummer's
 * theorem on binomial coefficients mod 2. Testing progressively fewer bits of
 * the same AND term gives coarser tiled copies of the same triangle, so three
 * nested layers cost one 9 bit AND and three OR reductions.
 *
 * g0 implies g1 implies g2, so the layers can be muxed as a straight priority
 * chain with no overlap logic.
 */

`default_nettype none

module pat_sierp (
    input  wire [9:0] pix_x,
    input  wire [9:0] pix_y,
    input  wire [7:0] frame,
    output wire [5:0] rgb
);
  wire [8:0] a = pix_x[8:0] & pix_y[8:0];

  wire g0 = ~|a;       // the full gasket
  wire g1 = ~|a[5:0];  // 64 pixel tiled gaskets, contains g0
  wire g2 = ~|a[2:0];  // 8 pixel tiled gaskets, contains g1

  wire [1:0] r = g0 ? 2'd3 : g1 ? 2'd2 : g2 ? 2'd1 : 2'd0;
  wire [1:0] g = g0 ? frame[7:6] : g1 ? 2'd1 : 2'd0;
  wire [1:0] b = g0 ? ~frame[7:6] : g2 ? 2'd2 : 2'd0;

  assign rgb = {r, g, b};

  wire _unused = &{pix_x[9], pix_y[9], frame[5:0], 1'b0};
endmodule
