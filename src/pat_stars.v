/*
 * Copyright (c) 2026 Daniel Tyukov
 * SPDX-License-Identifier: Apache-2.0
 *
 * Pattern 6: starfield driven by the whitened random stream.
 *
 * There is no memory for a star table, so the LFSR state is sampled at pixel
 * rate and a star is drawn whenever the low ten bits happen to be zero. For a
 * maximal length 16 bit LFSR the all-zero ten bit window occurs 2^6 - 1 = 63
 * times per 65535 step period, so the density is about 1/1040 and a visible
 * frame of 307200 pixels carries roughly 300 stars.
 *
 * A frame is 420000 pixel clocks and the LFSR period is 65535, so the phase
 * advances by 420000 mod 65535 = 27210 steps per frame. The field is therefore
 * different on every frame and the starfield twinkles. When real entropy is
 * being accumulated into the LFSR the field is additionally unpredictable,
 * which is the point of wiring the pattern to the TRNG at all.
 */

`default_nettype none

module pat_stars (
    input  wire [15:0] rnd,
    output wire [ 5:0] rgb
);
  wire       star = ~|rnd[9:0];
  wire [1:0] lum  = {rnd[12], 1'b1};  // 2'b01 or 2'b11, never invisible

  // Three channel enables give white and six tinted star colours. All zero
  // would be an invisible star, so that code is remapped to white.
  wire [2:0] tint = rnd[15:13];
  wire [2:0] en   = (tint == 3'b000) ? 3'b111 : tint;

  assign rgb = {(star & en[2]) ? lum : 2'b00,
                (star & en[1]) ? lum : 2'b00,
                (star & en[0]) ? lum : 2'b00};

  wire _unused = &{rnd[11:10], 1'b0};
endmodule
