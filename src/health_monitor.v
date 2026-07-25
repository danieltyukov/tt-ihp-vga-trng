/*
 * Copyright (c) 2026 Daniel Tyukov
 * SPDX-License-Identifier: Apache-2.0
 *
 * Continuous health tests on the noise source, in the spirit of NIST
 * SP 800-90B section 4.4.
 *
 * Both tests run on the raw samples, before the debiaser and before the
 * conditioner. That placement is deliberate and it is what the standard asks
 * for: the tests exist to detect the noise source failing, and both von Neumann
 * debiasing and an LFSR would hide exactly the failures being looked for. A
 * stuck-at-0 source produces a perfectly healthy looking LFSR output forever.
 *
 * Repetition count test (4.4.1)
 * -----------------------------
 * Count consecutive identical samples. Fail when the run reaches the cutoff C.
 * The standard picks C from the assessed min-entropy and a false positive rate
 * alpha: C = 1 + ceil(-log2(alpha) / H). This design exposes C as a two bit
 * selector over {4, 8, 16, 32} rather than hardwiring one value, because the
 * min-entropy of a ring oscillator sampled at a given rate is not known until
 * silicon is measured. 32 corresponds to roughly H = 0.65 bits/sample at
 * alpha = 2^-20; 4 is a deliberately hair-trigger setting for bench bring-up.
 *
 * Adaptive proportion test (4.4.2)
 * --------------------------------
 * Take the first sample of each window as the reference value, count how many
 * of the W samples in the window equal it, and fail if that count exceeds the
 * cutoff. W is 64 here (the standard uses 64 for binary sources) and the cutoff
 * is a two bit selector over {40, 48, 56, 62}. This catches a source that has
 * drifted heavily biased without ever getting stuck long enough to trip the
 * repetition test.
 *
 * Both failures latch. Once set, a sticky flag stays set until clr is asserted,
 * so a transient failure cannot be missed by software polling slowly. While
 * either flag is set the conditioned output is gated off upstream, which is the
 * "stop producing output on failure" behaviour the standard requires.
 */

`default_nettype none

module health_monitor (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       smp_bit,
    input  wire       smp_stb,
    input  wire [1:0] rct_cut_sel,
    input  wire [1:0] apt_cut_sel,
    input  wire       clr,        // level sensitive clear of both sticky flags
    output reg        rct_fail,
    output reg        apt_fail
);
  localparam [5:0] W_LAST = 6'd63;  // window is 64 samples, indices 0 .. 63

  // ---- cutoff decode -------------------------------------------------------
  reg [5:0] rct_cut;
  always @(*) begin
    case (rct_cut_sel)
      2'd0:    rct_cut = 6'd4;
      2'd1:    rct_cut = 6'd8;
      2'd2:    rct_cut = 6'd16;
      default: rct_cut = 6'd32;
    endcase
  end

  reg [6:0] apt_cut;
  always @(*) begin
    case (apt_cut_sel)
      2'd0:    apt_cut = 7'd40;
      2'd1:    apt_cut = 7'd48;
      2'd2:    apt_cut = 7'd56;
      default: apt_cut = 7'd62;
    endcase
  end

  // ---- repetition count test ----------------------------------------------
  reg       prev_bit;
  reg       prev_val;  // 0 until the first sample has been seen
  reg [5:0] run_len;

  // ---- adaptive proportion test -------------------------------------------
  reg       apt_ref;
  reg [5:0] win_cnt;   // 0 .. W-1
  reg [6:0] match_cnt;

  wire [5:0] run_next   = prev_val && (smp_bit == prev_bit) ? run_len + 6'd1 : 6'd1;
  wire       win_start  = (win_cnt == 6'd0);
  wire       ref_bit    = win_start ? smp_bit : apt_ref;
  wire [6:0] match_next = (win_start ? 7'd0 : match_cnt) + ((smp_bit == ref_bit) ? 7'd1 : 7'd0);

  always @(posedge clk) begin
    if (!rst_n) begin
      prev_bit  <= 1'b0;
      prev_val  <= 1'b0;
      run_len   <= 6'd1;
      apt_ref   <= 1'b0;
      win_cnt   <= 6'd0;
      match_cnt <= 7'd0;
      rct_fail  <= 1'b0;
      apt_fail  <= 1'b0;
    end else begin
      // clr comes first so that a failure detected on the same clock still
      // wins: clearing must never swallow a live failure.
      if (clr) begin
        rct_fail <= 1'b0;
        apt_fail <= 1'b0;
      end

      if (smp_stb) begin
        // repetition count
        prev_bit <= smp_bit;
        prev_val <= 1'b1;
        run_len  <= run_next;
        if (run_next >= rct_cut) rct_fail <= 1'b1;

        // adaptive proportion
        apt_ref   <= ref_bit;
        match_cnt <= match_next;
        win_cnt   <= (win_cnt == W_LAST) ? 6'd0 : win_cnt + 6'd1;
        if ((win_cnt == W_LAST) && (match_next > apt_cut)) apt_fail <= 1'b1;
      end
    end
  end
endmodule
