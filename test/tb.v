`default_nettype none
`timescale 1ns / 1ps

/*
 * cocotb wrapper around the tile.
 *
 * SIM_ENTROPY is forced to 1 for RTL simulation so that the noise source is
 * uio_in[0] instead of a pair of ring oscillators. See src/entropy_source.v for
 * why: a delay annotated inverter loop in an event simulator is a periodic
 * square wave, not entropy, and testing against it would prove nothing. The
 * ring oscillator path is covered separately by test/tb_ring.v.
 *
 * The gate level netlist has no parameters, so the GL build instantiates the
 * hardened module as is. GL simulation therefore exercises the ring oscillator
 * path and only the VGA timing and reset tests are meaningful there.
 */
module tb ();

  initial begin
    $dumpfile("tb.fst");
    $dumpvars(0, tb);
    #1;
  end

  reg clk;
  reg rst_n;
  reg ena;
  reg [7:0] ui_in;
  reg [7:0] uio_in;
  wire [7:0] uo_out;
  wire [7:0] uio_out;
  wire [7:0] uio_oe;

`ifdef GL_TEST
  tt_um_danieltyukov_vga_trng user_project (
`else
  tt_um_danieltyukov_vga_trng #(
      .SIM_ENTROPY(1)
  ) user_project (
`endif
      .ui_in  (ui_in),
      .uo_out (uo_out),
      .uio_in (uio_in),
      .uio_out(uio_out),
      .uio_oe (uio_oe),
      .ena    (ena),
      .clk    (clk),
      .rst_n  (rst_n)
  );

endmodule
