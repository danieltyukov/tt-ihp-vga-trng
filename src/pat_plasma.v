/*
 * Copyright (c) 2026 Daniel Tyukov
 * SPDX-License-Identifier: Apache-2.0
 *
 * Pattern 4: plasma field built from three interfering sine waves.
 *
 * Three phases: one scrolling horizontally, one scrolling vertically the other
 * way at a different rate, and one static diagonal term. The 5 bit adds wrap,
 * which is exactly the modulo behaviour a phase accumulator wants, so no
 * masking is needed.
 *
 * The three amplitudes are summed and the colour is taken from overlapping bit
 * windows of the sum, which gives a hue sweep instead of three identical grey
 * ramps. See src/sine_q.v for the table.
 */

`default_nettype none

module pat_plasma (
    input  wire [9:0] pix_x,
    input  wire [9:0] pix_y,
    input  wire [7:0] frame,
    output wire [5:0] rgb
);
  wire [4:0] ph0 = pix_x[8:4] + frame[5:1];
  wire [4:0] ph1 = pix_y[8:4] - frame[6:2];
  wire [4:0] ph2 = pix_x[7:3] + pix_y[7:3];

  wire [3:0] s0, s1, s2;
  sine_q u_s0 (
      .phase(ph0),
      .amp  (s0)
  );
  sine_q u_s1 (
      .phase(ph1),
      .amp  (s1)
  );
  sine_q u_s2 (
      .phase(ph2),
      .amp  (s2)
  );

  wire [5:0] sum = {2'b00, s0} + {2'b00, s1} + {2'b00, s2};  // 0 .. 45

  assign rgb = {sum[5:4], sum[4:3], sum[3:2]};

  wire _unused = &{pix_x[9], pix_x[2:0], pix_y[9], pix_y[2:0],
                   frame[7], frame[0], sum[1:0], 1'b0};
endmodule
