/*
 * Copyright (c) 2026 Daniel Tyukov
 * SPDX-License-Identifier: Apache-2.0
 *
 * Pattern 7: rule 30 elementary cellular automaton, drawn as a space-time
 * diagram.
 *
 * 40 cells at 16 pixels each is exactly 640, so the cell index is pix_x[9:4]
 * with no arithmetic. The row is re-seeded with a single live centre cell at the
 * end of every frame, so the figure is stable from frame to frame while its
 * colour cycles with the frame counter.
 *
 * One generation per 32 scanlines, not one per scanline. Rule 30 spreads one
 * cell left and one cell right per generation, so 480 generations on a 40 cell
 * cyclic row wraps around after 20 and the rest of the screen is undifferentiated
 * chaos. 480 / 32 is 15 generations, which spans cells 6 to 34 and stays clear of
 * the wrap, so what is drawn is a readable rule 30 space-time diagram: the
 * regular right edge, and the chaotic left half that rule 30 is famous for.
 * Dividing by 32 is free, it is a test on pix_y[4:0].
 *
 * Rule 30 is next[i] = left XOR (centre OR right), with cyclic edges. Unlike the
 * Sierpinski pattern, which is a closed form fractal, this one is genuinely
 * iterated: the chaotic half cannot be computed from (pix_x, pix_y) directly,
 * which is what makes it worth 40 flip-flops.
 */

`default_nettype none

module pat_rule30 (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       line_end,
    input  wire       frame_end,
    input  wire [9:0] pix_x,
    input  wire [9:0] pix_y,
    input  wire [7:0] frame,
    output wire [5:0] rgb
);
  localparam integer N = 40;
  localparam [N-1:0] SEED = 40'd1 << 20;  // single live cell at the centre

  reg [N-1:0] row;

  // Cyclic neighbourhood: the cell left of row[0] is row[N-1], and the cell
  // right of row[N-1] is row[0]. 'row' rather than 'cell' because 'cell' is a
  // reserved Verilog keyword.
  wire [N-1:0] left  = {row[N-2:0], row[N-1]};
  wire [N-1:0] right = {row[0], row[N-1:1]};
  wire [N-1:0] next  = left ^ (row | right);

  // One generation every 32 scanlines.
  wire gen_end = line_end & (pix_y[4:0] == 5'b11111);

  always @(posedge clk) begin
    if (!rst_n) row <= SEED;
    else if (frame_end) row <= SEED;
    else if (gen_end) row <= next;
  end

  // Zero extending to 64 bits keeps the index legal during horizontal
  // blanking, where pix_x[9:4] reaches 49. The constant zeros cost nothing.
  wire [63:0] row_ext = {24'd0, row};
  wire        on = row_ext[pix_x[9:4]];

  wire [1:0] sh = frame[7:6];  // live cells cycle from blue to white

  assign rgb = on ? {sh, sh, 2'b11} : 6'b00_00_00;

  wire _unused = &{pix_x[3:0], pix_y[9:5], frame[5:0], 1'b0};
endmodule
