# Adapting this design

This repository is a working Tiny Tapeout tile for the IHP 130nm shuttle with a
complete local flow attached. If you want your own design in that flow, most of
what is here carries over unchanged and a small, well defined set of things does
not.

| carries over unchanged | is specific to this tile |
| --- | --- |
| `Makefile`, every `scripts/*.sh` and `scripts/*.py` | the eight pattern generators |
| the four CI workflows | the entropy pipeline |
| `hardening/config.json` and `constraints.sdc` (edit the names and the clock) | the pin map in `info.yaml` |
| `test/tbutil.py`, the lockstep model comparison pattern | `test/model.py`, `test/test.py` |
| the tile geometry facts and `scripts/check_area.py` | the measured area and timing numbers |

Sections below, in the order you are likely to need them:

1. [Rename the tile](#0-rename-the-tile)
2. [Add a pattern generator](#1-add-a-pattern-generator)
3. [Change the VGA timing or resolution](#2-change-the-vga-timing-or-resolution)
4. [Swap or retune the entropy pipeline](#3-swap-or-retune-the-entropy-pipeline)
5. [Retarget the tile size](#4-retarget-the-tile-size)
6. [Re-run the hardening flow and regenerate the renders](#5-re-run-the-hardening-flow-and-regenerate-the-renders)
7. [What to re-measure after a change](#6-what-to-re-measure-after-a-change)

The design itself is documented in [design.md](design.md). This file is about
changing it.

---

## 0. Rename the tile

Tiny Tapeout requires the top module to be `tt_um_<something>`, and by convention
that is `tt_um_<github username>_<project>`. The name appears in 18 committed
files plus the generated reports:

```sh
git grep -l tt_um_danieltyukov_vga_trng -- ':!docs/synth' ':!docs/sta' ':!docs/hardening' \
  | xargs sed -i 's/tt_um_danieltyukov_vga_trng/tt_um_you_yourproject/g'
git mv src/tt_um_danieltyukov_vga_trng.v src/tt_um_you_yourproject.v
```

That covers `info.yaml` (`top_module` and `source_files`), `test/Makefile`
(`PROJECT_SOURCES` and the lint `--top-module`), `test/tb.v`,
`hardening/config.json` (`DESIGN_NAME` and `VERILOG_FILES`),
`hardening/constraints.sdc`, `scripts/harden.sh`, `scripts/run_sta.sh`,
`scripts/sta.tcl`, `scripts/synth_report.sh`, `scripts/run_gl.sh`,
`scripts/make_images.py`, `fpga/fpga_top.v` and the prose.

The three excluded directories are tool output, and the reports in them still name
the old module. Do not sed those: re-run `make synth`, `make sta` and
`make harden` so the committed reports come from tools that saw the new name.
`docs/img/block_diagram.svg` is hand written text and the sed does cover it.

---

## 1. Add a pattern generator

### The interface a pattern must implement

Five of the eight are pure combinational functions of the beam position and the
frame counter, and that is the cheapest thing to write:

```verilog
`default_nettype none

module pat_yours (
    input  wire [9:0] pix_x,   // 0 .. 799, counts through blanking
    input  wire [9:0] pix_y,   // 0 .. 524, counts through blanking
    input  wire [7:0] frame,   // frame counter, wraps at 256, held by FREEZE
    output wire [5:0] rgb      // {r[1:0], g[1:0], b[1:0]}
);
```

The contract:

- **Combinational, no clock.** `rgb` must be valid for the `(pix_x, pix_y)` it is
  given, on that same clock. There is no pipeline stage between a pattern and the
  pins: `pattern_mux` selects combinationally, the top level gates blanking
  combinationally, and `uo_out` is a continuous assignment.
- **`pix_x` and `pix_y` count through blanking**, so they reach 799 and 524. Do
  not assume they are inside the visible window. You may output anything outside
  it: the top level forces black during blanking, and it has to, or a monitor
  will not lock.
- **No latches.** `make synth` fails the build on an inferred latch. A `case`
  with a `default` or a full `always @(*)` assignment on every path is enough.
- **Silence the unused bits explicitly.** `verilator --lint-only -Wall` runs with
  zero tolerance in CI. The existing files end with
  `wire _unused = &{d[9:8], p[3:0], 1'b0};` rather than disabling the warning.

If your pattern needs state, take `clk` and `rst_n` and one of the blanking
strobes, and update state only on those:

```verilog
    input  wire clk,
    input  wire rst_n,
    input  wire frame_upd,   // one clock per frame, at frame_end, respects FREEZE
    input  wire line_end,    // last pixel clock of every scanline
    input  wire frame_end,   // last pixel clock of the last line
```

`pat_ball` updates on `frame_upd` and `pat_rule30` on every 32nd `line_end`.
Nothing updates on the pixel path, which is why the pattern select can change
mid frame without disturbing the sync generator, and `test_pattern_switch_mid_frame`
asserts exactly that.

If your pattern wants randomness, take `input wire [15:0] rnd` and read the
conditioner state the way `pat_stars` does. Two consequences: the pattern becomes
unpredictable while entropy is being injected, which is the point, and
`test_golden_frames` can only golden test it because it holds `ENT_IN` at 0 for
the whole test so the LFSR free runs from its reset seed.

### Where to register it

Nine places, and only two of them will tell you if you forget:

| # | file | what to add |
| --- | --- | --- |
| 1 | `src/pat_yours.v` | the module |
| 2 | `src/pattern_mux.v` | a `wire [5:0] rgbN`, the instance, and the `case (sel)` arm |
| 3 | `info.yaml` | `source_files` entry. Missing this hardens RTL that does not contain your module |
| 4 | `test/Makefile` | `PROJECT_SOURCES` entry. Missing this fails at elaboration |
| 5 | `hardening/config.json` | `VERILOG_FILES` entry, for the local `make harden` |
| 6 | `scripts/synth_report.sh` | `MODULES` entry, if you want its area reported separately |
| 7 | `test/model.py` | `PATTERN_NAMES` entry and a branch in `Model.rgb()`, plus a state class wired into `Model.step()` if it has state |
| 8 | `scripts/make_images.py` | `PATTERN_ORDER` entry, or it is missing from the gallery |
| 9 | `README.md`, `docs/info.md` | the pattern table and its measured area |

### There are exactly eight slots

`sel` is three bits, from `ui_in[2:0]` or from `rnd_state[2:0]`. A ninth pattern
is not a small change: you need a fourth select bit, and the only adjacent pin is
`ui_in[3]`, which is `RAND_EN`, so the pin map moves and `info.yaml`, the README
pin table and `test/tbutil.py`'s `ui()` helper all move with it. Then
`pattern_mux`'s case widens, `model.NUM_PATTERNS` changes, and every test that
loops over `range(M.NUM_PATTERNS)` gets longer.

Replacing a pattern is much cheaper than adding one. `pat_sierp` (152 um2) and
`pat_stars` (131 um2) are the two cheapest slots to reuse.

### The area you actually have

This is the part where a fork usually goes wrong, so here are the measured
numbers rather than a rule of thumb:

```
post synthesis cell area     18040 um2    Yosys, mapped to sg13g2
post route real cell area    25888 um2    LibreLane, 1771 cells
gross 1x1 tile area          31318 um2    202.08 x 154.98
post route density            82.7 %
```

Two things follow. First, **multiply any synthesis area by 1.44 before believing
it**: clock tree insertion and hold fixing added 7850 um2 that no `yosys stat`
can predict, of which 5831 um2 is timing repair buffers alone. Second, the tile
is already dense enough that the placer has to be told to expect it, and that was
measured too:

| `PL_TARGET_DENSITY_PCT` | result |
| --- | --- |
| 60, the default | global placement refuses, `[GPL-0302]` at 64.2% core utilisation |
| 80 | places, then detailed placement fails after CTS with `[DPL-0036]` once 234 hold buffers are in |
| 85 | places, routes, signs off with 0 DRC, 0 LVS, 0 antenna |

**Nobody has measured where the ceiling is.** The two data points above are all
there is. A pattern costing 200 to 300 um2 at synthesis is very likely fine; at
1000 um2 or more, harden it before you believe it, because the interesting
failure is not "does not fit" but "places at 88% and then detailed placement
cannot legalise ten cells after CTS", which only a full run tells you.

Existing costs, for calibration (full table in
[design.md](design.md#where-the-area-goes)):

```
pat_stars      131 um2    0 flops    reads the LFSR, owns no state
pat_sierp      152 um2    0 flops    (x & y) == 0, three layers from one AND
pat_bars       403 um2    0 flops
pat_xor        434 um2    0 flops
pat_ripple     953 um2    0 flops
pat_plasma    1310 um2    0 flops    including a 132 um2 folded quarter wave table
pat_ball      3346 um2   22 flops   24 bits declared, two fold away in mapping
pat_rule30    4209 um2   40 flops
```

Flip-flops are the expensive thing: `sg13g2_dfrbpq_1` is 48.99 um2, and 142 of
them is 38.6% of the whole design. If you need room, the two stateful patterns
are 7555 um2 together and dropping both takes the design to about 48% of a tile.

### Testing it

`test_golden_frames` picks up a new pattern automatically through
`M.NUM_PATTERNS`, but only if `Model.rgb()` dispatches it, so the model comes
first. Then:

```sh
make test
```

A mismatch prints the first twelve as `(x=.., y=.., f=..) got 0x.. want 0x..`.
The same test also asserts every pattern is pairwise distinct from every other
and that none is a single flat colour, so a pattern that is a subtle variation on
an existing one will fail.

Write the model from the intent, not by transliterating your Verilog. A model
copied from the RTL agrees with the RTL about the same wrong answer, and then
2 457 600 pixels of comparison prove nothing.

---

## 2. Change the VGA timing or resolution

`vga_sync` takes all eight intervals as parameters and derives the totals, sync
windows and `active` from them:

```verilog
vga_sync #(
    .H_ACTIVE(800), .H_FRONT(40), .H_SYNC(128), .H_BACK(88),
    .V_ACTIVE(600), .V_FRONT(1),  .V_SYNC(4),   .V_BACK(23)
) u_sync ( ... );
```

The top level does not currently override them, so either pass overrides there or
change the defaults in `src/vga_sync.v`. What the parameters do **not** cover:

- **The counters are 10 bits.** `pix_x` and `pix_y` are `[9:0]` in `vga_sync`,
  in `pattern_mux` and in every pattern, so the largest total either axis can
  reach is 1024. 640x480 totals 800 x 525 and fits. 800x600 totals 1056 x 628 and
  does not: every one of those ports and every internal comparison widens to 11
  bits, and so do `H_TOTAL`/`V_TOTAL` in `test/model.py`.
- **The pixel clock is the real constraint.** Post route this tile has +17.4537 ns
  of setup slack at 39.722 ns on the slow corner, so Fmax there is
  `1000 / (39.722 - 17.4537)` = **44.91 MHz**.

| mode | pixel clock | against the measured 44.91 MHz |
| --- | --- | --- |
| 640x480 at 59.94 Hz | 25.175 MHz | 1.78x margin, what is committed |
| 800x600 at 60 Hz | 40.0 MHz | 1.12x, plausible but re-measure before claiming it |
| 1024x768 at 60 Hz | 65.0 MHz | does not close, needs pipelining or a cheaper pattern set |

Everything that has to move together:

| file | what |
| --- | --- |
| `src/vga_sync.v` | the eight parameters, and the counter widths if a total exceeds 1023 |
| `src/pattern_mux.v`, `src/pat_*.v` | `pix_x` / `pix_y` widths, and any hardcoded centre constant (`pat_ripple` subtracts 320 and 240) |
| `test/model.py` | `H_ACTIVE` .. `V_BACK`, `PIXEL_CLOCK_HZ` |
| `test/test.py` | the expected numbers in `test_vga_timing` and the frame rate |
| `info.yaml` | `clock_hz` |
| `hardening/config.json` | `CLOCK_PERIOD` |
| `hardening/constraints.sdc` | `set clk_period`, and the comment that derives it |
| `src/config.json` | `CLOCK_PERIOD`, which is what Tiny Tapeout's own `gds` job uses |
| `scripts/run_sta.sh` | the `PERIOD` default, or pass `STA_PERIOD` |

Two practical notes. `tbutil.capture_frame` splits horizontal blanking into
checks of 8, 40, 40, 40 and 32 clocks and then covers `H_TOTAL - H_ACTIVE - 160`,
so it needs at least 160 clocks of horizontal blanking and at least 400 clocks
per line; both hold for the standard VESA modes, but check yours. And simulation
time scales with `H_TOTAL * V_TOTAL`: a frame is 420 000 clocks now and 663 168 at
800x600, so `test_golden_frames` gets 1.6x slower and `make capture` with it.

The cheapest useful change is to keep 640x480 and change only what the patterns
draw. Changing the mode touches every row of that table and both timing flows.

---

## 3. Swap or retune the entropy pipeline

### The contract between stages

```
entropy_source --(raw_bit, raw_stb)--> von_neumann --(out_bit, out_stb)--> lfsr_whitener
       |                                                                        |
       +--(raw_bit, raw_stb)--> health_monitor                    state[15:0], rnd_bit
```

Every stage uses the same convention: the data bit is valid on the clock where
its strobe is high. Any replacement stage keeps that, and keeps the health
monitor on the **raw** samples. Both tests tap before the debiaser and before the
conditioner on purpose: a stuck-at-0 source produces perfectly healthy looking
LFSR output forever, and a debiaser fed a constant simply stops emitting, which
is indistinguishable from a slow source.

### Replacing the noise source

Only the `g_ring_source` generate branch in `src/entropy_source.v` is the source.
Three things in that file are load bearing and should survive any replacement:

1. **The two flop synchroniser.** An asynchronous source sampled by the pixel
   clock will go metastable. The first flop is the one allowed to; the second
   gives it a full period to resolve.
2. **`raw_bit = osc_bit ^ ext_bit`.** This is what lets an external noise source
   be injected in silicon, and it is what makes the deterministic simulation path
   possible at all.
3. **The `SIM_ENTROPY` / `` `SYNTH `` split.** `SIM_ENTROPY = 1` elaborates no
   oscillator and takes the raw bit from the pin, which is what the whole cocotb
   regression runs against. `` `SYNTH `` is defined by Tiny Tapeout's `tt_fpga.py`
   and by nothing else, and it takes the same path because `nextpnr-ice40` refuses
   a design containing a combinational loop. Break either and you lose the RTL
   regression or the FPGA build.

If you keep ring oscillators but change their geometry: `STAGES` must be odd, the
two lengths should be coprime so the combined period is long, and `SIM_DELAY`
affects simulation only (`test/tb_ring.v` measures exactly
`2 * STAGES * SIM_DELAY` and asserts it). Then update the three places that stop
the mapper from silently deleting them:

- `src/ring_inv.v`, `src/ring_gate.v`, `src/ring_osc.v` carry
  `(* keep_hierarchy *)` and `(* keep *)`. Without them Yosys collapses the odd
  inverter chain to a single inverter: measured, **2 surviving cells instead of
  12**, both oscillators identical, and their XOR a constant. Every downstream
  check still passes, which is what makes this failure mode worth guarding.
- `scripts/synth_report.sh` counts the mapped stages and fails if the total is
  not 12. Change that constant with the geometry.
- `scripts/parse_harden.py` has `RING_STAGES = {"a": 5, "b": 7}` and counts them
  again in the routed netlist. A clean GDS with no noise source in it looks
  exactly like a clean GDS.

Also re-run `make ring-freq`. `scripts/ring_freq.py` interpolates the
`sg13g2_inv_1` and `sg13g2_nand2_1` delay tables at the self loaded capacitance
and computes `T = 2 * (t_nand + (N-1) * t_inv)` for the stage count you chose. It
is a hand calculation with no interconnect, so real rings are slower, but it tells
you the order of magnitude before you commit to a sample rate.

If you replace the source with something that is not a combinational loop, drop
the keep attributes and both stage count checks. They exist for the loop.

### Sample rate

`entropy_source` divides by 8 with a 3 bit counter, and `SAMP_FAST` (`ui_in[7]`)
bypasses the divider entirely. Widening to /16 or /32 is one counter bit each.

This is the knob that matters most on real silicon. At 25.175 MHz, /8 is 318 ns
of accumulated phase drift per sample, and the calculated ring frequencies give
554 to 1557 oscillator periods per sample across the corners. Sampling faster
than jitter accumulates is the classic way a ring oscillator TRNG fails, and the
correct rate is a property of the fabricated part, which is why it is a pin and
not a constant.

### Debiaser

`von_neumann` takes non overlapping pairs and emits **the first bit of the pair**
when the two differ: 10 emits 1, 01 emits 0, equal pairs are discarded. If the
samples are independent then P(01) = P(10) = p(1-p) for any bias p, so the output
is exactly unbiased. Yield is p(1-p), so 0.25 at best; measured here 0.1872
against a theoretical 0.1875 for the test stream.

Changing the convention or the algorithm means changing four things together:

- `src/von_neumann.v`
- `test/model.py`'s `VonNeumann` class
- `formal/von_neumann_fv.v`, which **proves** the 01 to 0 and 10 to 1 symmetry.
  This is the proof the unbiasedness claim rests on, so it has to be rewritten,
  not deleted.
- the mutation check in `scripts/run_formal.sh`, which rewrites
  `out_bit <= first_bit;` to `out_bit <= in_bit;` with `sed` and requires the
  proof to fail. If the line no longer exists the mutation silently does nothing
  and the check passes for the wrong reason.

Alternatives, honestly: Elias or Peres extraction recovers more of the input
entropy but needs recursion and buffering, which is flops. XOR folding of N
samples is cheaper but only reduces bias rather than removing it, and it discards
the symmetry argument entirely, so the proof would have nothing to prove.

### Conditioner

`lfsr_whitener` is `x^16 + x^15 + x^13 + x^4 + 1` in Fibonacci form with the de
Bruijn zero state correction, giving a period of 65536 that visits every state
exactly once and emits exactly 32768 ones per period. Debiased bits are XORed
into the feedback so entropy accumulates rather than being consumed one bit at a
time.

If you change the polynomial: update the `fb` expression, `model.Lfsr`, and check
`test_lfsr_period`, which walks all 65536 states. It stays true for any maximal
length tap set with the same correction. What does change is the starfield: a
star is drawn where `rnd[9:0] == 0`, which is 63 occurrences per period, about 1
pixel in 1040, and 293 stars in the captured frame. A different width or
correction moves that density and the committed golden frame with it.

Widening the register costs flops directly, at 48.99 um2 each, and changes how
many bits are available for the pattern select.

It is a linear conditioner. Sixteen consecutive output bits reveal the whole
state, so `RND_OUT` is not a CSPRNG and must not be treated as full entropy per
bit. Doing it properly means a sponge or a block cipher, and neither fits in this
tile.

### Health test thresholds, and what the numbers mean

Both cutoffs are **pins**, not parameters, so retuning on a bench needs no RTL
change. That is deliberate: the right cutoff depends on the min-entropy of the
fabricated source, which nobody knows yet.

**Repetition count** (SP 800-90B 4.4.1) counts consecutive identical samples and
fails on the sample that completes a run of C. The standard derives C from the
assessed min-entropy H per sample and an accepted false positive rate alpha:

```
C = 1 + ceil(-log2(alpha) / H)
```

At alpha = 2^-20, the four selectable cutoffs correspond to:

| `RCT_CUT` | C | implied H, bits/sample |
| --- | --- | --- |
| 0 | 4 | 6.7 |
| 1 | 8 | 2.9 |
| 2 | 16 | 1.3 |
| 3 | 32 | 0.65 |

A binary source cannot exceed 1 bit per sample, so **only cutoffs 16 and 32 are
meaningful as SP 800-90B thresholds here**. 4 and 8 exist because during bench
bring-up you want the flag to fire within a few samples of sticking the source,
and `test_health_sticky` uses cutoff 4 for exactly that reason.

**Adaptive proportion** (4.4.2) takes the first sample of each 64 sample window
as the reference, counts matches, and fails when the count *exceeds* the cutoff.
Under a fair binary source the count is Binomial(64, 0.5), mean 32, standard
deviation 4, so the per window false positive rate is:

| `APT_CUT` | cutoff | P(fire per window, fair source) |
| --- | --- | --- |
| 0 | 40 | 1.6e-2 |
| 1 | 48 | 1.2e-5 |
| 2 | 56 | 3.8e-11 |
| 3 | 62 | 3.5e-18 |

Cutoff 40 is a bench setting, not an operating one: at 1.6e-2 per window it fires
roughly once every 62 windows on a perfectly good source, and the flags are
sticky. `test_health_apt` fires it deliberately at 40, 48 and 56 with a stream of
60 ones per 64, checks that 62 correctly ignores that stream, and then runs 4096
fair samples at the loosest cutoff to show it does not false positive.

Changing the window size W is a real RTL change: `W_LAST`, the width of `win_cnt`
(6 bits for 64) and of `match_cnt` (7 bits), plus `model.APT_WINDOW` and the
biased stream in `test_health_apt`, which is constructed to put exactly 60 ones in
each window while keeping its longest run at 15 so the repetition test provably
cannot catch it. That separation is what makes the two tests demonstrably
independent, so preserve it.

---

## 4. Retarget the tile size

**Never compute Tiny Tapeout tile geometry from a tile pitch, and do not trust
the comment in the project template.** `info.yaml` ships with "a single tile is
about 167x108 uM", which for this shuttle is wrong by 74%. An earlier version of
this repository sized the design against 18036 um2 and concluded with confident
arithmetic that a 1x1 tile was impossible.

The authority is the DEF file their `gds` action hands the floorplanner, in
`TinyTapeout/tt-support-tools` on branch `main`:

```sh
# every tile size that exists for this shuttle
gh api repos/TinyTapeout/tt-support-tools/contents/tech/ihp-sg13g2/def --jq '.[].name'

# and the die of one of them
gh api repos/TinyTapeout/tt-support-tools/contents/tech/ihp-sg13g2/def/tt_block_1x1_pgvdd.def \
  --jq '.content' | base64 -d | grep DIEAREA
```

There are twelve, and every `DIEAREA` below was read out of its own DEF:

| tiles | die, um | area, um2 |
| --- | --- | --- |
| 1x1 | 202.08 x 154.98 | 31 318 |
| 1x2 | 202.08 x 313.74 | 63 401 |
| 2x2 | 419.52 x 313.74 | 131 620 |
| 3x2 | 636.96 x 313.74 | 199 840 |
| 4x2 | 854.40 x 313.74 | 268 059 |
| 6x2 | 1289.28 x 313.74 | 404 499 |
| 8x2 | 1724.16 x 313.74 | 540 938 |
| 3x4 | 636.96 x 710.64 | 452 649 |
| 4x4 | 854.40 x 710.64 | 607 171 |
| 5x4 | 1071.84 x 710.64 | 761 692 |
| 6x4 | 1289.28 x 710.64 | 916 214 |
| 8x4 | 1724.16 x 710.64 | 1 225 257 |

There is no 2x1: the second column of the "x1" family does not exist, so the step
up from a 1x1 is a 1x2. And the "x2" row is 313.74 um tall, which is 2.02 times
154.98 rather than exactly twice it. Neither fact is derivable from a pitch,
which is why this has to be read out of the DEF.

### Derive the count from a route, not from synthesis

The procedure that produced `tiles: "1x1"` here, and the one to repeat:

```sh
# 1. harden at the die you think you need, without touching the committed reports
HARDEN_TAG=try1x2 HARDEN_DIE="202.08 313.74" HARDEN_SKIP_REPORT=1 make harden

# 2. read the real numbers out of the run. design__instance__area__stdcell is the
#    one that matters: design__instance__area includes the fill cells.
python3 -c 'import json;m=json.load(open("runs/try1x2/final/metrics.json"));
print(m["design__instance__area__stdcell"], m["design__die__area"])'

# 3. only now set tiles: in info.yaml, and re-run the check
python3 scripts/check_area.py
```

`scripts/check_area.py` enforces both directions and CI runs it: the placed cell
area must fit the declared number of gross tiles, and the die that was actually
hardened must be the die that was declared. It also prints the synthesis forecast
next to the post route measurement, which on this design differ by 25 percentage
points of density (57.6% against 82.7%). The forecast said the design fits a 1x1
comfortably. That was the right answer for the wrong reason.

Going to a larger tile is not free. The 1x2 comparison run above routes at 40.9%
density with **41781 um** of wire against **69427 um** for the 1x1: the small die
costs 66% more wire in router detours. Timing barely notices here because the
design is slow relative to the process, but on a faster design that is where the
tile would be lost.

Changing the tile means changing all of: `info.yaml` `tiles`,
`hardening/config.json` `DIE_AREA`, possibly `PL_TARGET_DENSITY_PCT` in both
`hardening/config.json` and `src/config.json`, the detail render box in
`scripts/harden.sh` (76,104 to 88,116 is a point near the centre of a
202 x 155 die and means nothing on a different one), and every quoted number in
the README.

---

## 5. Re-run the hardening flow and regenerate the renders

```sh
make harden        # about 25 minutes
```

That runs LibreLane 3.0.0.dev44 on `ihp-sg13g2`, the version and PDK
`TinyTapeout/tt-gds-action@ttihp26a` pins, and writes:

```
docs/hardening/metrics.json    the full LibreLane final metrics
docs/hardening/summary.json    the subset the README quotes, plus derived densities
docs/hardening/signoff.txt     per corner timing, DRC, LVS, antenna, manufacturability
docs/img/layout.png            full die render
docs/img/layout_detail.png     12 x 12 um box near the centre
```

It differs from Tiny Tapeout's own `gds` job in three deliberate ways: it fixes
the clock at the 39.722 ns the design needs instead of the template's 20 ns, it
constrains the boundary from `hardening/constraints.sdc` instead of LibreLane's
generic fallback, and it runs KLayout DRC, which `src/config.json` turns off to
save shuttle time. It is also **stricter**, because it only fixes `DIE_AREA`
while their flow starts from `tt_block_<tile>_pgvdd.def` with the harness pin
frame and power grid already placed. A configuration that fails locally can pass
there. The committed density of 85 is the value both flows accept.

Environment overrides:

```sh
HARDEN_TAG=name            # run directory under runs/, default "local"
HARDEN_DIE="W H"           # override DIE_AREA in um
HARDEN_DENSITY=80          # override PL_TARGET_DENSITY_PCT
HARDEN_SKIP_REPORT=1       # run the flow, leave the committed reports alone
HARDEN_SKIP_FLOW=1         # re-extract reports and renders from an existing run
KLAYOUT_THREADS=8          # default nproc-2; KLayout DRC is single threaded otherwise
```

Use `HARDEN_SKIP_REPORT=1` for every experiment. Without it an exploratory run
overwrites the signoff numbers and the layout renders that the README describes,
with results from a floorplan it does not.

To regenerate only the renders from a run that already exists:

```sh
HARDEN_SKIP_FLOW=1 HARDEN_TAG=local make harden
```

or call KLayout directly. Note that `klayout -b` takes no positional arguments;
parameters arrive as `-rd name=value` and land in the script as globals:

```sh
klayout -b -rm scripts/render_gds.py \
  -rd gds=runs/local/final/gds/tt_um_you_yourproject.gds \
  -rd out=docs/img/layout.png -rd w=1240 -rd h=980
klayout -b -rm scripts/render_gds.py \
  -rd gds=runs/local/final/gds/tt_um_you_yourproject.gds \
  -rd out=docs/img/layout_detail.png -rd w=900 -rd h=900 -rd box=76,104,88,116
```

Two views on purpose: a full die render of a routed tile is close to unreadable
because every metal layer overlaps at that scale, so the full die carries the
outline, the pin frame and the power straps, and the box carries the cell rows,
contacts and metal2 routing. `scripts/harden.sh` then recompresses both with
Pillow, because KLayout writes uncompressed RGB and the full die view lands over
Tiny Tapeout's 512 kB per image documentation limit otherwise.

The 3D viewer is not something you run. The `viewer` job in `gds.yaml` publishes
`tinytapeout.oas` to GitHub Pages on every push, and the link is
`https://gds-viewer.tinytapeout.com/?model=https://<user>.github.io/<repo>/tinytapeout.oas&pdk=ihp-sg13g2`.
Enable Pages on the fork or the job fails at the deploy step.

Once a netlist exists, run the regression against it:

```sh
make gl
```

That is the check that synthesis, clock tree insertion and routing did not change
what the design does, and it is the one RTL simulation by construction cannot
make. Two things about it are specific to this design and will otherwise waste an
afternoon: stock Icarus 12 does not drive the `delayed_*` signals the IHP cell
models clock from, so every flop holds `x` forever and the run reports nothing
while appearing to work; and a ring oscillator against zero delay cell models is a
zero delay feedback loop that stops the simulator's timewheel. `scripts/run_gl.sh`
unpacks Tiny Tapeout's patched Icarus 13 under `build/` for the first, and
`test/tb.v` forces both ring chains for the second. There is a third thing to know
if you write your own probes: Yosys renames every cell instance to `_NNNNN_` and
flattens the hierarchy, so no RTL instance path survives. What does survive is net
names, as single escaped identifiers like `\rnd_state[0] ` and
`u_trng.u_vn.out_stb`, which VPI will not find by handle lookup because it reads
the dots as hierarchy separators. `test/tbutil.py` scans the children once, keys
them on the reported name, and switches on `GATES` so the same test module reads
the RTL hierarchy in one build and flat net names in the other.

---

## 6. What to re-measure after a change

| you changed | run | commit |
| --- | --- | --- |
| any RTL | `make check` | `docs/synth/`, `docs/formal/` |
| a pattern | `make test && make capture && make images` | `docs/img/` |
| the clock or the timing | `make sta`, then `make harden` | `docs/sta/`, `docs/hardening/` |
| the entropy pipeline | `make check`, `make ring`, `make ring-freq` | `docs/synth/`, `docs/sta/ring_freq.json` |
| the ring geometry | the stage counts in `synth_report.sh` and `parse_harden.py` first | both, plus `docs/hardening/` |
| the die, the tiles field or the density | `make harden`, `python3 scripts/check_area.py` | `docs/hardening/`, `docs/img/layout*.png` |
| anything that lands in the netlist | `make gl` after `make harden` | nothing, it is a check |

And the rule the whole repository is built on: if you change a number that the
documentation quotes, re-run the tool that produced it and commit the report. The
reports in `docs/` are committed so that a reader can check the prose against the
tool output, which only works if they are current.
