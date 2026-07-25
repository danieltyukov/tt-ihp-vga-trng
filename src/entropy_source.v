/*
 * Copyright (c) 2026 Daniel Tyukov
 * SPDX-License-Identifier: Apache-2.0
 *
 * Noise source front end: prescaler, path select, metastability filter.
 * raw_bit is valid on every clock where raw_stb is high.
 *
 * Why there are two paths
 * -----------------------
 * A free running ring oscillator has no meaning in an event driven simulator.
 * Icarus will happily oscillate a delay annotated inverter loop, but the result
 * is a perfectly periodic square wave with zero jitter, so sampling it produces
 * a deterministic sequence and not entropy. A "TRNG test" written against that
 * path measures the simulator's timewheel, not the design. That is the trap this
 * project is built to avoid, so the source is parameterised:
 *
 *   SIM_ENTROPY = 0  Two ring oscillators of coprime length are XORed and
 *                    sampled through a synchroniser. This is the path that gets
 *                    hardened and taped out. It can be checked structurally
 *                    (test/tb_ring.v proves it oscillates and that the enable
 *                    gate works) but never statistically in simulation.
 *
 *   SIM_ENTROPY = 1  The raw bit comes straight from ext_bit and no ring
 *                    oscillator is elaborated at all. The testbench drives a
 *                    known stream, so the debiaser, the conditioner and both
 *                    health tests are bit exact checkable against a Python
 *                    model.
 *
 * In both builds ext_bit (uio_in[0]) is XORed into the sampled value, so an
 * external noise source can also be injected in silicon.
 *
 * Sampling rate
 * -------------
 * The oscillator is sampled once every 8 pixel clocks by default, which at
 * 25.175 MHz is 318 ns of accumulated phase drift per sample. sample_fast drops
 * the divider to 1 so simulation and bench characterisation do not have to wait.
 * Sampling faster than the jitter accumulation time is how ring oscillator TRNGs
 * usually fail, which is why this is a runtime control and not a constant.
 */

`default_nettype none

module entropy_source #(
    parameter integer SIM_ENTROPY = 0
) (
    input  wire clk,
    input  wire rst_n,
    input  wire sample_fast,  // 1 = one sample per clock, 0 = one per 8 clocks
    input  wire ext_bit,      // external entropy input, always XORed in
    output wire raw_bit,
    output wire raw_stb
);
  reg [2:0] div;
  always @(posedge clk) begin
    if (!rst_n) div <= 3'd0;
    else div <= div + 3'd1;
  end
  assign raw_stb = sample_fast | (div == 3'd7);

  wire osc_bit;

  generate
    if (SIM_ENTROPY != 0) begin : g_sim_source
      assign osc_bit = 1'b0;
    end else begin : g_ring_source
      // Two chains of coprime length. XORing them makes each sample depend on
      // both phases, so the combined period is long and the jitter of both
      // chains contributes.
      wire osc_a, osc_b;
      ring_osc #(
          .STAGES(5),
          .SIM_DELAY(3)
      ) u_osc_a (
          .en (rst_n),
          .osc(osc_a)
      );
      ring_osc #(
          .STAGES(7),
          .SIM_DELAY(2)
      ) u_osc_b (
          .en (rst_n),
          .osc(osc_b)
      );

      // Two stage synchroniser. The first flop is the one allowed to go
      // metastable; the second gives it a full clock period to resolve.
      reg meta_q, sync_q;
      always @(posedge clk) begin
        if (!rst_n) begin
          meta_q <= 1'b0;
          sync_q <= 1'b0;
        end else begin
          meta_q <= osc_a ^ osc_b;
          sync_q <= meta_q;
        end
      end
      assign osc_bit = sync_q;
    end
  endgenerate

  assign raw_bit = osc_bit ^ ext_bit;
endmodule
