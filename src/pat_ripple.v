/*
 * Copyright (c) 2026 Daniel Tyukov
 * SPDX-License-Identifier: Apache-2.0
 *
 * Pattern 3: animated concentric diamonds.
 *
 * d = |x - 320| + |y - 240| is the Manhattan distance from screen centre, and
 * subtracting the frame counter makes the rings travel outward.
 *
 * Area note: the absolute value uses ~d instead of -d, which is off by one on
 * the negative side of each axis. That drops two 10 bit incrementers and the
 * error is a single pixel of asymmetry, which is not visible on a monitor. The
 * Python reference model reproduces the same off-by-one so the golden frame
 * comparison stays exact.
 */

`default_nettype none

module pat_ripple (
    input  wire [9:0] pix_x,
    input  wire [9:0] pix_y,
    input  wire [7:0] frame,
    output wire [5:0] rgb
);
  wire [9:0] dx = pix_x - 10'd320;
  wire [9:0] dy = pix_y - 10'd240;

  wire [8:0] ax = dx[9] ? ~dx[8:0] : dx[8:0];
  wire [8:0] ay = dy[9] ? ~dy[8:0] : dy[8:0];

  wire [9:0] d = {1'b0, ax} + {1'b0, ay};
  wire [7:0] p = d[7:0] - frame;

  assign rgb = {p[7:6], p[6:5], p[5:4]};

  wire _unused = &{d[9:8], p[3:0], 1'b0};
endmodule
