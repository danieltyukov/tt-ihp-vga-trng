# tt-ihp-vga-trng

A Tiny Tapeout tile for the **IHP 130nm open source PDK** shuttle: eight 640x480
VGA pattern generators sharing one sync generator, with the active pattern chosen
either from three input pins or by an on-chip true random number generator that
has von Neumann debiasing, LFSR conditioning and SP 800-90B style online health
tests. Output goes straight to a TinyVGA PMOD.

[![test](https://github.com/danieltyukov/tt-ihp-vga-trng/actions/workflows/test.yaml/badge.svg)](https://github.com/danieltyukov/tt-ihp-vga-trng/actions/workflows/test.yaml)
[![gds](https://github.com/danieltyukov/tt-ihp-vga-trng/actions/workflows/gds.yaml/badge.svg)](https://github.com/danieltyukov/tt-ihp-vga-trng/actions/workflows/gds.yaml)
[![docs](https://github.com/danieltyukov/tt-ihp-vga-trng/actions/workflows/docs.yaml/badge.svg)](https://github.com/danieltyukov/tt-ihp-vga-trng/actions/workflows/docs.yaml)
[![fpga](https://github.com/danieltyukov/tt-ihp-vga-trng/actions/workflows/fpga.yaml/badge.svg)](https://github.com/danieltyukov/tt-ihp-vga-trng/actions/workflows/fpga.yaml)

| | |
| --- | --- |
| Top module | `tt_um_danieltyukov_vga_trng` |
| Tiles | `1x1` ([why](#area-and-the-tile-decision)) |
| Clock | 25.175 MHz pixel clock, 640x480 at 59.9405 Hz |
| Hardened | LibreLane 3.0.0.dev44 on ihp-sg13g2: 25888 um2 of cells in a 202.08 x 154.98 um tile, 82.7% density, **DRC and LVS clean** |
| Timing | post route setup +17.45 ns at 39.722 ns on all three corners, so 44.9 MHz at the slow corner against the 25.175 MHz the design needs |
| External hardware | [TinyVGA PMOD](https://github.com/mole99/tiny-vga) |
| Regression | 11 cocotb tests, 2.5 million pixels compared, passing at RTL and again on the hardened gate level netlist |
| Formal | debiaser symmetry and sync counter invariants proved with SymbiYosys, mutation checked |

## The hardened tile

| | |
| --- | --- |
| ![Full die](docs/img/layout.png) | ![Detail, 12 x 12 um](docs/img/layout_detail.png) |
| The whole tile, 202.08 x 154.98 um, packed to 82.7% standard cell density. Die outline, the pin frame around the edge, and the five vertical VPWR/VGND power straps. | A 12 x 12 um box near the centre at the same scale a designer would inspect: standard cell rows with their power rails, contacts, and metal2 routing between cells. |

**[Open the layout in the 3D chip viewer](https://gds-viewer.tinytapeout.com/?model=https://danieltyukov.github.io/tt-ihp-vga-trng/tinytapeout.oas&pdk=ihp-sg13g2)**
&nbsp;&nbsp;rotate and zoom the actual layout in a browser. Published to GitHub
Pages by the `viewer` job in [`gds.yaml`](.github/workflows/gds.yaml).

Hardened with **LibreLane 3.0.0.dev44** on `ihp-sg13g2`, the same tool version and
PDK that `TinyTapeout/tt-gds-action@ttihp26a` pins, both locally via `make harden`
and in CI. Signoff from the local run, which unlike theirs also runs KLayout DRC
and constrains timing from a real SDC:

| | | | |
| --- | --- | --- | --- |
| die area | **31318 um2** (202.08 x 154.98) | route DRC | **0** |
| real cell area | **25887.9 um2**, 1771 cells | magic DRC | **0** |
| density | **82.7%** | klayout DRC | **0** |
| fill cells | 3053.6 um2, 572 cells | LVS | **0** |
| setup worst slack | **+17.4537 ns** at 39.722 ns | antenna | **0** nets, **0** pins |
| hold worst slack | +0.1535 ns | power grid | **0** |
| clock skew | 0.2733 ns | unmapped cells | **0** |
| power | 0.3507 mW | max slew / max cap | **0** / **0** |
| wirelength | 69427 um | setup / hold TNS | **0** / **0** |

Tiny Tapeout's own **`precheck` job passes** on this repository, so the tile
clears their submission checks.

**This is a hardened layout, not fabricated silicon.** Nothing here has been
submitted to a shuttle and nothing has been manufactured. What the numbers above
establish is that the design places, routes and passes DRC and LVS on the real
PDK. Fabrication requires submitting to a Tiny Tapeout shuttle, which is a
separate step this repository does not perform.

## Pattern gallery

Every image below is a real frame captured off the tile's `uo_out` pins in an
Icarus simulation and checked pixel by pixel against an independent Python model
before being written. None of them is a mockup.

![Pattern gallery](docs/img/pattern_gallery.png)

| `SEL` | pattern | state | area | notes |
| --- | --- | --- | --- | --- |
| 0 | XOR munching field | none | 434 um2 | `(x ^ y) + frame`, palette scrolls diagonally |
| 1 | SMPTE style bars + grey ramp | none | 403 um2 | bar index is `(x >> 4) / 5` as a compare chain |
| 2 | Sierpinski bit fractal | none | 152 um2 | `(x & y) == 0`, three nested layers from one AND |
| 3 | Manhattan ripple | none | 953 um2 | `abs(x-320) + abs(y-240) - frame`, rings travel outward |
| 4 | Plasma | none | 1310 um2 | three interfering sines over a folded quarter wave table |
| 5 | Bouncing box | 24 ff | 3346 um2 | 32x32 box, 2 px/frame, colour cycles on collision |
| 6 | Starfield | none | 131 um2 | star wherever `lfsr[9:0] == 0`, measured 293 stars/frame |
| 7 | Rule 30 automaton | 40 ff | 4209 um2 | 40 cells, one generation per 32 scanlines |

Full resolution single pattern captures are in `docs/img/`, one file per pattern:
[`pattern_xor_field.png`](docs/img/pattern_xor_field.png),
[`pattern_smpte_bars.png`](docs/img/pattern_smpte_bars.png),
[`pattern_sierpinski.png`](docs/img/pattern_sierpinski.png),
[`pattern_ripple.png`](docs/img/pattern_ripple.png),
[`pattern_plasma.png`](docs/img/pattern_plasma.png),
[`pattern_bouncing_box.png`](docs/img/pattern_bouncing_box.png),
[`pattern_starfield.png`](docs/img/pattern_starfield.png),
[`pattern_rule30.png`](docs/img/pattern_rule30.png).

Six of the eight are pure combinational functions of `(pix_x, pix_y, frame_cnt)`.
That is not a stylistic choice: a 640x480 frame at 6 bits per pixel is 1 843 200
bits, and the whole tile holds 142 flip-flops. Even one scanline would be 3840
bits. There is no framebuffer because there is nowhere to put one.

### Animation

The ripple pattern over 32 consecutive verified frames, and the TRNG choosing a
new pattern every 8 frames with `RAND_EN` set:

| animated pattern | TRNG driven selection |
| --- | --- |
| ![Ripple animation](docs/img/anim_ripple.gif) | ![TRNG driven pattern switching](docs/img/anim_trng_switch.gif) |

In the right-hand GIF the pattern index is not chosen by the testbench. It is read
out of the DUT's own `sel_rand` register, asserted equal to the model's, and then
used as the expected pattern for the pixel comparison of that frame. Entropy was
driven into `ENT_IN` during vertical blanking, which is where it has to arrive to
influence the reselect at the frame boundary.

## VGA timing

![VGA timing](docs/img/vga_timing.svg)

`test_vga_timing` derives all eight intervals from `uo_out` alone, with no
internal signal read anywhere, and asserts each number:

```
horizontal: active=640 front=16 sync=96 back=48 total=800
vertical:   active=480 front=10 sync=2  back=33 total=525
frame rate: 420000 clocks per frame -> 59.9405 Hz
both syncs negative polarity (idle high, pulse low)
```

Pattern 5 is used as the probe because every pixel of its visible area is
non-black, so the black to non-black transition on the pins marks the active
window exactly.

## Pin map

Every used pin is labelled here and in [`info.yaml`](info.yaml). No pin is used
without a name.

### Inputs `ui_in`

| pin | name | function |
| --- | --- | --- |
| `ui_in[2:0]` | `SEL` | manual pattern select, 0 to 7. Used when `RAND_EN` is low |
| `ui_in[3]` | `RAND_EN` | 1 selects the pattern from the TRNG instead of `SEL` |
| `ui_in[4]` | `HEALTH_CLR` | clears both sticky health flags while high |
| `ui_in[5]` | `FAST_SW` | random reselect every 8 frames instead of every 64 |
| `ui_in[6]` | `FREEZE` | holds the frame counter, so animation stops |
| `ui_in[7]` | `SAMP_FAST` | sample entropy every clock instead of every 8 clocks |

### Outputs `uo_out` (TinyVGA PMOD)

`uo_out = {hsync, B0, G0, R0, vsync, B1, G1, R1}`, 2 bits per channel, 64 colours.

| pin | name | | pin | name |
| --- | --- | --- | --- | --- |
| `uo_out[0]` | `R1` red MSB | | `uo_out[4]` | `R0` red LSB |
| `uo_out[1]` | `G1` green MSB | | `uo_out[5]` | `G0` green LSB |
| `uo_out[2]` | `B1` blue MSB | | `uo_out[6]` | `B0` blue LSB |
| `uo_out[3]` | `VSYNC` negative | | `uo_out[7]` | `HSYNC` negative |

### Bidirectional `uio`, `uio_oe = 8'b1110_0000`

| pin | dir | name | function |
| --- | --- | --- | --- |
| `uio[0]` | in | `ENT_IN` | external entropy bit, XORed into the noise source |
| `uio[2:1]` | in | `RCT_CUT` | repetition count cutoff: 4, 8, 16, 32 |
| `uio[4:3]` | in | `APT_CUT` | adaptive proportion cutoff: 40, 48, 56, 62 of 64 |
| `uio[5]` | out | `RCT_FAIL` | repetition count test sticky failure flag |
| `uio[6]` | out | `APT_FAIL` | adaptive proportion test sticky failure flag |
| `uio[7]` | out | `RND_OUT` | conditioned random bit stream, gated on health |

## TRNG architecture

```
ring_osc(5) \                                        +--> health_monitor (RAW samples)
             XOR -> sync -> entropy_source -> raw_bit
ring_osc(7) /          or the ENT_IN pin              +--> von_neumann -> lfsr_whitener
                                                                              |
                                          state[15:0] -> starfield pattern <---+
                                          state[2:0]  -> pattern select   <---+
                                          state[15]   -> RND_OUT pin, health gated
```

Full detail, including the SP 800-90B rationale, is in
[docs/design.md](docs/design.md). The parts worth knowing before trusting
anything:

### The ring oscillators cannot be simulated, and pretending otherwise is the trap

A free running ring oscillator has no meaning in an event driven simulator. Icarus
will happily oscillate a delay annotated inverter loop, and `test/tb_ring.v`
measures the result: **exactly 30 ns for the 5 stage ring and exactly 28 ns for
the 7 stage ring**, which is `2 * STAGES * SIM_DELAY` to the picosecond. A square
wave with zero jitter. Sampling it gives a deterministic sequence, and any
statistics gathered through it describe the simulator's timewheel.

So `entropy_source` has two paths. `SIM_ENTROPY = 0` keeps the ring oscillators
and is what gets taped out; it is verified structurally only. `SIM_ENTROPY = 1`
takes the raw bit from `ENT_IN` and elaborates no oscillator, which makes the
debiaser, the conditioner and both health tests bit exact checkable against a
Python model. `test/tb.v` selects the second for RTL simulation, the gate level
run reaches the same state by forcing the rings in the hardened netlist, and the
FPGA build takes it because `nextpnr-ice40` will not place a combinational loop.
Both paths XOR `ENT_IN` in, so an external noise source works in silicon too.

### The optimiser will destroy a ring oscillator silently

Written as one expression inside a single module, the mapper collapses the odd
inverter chain to a single inverter. Measured with Yosys 0.33 against the sg13g2
library: **2 surviving cells instead of 12**. Both oscillators become one inverter
plus one AND gate, their frequencies become identical, and the XOR of two
identical oscillators is a constant. The noise source silently becomes a wire tied
low and every downstream check still passes.

The fix is one `(* keep_hierarchy *)` module per stage plus `(* keep *)` on the
chain nodes. `make synth` counts the surviving stages after mapping and **fails
the build** if there are not 12, and `make harden` counts them again in the routed
netlist, because a clean GDS with no noise source in it looks exactly like a clean
GDS.

### The conditioner is linear, and the statistics measure it, not silicon

```
x^16 + x^15 + x^13 + x^4 + 1
```

with the de Bruijn zero state correction, so the period is 65536 rather than
65535, the all-zero state cannot lock the register up, and one period of output
carries exactly 32768 ones. `test_lfsr_period` walks the whole cycle and asserts
all 65536 states are visited.

An LFSR is a decorrelator and a rate matcher, **not** a cryptographic
conditioner. Sixteen consecutive output bits reveal the whole state. Do not treat
`RND_OUT` as a CSPRNG or as full entropy per bit. Doing it properly needs a sponge
or a block cipher, and neither fits in this tile.

Measured over 262144 output bits:

| | |
| --- | --- |
| bias | -0.00012, asserted within +/-0.01 |
| runs of length 1 | 0.5001 of 130757 runs |
| longest run | 17 bits |
| byte chi-square | 214.1 on 255 df (critical value 330.5 at p = 0.001) |
| von Neumann | bias +0.2496 to +0.0031, yield 0.1872 vs theoretical 0.1875 |

| | |
| --- | --- |
| ![Bias over time](docs/img/trng_bias.png) | ![Run length histogram](docs/img/trng_runs.png) |
| ![Byte value histogram](docs/img/trng_bytes.png) | ![Von Neumann debiasing](docs/img/trng_debias.png) |

**None of this measures silicon entropy.** The entropy input for those runs was a
Python pseudorandom generator driven into `ENT_IN`, because the ring oscillators
cannot be simulated. What the numbers are worth is that a wrong tap set, a stuck
output, a broken debiaser, a health test firing on fair input, or an accidentally
gated output all fail immediately.

### Health tests run on the raw samples, on purpose

Both tests tap the noise source before the debiaser and before the conditioner,
which is what SP 800-90B asks for. A stuck-at-0 source produces perfectly healthy
looking LFSR output forever, and a debiaser fed a constant simply stops emitting,
which is indistinguishable from a slow source.

- **Repetition count**, cutoff 4/8/16/32 selectable. Fires on the sample that
  completes a run of exactly the cutoff.
- **Adaptive proportion**, window 64, cutoff 40/48/56/62 selectable. Catches a
  source that drifted heavily biased without ever getting stuck long enough to
  trip the repetition test. `test_health_apt` proves the separation by using a
  stream whose longest run is 15, invisible to a cutoff of 32, while 60 of every
  64 samples match the window reference.

Both flags are sticky until `HEALTH_CLR`. While either is set, `RND_OUT` is held
low and the random reselect is inhibited, which is the standard's "stop producing
output once the source has failed" rule.

## Area and the tile decision

![Per submodule area and tile budget](docs/img/synth_area.png)

**Start with the tile, because the number the template gives for it is wrong.**
The Tiny Tapeout project template says, in a comment in `info.yaml`, that "a
single tile is about 167x108 uM". For this shuttle it is not. Tiny Tapeout's own
floorplan templates in `tt-support-tools`, which are the DEF files their `gds`
action hands the floorplanner, give:

| tiles | die | area |
| --- | --- | --- |
| 1x1 | 202.08 x 154.98 um | 31318 um2 |
| 1x2 | 202.08 x 313.74 um | 63401 um2 |

74% more area per tile than the comment. An earlier version of this repository
sized the design against 18036 um2 and concluded, with confident arithmetic, that
a 1x1 tile was impossible. It was measuring against the wrong tile.

Against the real one, three numbers from three points in the flow, all on the
real `sg13g2` library from
[IHP-Open-PDK](https://github.com/IHP-GmbH/IHP-Open-PDK):

| stage | cell area | as a fraction of a 1x1 tile | tool |
| --- | --- | --- | --- |
| post synthesis | 18040 um2, 1288 cells, 142 flip-flops | 57.6% | Yosys 0.33, `stat -liberty` |
| post route, real cells | **25888 um2, 1771 cells** | **82.7%** | LibreLane 3.0.0.dev44 |
| post route, plus fill | 28941 um2, 2343 instances | 92.4% | same run |

Synthesis says this fits a 1x1 tile comfortably. Post route it is 82.7% of the
tile, which by the usual rule of thumb says it does not fit at all: LibreLane's
default placement density target, and the template's, is 60%. The rule of thumb
is no more reliable than the forecast. What settles it is running the thing, and
it does fit, but only just:

| target density | what happens |
| --- | --- |
| 60, the default | global placement refuses: `[GPL-0302]` at 64.2% core utilisation, suggested 0.65 |
| 80 | places, then detailed placement fails after CTS with `[DPL-0036]`, unable to legalise 10 instances once 234 hold buffers are in |
| **85** | **places, routes, and signs off with 0 DRC (route, magic and klayout), 0 LVS, 0 antenna, +17.45 ns setup and +0.15 ns hold** |

`src/config.json` invites exactly one edit, `PL_TARGET_DENSITY_PCT`, for exactly
the `GPL-0302` error, so that is the one thing changed there, and the three
measurements above are written next to it. `tiles: "1x1"`.

Those three rows are from `make harden`, which only fixes `DIE_AREA`. Tiny
Tapeout's own `gds` job starts from `tt_block_1x1_pgvdd.def`, which carries their
pin frame and power grid as well, and it is more forgiving: a push with the target
at 80 hardened and cleared `precheck` there while failing locally. The committed
value is 85, which is what both flows accept.

It costs something. A 1x2 die was hardened for comparison, `make harden` with
`HARDEN_DIE="202.08 313.74"`, and at 40.9% density it routes with **41781 um** of
wire against **69427 um** for the 1x1: 66% more wire to fit the same logic in half
the area, all of it router detours around congestion. Timing barely notices
(+17.50 ns against +17.45 ns of setup slack) because the design is slow relative
to the process, but on a faster design that wirelength is where the tile would be
lost.

Where the 7850 um2 between synthesis and route goes is the part a synthesis-only
estimate misses entirely, and here it is the difference between 57.6% and 82.7%:

| class | area | count |
| --- | --- | --- |
| multi-input combinational | 11364 um2 | 1161 |
| sequential (flip-flops) | 7078 um2 | 142 |
| timing repair buffers | 5831 um2 | 342, of which 240 are hold buffers |
| clock tree buffers and inverters | 1247 um2 | 65 |
| inverters and buffers | 368 um2 | 61 |
| fill | 3054 um2 | 572 |

Hold fixing alone is 5831 um2, 23% of the real cell area, and none of it exists
until after placement. Anyone sizing a Tiny Tapeout tile from a `yosys stat`
number is going to be about 40% optimistic.

`make synth` fails the build on any blackbox, any inferred latch, or any ring
oscillator stage lost to the optimiser. `scripts/check_area.py`, which the CI
synth job runs, compares a fresh report against the committed one within 2% and
re-derives the tile count twice, once from the synthesis estimate and once from
the hardened die, so the `tiles` field in `info.yaml` cannot drift away from the
measurement. Reports are committed in [docs/synth/](docs/synth/) and
[docs/hardening/](docs/hardening/).

## Hardening and timing closure

`make harden` runs LibreLane **3.0.0.dev44** with `pdk: ihp-sg13g2`, exactly what
`TinyTapeout/tt-gds-action@ttihp26a` pins, so it is the shuttle flow rather than
an approximation of it. It differs from the `gds` job in two ways, both
deliberate: it fixes the clock at the 39.722 ns the design actually needs instead
of the template's 20 ns, it constrains the boundary from a real SDC instead of
LibreLane's generic fallback, and it runs KLayout DRC, which
[`src/config.json`](src/config.json) turns off to save shuttle time.

```
die area            31318.4 um2   202.08 x 154.98, one 1x1 tile
real cell area      25887.9 um2   1771 cells, 82.7% density
fill cells           3053.6 um2   572 cells
setup worst slack    17.4537 ns   at a 39.722 ns period
hold worst slack      0.1535 ns
clock skew            0.2733 ns
power                 0.3507 mW
wirelength              69427 um

route DRC 0    magic DRC 0    klayout DRC 0    LVS 0
antenna 0 nets, 0 pins        power grid 0     unmapped cells 0
max slew 0     max cap 0      setup TNS 0      hold TNS 0
```

Post route timing at all three corners LibreLane signs off on:

| corner | setup worst slack | hold worst slack |
| --- | --- | --- |
| slow 1.08 V 125 C | +17.4537 ns | +0.7188 ns |
| typ 1.20 V 25 C | +18.2674 ns | +0.3631 ns |
| fast 1.32 V -40 C | +18.7310 ns | +0.1535 ns |

Those numbers are measured against [`hardening/constraints.sdc`](hardening/constraints.sdc),
a real SDC, not the generic fallback LibreLane substitutes when
`PNR_SDC_FILE` is unset. It budgets 25% of the clock period at each boundary for
the harness input and output mux, models the boundary with `sg13g2_inv_1` drive
and load, and gives a reason for every number in it. A slack figure from a
fallback SDC would not be worth quoting.

### Does the declared clock actually close?

`info.yaml` says `clock_hz: 25175000`. `make sta` proves it, with OpenSTA 3.1.0
on netlists mapped per corner (`dfflibmap` and `abc` pick cells from whichever
liberty they are handed, so a slow corner timing report has to run on a slow
corner netlist):

| corner | setup slack at 39.722 ns | hold slack | Fmax | margin over 25.175 MHz |
| --- | --- | --- | --- | --- |
| slow 1.08 V 125 C | +33.8093 ns | +0.0989 ns | 169.13 MHz | 6.72x |
| typ 1.20 V 25 C | +35.9221 ns | +0.0643 ns | 263.16 MHz | 10.45x |
| fast 1.65 V -40 C | +37.9347 ns | +0.0350 ns | 559.50 MHz | 22.22x |

Total negative slack is 0.0 at every corner. The setup critical path is 5.70 ns
at the slow corner, running from a `vga_sync` counter flop through the `gen_end`
term into the rule 30 row register. `scripts/parse_sta.py` fails the run if setup
does not close at the signoff corner, so the `clock_hz` claim cannot silently rot.

Those are post synthesis numbers. The post route ones are lower, and the honest
comparison is the pair: the same slow corner gives +33.81 ns of setup slack after
synthesis and +17.45 ns after routing, so Fmax at that corner falls from 169.13
MHz to **44.86 MHz**. Post synthesis STA estimates interconnect from the liberty
wireload model, while the hardened number carries extracted parasitics, the real
clock tree and 240 hold buffers. Both are reported rather than just the flattering
one. Either way 25.175 MHz closes, with 1.78x of margin on the routed design.

### One violation that is not clean, stated plainly

`design__max_fanout_violation__count` is **1**. The clock tree root buffer
`clkbuf_0_clk/X` drives 16 sinks against the library's `default_max_fanout` of 8.

It is left as it is, with the reasoning written down rather than the number
hidden: `max_fanout` is a proxy design rule for slew and capacitance, and both of
the things it stands in for are clean at every corner (max slew 0, max cap 0).
The clock tree it produced has 33 ps of skew and 0.68 to 0.72 ns of latency, and
setup and hold both close with margin. See
[docs/design.md](docs/design.md#the-one-violation-that-is-not-clean) for what was
tried.

### Ring oscillator frequency, calculated not measured

The real PDK gives real inverter delays, so the expected oscillation frequency
can be derived instead of guessed. `scripts/ring_freq.py` interpolates the
`sg13g2_inv_1` and `sg13g2_nand2_1` delay tables at the self-loaded capacitance,
solving for a self consistent input slew, and computes
`T = 2 * (t_nand + (N-1) * t_inv)`:

| corner | inverter delay | 5 stage ring | 7 stage ring | oscillator periods per sample at /8 |
| --- | --- | --- | --- | --- |
| slow 1.08 V 125 C | 38 ps | 2376 MHz | 1742 MHz | 554 |
| typ 1.20 V 25 C | 25 ps | 3677 MHz | 2686 MHz | 854 |
| fast 1.65 V -40 C | 14 ps | 6741 MHz | 4898 MHz | 1557 |

**This is a hand calculation from Liberty tables, not a measurement.** It
excludes interconnect, so real rings on silicon will be slower than every figure
in that table. It is quoted because the conclusion survives a large error bar:
even at the slow corner, and even if routing halved these frequencies, the
default divide-by-8 sample rate still gives hundreds of oscillator periods per
sample for jitter to accumulate in. That is what `SAMP_FAST` exists to let you
adjust once the real number is known.

## Simulating and testing locally

Everything runs through a repo local venv, so no shell activation is needed.

```sh
make venv     # create .venv and install test/requirements.txt
make test     # the cocotb regression, about 6 minutes
make gl       # the same regression on the hardened gate level netlist
make lint     # verilator --lint-only -Wall, zero warnings expected
make ring     # ring oscillator structural testbench, plain Icarus
make synth    # Yosys area report against the real IHP liberty (needs network once)
make capture  # 64 further model-verified frames for the animated images, ~16 min
make sta      # OpenSTA timing closure across three real IHP corners
make harden   # LibreLane hardening to GDS, DRC and LVS signoff, layout renders
make fpga     # yosys + nextpnr-ice40 + icepack for an ICE40UP5K
make formal   # SymbiYosys proofs of the debiaser and sync generator
make ring-freq # ring oscillator frequency from the Liberty delay tables
make images   # regenerate every PNG and GIF in docs/img from simulation output
make check    # lint + ring + formal + test + synth
```

Requires `iverilog`, `verilator`, `yosys` and Python 3.11+ for the simulation and
synthesis targets. Tested with Icarus 12.0, Verilator 5.020, Yosys 0.33 and
cocotb 2.0.1.

`make sta` additionally needs `openroad` (OpenSTA 3.1.0) and an installed
`ihp-sg13g2` PDK; `make harden` needs `librelane` 3.0.0.dev44 and `klayout`. Both
default to `/home/danieltyukov/.local/share/pdk/IHP-Open-PDK/ihp-sg13g2` and take
`PDK_ROOT_IHP` as an override. `make gl` needs the PDK cell models and downloads
Tiny Tapeout's Icarus itself. `make synth` works without an installed PDK: it
falls back to fetching the one liberty file it needs.

`make images` reads what `make test` and `make capture` left in `test/output/`, so
run those first. `make capture` is a further 64 frames of simulation, about 16
minutes; those frames are verified against the model too, so it is a test as well
as an image source.

Gate level simulation, once a hardened netlist exists:

```sh
./scripts/run_gl.sh                 # newest netlist from make harden
./scripts/run_gl.sh path/to/nl.v    # or a specific one
```

That runs the same regression against the netlist. It is a script rather than a
bare `make -B GATES=yes` because it has to unpack Tiny Tapeout's patched Icarus
first; see [below](#gate-level-the-same-suite-on-the-hardened-netlist) for why a
stock Icarus reports nothing at all here.

### What the test suite actually asserts

| test | assertion |
| --- | --- |
| `test_reset` | no output x or z, `uio_oe == 0b11100000`, syncs idle high at (0,0), health flags clear, LFSR reloads its seed, mid frame reset returns to the (0,0) state, and equal clock counts after reset give equal pixels |
| `test_vga_timing` | 640/16/96/48 and 480/10/2/33 measured from the pins, both totals, both polarities, 59.9405 Hz |
| `test_golden_frames` | 8 frames, 2 457 600 pixels, all pixel exact against `test/model.py`, all pairwise distinct, none flat |
| `test_pattern_switch_mid_frame` | `sel` changed at (321,200): sync exact on all 420 000 clocks, 128 321 pixels matched the old pattern and 178 879 the new one |
| `test_von_neumann` | all four pair cases, then 20 000 biased samples: bias +0.2496 to +0.0031, yield 0.1872 |
| `test_lfsr_sequence` | 8 000 steps against the model, free running and with entropy injection |
| `test_lfsr_period` | all 65 536 states visited including zero, seed recurs at exactly step 65 536 |
| `test_health_rct` | fires on the sample completing a run of exactly the cutoff, all four cutoffs, no false positive on alternating input |
| `test_health_apt` | fires on 60-of-64 bias at three cutoffs, ignores it at 62, no false positive on 4096 fair samples, repetition flag clear throughout |
| `test_health_sticky` | flag survives 256 healthy samples, gates the output on the 126 clocks where the LFSR bit was 1, clears on demand, then ungates |
| `test_trng_statistics` | bias within bound, runs distribution sane, byte chi-square under bound, no health test fires on fair input |

Every one of those runs twice: at RTL, and again against the hardened gate level
netlist in the `gl_test` job, where it is checking that synthesis, placement,
clock tree insertion and routing did not change what the design does.

Plus `test/tb_ring.v` with 12 structural checks on the ring oscillator path, and
`test/capture.py` with 64 further model-verified frames.

### Formal verification

`make formal` runs SymbiYosys on the two blocks where a proof is worth more than a
test:

| target | what is proved | scope |
| --- | --- | --- |
| `von_neumann` | nothing is emitted without a completed pair; **01 emits 0, 10 emits 1, equal pairs emit nothing**; two consecutive output strobes are impossible | bounded, 40 cycles from reset |
| `vga_sync` | counters stay inside 0..799 and 0..524; syncs are low only inside their windows and never inside the visible area; `active` matches the visible window exactly; `line_end` and `frame_end` only at the ends; the counters advance by exactly one and wrap | unbounded, base case plus one step induction |

The debiaser property is the one that matters. The README's unbiasedness claim
rests on P(01) = P(10) for independent samples, so a debiaser that emits 0 on
exactly 01 and 1 on exactly 10 is unbiased by construction. Checking that against
two streams shows it worked twice. Proving the symmetry shows it always holds. The
statistical step still needs the input samples to be independent, which is an
assumption about the noise source that no tool can prove.

The sync generator is structured as a real induction: a base task forces a reset
and proves the counters land on (0,0), and a step task assumes only that they
start somewhere legal and proves one clock preserves every property. That is
unbounded, and it is also far cheaper than bounded checking from reset, which
needs 656 cycles just to reach the sync window and was taking ten seconds per step
at step 220.

`make formal` also runs a **mutation check**, because a proof that passes on a
broken design proves nothing: it injects two specific bugs, a `line_end` that
fires one pixel early and a debiaser that emits the second bit of the pair, and
fails if either proof still passes. Both are caught.

Two honest notes. The debiaser result is bounded rather than unbounded because
z3 4.8.12, the version available here, does not converge on the induction step
for that miter, and no newer solver was installable (`yices2` is not packaged,
`boolector` is the 2012 release, `cvc5` would not install). And these are two
blocks, not the whole tile: the pattern generators and the health monitor are
covered by simulation only.

## CI jobs and what they need

| workflow | jobs | status here |
| --- | --- | --- |
| `test.yaml` | lint, ring, cocotb, synth | **passing**, badge above |
| `gds.yaml` | gds, precheck, gl_test, viewer | **passing**, badge above |
| `docs.yaml` | datasheet render | **passing**, badge above |
| `fpga.yaml` | ice40 bitstream | **passing**, badge above. The template ships this one disabled |

All of these run on plain `ubuntu-24.04` runners with no secrets and no Tiny
Tapeout API access.

### Gate level: the same suite on the hardened netlist

`gl_test` re-runs the cocotb regression against the post place and route netlist.
That catches anything synthesis, clock tree insertion or routing changed about the
design, which RTL simulation by construction cannot see. It sat `in_progress` for
1h51m and was deleted from this workflow once. Two things had to be dealt with to
get it back, and both are specific to this design rather than to CI.

**The flops never clock under a stock Icarus.** `sg13g2_dfrbpq_1` does not clock
from `CLK`, it clocks from `delayed_CLK`, which is the signal its `$setuphold` and
`$recrem` timing checks produce:

```verilog
ihp_dff_r (int_fwire_IQ, notifier, delayed_CLK, delayed_D, int_fwire_r, xcr_0);
...
$setuphold (posedge CLK, posedge D, 0.0, 0.0, notifier,,, delayed_CLK, delayed_D);
```

Icarus 12 prints `warning: Timing checks are not supported and delayed signal
"delayed_CLK" will not be driven` and carries on, so every flop in the design
holds `x` forever. The netlist elaborates, the simulation runs, and it verifies
nothing. Tiny Tapeout's patched Icarus 13 drives those signals, and their
`gl_test` action installs it; `scripts/run_gl.sh` unpacks the same `.deb` under
`build/` rather than installing it, so the system Icarus is left alone.

**The ring oscillators stop time.** `src/ring_osc.v` is a deliberate combinational
loop and it has to survive synthesis for the TRNG to exist, so the netlist holds a
five inverter and a seven inverter ring. The IHP cell models are zero delay
(`sg13g2_inv_1` is `not (Y, A);` with a `0.0` specify block), so the moment `rst_n`
releases and the enable NAND opens, the simulator has a zero delay feedback loop
and makes no further progress. That is inherent to gate level simulation of any
ring oscillator against zero delay models and is not fixable in the RTL, because
the loop is the design.

[`test/tb.v`](test/tb.v) cuts both rings with a `force` on `chain[0]`. Each chain
then resolves to a static alternating pattern, both odd length rings settle their
output to 0, so the sampled bit `osc_a ^ osc_b` is a constant 0 and
`raw_bit = 0 ^ ext_bit` is exactly `uio_in[0]`. That is bit for bit what the RTL
regression drives through `SIM_ENTROPY = 1`, which is why the same test module
runs against both. [`test/test_gl.py`](test/test_gl.py) asserts that state instead
of assuming it: every one of the 12 chain nets, both settled ring outputs, the
synchroniser output that feeds the sampler, and `uio_oe` through the tie cells.

The result, on the netlist the `gds` job produced:

```
test_gl_tie_cells                 PASS
test_gl_rings_are_broken          PASS
test_reset                        PASS
test_vga_timing                   PASS      216 s
test_golden_frames                PASS      513 s   8 frames, 2 457 600 pixels
test_pattern_switch_mid_frame     PASS       95 s
test_von_neumann                  PASS
test_lfsr_sequence                PASS
test_lfsr_period                  PASS       13 s   all 65 536 LFSR states
test_health_rct / apt / sticky    PASS
test_trng_statistics              PASS       47 s   262 144 output bits
                                  ------
TESTS=13 PASS=13 FAIL=0                     891 s
```

Nothing was reduced for the gate level run: the same 11 tests, the same 8 golden
frames, the same 65 536 state LFSR walk and the same 262 144 sample statistics run
against the netlist, in about 15 minutes. The only difference is that
`test/tbutil.py` reads the four internal probes through the flat netlist names
(`\rnd_state[0] `) instead of through the RTL hierarchy, and the frames are not
written to `test/output/`, because every image in `docs/img` comes from the RTL
run and a second writer would quietly make that untrue.

What this does **not** verify is the oscillator, which is held broken throughout.
Nothing in an event simulator can verify it. That is covered structurally by
`test/tb_ring.v`, and by the ring stage counts that `make synth` checks after
mapping and `make harden` checks again in the routed netlist.

One more thing worth writing down, because it depends on which PDK snapshot you
have. The snapshot `tt-gds-action@ttihp26a` pins (IHP-Open-PDK `cb7daaa`) defines
the `ihp_dff_r`, `ihp_mux2` and `ihp_mux4` UDPs inside `sg13g2_stdcell.v`. Newer
ones split them into `sg13g2_udp.v`, and then `sg13g2_stdcell.v` will not
elaborate without it: 154 `Unknown module type` errors. Naming a file that does
not exist is a hard error and so is defining the UDPs twice, so `test/Makefile`
picks it up with a `$(wildcard ...)` and works with either layout. The stock
template handles neither.

### The FPGA path

`fpga.yaml` builds an ICE40UP5K bitstream through Tiny Tapeout's own
`tt_fpga.py`. The template ships that workflow disabled, and the obvious build
does not work:

```
ERROR: timing analysis failed due to presence of combinatorial loops,
       incomplete specification of timing ports, etc.
```

That is `nextpnr-ice40` refusing the ring oscillators, and it is not negotiable:
the tool will not place a design containing a combinational cycle. So the
oscillators are left out of the FPGA build. `tt_fpga.py` synthesises with
`-DSYNTH` and [`src/entropy_source.v`](src/entropy_source.v) takes that as the
signal to source entropy from the `ENT_IN` pin instead. Nothing else changes, and
the ASIC flow never defines `SYNTH`: LibreLane runs with `VERILOG_DEFINES` null,
and if that ever stopped being true, `make synth` and `make harden` both count the
12 ring stages and fail without them.

Leaving them out is also the honest build for an FPGA. Routed LUTs cannot host a
usable ring oscillator TRNG, so on a board the noise has to arrive from outside,
and whatever is fed to that pin is not a TRNG.

From the workflow run, on Tiny Tapeout's `tt_fpga_top` and their FabricFox pin
assignment:

```
ICESTORM_LC     630 / 5280   11%
SB_IO            26 /   39   66%
SB_GB             6 /    8   75%
BRAM, DSP, PLL, SPRAM        0%      (no framebuffer, so nothing to store)

register to register   41.49 MHz, PASS at the 12 MHz the action asks for,
                       and 1.65x over the 25.175 MHz pixel clock
```

`make fpga` runs the same flow locally through
[`fpga/fpga_top.v`](fpga/fpga_top.v), a wrapper that exists because the raw tile
has 43 ports and sg48 has 39 usable I/O. It uses no PCF, so its numbers differ:
680 logic cells and 33.27 MHz register to register, still 1.32x over the pixel
clock. Its clock to output pad path is 43.96 ns against a 39.72 ns pixel period,
which is over budget and reported rather than left out. There is no output delay
constraint in that run, because inventing pin numbers for a board nobody has would
be worse than not constraining them; on a real board that path needs pin
constraints and probably an output register stage. It does not affect the ASIC,
where those ports go to the Tiny Tapeout harness rather than to pads. Reports are
in [docs/fpga/](docs/fpga/).

## Repository layout

```
src/                 20 Verilog files, one module each
  tt_um_danieltyukov_vga_trng.v   top level, pin map, select logic
  vga_sync.v                      800x525 counters
  pattern_mux.v                   the eight generators and the 8:1 mux
  pat_*.v, sine_q.v               the pattern generators
  trng.v                          entropy pipeline top
  ring_inv.v ring_gate.v ring_osc.v   protected ring oscillator stages
  entropy_source.v                prescaler, path select, synchroniser
  von_neumann.v                   debiaser
  lfsr_whitener.v                 conditioner and pixel rate PRNG
  health_monitor.v                repetition count and adaptive proportion tests
  config.json                     LibreLane config, template default plus a
                                  measured PL_TARGET_DENSITY_PCT
test/
  test.py                         the 11 test regression
  model.py                        independent cycle accurate reference model
  tbutil.py                       reset, lockstep stepping, frame capture
  capture.py                      animation frame capture, also model verified
  tb.v                            cocotb wrapper: SIM_ENTROPY=1 at RTL, and the
                                  ring force that makes gate level simulatable
  tb_ring.v                       ring oscillator structural testbench
  test_gl.py                      netlist specific checks, run before the suite
scripts/
  synth_report.sh                 Yosys area report against the real IHP liberty
  parse_synth.py                  Yosys text to docs/synth/area.json
  check_area.py                   re-derives the tile count from the measurements
  harden.sh, parse_harden.py      LibreLane run, signoff extract, ring survival
  run_sta.sh, parse_sta.py        OpenSTA across the three corners
  run_gl.sh                       gate level regression on a hardened netlist
  run_fpga.sh, parse_fpga.py      iCE40 flow and its report
  run_formal.sh                   SymbiYosys proofs plus the mutation check
  ring_freq.py                    ring frequency from the Liberty delay tables
  render_gds.py                   KLayout layout renders
  frames.py                       read the raw frame dumps
  make_images.py                  regenerate every raster image in docs/img
hardening/
  config.json                     LibreLane config for the local hardening run
  constraints.sdc                 real timing constraints, not the fallback
fpga/
  fpga_top.v                      iCE40 demo wrapper for a board
formal/
  von_neumann_fv.v, *.sby         debiaser symmetry proof
  vga_sync_fv.v, *.sby            sync counter invariants, base plus step
docs/
  info.md                         shuttle datasheet
  design.md                       area budget, pattern costs, entropy design
  synth/                          committed Yosys area reports
  sta/                            OpenSTA per corner reports, ring frequency
  hardening/                      LibreLane metrics and signoff
  fpga/                           iCE40 utilisation and timing
  formal/                         SymbiYosys task results
  img/                            hand written SVGs, generated PNGs and GIFs,
                                  and the two routed layout renders
```

## Honesty notes

Collected in one place so none of it has to be dug out of the prose:

- Nothing in this repository measures entropy from silicon. The ring oscillator
  path is verified structurally: it oscillates, it stops when disabled, the two
  rings have different periods, and all 12 stages survive both synthesis and
  routing. Its statistical behaviour is not and cannot be tested in an event
  simulator.
- Every statistical figure quoted was produced with a Python pseudorandom
  generator driven into `ENT_IN`. They characterise the debiaser and the LFSR
  conditioner.
- The LFSR conditioner is linear. `RND_OUT` is not a CSPRNG.
- The correct ring oscillator sample rate is a property of the fabricated
  silicon. `SAMP_FAST` and both cutoff selectors are runtime controls so it can
  be found on a bench.
- The tile is **hardened and DRC clean, not fabricated**. Every job of `gds`,
  `docs`, `test` and `fpga` passes in CI, which means it places, routes, passes
  DRC and LVS, clears Tiny Tapeout's precheck, and its hardened netlist passes the
  regression again. It has not been submitted to a shuttle and no silicon exists.
- **Gate level simulation runs with both ring oscillators held broken.** A live
  ring against zero delay cell models stops an event simulator's timewheel, so
  `test/tb.v` forces both chains and `test/test_gl.py` asserts the resulting
  state. Everything else in the netlist is verified; the oscillator is not.
- The ring oscillator frequency table is a hand calculation from Liberty delay
  tables with no interconnect. Real rings will be slower. It is not a measurement.
- **The FPGA bitstream has no ring oscillators in it.** `nextpnr-ice40` refuses a
  design containing a combinational loop, so the FPGA build takes entropy from the
  `ENT_IN` pin. Whatever is fed to that pin is not a TRNG.
- The local FPGA run is unconstrained: no PCF, no output delay constraint. The
  register to register frequency passes at 1.32x, the clock to output pad path
  does not fit a pixel period, and both are reported. The `fpga` workflow builds
  Tiny Tapeout's own top and pin assignment instead, and is the one the badge
  points at.
- One `max_fanout` design rule violation remains, on the clock tree root buffer.
  It is documented rather than papered over, together with what was tried.
- `make harden` fixes the die at Tiny Tapeout's own 1x1 tile area, but only the
  area: their `gds` job starts from `tt_block_1x1_pgvdd.def`, which also carries
  the harness pin frame and power grid obstructions. Their flow runs on every push
  and passes, so the difference is not hypothetical, but the two are not the same
  floorplan.
- **The tile fits at 82.7% density, which is not much room.** `make harden` fails
  placement outright at a 60% target and at an 80% one; 85 is what works there.
  Tiny Tapeout's own flow is more forgiving and hardened it at 80, but the
  committed value is 85 because that is what both accept. Any future change needs
  the density rechecked rather than assumed.

## License

Apache-2.0, Copyright 2026 Daniel Tyukov. See [LICENSE](LICENSE).
