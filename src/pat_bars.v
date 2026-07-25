/*
 * Copyright (c) 2026 Daniel Tyukov
 * SPDX-License-Identifier: Apache-2.0
 *
 * Pattern 1: eight bar test card with a grey ramp along the bottom.
 *
 * 640 = 8 * 80 and 80 = 5 * 16, so the bar index is (pix_x >> 4) / 5. The
 * divide is done as a compare chain against multiples of five on a 6 bit
 * value, which synthesises to a fraction of a real divider. The palette
 * rotates with frame[7:5], so the card scrolls its colours every 32 frames.
 */

`default_nettype none

module pat_bars (
    input  wire [9:0] pix_x,
    input  wire [9:0] pix_y,
    input  wire [7:0] frame,
    output wire [5:0] rgb
);
  wire [5:0] q = pix_x[9:4];  // 0 .. 39 across the visible width

  wire [2:0] bar = (q >= 6'd35) ? 3'd7 :
                   (q >= 6'd30) ? 3'd6 :
                   (q >= 6'd25) ? 3'd5 :
                   (q >= 6'd20) ? 3'd4 :
                   (q >= 6'd15) ? 3'd3 :
                   (q >= 6'd10) ? 3'd2 :
                   (q >= 6'd05) ? 3'd1 : 3'd0;

  wire [2:0] idx = bar + frame[7:5];

  // 75% SMPTE bar order: white, yellow, cyan, green, magenta, red, blue, black
  reg [5:0] bar_rgb;
  always @(*) begin
    case (idx)
      3'd0:    bar_rgb = 6'b11_11_11;  // white
      3'd1:    bar_rgb = 6'b11_11_00;  // yellow
      3'd2:    bar_rgb = 6'b00_11_11;  // cyan
      3'd3:    bar_rgb = 6'b00_11_00;  // green
      3'd4:    bar_rgb = 6'b11_00_11;  // magenta
      3'd5:    bar_rgb = 6'b11_00_00;  // red
      3'd6:    bar_rgb = 6'b00_00_11;  // blue
      default: bar_rgb = 6'b00_00_00;  // black
    endcase
  end

  // For y < 512, pix_y[8] & pix_y[7] is exactly y >= 384, so the bottom fifth
  // of the visible area becomes a four step luminance ramp.
  wire       ramp_zone = pix_y[8] & pix_y[7];
  wire [1:0] lum       = pix_x[8:7];

  assign rgb = ramp_zone ? {lum, lum, lum} : bar_rgb;

  wire _unused = &{pix_x[3:0], pix_y[9], pix_y[6:0], frame[4:0], 1'b0};
endmodule
