/*
 * Copyright (c) 2026 Daniel Tyukov
 * SPDX-License-Identifier: Apache-2.0
 *
 * Demo wrapper for putting this tile on an iCE40 board.
 *
 * Why a wrapper at all
 * --------------------
 * Two reasons, and neither is cosmetic.
 *
 * 1. Pin count. The raw tile has 43 ports: ui_in, uo_out, uio_in, uio_out,
 *    uio_oe, ena, clk, rst_n. An ICE40UP5K in sg48 has 39 usable I/O. On real
 *    silicon those ports go to the Tiny Tapeout harness, not to pads, so
 *    exposing all of them on a board is not what anyone would build. This
 *    wrapper exposes the 26 that a board actually needs: the VGA PMOD, the
 *    control switches, the entropy and cutoff inputs, and the three status
 *    outputs.
 *
 * 2. Board pin names. The tile speaks ui_in/uio_in; a board speaks switches,
 *    a VGA PMOD and three status LEDs.
 *
 * What this wrapper deliberately does NOT do is choose the entropy source. It
 * used to pass SIM_ENTROPY = 1 to drop the ring oscillators, which meant the
 * local flow was building something the `fpga` workflow does not. Both now go
 * through the same `SYNTH branch in src/entropy_source.v, which tt_fpga.py
 * defines and scripts/run_fpga.sh defines too, so a local pass and a CI pass are
 * about the same netlist. See src/entropy_source.v for why nextpnr-ice40 leaves
 * no other option, and why an external entropy pin is the right answer on an
 * FPGA regardless.
 *
 * This wrapper is for FPGA bring-up and for the pattern generators. It is not
 * part of the ASIC deliverable and is not listed in info.yaml.
 */

`default_nettype none

module fpga_top (
    input  wire       clk,       // 25.175 MHz pixel clock, from a PLL or oscillator
    input  wire       rst_n,

    // TinyVGA PMOD, wired straight through
    output wire [7:0] vga,       // {hsync, B0, G0, R0, vsync, B1, G1, R1}

    // controls, see the pin map in README.md
    input  wire [7:0] sw,        // ui_in

    // entropy in and the health test cutoff selects
    input  wire       ent_in,    // uio_in[0]
    input  wire [1:0] rct_cut,   // uio_in[2:1]
    input  wire [1:0] apt_cut,   // uio_in[4:3]

    // status out
    output wire       rct_fail,  // uio_out[5]
    output wire       apt_fail,  // uio_out[6]
    output wire       rnd_out    // uio_out[7]
);

  wire [7:0] uio_out;
  wire [7:0] uio_oe;

  tt_um_danieltyukov_vga_trng u_tile (
      .ui_in  (sw),
      .uo_out (vga),
      .uio_in ({3'b000, apt_cut, rct_cut, ent_in}),
      .uio_out(uio_out),
      .uio_oe (uio_oe),
      .ena    (1'b1),
      .clk    (clk),
      .rst_n  (rst_n)
  );

  assign rct_fail = uio_out[5];
  assign apt_fail = uio_out[6];
  assign rnd_out  = uio_out[7];

  // uio_oe is a constant 8'b1110_0000 and the wrapper has already committed to
  // that direction split, so nothing here needs it. Sink it so the linters stay
  // quiet, the same idiom the rest of the design uses.
  wire _unused = &{uio_oe, uio_out[4:0], 1'b0};

endmodule
