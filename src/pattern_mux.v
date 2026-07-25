/*
 * Copyright (c) 2026 Daniel Tyukov
 * SPDX-License-Identifier: Apache-2.0
 *
 * The eight pattern generators and the output multiplexer.
 *
 * All eight run concurrently and only one result is selected. That is the
 * cheapest arrangement here: six of the eight are pure functions of
 * (pix_x, pix_y, frame) with no state to duplicate, and time multiplexing them
 * would need a pipeline plus sequencing logic that costs more than the combi-
 * national logic it would save.
 *
 * Changing sel takes effect on the next pixel, mid frame included. Nothing in
 * the sync generator depends on sel, so switching cannot disturb the timing.
 * test/test.py asserts exactly that.
 */

`default_nettype none

module pattern_mux (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [ 2:0] sel,
    input  wire [ 9:0] pix_x,
    input  wire [ 9:0] pix_y,
    input  wire [ 7:0] frame,
    input  wire        frame_upd,  // one clock per frame, respects freeze
    input  wire        line_end,
    input  wire        frame_end,
    input  wire [15:0] rnd_state,
    output reg  [ 5:0] rgb
);
  wire [5:0] rgb0, rgb1, rgb2, rgb3, rgb4, rgb5, rgb6, rgb7;

  pat_xor u_p0 (
      .pix_x(pix_x),
      .pix_y(pix_y),
      .frame(frame),
      .rgb  (rgb0)
  );

  pat_bars u_p1 (
      .pix_x(pix_x),
      .pix_y(pix_y),
      .frame(frame),
      .rgb  (rgb1)
  );

  pat_sierp u_p2 (
      .pix_x(pix_x),
      .pix_y(pix_y),
      .frame(frame),
      .rgb  (rgb2)
  );

  pat_ripple u_p3 (
      .pix_x(pix_x),
      .pix_y(pix_y),
      .frame(frame),
      .rgb  (rgb3)
  );

  pat_plasma u_p4 (
      .pix_x(pix_x),
      .pix_y(pix_y),
      .frame(frame),
      .rgb  (rgb4)
  );

  pat_ball u_p5 (
      .clk(clk),
      .rst_n(rst_n),
      .frame_upd(frame_upd),
      .pix_x(pix_x),
      .pix_y(pix_y),
      .rgb(rgb5)
  );

  pat_stars u_p6 (
      .rnd(rnd_state),
      .rgb(rgb6)
  );

  pat_rule30 u_p7 (
      .clk(clk),
      .rst_n(rst_n),
      .line_end(line_end),
      .frame_end(frame_end),
      .pix_x(pix_x),
      .frame(frame),
      .rgb(rgb7)
  );

  always @(*) begin
    case (sel)
      3'd0:    rgb = rgb0;
      3'd1:    rgb = rgb1;
      3'd2:    rgb = rgb2;
      3'd3:    rgb = rgb3;
      3'd4:    rgb = rgb4;
      3'd5:    rgb = rgb5;
      3'd6:    rgb = rgb6;
      default: rgb = rgb7;
    endcase
  end
endmodule
