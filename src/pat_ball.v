/*
 * Copyright (c) 2026 Daniel Tyukov
 * SPDX-License-Identifier: Apache-2.0
 *
 * Pattern 5: 32x32 box bouncing inside a framed playfield, changing colour on
 * every wall collision.
 *
 * This is the only pattern that owns animation state: 10 + 10 bits of
 * position, 2 direction bits and a 2 bit colour index, 24 flip-flops. The box
 * test uses unsigned wraparound instead of two comparisons per axis:
 * (pix_x - box_x) lands in 0..31 only inside the box, and underflows to a
 * large value everywhere to the left of it, so a zero test on the upper five
 * bits is the whole comparison.
 */

`default_nettype none

module pat_ball (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       frame_upd,  // one clock per frame, gated by the freeze input
    input  wire [9:0] pix_x,
    input  wire [9:0] pix_y,
    output wire [5:0] rgb
);
  localparam [9:0] X_MAX = 10'd608;  // 640 - 32
  localparam [9:0] Y_MAX = 10'd448;  // 480 - 32

  reg [9:0] box_x, box_y;
  reg       dir_x, dir_y;
  reg [1:0] col;

  wire bounce_x = dir_x ? (box_x >= X_MAX - 10'd2) : (box_x <= 10'd2);
  wire bounce_y = dir_y ? (box_y >= Y_MAX - 10'd2) : (box_y <= 10'd2);

  always @(posedge clk) begin
    if (!rst_n) begin
      box_x <= 10'd100;
      box_y <= 10'd80;
      dir_x <= 1'b1;
      dir_y <= 1'b1;
      col   <= 2'd0;
    end else if (frame_upd) begin
      box_x <= dir_x ? box_x + 10'd2 : box_x - 10'd2;
      box_y <= dir_y ? box_y + 10'd2 : box_y - 10'd2;
      if (bounce_x) dir_x <= ~dir_x;
      if (bounce_y) dir_y <= ~dir_y;
      if (bounce_x || bounce_y) col <= col + 2'd1;
    end
  end

  wire [9:0] rel_x = pix_x - box_x;
  wire [9:0] rel_y = pix_y - box_y;
  wire       in_box = ~|rel_x[9:5] & ~|rel_y[9:5];

  // 8 pixel white frame. Each edge is an equality against a constant on the
  // upper seven bits, which collapses to a single AND gate after synthesis.
  wire border = ~|pix_x[9:3] | (pix_x[9:3] == 7'd79) |
                ~|pix_y[9:3] | (pix_y[9:3] == 7'd59);

  wire      chk = pix_x[5] ^ pix_y[5];
  reg [5:0] box_rgb;
  always @(*) begin
    case (col)
      2'd0:    box_rgb = 6'b11_00_00;  // red
      2'd1:    box_rgb = 6'b00_11_00;  // green
      2'd2:    box_rgb = 6'b01_01_11;  // pale blue
      default: box_rgb = 6'b11_11_00;  // yellow
    endcase
  end

  assign rgb = border ? 6'b11_11_11 :
               in_box ? box_rgb :
               chk    ? 6'b00_00_01 : 6'b01_00_01;

  // Only the upper five bits of each relative coordinate are tested; the low
  // five are the position inside the box and are deliberately ignored.
  wire _unused = &{rel_x[4:0], rel_y[4:0], 1'b0};
endmodule
