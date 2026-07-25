# tt-ihp-vga-trng

A Tiny Tapeout tile for the **IHP 130nm open source PDK** shuttle: eight 640x480
VGA pattern generators sharing one sync generator, with the active pattern chosen
either from three input pins or by an on-chip true random number generator that
has von Neumann debiasing, LFSR conditioning and SP 800-90B style online health
tests. Output goes straight to a TinyVGA PMOD.

[![test](https://github.com/danieltyukov/tt-ihp-vga-trng/actions/workflows/test.yaml/badge.svg)](https://github.com/danieltyukov/tt-ihp-vga-trng/actions/workflows/test.yaml)

| | |
| --- | --- |
| Top module | `tt_um_danieltyukov_vga_trng` |
| Tiles | `1x2` ([why](#area-and-the-tile-decision)) |
| Clock | 25.175 MHz pixel clock, 640x480 at 59.9405 Hz |
| Mapped area | 1288 cells, 142 flip-flops, 18040 um2 (IHP sg13g2) |
| External hardware | [TinyVGA PMOD](https://github.com/mole99/tiny-vga) |
| Regression | 11 cocotb tests, 2.5 million pixels compared, all passing |

![Block diagram](docs/img/block_diagram.svg)

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
Python model. `test/tb.v` selects the second for RTL simulation. Both builds XOR
`ENT_IN` in, so an external noise source works in silicon too.

### The optimiser will destroy a ring oscillator silently

Written as one expression inside a single module, the mapper collapses the odd
inverter chain to a single inverter. Measured with Yosys 0.33 against the sg13g2
library: **2 surviving cells instead of 12**. Both oscillators become one inverter
plus one AND gate, their frequencies become identical, and the XOR of two
identical oscillators is a constant. The noise source silently becomes a wire tied
low and every downstream check still passes.

The fix is one `(* keep_hierarchy *)` module per stage plus `(* keep *)` on the
chain nodes. `make synth` counts the surviving stages and **fails the build** if
there are not 12.

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

Yosys 0.33 mapped against the real `sg13g2_stdcell_typ_1p20V_25C.lib` from
[IHP-Open-PDK](https://github.com/IHP-GmbH/IHP-Open-PDK), not generic gates and
not a gate-equivalent estimate:

```
1288 standard cells
 142 flip-flops, all sg13g2_dfrbpq_1, no latches
18040 um2 of mapped standard cell area
```

A tile is about 167 x 108 um = 18036 um2, and `src/config.json` leaves
`PL_TARGET_DENSITY_PCT` at the Tiny Tapeout default of 60.

| tiles | tile area | required density | verdict |
| --- | --- | --- | --- |
| 1x1 | 18036 um2 | **100.0%** | impossible: no room for filler, PDN or router detours |
| 1x2 | 36072 um2 | **50.0%** | comfortably inside the 60% target |

At 60% the design needs 1.67 tiles, so `tiles: "1x2"`.

Reaching 60% on one tile means shedding 7218 um2. The only two blocks large
enough are the two that hold state: `pat_rule30` at 4209 um2 and `pat_ball` at
3346 um2, 7555 um2 together. Deleting both leaves 10485 um2, which is 58.1%
density: it clears the target by 1.9 percentage points, at the cost of both
animated patterns, the collision behaviour, and the only genuinely iterated
pattern in the design.
[docs/design.md](docs/design.md#1-area-budget-and-the-tile-decision) lists the
smaller optimisations that were considered and why none of them changes the
answer.

`make synth` also fails the build on any blackbox, any inferred latch, or any ring
oscillator stage lost to the optimiser. `scripts/check_area.py`, which the CI synth
job runs, compares a fresh report against the committed one within 2% and
independently re-derives the required tile count from the measured area, so the
`tiles` field in `info.yaml` cannot drift away from the measurement. Reports are
committed in [docs/synth/](docs/synth/).

## Simulating and testing locally

Everything runs through a repo local venv, so no shell activation is needed.

```sh
make venv     # create .venv and install test/requirements.txt
make test     # the cocotb regression, about 6 minutes
make lint     # verilator --lint-only -Wall, zero warnings expected
make ring     # ring oscillator structural testbench, plain Icarus
make synth    # Yosys area report against the real IHP liberty (needs network once)
make capture  # 64 further model-verified frames for the animated images, ~16 min
make images   # regenerate every PNG and GIF in docs/img from simulation output
make check    # lint + ring + test + synth
```

Requires `iverilog`, `verilator`, `yosys` and Python 3.11+. Tested with Icarus
12.0, Verilator 5.020, Yosys 0.33 and cocotb 2.0.1.

`make images` reads what `make test` and `make capture` left in `test/output/`, so
run those first. `make capture` is a further 64 frames of simulation, about 16
minutes; those frames are verified against the model too, so it is a test as well
as an image source.

Gate level simulation, once the netlist exists:

```sh
cp runs/wokwi/results/final/verilog/gl/tt_um_danieltyukov_vga_trng.v test/gate_level_netlist.v
make -C test -B GATES=yes
```

The hardened netlist has no parameters, so GL simulation exercises the ring
oscillator path. The VGA timing and reset tests are meaningful there; the entropy
pipeline tests are not, because they need the deterministic source.

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

Plus `test/tb_ring.v` with 12 structural checks on the ring oscillator path, and
`test/capture.py` with 64 further model-verified frames.

## CI jobs and what they need

| workflow | needs Tiny Tapeout infrastructure | validated here |
| --- | --- | --- |
| `test.yaml` | no. apt `iverilog`, `verilator`, `yosys` plus pip | yes, all four jobs run locally |
| `gds.yaml` | yes. `TinyTapeout/tt-gds-action`, ihp-sg13g2 PDK, Librelane container | no |
| `docs.yaml` | yes. `TinyTapeout/tt-gds-action/docs` | no |
| `fpga.yaml` | yes. their ice40 toolchain container. Off by default, as in the template | no |

Only `test.yaml` has a badge, because it is the only one that can be claimed to
pass. `gds.yaml`, `docs.yaml` and `fpga.yaml` are present for shuttle submission
and are the template's own, unmodified except for comments.

Anyone enabling `fpga.yaml` should build with `SIM_ENTROPY = 1`: Yosys' ice40
target will not synthesise a combinational loop, so the ring oscillators have to
be replaced by the `ENT_IN` pin.

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
  config.json                     Librelane config, template default
test/
  test.py                         the 11 test regression
  model.py                        independent cycle accurate reference model
  tbutil.py                       reset, lockstep stepping, frame capture
  capture.py                      animation frame capture, also model verified
  tb.v                            cocotb wrapper, selects SIM_ENTROPY=1
  tb_ring.v                       ring oscillator structural testbench
scripts/
  synth_report.sh                 Yosys area report against the real IHP liberty
  parse_synth.py                  Yosys text to docs/synth/area.json
  frames.py                       read the raw frame dumps
  make_images.py                  regenerate every raster image in docs/img
docs/
  info.md                         shuttle datasheet
  design.md                       area budget, pattern costs, entropy design
  synth/                          committed Yosys reports
  img/                            hand written SVGs and generated PNGs and GIFs
```

## Honesty notes

Collected in one place so none of it has to be dug out of the prose:

- Nothing in this repository measures entropy from silicon. The ring oscillator
  path is verified structurally: it oscillates, it stops when disabled, the two
  rings have different periods, and all 12 stages survive synthesis. Its
  statistical behaviour is not and cannot be tested in an event simulator.
- Every statistical figure quoted was produced with a Python pseudorandom
  generator driven into `ENT_IN`. They characterise the debiaser and the LFSR
  conditioner.
- The LFSR conditioner is linear. `RND_OUT` is not a CSPRNG.
- The correct ring oscillator sample rate is a property of the fabricated
  silicon. `SAMP_FAST` and both cutoff selectors are runtime controls so it can
  be found on a bench.
- The `gds`, `docs` and `fpga` workflows have not been run. Only `test.yaml` has.
- Area figures are Yosys post-mapping standard cell area, which is what decides
  the tile count. Final placed and routed area comes out of the tt-gds flow and
  will be larger.

## License

Apache-2.0, Copyright 2026 Daniel Tyukov. See [LICENSE](LICENSE).
