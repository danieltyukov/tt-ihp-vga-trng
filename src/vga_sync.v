/*
 * Copyright (c) 2026 Daniel Tyukov
 * SPDX-License-Identifier: Apache-2.0
 *
 * 640x480 @ 59.94 Hz VGA timing generator.
 *
 * Pixel clock is 25.175 MHz. Totals are 800 x 525, which gives
 * 25175000 / (800 * 525) = 59.9405 Hz.
 *
 * Both syncs are negative polarity, which is what the VESA 640x480 mode and
 * the TinyVGA PMOD expect: the sync output sits high and pulses low.
 */

`default_nettype none

module vga_sync #(
    parameter integer H_ACTIVE = 640,
    parameter integer H_FRONT  = 16,
    parameter integer H_SYNC   = 96,
    parameter integer H_BACK   = 48,
    parameter integer V_ACTIVE = 480,
    parameter integer V_FRONT  = 10,
    parameter integer V_SYNC   = 2,
    parameter integer V_BACK   = 33
) (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       frame_en,     // 0 freezes frame_cnt so animations hold still
    output reg  [9:0] pix_x,        // 0 .. H_TOTAL-1, counts through blanking
    output reg  [9:0] pix_y,        // 0 .. V_TOTAL-1, counts through blanking
    output wire       hsync_n,
    output wire       vsync_n,
    output wire       active,       // inside the 640x480 visible window
    output wire       line_end,     // last pixel clock of every scanline
    output wire       frame_end,    // last pixel clock of the last line of a frame
    output reg  [7:0] frame_cnt
);

  localparam integer H_TOTAL    = H_ACTIVE + H_FRONT + H_SYNC + H_BACK;  // 800
  localparam integer V_TOTAL    = V_ACTIVE + V_FRONT + V_SYNC + V_BACK;  // 525
  localparam integer H_SYNC_ON  = H_ACTIVE + H_FRONT;                    // 656
  localparam integer H_SYNC_OFF = H_SYNC_ON + H_SYNC;                    // 752
  localparam integer V_SYNC_ON  = V_ACTIVE + V_FRONT;                    // 490
  localparam integer V_SYNC_OFF = V_SYNC_ON + V_SYNC;                    // 492

  assign line_end  = (pix_x == H_TOTAL[9:0] - 10'd1);
  assign frame_end = line_end && (pix_y == V_TOTAL[9:0] - 10'd1);

  // Synchronous reset, as recommended for the Tiny Tapeout hardening flow.
  always @(posedge clk) begin
    if (!rst_n) begin
      pix_x     <= 10'd0;
      pix_y     <= 10'd0;
      frame_cnt <= 8'd0;
    end else begin
      if (line_end) begin
        pix_x <= 10'd0;
        pix_y <= frame_end ? 10'd0 : pix_y + 10'd1;
      end else begin
        pix_x <= pix_x + 10'd1;
      end
      if (frame_end && frame_en) frame_cnt <= frame_cnt + 8'd1;
    end
  end

  assign active  = (pix_x < H_ACTIVE[9:0]) && (pix_y < V_ACTIVE[9:0]);
  assign hsync_n = ~((pix_x >= H_SYNC_ON[9:0]) && (pix_x < H_SYNC_OFF[9:0]));
  assign vsync_n = ~((pix_y >= V_SYNC_ON[9:0]) && (pix_y < V_SYNC_OFF[9:0]));

endmodule
