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
 * hardened module as is, with SIM_ENTROPY = 0 and both ring oscillators present.
 * See the force block at the bottom of this file for what that costs and how it
 * is dealt with.
 */
module tb ();

  // The regression runs about 230 ms of simulated time, so a full hierarchy
  // dump is tens of megabytes and costs roughly 20% of the runtime. By default
  // only the tile pins are dumped, which is what you look at for VGA timing.
  // Pass +dump_all to vvp for the whole hierarchy when debugging internals.
  initial begin
    $dumpfile("tb.fst");
    if ($test$plusargs("dump_all")) $dumpvars(0, tb);
    else $dumpvars(1, tb);
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

`ifdef GL_TEST
  // ------------------------------------------------------------------------
  // Break the two ring oscillators, or nothing past reset release simulates.
  //
  // src/ring_osc.v is a deliberate combinational loop and it survives synthesis,
  // so the hardened netlist holds a five inverter and a seven inverter ring. The
  // IHP functional cell models are zero delay (sg13g2_inv_1 is `not (Y, A);` with
  // a 0.0 specify block), so the moment rst_n releases and the enable NAND opens,
  // an event driven simulator has a zero delay feedback loop and stops advancing
  // in time. Measured: vvp runs the reset phase and then makes no further
  // progress, which is what left the gl_test job sitting for 1h51m before this
  // block existed. It is inherent to gate level simulation of any ring oscillator
  // against zero delay models, not a defect in the RTL or in the netlist.
  //
  // Forcing chain[0] of each ring low cuts the loop at the enable NAND output.
  // The rest of each chain then resolves to a static alternating pattern, and
  // because both chains have an odd stage count both ring outputs settle to 0:
  //
  //   osc_a = chain_a[4] = ~~~~0 = 0        osc_b = chain_b[6] = ~~~~~~0 = 0
  //
  // entropy_source.v samples osc_a ^ osc_b, so the sampled oscillator bit is a
  // constant 0 and raw_bit = 0 ^ ext_bit = uio_in[0]. That is bit for bit the
  // SIM_ENTROPY = 1 behaviour the RTL regression drives, which is why the same
  // test module can run against this netlist. test_gl.py asserts all of it
  // (both forced nets, the settled ring outputs and the sampled bit) rather than
  // taking it on trust.
  //
  // What this does NOT verify is the oscillator itself. Nothing in simulation
  // can: see src/entropy_source.v and test/tb_ring.v.
  //
  // The net names come from the LibreLane netlist. They are yosys' flattened
  // hierarchical names, stable across runs because ring_osc/ring_inv/ring_gate
  // carry (* keep_hierarchy *), and verified identical between the local
  // `make harden` netlist and the one the CI gds job produced. If a future PDK or
  // LibreLane version renames them, this fails at elaboration with an unmistakable
  // error, which is the behaviour we want over silently hanging again.
  // ------------------------------------------------------------------------
  initial begin
    force user_project.\u_trng.u_src.g_ring_source.u_osc_a.chain[0] = 1'b0;
    force user_project.\u_trng.u_src.g_ring_source.u_osc_b.chain[0] = 1'b0;
  end
`endif

endmodule
