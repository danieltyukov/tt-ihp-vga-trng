/*
 * Copyright (c) 2026 Daniel Tyukov
 * SPDX-License-Identifier: Apache-2.0
 *
 * tt_um_danieltyukov_vga_trng
 *
 * A 640x480 VGA pattern engine for the Tiny Tapeout IHP 130nm shuttle. Eight
 * pattern generators share one sync generator; the active pattern is chosen
 * either from three input pins or by a hardware true random number generator
 * with von Neumann debiasing, LFSR conditioning and SP 800-90B style online
 * health tests.
 *
 * Pin map
 * -------
 *  ui_in[2:0]   manual pattern select, used when ui_in[3] is low
 *  ui_in[3]     random select enable
 *  ui_in[4]     health flag clear, level sensitive
 *  ui_in[5]     random reselect rate: 0 = every 64 frames, 1 = every 8 frames
 *  ui_in[6]     freeze animation, holds the frame counter
 *  ui_in[7]     entropy sample rate: 0 = one sample per 8 clocks, 1 = per clock
 *
 *  uo_out       TinyVGA PMOD, {hsync, B0, G0, R0, vsync, B1, G1, R1}
 *
 *  uio_in[0]    external entropy bit, XORed into the noise source
 *  uio_in[2:1]  repetition count test cutoff select: 4, 8, 16, 32
 *  uio_in[4:3]  adaptive proportion test cutoff select: 40, 48, 56, 62 of 64
 *  uio_out[5]   repetition count test sticky failure flag
 *  uio_out[6]   adaptive proportion test sticky failure flag
 *  uio_out[7]   conditioned random bit stream, gated by the health flags
 *  uio_in[7:5]  unused, uio_oe makes these three pins outputs
 *
 * Design constraint
 * -----------------
 * There is no framebuffer and there is no room for one. A 640x480 frame at
 * 6 bits per pixel is 230 kB, and the whole 1x1 tile has room for on the order
 * of a hundred flip-flops. Six of the eight patterns are therefore pure
 * combinational functions of (pix_x, pix_y, frame_cnt). Only the bouncing box
 * and the cellular automaton hold state, and between them that is 64 bits.
 */

`default_nettype none

module tt_um_danieltyukov_vga_trng #(
    // 0 keeps the ring oscillators, which is what gets taped out. 1 replaces
    // them with uio_in[0] so the entropy pipeline is deterministically
    // testable. test/tb.v sets this to 1 for RTL simulation.
    parameter integer SIM_ENTROPY = 0
) (
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: Input path
    output wire [7:0] uio_out,  // IOs: Output path
    output wire [7:0] uio_oe,   // IOs: Enable path (active high: 0=input, 1=output)
    input  wire       ena,      // always 1 when the design is powered
    input  wire       clk,      // 25.175 MHz pixel clock
    input  wire       rst_n     // active low reset
);

  // ---- input decode --------------------------------------------------------
  wire [2:0] sel_manual = ui_in[2:0];
  wire       rand_en    = ui_in[3];
  wire       health_clr = ui_in[4];
  wire       fast_sw    = ui_in[5];
  wire       freeze     = ui_in[6];
  wire       samp_fast  = ui_in[7];

  wire       ext_ent    = uio_in[0];
  wire [1:0] rct_sel    = uio_in[2:1];
  wire [1:0] apt_sel    = uio_in[4:3];

  // ---- sync generator ------------------------------------------------------
  wire [9:0] pix_x, pix_y;
  wire [7:0] frame_cnt;
  wire       hsync_n, vsync_n, active, line_end, frame_end;

  vga_sync u_sync (
      .clk(clk),
      .rst_n(rst_n),
      .frame_en(~freeze),
      .pix_x(pix_x),
      .pix_y(pix_y),
      .hsync_n(hsync_n),
      .vsync_n(vsync_n),
      .active(active),
      .line_end(line_end),
      .frame_end(frame_end),
      .frame_cnt(frame_cnt)
  );

  wire frame_upd = frame_end & ~freeze;

  // ---- entropy pipeline ----------------------------------------------------
  wire        rnd_bit;
  wire [15:0] rnd_state;
  wire        rct_fail, apt_fail;

  trng #(
      .SIM_ENTROPY(SIM_ENTROPY)
  ) u_trng (
      .clk(clk),
      .rst_n(rst_n),
      .sample_fast(samp_fast),
      .ext_bit(ext_ent),
      .rct_cut_sel(rct_sel),
      .apt_cut_sel(apt_sel),
      .health_clr(health_clr),
      .rnd_bit(rnd_bit),
      .rnd_state(rnd_state),
      .rct_fail(rct_fail),
      .apt_fail(apt_fail)
  );

  // ---- random pattern selection -------------------------------------------
  // The conditioned stream is sampled once every 8 or 64 frames, which is
  // 3.4 to 27 million pixel clocks apart, so three bits straight off the LFSR
  // state are uncorrelated between reloads and no output shift register is
  // needed. Reload is inhibited while a health failure is latched, matching
  // the "stop using the source once it has failed" rule.
  wire health_fail = rct_fail | apt_fail;
  wire reload = frame_upd && (fast_sw ? (frame_cnt[2:0] == 3'b111)
                                     : (frame_cnt[5:0] == 6'b111111));

  reg [2:0] sel_rand;
  always @(posedge clk) begin
    if (!rst_n) sel_rand <= 3'd0;
    else if (reload && !health_fail) sel_rand <= rnd_state[2:0];
  end

  wire [2:0] sel = rand_en ? sel_rand : sel_manual;

  // ---- pattern bank --------------------------------------------------------
  wire [5:0] rgb_raw;
  pattern_mux u_pat (
      .clk(clk),
      .rst_n(rst_n),
      .sel(sel),
      .pix_x(pix_x),
      .pix_y(pix_y),
      .frame(frame_cnt),
      .frame_upd(frame_upd),
      .line_end(line_end),
      .frame_end(frame_end),
      .rnd_state(rnd_state),
      .rgb(rgb_raw)
  );

  // Blanking must be black or the monitor will not lock.
  wire [5:0] rgb = active ? rgb_raw : 6'b00_00_00;
  wire [1:0] r = rgb[5:4];
  wire [1:0] g = rgb[3:2];
  wire [1:0] b = rgb[1:0];

  // ---- output packing ------------------------------------------------------
  // TinyVGA PMOD bit order.
  assign uo_out  = {hsync_n, b[0], g[0], r[0], vsync_n, b[1], g[1], r[1]};

  assign uio_out = {rnd_bit, apt_fail, rct_fail, 5'b00000};
  assign uio_oe  = 8'b1110_0000;

  // ena is tied high by the harness and uio_in[7:5] are driven as outputs, so
  // they are read here only to keep the linters from reporting unused inputs.
  wire _unused = &{ena, uio_in[7:5], 1'b0};

endmodule
