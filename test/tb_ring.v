/*
 * Copyright (c) 2026 Daniel Tyukov
 * SPDX-License-Identifier: Apache-2.0
 *
 * Structural testbench for the ring oscillator path.
 *
 * This is deliberately NOT part of the cocotb regression and it deliberately
 * makes no claim about randomness. In an event simulator a delay annotated
 * inverter loop is an exact square wave, so anything statistical measured here
 * would be a property of the timewheel. What can honestly be checked is
 * structure and control:
 *
 *   1. the loop does not oscillate while en is low, and it settles to a defined
 *      value rather than staying at x,
 *   2. it oscillates once en is released,
 *   3. a 5 stage and a 7 stage ring have different periods, which is the whole
 *      reason there are two of them (if synthesis collapses the chains, both
 *      degrade to one inverter, the periods become equal and the XOR of the two
 *      becomes a constant),
 *   4. the measured periods match 2 * STAGES * SIM_DELAY,
 *   5. entropy_source with SIM_ENTROPY=1 elaborates no oscillator and follows
 *      ext_bit exactly.
 *
 * Run with: make -C test ring
 */

`default_nettype none
`timescale 1ns / 1ps

module tb_ring ();

  integer errors = 0;

  task check(input cond, input [8*64-1:0] name);
    begin
      if (cond) $display("  PASS  %0s", name);
      else begin
        $display("  FAIL  %0s", name);
        errors = errors + 1;
      end
    end
  endtask

  // ---- oscillators under test ---------------------------------------------
  reg  en = 1'b0;
  wire osc5, osc7;

  ring_osc #(
      .STAGES(5),
      .SIM_DELAY(3)
  ) u_r5 (
      .en (en),
      .osc(osc5)
  );

  ring_osc #(
      .STAGES(7),
      .SIM_DELAY(2)
  ) u_r7 (
      .en (en),
      .osc(osc7)
  );

  integer edges5 = 0;
  integer edges7 = 0;
  always @(posedge osc5) edges5 = edges5 + 1;
  always @(posedge osc7) edges7 = edges7 + 1;

  // ---- deterministic path -------------------------------------------------
  reg        clk = 1'b0;
  reg        rst_n = 1'b0;
  reg        ext_bit = 1'b0;
  wire       sim_raw, sim_stb;

  entropy_source #(
      .SIM_ENTROPY(1)
  ) u_sim_src (
      .clk        (clk),
      .rst_n      (rst_n),
      .sample_fast(1'b1),
      .ext_bit    (ext_bit),
      .raw_bit    (sim_raw),
      .raw_stb    (sim_stb)
  );

  always #20 clk = ~clk;  // 25 MHz-ish, only used for the deterministic path

  integer t0, t1;
  integer i;
  integer p5, p7;
  integer mism;
  integer xor_hi;
  integer xor_edges;
  reg     xor_prev;

  initial begin
    $display("ring oscillator structural checks");

    // 1. Held disabled. The chain must resolve out of x, which is itself one
    //    transition, so the counters are cleared after settling and then the
    //    quiet window is checked.
    #200;
    check(osc5 === 1'b0 || osc5 === 1'b1, "5 stage chain resolves out of x with en low");
    check(osc7 === 1'b0 || osc7 === 1'b1, "7 stage chain resolves out of x with en low");
    edges5 = 0;
    edges7 = 0;
    #400;
    check(edges5 == 0 && edges7 == 0, "no oscillation while en is low");

    // 2. Release enable, confirm both start.
    en = 1'b1;
    #500;
    check(edges5 > 0, "5 stage ring oscillates once enabled");
    check(edges7 > 0, "7 stage ring oscillates once enabled");

    // 3. Measure the periods.
    @(posedge osc5) t0 = $time;
    @(posedge osc5) t1 = $time;
    p5 = t1 - t0;
    @(posedge osc7) t0 = $time;
    @(posedge osc7) t1 = $time;
    p7 = t1 - t0;
    $display("  measured period: 5 stage = %0d ns, 7 stage = %0d ns", p5, p7);
    check(p5 == 2 * 5 * 3, "5 stage period equals 2 * STAGES * SIM_DELAY = 30 ns");
    check(p7 == 2 * 7 * 2, "7 stage period equals 2 * STAGES * SIM_DELAY = 28 ns");

    // 4. The two rings must not be the same oscillator, and their XOR, which is
    //    what the synchroniser samples, must actually move.
    check(p5 != p7, "the two rings have different periods");
    xor_hi    = 0;
    xor_edges = 0;
    xor_prev  = osc5 ^ osc7;
    for (i = 0; i < 420; i = i + 1) begin
      #1;
      if (osc5 ^ osc7) xor_hi = xor_hi + 1;
      if ((osc5 ^ osc7) !== xor_prev) xor_edges = xor_edges + 1;
      xor_prev = osc5 ^ osc7;
    end
    $display("  XOR high for %0d of 420 ns with %0d transitions", xor_hi, xor_edges);
    check(xor_hi > 40 && xor_hi < 380, "XOR of the two rings is not stuck at a constant");
    check(xor_edges > 20, "XOR of the two rings toggles many times per sample interval");

    // 5. Disable again. Settling counts as one transition, so clear and recheck.
    en = 1'b0;
    #200;
    edges5 = 0;
    edges7 = 0;
    #400;
    check(edges5 == 0 && edges7 == 0, "oscillation stops when en is deasserted");

    // 6. Deterministic path follows ext_bit with no oscillator elaborated.
    rst_n = 1'b1;
    @(posedge clk);
    mism = 0;
    for (i = 0; i < 64; i = i + 1) begin
      ext_bit = i[0] ^ i[3];
      @(negedge clk);
      if (sim_raw !== ext_bit) mism = mism + 1;
      if (sim_stb !== 1'b1) mism = mism + 1;
    end
    check(mism == 0, "SIM_ENTROPY=1 source tracks ext_bit and strobes every clock");

    $display("");
    if (errors == 0) $display("tb_ring: all checks passed");
    else begin
      $display("tb_ring: %0d CHECK(S) FAILED", errors);
      $fatal(1, "tb_ring failed");
    end
    $finish;
  end

endmodule
