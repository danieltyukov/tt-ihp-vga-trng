/*
 * Copyright (c) 2026 Daniel Tyukov
 * SPDX-License-Identifier: Apache-2.0
 *
 * TRNG top level. Wires the entropy pipeline together:
 *
 *   entropy_source -> von_neumann -> lfsr_whitener -> rnd_bit / state
 *                  \-> health_monitor (raw samples, pre conditioning)
 *
 * The conditioned bit on the pin is gated by the sticky health status, so a
 * detected noise source failure stops the output rather than quietly shipping
 * whatever the LFSR happens to be doing. The LFSR state itself keeps running,
 * because the starfield pattern uses it as a plain pixel rate PRNG and there is
 * no reason to freeze the display when the noise source misbehaves.
 */

`default_nettype none

module trng #(
    parameter integer SIM_ENTROPY = 0
) (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        sample_fast,
    input  wire        ext_bit,
    input  wire [1:0]  rct_cut_sel,
    input  wire [1:0]  apt_cut_sel,
    input  wire        health_clr,
    output wire        rnd_bit,      // gated conditioned output
    output wire [15:0] rnd_state,    // raw LFSR state, for the starfield
    output wire        rct_fail,
    output wire        apt_fail
);
  wire raw_bit, raw_stb;
  entropy_source #(
      .SIM_ENTROPY(SIM_ENTROPY)
  ) u_src (
      .clk(clk),
      .rst_n(rst_n),
      .sample_fast(sample_fast),
      .ext_bit(ext_bit),
      .raw_bit(raw_bit),
      .raw_stb(raw_stb)
  );

  wire vn_bit, vn_stb;
  von_neumann u_vn (
      .clk(clk),
      .rst_n(rst_n),
      .in_bit(raw_bit),
      .in_stb(raw_stb),
      .out_bit(vn_bit),
      .out_stb(vn_stb)
  );

  wire lfsr_out;
  lfsr_whitener u_white (
      .clk(clk),
      .rst_n(rst_n),
      .ent_bit(vn_bit),
      .ent_stb(vn_stb),
      .rnd_bit(lfsr_out),
      .state(rnd_state)
  );

  health_monitor u_health (
      .clk(clk),
      .rst_n(rst_n),
      .smp_bit(raw_bit),
      .smp_stb(raw_stb),
      .rct_cut_sel(rct_cut_sel),
      .apt_cut_sel(apt_cut_sel),
      .clr(health_clr),
      .rct_fail(rct_fail),
      .apt_fail(apt_fail)
  );

  assign rnd_bit = lfsr_out & ~(rct_fail | apt_fail);
endmodule
