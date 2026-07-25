# Design document

Everything here is measured, not estimated. Cell counts and areas come from
Yosys 0.33 mapped against the real IHP `sg13g2_stdcell_typ_1p20V_25C.lib`, which
`scripts/synth_report.sh` fetches from
[IHP-Open-PDK](https://github.com/IHP-GmbH/IHP-Open-PDK). Timing numbers come out
of the cocotb regression. Raw reports are in [synth/](synth/).

## Contents

1. [Area budget and the tile decision](#1-area-budget-and-the-tile-decision)
2. [Why there is no framebuffer](#2-why-there-is-no-framebuffer)
3. [Pattern choices and what each one costs](#3-pattern-choices-and-what-each-one-costs)
4. [The entropy pipeline](#4-the-entropy-pipeline)
5. [Health tests and the SP 800-90B rationale](#5-health-tests-and-the-sp-800-90b-rationale)
6. [Verification plan](#6-verification-plan)
7. [Physical implementation](#7-physical-implementation)
8. [Known limitations](#8-known-limitations)

---

## 1. Area budget and the tile decision

### First, what a tile actually is

The project template says in an `info.yaml` comment that "a single tile is about
167x108 uM". For this shuttle that is wrong, and an earlier version of this
document repeated it. Tiny Tapeout's own floorplan templates,
`tt/tech/ihp-sg13g2/def/tt_block_NxM_pgvdd.def`, are the DEF files their `gds`
action hands the floorplanner, and they give:

| tiles | die | area |
| --- | --- | --- |
| 1x1 | 202.08 x 154.98 um | 31318 um2 |
| 1x2 | 202.08 x 313.74 um | 63401 um2 |

74% more per tile than the comment. Everything below is against the real numbers.

### The measurement

Three points in the flow, all on the real `sg13g2` library:

| stage | cell area | cells | fraction of a 1x1 tile | tool |
| --- | --- | --- | --- | --- |
| post synthesis | 18040 um2 | 1288, 142 flip-flops | 57.6% | Yosys 0.33 `stat -liberty` |
| **post route, real cells** | **25887.9 um2** | **1771** | **82.7%** | LibreLane 3.0.0.dev44 |
| post route, plus fill | 28941.5 um2 | 2343 instances | 92.4% | same run |

Synthesis says this fits a 1x1 tile comfortably. Post route it is 82.7% of the
tile, which by the usual rule of thumb says it does not fit at all: LibreLane and
`src/config.json` both target 60% placement density. Neither number is the
answer. The answer is to run it:

| `PL_TARGET_DENSITY_PCT` | outcome |
| --- | --- |
| 60, the default | global placement refuses: `[GPL-0302]`, 64.2% core utilisation, suggested 0.65 |
| 80 | places, then detailed placement fails after CTS with `[DPL-0036]`, 10 instances cannot be legalised once 234 hold buffers are in |
| **85** | **places, routes, signs off: 0 route/magic/klayout DRC, 0 LVS, 0 antenna, +17.45 ns setup, +0.15 ns hold** |

So `tiles: "1x1"`, with `PL_TARGET_DENSITY_PCT` raised to 85 in
`src/config.json`. That file invites exactly one edit, that key, for exactly the
`GPL-0302` error, and the three rows above are recorded next to it.

Those rows are from `make harden`, which only fixes `DIE_AREA`. Tiny Tapeout's own
`gds` job starts from `tt_block_1x1_pgvdd.def`, which carries their pin frame and
power grid as well, and it is more forgiving: a push with the target at 80
hardened and cleared `precheck` there while failing locally. 85 is committed
because it is what both flows accept.

### What it costs

A 1x2 die was hardened for comparison (`make harden` with
`HARDEN_DIE="202.08 313.74"`). At 40.9% density it routes with **41781 um** of
wire; the 1x1 needs **69427 um**, 66% more, all of it detours around congestion.
Setup slack barely moves, +17.50 ns against +17.45 ns, because this design is slow
relative to the process. On a design with real timing pressure that wirelength is
where the tile would be lost, and 1x2 would be the right call.

### What synthesis does not tell you

7850 um2 appears between synthesis and route, 44% on top of the synthesis
estimate, and it is the whole difference between 57.6% and 82.7% of a tile:

| class | area | count | what it is |
| --- | --- | --- | --- |
| multi-input combinational | 11363.6 um2 | 1161 | the logic |
| sequential | 7078.0 um2 | 142 | the flip-flops |
| **timing repair buffers** | **5831.5 um2** | **342**, 240 of them hold buffers | inserted after placement |
| clock buffers and inverters | 1246.5 um2 | 65 | the clock tree, which synthesis does not build |
| inverters and buffers | 368.3 um2 | 61 | drive strength fixes |
| fill | 3053.6 um2 | 572 | occupies whatever is left |

Hold fixing alone is 5831 um2, 23% of the real cell area, and none of it exists
until after placement. Anyone sizing a Tiny Tapeout tile from a `yosys stat`
number is going to be roughly 40% optimistic. That is the single most useful
thing this project measured.

![Per submodule area and the tile budget](img/synth_area.png)

### What it would take to get the density down

The tile fits at 82.7%, which is dense enough that the placer has to be told to
expect it, so it is worth knowing where the slack would come from if a future
change pushed it over. The only two blocks big enough to matter are the two that
hold state:

```
pat_rule30   4209 um2   40 flops
pat_ball     3346 um2   22 flops
             -------
             7555 um2
```

Dropping both takes post synthesis area from 18040 um2 to 10485 um2, and applying
the measured 44% post route growth gives roughly 15100 um2, about 48% of a tile.
That is comfortable, and the price is both animated patterns, the collision
behaviour, and the only genuinely iterated pattern in the design. It is not a
trade worth making while 85% density signs off clean, but it is the lever.

Smaller savings that were considered:

- The 8:1 mux over eight concurrent generators could be time multiplexed. Six of
  the eight are pure functions of the pixel position with no state to serialise,
  so the sequencing logic and pipeline registers would cost more than the
  combinational logic saved.
- `pat_rule30` could drop to 20 cells of 32 pixels, saving roughly 2000 um2, which
  is about 6 percentage points of density. The diagram gets chunkier.
- `health_monitor` (2368 um2) is 13% of the design and could be dropped. It is
  one of the reasons this project exists.

Two optimisations that were kept because they were free:

- `pat_ripple` computes the absolute value as `~d` instead of `-d`, dropping two
  10 bit incrementers. The result is one pixel of asymmetry either side of centre,
  which no monitor shows. The reference model reproduces the same off-by-one so
  the golden frame comparison stays exact.
- `pat_stars` reads the conditioner's LFSR directly instead of owning a pixel
  rate PRNG, saving 15 flip-flops (roughly 400 um2 with their logic).

### Where the area goes

| module | cells | flops | area um2 | share |
| --- | --- | --- | --- | --- |
| `pat_rule30` | 265 | 40 | 4209 | 23.3% |
| `pat_ball` | 251 | 22 | 3346 | 18.5% |
| `vga_sync` | 135 | 28 | 2395 | 13.3% |
| `health_monitor` | 159 | 24 | 2368 | 13.1% |
| `pat_plasma` | 115 | 0 | 1310 | 7.3% |
| `lfsr_whitener` | 46 | 16 | 1081 | 6.0% |
| `pat_ripple` | 81 | 0 | 953 | 5.3% |
| `entropy_source` | 28 | 5 | 437 | 2.4% |
| `pat_xor` | 39 | 0 | 434 | 2.4% |
| `pat_bars` | 42 | 0 | 403 | 2.2% |
| `von_neumann` | 17 | 4 | 325 | 1.8% |
| `pat_sierp` | 17 | 0 | 152 | 0.8% |
| `sine_q` | 11 | 0 | 132 | 0.7% |
| `pat_stars` | 16 | 0 | 131 | 0.7% |
| `ring_osc` (5 stage) | 5 | 0 | 29 | 0.2% |

Group totals: `pattern_mux` 861 cells / 10951 um2, `trng` 246 cells / 4191 um2.
Leaf modules sum to 17688 um2 against a flattened total of 18040; the 352 um2
difference is the top level glue, the blanking gate, the TinyVGA packing and the
pattern select register, plus what cross-module optimisation moves around.

Flip-flops dominate. `sg13g2_dfrbpq_1` is 48.99 um2 in this library, so 142 of
them is 6956 um2: **38.6% of the whole design is flip-flops**, before any of the
logic that drives them. That is the single fact that shaped every decision here,
and it is why six of the eight patterns hold no state at all.

---

## 2. Why there is no framebuffer

A 640x480 frame at 6 bits per pixel is 1 843 200 bits. As `sg13g2_dfrbpq_1` flops
at 48.99 um2 each that is 90.3 million um2, about 5006 tiles. Even one scanline of
640 pixels at 6 bits is 3840 bits, 188 000 um2, ten and a half tiles.

So the colour of a pixel has to be a function of where the beam is right now.
`pattern_mux` receives `(pix_x, pix_y, frame_cnt)` and six of the eight patterns
are combinational functions of exactly those three. The two exceptions hold state
that is *much smaller than a line*:

- `pat_ball` holds 24 bits: position, direction and colour index. The box is
  drawn by testing the current pixel against that position, not by remembering
  which pixels are inside it.
- `pat_rule30` holds 40 bits, one per automaton cell, which is 40 cells of 16
  pixels each rather than 640 individual pixels.

Both are updated during blanking (`frame_end` and every 32nd `line_end`), so
neither adds anything to the pixel path.

---

## 3. Pattern choices and what each one costs

The brief was at least six patterns that are genuinely different rather than six
variations on a gradient. The selection criteria were: is it visually distinct
from everything else here, does it fit, and does it exercise a different part of
the design.

### 0. XOR munching field, 434 um2, no state

`t = (x[7:0] ^ y[7:0]) + frame`, colour from three overlapping windows of `t`.
The XOR draws the interference figure and the addition scrolls the palette
diagonally through it, so a whole animated pattern costs one 8 bit XOR and one
8 bit adder. Cheapest way to get motion in the design.

### 1. SMPTE style bars with a grey ramp, 403 um2, no state

The one pattern that is useful rather than pretty: eight 75% colour bars with a
four step luminance ramp along the bottom, for checking a monitor actually locked
and that all six colour bits reach the PMOD.

The interesting part is the arithmetic. 640 = 8 x 80 and 80 = 5 x 16, so the bar
index is `(pix_x >> 4) / 5`. A divider is out of the question; a seven deep
compare chain against multiples of five on a 6 bit value is 403 um2 including the
palette and the ramp.

### 2. Sierpinski bit fractal, 152 um2, no state

`(x & y) == 0` draws the Sierpinski gasket, which is Kummer's theorem on
binomial coefficients mod 2 showing up in hardware. Testing progressively fewer
bits of the same AND term gives coarser tiled copies of the same triangle, so
three nested layers cost one 9 bit AND and three OR reductions. Cheapest pattern
in the design and one of the most detailed.

`g0` implies `g1` implies `g2`, so the layers mux as a plain priority chain.

### 3. Manhattan distance ripple, 953 um2, no state

`d = |x - 320| + |y - 240|`, minus the frame counter, colour from windows of the
result. Concentric diamonds travelling outward. This is the most expensive
stateless pattern because of the two 10 bit subtractions, and it is where the
`~d` for `-d` trick pays for itself.

### 4. Plasma, 1310 um2 including 132 um2 of sine table, no state

Three interfering sine waves: one scrolling horizontally, one scrolling
vertically the other way at a different rate, and a static diagonal term. The
amplitudes are summed and the colour is taken from overlapping windows of the
sum, which gives a hue sweep rather than three identical grey ramps.

`sine_q` is where the cost was controlled. A full 32 entry table would be 128
bits of ROM. Storing only the rising quarter wave as eight 3 bit entries and
recovering the other three quadrants by folding the phase costs 132 um2 per
instance. Phase accumulation is 5 bit adds that wrap, which is exactly the
modulo behaviour wanted, so no masking is needed anywhere.

### 5. Bouncing box with wall collisions, 3346 um2, 24 flops

The pattern that proves the design can animate an object rather than a field.
A 32x32 box moves 2 pixels per frame inside a white framed playfield and cycles
through four colours on every wall collision.

The box test avoids two comparisons per axis: `(pix_x - box_x)` lands in 0..31
only inside the box and underflows to a large value everywhere to the left of it,
so a zero test on the upper five bits is the whole comparison. The playfield
border is four equality tests against constants on the upper seven bits of each
coordinate, which collapse to single AND gates.

Expensive at 18.5% of the design. Kept because a bouncing object with collision
response is the clearest demonstration that the tile has real animation state,
and because it doubles as the ideal probe for the timing test: every pixel of its
visible area is non-black, so the black to non-black transition marks the active
window exactly and all eight VGA intervals can be measured without reading a
single internal signal.

### 6. Starfield driven by the whitened stream, 131 um2, no state of its own

A star is drawn wherever the low ten bits of the LFSR state happen to be zero.
For a maximal length 16 bit LFSR the all-zero ten bit window occurs 2^6 - 1 = 63
times per 65536 step period, so the density is about 1 in 1040 and a visible
frame carries roughly 300 stars. The measured figure from the captured frame is
**293 stars in 307200 pixels, 1 in 1048**.

A frame is 420000 pixel clocks and the period is 65536, so the phase advances
420000 mod 65536 = 27210 steps per frame and the field is different every frame:
the starfield twinkles. When real entropy is being accumulated it is also
unpredictable, which is the point of wiring a pattern to the TRNG at all.

### 7. Rule 30 cellular automaton, 4209 um2, 40 flops

The only pattern that is genuinely iterated. Rule 30 is
`next[i] = left XOR (centre OR right)` with cyclic edges, drawn as a space-time
diagram: 40 cells of 16 pixels, one generation per 32 scanlines, re-seeded with a
single live centre cell at every frame boundary so the figure is stable while its
colour cycles.

One generation per 32 lines rather than per line, because rule 30 spreads one
cell in each direction per generation. 480 generations on a 40 cell cyclic row
wraps after 20 and the rest of the screen is undifferentiated chaos, which is
what the first version looked like. 480/32 = 15 generations spans cells 6 to 34
and stays clear of the wrap, so what gets drawn is a readable diagram with the
regular right edge and the chaotic left half rule 30 is known for. Dividing by 32
is a test on `pix_y[4:0]`, so it is free.

Most expensive pattern at 23.3%. Justified because the Sierpinski pattern already
covers "closed form fractal" and this covers something a closed form cannot: the
chaotic half of a rule 30 diagram is not computable from `(pix_x, pix_y)`.

---

## 4. The entropy pipeline

```
                          +----------------------------+
uio_in[0] ENT_IN -------->| entropy_source             |
                          |  SIM_ENTROPY=0: ring_osc   |
     ring_osc(5) --\      |    5 and 7 stages, XOR,    |
     ring_osc(7) --/-XOR->|    2 stage synchroniser    |
                          |  SIM_ENTROPY=1: ENT_IN     |
                          +-------------+--------------+
                                        | raw_bit, raw_stb
                     +------------------+---------------------+
                     |                                        |
                     v                                        v
          +----------------------+                +-------------------------+
          | von_neumann          |                | health_monitor          |
          | pairs, unequal only  |                | RCT + APT on RAW samples|
          +----------+-----------+                +------------+------------+
                     | vn_bit, vn_stb                          | sticky flags
                     v                                         |
          +----------------------+                             |
          | lfsr_whitener        |--- state[15:0] -> starfield |
          | x16+x15+x13+x4+1     |--- state[2:0]  -> select    |
          +----------+-----------+                             |
                     | rnd_bit                                 |
                     v                                         v
                  +--------------------------------------------+
                  | AND: output gated while a failure is latched|
                  +---------------------+----------------------+
                                        v uio_out[7] RND_OUT
```

### Two source paths, and why

A free running ring oscillator has no meaning in an event driven simulator.
Icarus will happily oscillate a delay annotated inverter loop, and
`test/tb_ring.v` measures the result: **exactly 30 ns for the 5 stage ring and
exactly 28 ns for the 7 stage ring**, which is `2 * STAGES * SIM_DELAY` to the
picosecond. That is a square wave with zero jitter. Sampling it produces a
deterministic sequence. A "TRNG test" written against that path measures the
simulator's timewheel and nothing else, and that is exactly the trap this project
was written to avoid.

So `entropy_source` is parameterised:

- `SIM_ENTROPY = 0` keeps the ring oscillators. This is what gets hardened and
  taped out. It can be checked structurally but never statistically in
  simulation.
- `SIM_ENTROPY = 1` takes the raw bit from `uio_in[0]` and elaborates no
  oscillator at all. `test/tb.v` selects this for RTL simulation, so the
  debiaser, the conditioner and both health tests become bit exact checkable
  against `test/model.py`.

`uio_in[0]` is XORed into the sampled value on both paths, so an external noise
source can be injected in silicon too.

### Protecting the ring oscillators from synthesis

This is the part that is easy to get wrong and silent when it goes wrong.
Written as one expression inside a single module, the mapper collapses an odd
inverter chain to a single inverter. Measured with Yosys 0.33 and the sg13g2
library: **2 surviving cells instead of 12**. Both oscillators come out as one
inverter plus one AND gate, their frequencies become identical, and the XOR of
two identical oscillators is a constant. The entropy source silently becomes a
wire tied to zero and everything downstream still looks healthy.

The fix is one `(* keep_hierarchy *)` module per stage (`src/ring_inv.v`,
`src/ring_gate.v`), plus `(* keep *)` on the chain wires so `opt_clean` cannot
remove the loop as unobservable. `scripts/synth_report.sh` asserts that all 12
stages survive mapping and fails the build if they do not.

Stage 0 is a NAND against an enable rather than a plain inverter. That gives the
loop a power down and, more importantly, a defined starting state: an inverter
ring whose nodes begin at `x` stays at `x` forever in a simulator, because `~x`
is `x`. With the enable low the NAND output is a hard 1, the whole chain
resolves, and releasing the enable starts oscillation from a known state.

One consequence worth stating plainly: because each stage is its own kept module,
no single module contains a cycle, so neither Yosys `check` nor `abc` reports a
loop. Static timing in the physical flow works on the fully flattened netlist and
will report it. That is expected. The ring is not on the clock tree and its only
consumer is the two stage synchroniser.

### Sampling rate

The oscillator is sampled once every 8 pixel clocks by default, 318 ns of
accumulated phase drift per sample at 25.175 MHz. `SAMP_FAST` drops the divider
to 1 so simulation and bench characterisation do not have to wait. Sampling
faster than the jitter accumulation time is the usual way ring oscillator TRNGs
fail, which is why this is a runtime control and not a constant: the right value
is a property of the silicon and is not known until it is measured.

### Von Neumann debiasing

Raw samples are taken in non overlapping pairs. An unequal pair emits its first
bit; an equal pair is discarded. If the source is biased but its samples are
independent then P(01) = P(10) = p(1-p) regardless of p, so the emitted bit is
exactly unbiased. The price is throughput: p(1-p) output bits per input bit,
0.25 for an unbiased source, falling off quadratically as the bias grows.

Measured by `test_von_neumann` on 20000 samples driven at P(1) = 0.75:

```
raw bias      +0.2496
output bias   +0.0031
yield          0.1872   against the theoretical p(1-p) = 0.1875
```

![Bias before and after von Neumann debiasing](img/trng_debias.png)

What it does not fix: von Neumann removes static bias, not serial correlation. A
source with correlated adjacent samples stays correlated after debiasing. That is
one reason the conditioner is downstream and the repetition count test is
upstream.

### LFSR conditioning

```
x^16 + x^15 + x^13 + x^4 + 1
```

Fibonacci form, taps at state bits 15, 14, 12 and 3. A standard maximal length
16 bit tap set, plus the usual de Bruijn correction: `(state[14:0] == 0)` is
XORed into the feedback, which splices `0x0000` into the cycle just ahead of
`0x0001`. Two reasons that 15 input NOR is worth its area:

- **No lockup.** Entropy is XORed into the feedback. From state `0x8000` an
  injected 1 would otherwise drive the register to all zeros, where a pure LFSR
  stalls until another 1 happens to arrive.
- **Perfect balance.** `state[15]` is 1 for exactly 32768 of the 65536 states, so
  one period of output carries exactly 32768 ones. An m-sequence is off by one;
  this is not.

The cost is one 16 bit run of zeros per period, which is the single artefact the
runs histogram is expected to show.

`test_lfsr_period` walks the whole cycle and asserts that all 65536 states are
visited, that the all-zero state is among them, and that the seed recurs at
exactly step 65536 and not before.

The register does two jobs. It conditions the entropy, and it is the pixel rate
PRNG the starfield samples. Reusing it saved the 15 flip-flops a separate pixel
PRNG would have cost. Because it keeps stepping while it waits for the debiaser,
the arrival *times* of the debiased bits carry information too.

**An LFSR is linear.** It is a decorrelator and a rate matcher, not a
cryptographic conditioner. Given 16 consecutive output bits the whole state is
recoverable, so the output must not be treated as a CSPRNG or as full entropy per
bit. Doing this properly means a sponge or a block cipher, and neither fits in
this tile.

---

## 5. Health tests and the SP 800-90B rationale

Both tests run on the **raw** samples, before the debiaser and before the
conditioner. That placement is the whole point. The tests exist to detect the
noise source failing, and both von Neumann debiasing and an LFSR hide exactly the
failures being looked for: a stuck-at-0 source produces perfectly healthy looking
LFSR output forever, and a debiaser fed a constant simply stops emitting, which
is indistinguishable from a slow source.

### Repetition count test (SP 800-90B 4.4.1)

Count consecutive identical samples; fail when the run reaches a cutoff C. The
standard derives C from the assessed min-entropy H and a false positive rate
alpha as `C = 1 + ceil(-log2(alpha) / H)`.

C is a two bit selector over {4, 8, 16, 32} on `uio_in[2:1]` rather than a
hardwired constant, because the min-entropy of a ring oscillator sampled at a
given rate is not known until the silicon is measured. 32 corresponds to roughly
H = 0.65 bits per sample at alpha = 2^-20. 4 is a deliberately hair-trigger
setting for bench bring-up.

`test_health_rct` asserts the flag fires on the sample that completes a run of
exactly C, for all four cutoffs, and that at the tightest cutoff it does not fire
on a perfectly alternating source.

### Adaptive proportion test (SP 800-90B 4.4.2)

Take the first sample of each window as the reference, count how many of the W
samples in the window equal it, fail if that count exceeds the cutoff. W = 64,
which is the standard's value for binary sources. The cutoff is a two bit
selector over {40, 48, 56, 62} on `uio_in[4:3]`.

This catches a source that has drifted heavily biased without ever getting stuck
long enough to trip the repetition test. `test_health_apt` demonstrates exactly
that separation: the test stream is 15 ones then a zero repeated, so 60 of every
64 samples match the reference while the longest run is 15, well inside the
repetition cutoff of 32. The repetition flag is asserted to stay clear for the
whole run, so the two tests are demonstrably independent rather than two names for
the same check.

### Sticky flags and output gating

Both flags latch and stay latched until `HEALTH_CLR` is asserted, so a transient
failure cannot be missed by software polling slowly. Clearing loses to a
simultaneous failure by construction: `clr` is assigned first in the always block
and the failure assignment overrides it.

While either flag is set, `RND_OUT` is forced low and the random pattern reselect
is inhibited. That is the standard's "stop producing output once the source has
failed" requirement. The LFSR itself keeps running, because the starfield uses it
as a plain PRNG and there is no reason to freeze the display when the noise source
misbehaves.

`test_health_sticky` proves the flag is latched rather than continuously
re-triggered: after tripping it on a stuck source, the source is switched to a
perfectly alternating stream, so the failure condition is provably absent, and the
flag is asserted to stay set for 256 further samples. Over those samples the LFSR
output bit was 1 on **126 clocks**, all of which were gated to 0 on the pin, so
the gating assertion is not vacuous.

### What the statistics do and do not show

![Conditioned output bias over time](img/trng_bias.png)
![Run length distribution](img/trng_runs.png)
![Byte value distribution](img/trng_bytes.png)

Measured over 262144 output bits:

```
bias                    -0.00012   asserted within +/-0.01
runs of length 1         0.5001    of 130757 runs
longest run             17 bits
byte chi-square        214.1       on 255 df, critical value 330.5 at p=0.001
```

**These numbers characterise the debiaser and the LFSR conditioner. They are not
a measurement of entropy.** The entropy input for that run was a Python
pseudorandom generator driven into `uio_in[0]`, because the ring oscillators
cannot be simulated. Nothing in this repository measures silicon entropy and
nothing here should be read as if it did.

What the test is genuinely worth: a wrong tap set, a stuck output, a broken
debiaser, a health test that fires on fair input, or an output accidentally
gated off all fail it immediately.

---

## 6. Verification plan

The reference project that prompted this one has `cocotb.pass_test()` as the
first statement of its only test, so its entire testbench body is dead code. That
shaped the plan here: every test asserts, and every assertion message carries the
numbers needed to debug the failure.

### The independent model

`test/model.py` is a cycle accurate model of the whole tile written from the
design intent rather than transliterated from the Verilog. It reproduces the
design's deliberate quirks on purpose, and says so at each one:

- the off-by-one absolute value in `pat_ripple`
- the de Bruijn zero state correction in the LFSR
- the "emit the first bit of the pair" von Neumann convention
- the one cycle of registered latency between the debiaser and the conditioner,
  which determines exactly which clock an entropy bit is XORed in on
- deriving `gen_end` from the pre-edge `pix_y`, matching the RTL

One call to `Tile.step()` is one rising clock edge. Construct it at the moment
reset is released and it stays in lockstep with the DUT indefinitely, which is
what makes pixel exact frame comparison possible at all.

### The tests

| test | what it asserts | scale |
| --- | --- | --- |
| `test_reset` | no output is x or z, `uio_oe` is exactly `0b11100000`, both syncs idle high at pixel (0,0), health flags clear, the LFSR reloads its seed, a mid frame reset returns to the (0,0) state, and the same clock count after reset gives the same pixel | 2 resets |
| `test_vga_timing` | all eight intervals derived from the pins alone | 4 lines per clock + 1050 lines |
| `test_golden_frames` | pixel exact model equality for all eight patterns, all pairwise distinct, none flat | 2 457 600 pixels |
| `test_pattern_switch_mid_frame` | sync exact on every clock of a frame across a mid line `sel` change, and the pixels follow the old then the new pattern | 420 000 clocks |
| `test_von_neumann` | all four pair cases explicitly, then bias and yield on 20000 biased samples | 20 020 samples |
| `test_lfsr_sequence` | state matches the model step by step, free running and with injection | 8 000 steps |
| `test_lfsr_period` | all 65536 states visited, zero among them, seed recurs at exactly 65536 | 65 536 steps |
| `test_health_rct` | fires on the sample completing a run of exactly C, all four cutoffs, no false positive on alternating input | 4 cutoffs + 400 samples |
| `test_health_apt` | fires on 60-of-64 bias at three cutoffs, ignores it at 62, no false positive on 4096 fair samples, repetition flag clear throughout | 4 cutoffs + 4096 samples |
| `test_health_sticky` | flag survives 256 healthy samples, gates the output on the 126 clocks where it mattered, clears on demand, output ungates | 330 samples |
| `test_trng_statistics` | bias within a documented bound, runs distribution sane, byte chi-square under bound, no health test fires on fair input | 262 144 bits |

### Formal verification

Two blocks are proved rather than only tested, chosen because in both cases a
proof says something a test structurally cannot.

**The debiaser.** Its reason to exist is a symmetry argument: for independent
samples P(01) = P(10) = p(1-p) whatever p is, so a debiaser that emits 0 on
exactly 01 and 1 on exactly 10 is unbiased by construction. `test_von_neumann`
shows that held for two particular streams. `formal/von_neumann_fv.v` asserts the
symmetry itself, along with "nothing is emitted without a completed pair" and
"two consecutive output strobes are impossible", and SymbiYosys checks them
against every input sequence up to 40 cycles from reset. The state machine has a
period of two samples, so 40 cycles covers every pairing, alignment and discard
case many times over. The statistical conclusion still needs the input samples to
be independent, which is an assumption about the noise source and not something
any tool can prove about a debiaser.

**The sync generator.** `test_vga_timing` measures one frame and asserts every
interval, which catches a wrong constant. What it cannot catch is a counter that
only misbehaves from a state one captured frame never visits, and on a VGA output
that means a monitor that loses lock. `formal/vga_sync_fv.v` proves the counters
stay inside 0..799 and 0..524, that the syncs are low only inside their windows
and never inside the visible area, that `active` matches the visible window
exactly, that `line_end` and `frame_end` fire only at the ends, and that the
counters advance by exactly one and wrap correctly.

This one is structured as a genuine induction rather than a bounded check: a
`base` task forces a reset and proves the counters land on (0, 0), and a `step`
task assumes only that they start somewhere legal and proves one clock preserves
every property. Together those are unbounded. It is also much cheaper than the
obvious alternative: bounded checking from reset needs 656 cycles just to reach
the horizontal sync window, and z3 was taking ten seconds per step by step 220.

**Mutation checking.** A proof that passes on a broken design proves nothing, so
`make formal` injects two specific bugs and fails if either proof still passes:
a `line_end` that fires one pixel early, and a debiaser that emits the second bit
of the pair instead of the first. Both are caught, and the sources are restored
afterwards.

Two limitations, stated because they matter. The debiaser result is bounded rather
than unbounded: z3 4.8.12 is the version available here and it does not converge
on the induction step for that property, and no newer solver could be installed
(`yices2` is not packaged, `boolector` is the 2012 1.5 release, `cvc5` failed to
install). Writing the same property inside a single module proves by induction in
one second, so this is a solver limitation and not a statement about the design.
And these are two blocks out of the design: the pattern generators, the health
monitor and the conditioner are covered by simulation only.

Plus, outside cocotb:

- `test/tb_ring.v`, 12 structural checks on the ring oscillator path: resolves out
  of `x` with the enable low, silent while disabled, starts when enabled, stops
  again, both periods equal `2 * STAGES * SIM_DELAY`, the two rings differ, their
  XOR is not constant, and the `SIM_ENTROPY=1` path tracks its pin exactly.
- `test/capture.py`, 64 further frames verified against the model while capturing
  the animation sequences, including the TRNG selection sequence where the
  expected pattern is read out of the DUT's own `sel_rand` register and asserted
  against the model's before being used for the pixel comparison.
- `make lint`, Verilator `-Wall` with zero warnings.
- `make synth`, which fails the build on any blackbox, any inferred latch, or any
  ring oscillator stage lost to the optimiser.
- `make formal`, SymbiYosys proofs of the debiaser and the sync generator, with a
  mutation check that both proofs actually catch injected bugs.
- `scripts/check_area.py`, run by the CI synth job, which compares a fresh area
  report against the committed one within 2% and re-derives the required tile
  count from the measured area, so `tiles` in `info.yaml` cannot drift away from
  what was measured. Compared with a tolerance rather than exactly because Yosys
  cell counts move slightly between versions, and pinning CI to one version to
  protect a byte for byte match would make the check about the runner image.

### How the timing test avoids reading internal signals

Deriving the front porch and the back porch black box needs a way to know where
the active window is, and that means a pattern with no black pixels anywhere in
it. Pattern 5 qualifies by construction: white border, coloured box, and a
background checkerboard of two non-black colours. So with `sel = 5` the black to
non-black transition on `uo_out` is exactly the active window boundary, and all
eight intervals fall out of run length analysis on the pins.

Vertical measurement starts 300 lines into a frame rather than at line 0. Starting
on an active run leaves only one active-to-active transition in two frames, and
the vertical total cannot be measured from one transition.

### Why the golden frame test holds `ENT_IN` at 0

Every von Neumann pair becomes (0,0), so the debiaser never emits, nothing is
injected into the conditioner, and the LFSR free runs from its reset seed. That is
what makes the starfield predictable, and it is the only way to golden test a
pattern whose pixels come from the random stream.

### Runtime

The full regression is about 6 minutes. Icarus runs this design at roughly 30000
pixel clocks per second and a frame is 420000 clocks, so a frame costs about 14
seconds no matter how few pixels are read. Frame capture for the animated images
is a separate `make -C test capture` target for that reason, about 15 minutes for
64 frames.

---

## 7. Physical implementation

`make harden` runs LibreLane **3.0.0.dev44** with `pdk: ihp-sg13g2`, which is
exactly the version and PDK `TinyTapeout/tt-gds-action@ttihp26a` pins. So this is
the shuttle hardening flow, not a stand-in for it. The `gds` workflow runs their
version of it on every push and passes, including their own `precheck`. What
neither is is a shuttle submission: that and fabrication are separate steps this
repository does not perform.

![Routed layout](img/layout.png)

The die is fixed at 202.08 x 154.98 um in `hardening/config.json`, which is Tiny
Tapeout's own 1x1 tile from `tt_block_1x1_pgvdd.def`. Fixing it rather than
letting the floorplanner choose is the point: it makes the run answer "does it fit
the tile I claimed" instead of "what area would it like".

### Signoff

```
route DRC 0    magic DRC 0    klayout DRC 0    LVS 0
antenna 0 nets, 0 pins        power grid 0     unmapped cells 0
max slew 0     max cap 0      setup TNS 0      hold TNS 0

die area            31318.4 um2   202.08 x 154.98
real cell area      25887.9 um2   1771 cells, 82.7% density
setup worst slack    17.4537 ns   at a 39.722 ns period
hold worst slack      0.1535 ns
clock skew            0.2733 ns
power                 0.3507 mW
wirelength              69427 um
```

| corner | setup worst slack | hold worst slack |
| --- | --- | --- |
| slow 1.08 V 125 C | +17.4537 ns | +0.7188 ns |
| typ 1.20 V 25 C | +18.2674 ns | +0.3631 ns |
| fast 1.32 V -40 C | +18.7310 ns | +0.1535 ns |

### The SDC is real, which is the only reason those numbers mean anything

LibreLane warns `'PNR_SDC_FILE' is not defined. Using generic fallback SDC` when
you do not give it constraints, and slack measured against a fallback is not a
claim worth making. [`hardening/constraints.sdc`](../hardening/constraints.sdc)
sets both `PNR_SDC_FILE` and `SIGNOFF_SDC_FILE`, and the warning is gone from the
run log. Every number in it is justified in place:

- 39.7220 ns period, which is the `clock_hz` in `info.yaml`.
- 0.25 ns clock uncertainty, 0.63% of the period. The harness distributes one
  clock to every user tile, so the clock arriving here has picked up jitter and
  skew this tile does not control.
- 25% of the period budgeted at each boundary, in and out. The harness input and
  output multiplexers are between this tile and the pads. Assuming zero external
  delay would be easier and less true; there is enough margin to afford the
  honest version.
- `sg13g2_inv_1` drive and load at the boundary rather than an ideal source and a
  zero load.

### Post synthesis versus post route timing

`make sta` reports a slow corner Fmax of 169 MHz; the hardened run has 17.45 ns
of slack at 39.722 ns, which is 44.9 MHz. Both are in the repo because they
measure different things. Post synthesis STA estimates interconnect from the
liberty wireload model and has no clock tree and no hold buffers. The hardened
number has extracted parasitics, a real 65 cell clock tree, and 240 hold buffers.
Quoting only the flattering one would be the easy mistake.

### The one violation that is not clean

`design__max_fanout_violation__count` is **1**, at every corner. The clock tree
root buffer `clkbuf_0_clk/X` drives 16 sinks against the library's
`default_max_fanout` of 8 (from the `sg13g2` liberty header, not from this
design's SDC, which sets 10).

Two attempts to remove it, both recorded because negative results are results:

1. `CTS_SINK_CLUSTERING_SIZE: 40`, up from OpenROAD's default of 20, on the
   theory that larger sink clusters mean fewer level one buffers for the root to
   drive. **Changed nothing.** Not one metric moved: same fanout violation, same
   51 clock buffers, same 1170.29 um2 of them, same slack to four decimals.
2. `MAX_FANOUT_CONSTRAINT: 8` plus `CTS_BALANCE_LEVELS: true`, to make the repair
   steps aware of the real limit and let CTS add a level. **Also changed
   nothing.** Identical metrics again, to four decimal places.

Two independent knobs producing byte identical results is itself informative:
neither reaches OpenROAD's clock tree synthesis in a way that alters the root
buffer for a design this small, or the tree is already what CTS considers optimal
by its own criteria. Neither setting is left in `hardening/config.json`, because
a config key that demonstrably does nothing is worse than no key at all. Both are
recorded there as comments.

It is left in place, with the reasoning stated rather than the number buried:
`max_fanout` is a proxy design rule for slew and capacitance, and both quantities
it stands in for are clean at every corner (max slew 0, max cap 0). The tree it
produced has 33 ps of skew and 0.68 to 0.72 ns of latency, and setup and hold
both close with margin. It is also worth noting that Tiny Tapeout's own flow runs
its own CTS with its own settings and the harness supplies the clock, so this
particular clock tree is not what a shuttle would build anyway.

### Ring oscillator frequency from Liberty data

`scripts/ring_freq.py` derives what to expect from the two rings rather than
guessing. For an N stage ring every node toggles once per half period, so
`T = 2 * (t_nand + (N-1) * t_inv)`, with each stage driving exactly one identical
stage, so the load is that cell's own input capacitance. Delay comes from
bilinear interpolation of the Liberty 7x7 tables at that load, with the input
slew solved by fixed point so it is self consistent with the output slew the
previous stage produces rather than assumed.

| corner | t_inv | t_nand2 | 5 stage | 7 stage | beat | periods per sample at /8 |
| --- | --- | --- | --- | --- | --- | --- |
| slow 1.08 V 125 C | 38.3 ps | 57.1 ps | 2376 MHz | 1742 MHz | 634 MHz | 554 |
| typ 1.20 V 25 C | 25.1 ps | 35.6 ps | 3677 MHz | 2686 MHz | 991 MHz | 854 |
| fast 1.65 V -40 C | 14.0 ps | 18.3 ps | 6741 MHz | 4898 MHz | 1843 MHz | 1557 |

**This is a hand calculation, not a measurement, and it cannot be one.** A ring
oscillator's frequency depends on routed parasitics, the local supply, the die
temperature and the process corner of the individual part, and its entire purpose
is to jitter. Interconnect is not included here, so real rings will be slower
than every figure in that table.

It is worth computing anyway, because the conclusion survives a large error bar.
Even at the slow corner, and even if routing halved these frequencies, the
default divide-by-8 sample rate gives hundreds of oscillator periods per sample
for jitter to accumulate over, and the two rings are hundreds of MHz apart so
their XOR is not a near-static beat. Sampling faster than the jitter accumulates
is the usual way a ring oscillator TRNG fails, which is what `SAMP_FAST` exists
to let a bench adjust once the real frequency is known.

---

## 8. Known limitations

- **No silicon entropy measurement exists here.** Everything statistical in this
  repository was measured with a Python pseudorandom generator driven into
  `ENT_IN`. The ring oscillator path is verified structurally only, and its
  frequency table is a Liberty hand calculation with no interconnect.
- **The conditioner is linear.** Sixteen consecutive output bits reveal the whole
  state. Not a CSPRNG.
- **The ring oscillator sample rate is a guess until measured.** `SAMP_FAST` and
  the two cutoff selectors exist so the right values can be found on a bench
  rather than being frozen in the RTL.
- **Gate level simulation does not cover the oscillators.** `make gl` runs the
  whole regression against the hardened netlist, but only because `test/tb.v`
  forces both ring chains to a static value: the IHP cell models are zero delay, so
  a live ring stops the simulator's timewheel dead. With the rings cut, the
  sampled oscillator bit is a constant 0 and the entropy path behaves exactly as
  `SIM_ENTROPY = 1` does, which `test/test_gl.py` asserts rather than assumes. The
  oscillator path itself is covered structurally by `test/tb_ring.v` and by the
  stage counts that `make synth` and `make harden` enforce, and not at all at gate
  level.
- **CI proves the tile hardens, not that it would be accepted by a shuttle.** All
  four `gds` jobs pass, including Tiny Tapeout's own `precheck`, so it places,
  routes, passes DRC and LVS and clears their submission checks on a plain runner.
  Submission and fabrication are separate steps this repository does not perform,
  and harness integration is untested.
- **The local hardening die is the right size but not the right floorplan.**
  202.08 x 154.98 um is Tiny Tapeout's own 1x1 tile area, but `make harden` only
  fixes `DIE_AREA`; their `gds` job starts from `tt_block_1x1_pgvdd.def`, which
  also carries the harness pin frame and power grid obstructions. Their flow runs
  on every push and passes, so the difference is not hypothetical, but the two are
  not the same floorplan.
- **The design fits 1x1 with little room to spare.** 82.7% post route density, and
  placement fails outright at a 60% or 80% target. A future change of any size
  needs the density rechecked, not assumed.
- **One max fanout violation remains** on the clock tree root buffer, documented
  in section 7 with both attempts to remove it.
- **The FPGA build has no ring oscillators.** `nextpnr-ice40` refuses any design
  containing a combinational loop, so `tt_fpga.py`'s `-DSYNTH` selects the external
  entropy path in `src/entropy_source.v`. That is the correct build for an FPGA
  regardless, since routed LUTs cannot host a usable ring oscillator TRNG, but it
  means the `fpga` bitstream has no noise source of its own.
