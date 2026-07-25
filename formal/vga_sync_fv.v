/*
 * Copyright (c) 2026 Daniel Tyukov
 * SPDX-License-Identifier: Apache-2.0
 *
 * Formal proof harness for the sync generator.
 *
 * test_vga_timing measures one frame from the pins and asserts every interval.
 * That catches a wrong constant. What it cannot catch is a counter that only
 * misbehaves from a state a single captured frame never visits, and on a VGA
 * output a counter that wanders out of range means a monitor that loses lock.
 *
 * Structured as a one step induction with a hand written invariant, rather than
 * as a bounded check from reset. The BASE task forces a reset and proves the
 * counters land on (0, 0). The STEP task assumes only that the counters start
 * somewhere legal, and proves that one clock preserves legality and that every
 * output property below holds. Together those two are an unbounded proof.
 *
 * That structure is not a shortcut, it is both cheaper and stronger. Bounded
 * checking from reset needs 656 cycles just to reach the horizontal sync window,
 * and z3 4.8.12, which is the version on this machine, was taking ten seconds per
 * step by step 220 and would never have finished. Assuming the invariant instead
 * lets the solver start one clock before any state of interest, so the sync
 * pulses, the line wrap and the frame wrap are each one step away.
 *
 * The invariants:
 *
 *   1. pix_x is always inside 0 .. H_TOTAL-1 and pix_y inside 0 .. V_TOTAL-1.
 *      This is the one that matters. It rules out the whole class of bug where a
 *      comparison is written against the wrong constant and the counter runs past
 *      the end of the frame before wrapping.
 *   2. The syncs are low only inside their specified windows, so no out of spec
 *      pulse can be emitted from any state.
 *   3. active is true only inside the visible window, so blanking can never carry
 *      colour.
 *   4. line_end and frame_end can only assert at the last pixel of a line and of
 *      a frame.
 *   5. Advancing exactly one pixel per clock: the counters step by one, wrap to
 *      zero, and never skip.
 */

`default_nettype none

module vga_sync_fv (
    input wire clk,
    input wire rst_n,
    input wire frame_en
);

  localparam integer H_ACTIVE = 640;
  localparam integer H_FRONT = 16;
  localparam integer H_SYNC = 96;
  localparam integer H_BACK = 48;
  localparam integer V_ACTIVE = 480;
  localparam integer V_FRONT = 10;
  localparam integer V_SYNC = 2;
  localparam integer V_BACK = 33;
  localparam integer H_TOTAL = H_ACTIVE + H_FRONT + H_SYNC + H_BACK;  // 800
  localparam integer V_TOTAL = V_ACTIVE + V_FRONT + V_SYNC + V_BACK;  // 525
  localparam integer H_SYNC_ON = H_ACTIVE + H_FRONT;                  // 656
  localparam integer H_SYNC_OFF = H_SYNC_ON + H_SYNC;                 // 752
  localparam integer V_SYNC_ON = V_ACTIVE + V_FRONT;                  // 490
  localparam integer V_SYNC_OFF = V_SYNC_ON + V_SYNC;                 // 492

  wire [9:0] pix_x, pix_y;
  wire [7:0] frame_cnt;
  wire hsync_n, vsync_n, active, line_end, frame_end;

  vga_sync dut (
      .clk      (clk),
      .rst_n    (rst_n),
      .frame_en (frame_en),
      .pix_x    (pix_x),
      .pix_y    (pix_y),
      .hsync_n  (hsync_n),
      .vsync_n  (vsync_n),
      .active   (active),
      .line_end (line_end),
      .frame_end(frame_end),
      .frame_cnt(frame_cnt)
  );

  reg init_done = 1'b0;
  always @(posedge clk) init_done <= 1'b1;

  // Shadow copies of the previous cycle's counters, so the step properties can be
  // written without $past.
  reg [9:0] prev_x, prev_y;
  reg       prev_valid;
  always @(posedge clk) begin
    if (!rst_n) begin
      prev_x     <= 10'd0;
      prev_y     <= 10'd0;
      prev_valid <= 1'b0;
    end else begin
      prev_x     <= pix_x;
      prev_y     <= pix_y;
      prev_valid <= 1'b1;
    end
  end

`ifdef BASE_CASE
  // Base case: force a reset on the first cycle and prove where the counters land.
  // Flip-flops power up at an arbitrary value and a formal tool models that
  // faithfully, which is exactly why the base case has to be stated rather than
  // quietly assumed. The design uses a synchronous reset and the Tiny Tapeout
  // harness always asserts it.
  always @(posedge clk) if (!init_done) assume (!rst_n);

  always @(posedge clk) begin
    // prev_valid is still low on the first cycle after reset is released, which
    // is the moment the base case is about.
    if (rst_n && init_done && !prev_valid) begin
      assert (pix_x == 10'd0);
      assert (pix_y == 10'd0);
    end
  end
`else
  // Step case: assume nothing except that the counters start somewhere legal, so
  // everything below has to hold for one clock from ANY legal state. With the base
  // case above, that is an unbounded proof.
  always @(posedge clk) begin
    if (!init_done) begin
      assume (pix_x < H_TOTAL);
      assume (pix_y < V_TOTAL);
      // so the step property is only checked once prev_x and prev_y are real
      assume (!prev_valid);
    end
  end
`endif

  always @(posedge clk) begin
    if (rst_n) begin
      // 1. counters stay in range, from every reachable state
      assert (pix_x < H_TOTAL);
      assert (pix_y < V_TOTAL);

      // 2. no out of spec sync pulse: low only inside the specified window
      assert (hsync_n == !(pix_x >= H_SYNC_ON && pix_x < H_SYNC_OFF));
      assert (vsync_n == !(pix_y >= V_SYNC_ON && pix_y < V_SYNC_OFF));
      // and the syncs are never low outside the blanking interval
      if (!hsync_n) assert (pix_x >= H_ACTIVE);
      if (!vsync_n) assert (pix_y >= V_ACTIVE);
      // both syncs idle high inside the visible window
      if (active) begin
        assert (hsync_n);
        assert (vsync_n);
      end

      // 3. active only inside the visible window
      assert (active == (pix_x < H_ACTIVE && pix_y < V_ACTIVE));

      // 4. end flags only at the ends
      assert (line_end == (pix_x == H_TOTAL - 1));
      assert (frame_end == (pix_x == H_TOTAL - 1 && pix_y == V_TOTAL - 1));

      // 5. exactly one pixel per clock, wrapping to zero and never skipping
      if (prev_valid) begin
        if (prev_x == H_TOTAL - 1) begin
          assert (pix_x == 10'd0);
          if (prev_y == V_TOTAL - 1) assert (pix_y == 10'd0);
          else assert (pix_y == prev_y + 10'd1);
        end else begin
          assert (pix_x == prev_x + 10'd1);
          assert (pix_y == prev_y);
        end
      end
    end
  end

  // Non-vacuity: the interesting corners are reachable.
  always @(posedge clk) begin
    if (rst_n) begin
      cover (!hsync_n);
      cover (!vsync_n);
      cover (line_end);
      cover (active && pix_x == H_ACTIVE - 1);
    end
  end

endmodule
