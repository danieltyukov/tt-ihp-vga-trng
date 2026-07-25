/*
 * Copyright (c) 2026 Daniel Tyukov
 * SPDX-License-Identifier: Apache-2.0
 *
 * Pattern 0: XOR field, the classic "munching squares" interference figure.
 *
 * t = (x ^ y) + frame. The XOR draws the figure and the addition scrolls the
 * palette through it, so the whole thing animates for the price of one 8 bit
 * adder. No state at all.
 *
 * Every pattern module in this design takes the same (pix_x, pix_y, frame)
 * interface and sinks the bits it does not need into _unused, so the mux stays
 * uniform and the linters stay quiet.
 */

`default_nettype none

module pat_xor (
    input  wire [9:0] pix_x,
    input  wire [9:0] pix_y,
    input  wire [7:0] frame,
    output wire [5:0] rgb
);
  wire [7:0] t = (pix_x[7:0] ^ pix_y[7:0]) + frame;

  assign rgb = {t[7:6], t[5:4], t[3:2]};

  wire _unused = &{pix_x[9:8], pix_y[9:8], t[1:0], 1'b0};
endmodule
