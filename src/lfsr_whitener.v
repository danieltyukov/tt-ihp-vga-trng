/*
 * Copyright (c) 2026 Daniel Tyukov
 * SPDX-License-Identifier: Apache-2.0
 *
 * LFSR conditioner and pixel rate random source.
 *
 * Polynomial
 * ----------
 *   x^16 + x^15 + x^13 + x^4 + 1
 *
 * Fibonacci form, taps at bit positions 15, 14, 12 and 3 of the state register
 * (state[15] is x^16). This is one of the standard maximal length 16 bit tap
 * sets, so on its own the state cycles through all 65535 non-zero values.
 *
 * The all-zero state is then folded back in with the usual de Bruijn
 * correction, XORing (state[14:0] == 0) into the feedback. That splices 0x0000
 * into the cycle just ahead of 0x0001, giving a period of 65536 that visits
 * every 16 bit value exactly once. Two reasons to pay the 15 input NOR:
 *
 *   - No lockup. Entropy is XORed into the feedback, and from state 0x8000 an
 *     injected 1 would otherwise drive the register to all zeros, where a pure
 *     LFSR would stall until another 1 happened to arrive.
 *   - Perfect balance. state[15] is 1 for exactly 32768 of the 65536 states,
 *     so one period of output carries exactly 32768 ones. An m-sequence is off
 *     by one; this is not.
 *
 * The cost is one 16 bit run of zeros per period, which is the one statistical
 * artefact the runs histogram in the characterisation plots is expected to show.
 * test/test.py walks the whole period and asserts that all 65536 states are
 * visited and that the seed does not recur before step 65536.
 *
 * Two jobs, one register
 * ----------------------
 *  1. Conditioning. Every debiased bit is XORed into the feedback path, so
 *     entropy accumulates into the state instead of being consumed one bit at
 *     a time. Because the LFSR keeps stepping while it waits, the arrival
 *     times of the debiased bits also carry information.
 *  2. Pixel rate randomness. The register advances on every pixel clock, which
 *     is what the starfield pattern samples. Reusing it saves the 15 flip-flops
 *     a separate pixel PRNG would have cost, which matters on a 1x1 tile.
 *
 * Honest limitation: an LFSR is linear. It is a decorrelator and a rate
 * matcher, not a cryptographic conditioner. Given 16 consecutive output bits
 * the whole state is recoverable, so the output must not be treated as a CSPRNG
 * or as full entropy per bit. For that you would put a sponge or a block cipher
 * here, and neither fits in this tile.
 */

`default_nettype none

module lfsr_whitener #(
    parameter [15:0] SEED = 16'hACE1
) (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        ent_bit,   // debiased entropy bit
    input  wire        ent_stb,   // 1 when ent_bit is valid
    output wire        rnd_bit,   // conditioned output bit
    output reg  [15:0] state
);
  wire fb = state[15] ^ state[14] ^ state[12] ^ state[3]
          ^ (~|state[14:0])          // de Bruijn correction, see header
          ^ (ent_stb & ent_bit);     // entropy accumulation

  always @(posedge clk) begin
    if (!rst_n) state <= SEED;
    else state <= {state[14:0], fb};
  end

  assign rnd_bit = state[15];
endmodule
