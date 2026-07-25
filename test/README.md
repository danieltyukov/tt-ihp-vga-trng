# Test bench

Eleven cocotb tests plus a plain Icarus testbench for the ring oscillator path.
Every test asserts. There is no `cocotb.pass_test()` anywhere and no test whose
body is unreachable.

## Running

From the repository root, so the venv is handled for you:

```sh
make test     # the regression, about 6 minutes
make lint     # verilator --lint-only -Wall
make ring     # ring oscillator structural testbench
make check    # lint + ring + test + synth
```

Or from this directory with the venv on `PATH`:

```sh
source ../.venv/bin/activate
make -B
make lint
make ring
make capture   # 64 further model-verified frames for the animated images, ~16 min
```

`make -C test lint`, `ring` and `synth` work without cocotb on `PATH`; the
Makefile guards the cocotb include and warns instead of failing.

## Files

| file | what it is |
| --- | --- |
| `test.py` | the regression, 11 tests |
| `model.py` | independent cycle accurate model of the whole tile, imports no cocotb |
| `tbutil.py` | reset sequence, lockstep stepping, frame capture, output file layout |
| `capture.py` | animation frame sequences for `docs/img`, model verified too |
| `tb.v` | cocotb wrapper. Instantiates the tile with `SIM_ENTROPY = 1` |
| `tb_ring.v` | plain Icarus testbench for the ring oscillator path, 12 checks |
| `Makefile` | cocotb rules plus the `lint`, `ring`, `synth`, `capture` targets |

## What each test asserts

| test | assertion | scale |
| --- | --- | --- |
| `test_reset` | no output is x or z, `uio_oe == 0b11100000`, both syncs idle high at pixel (0,0), health flags clear, the LFSR reloads `0xACE1`, a mid frame reset returns to the (0,0) state, and the same clock count after reset gives the same pixel | 2 resets |
| `test_vga_timing` | all eight intervals derived from the pins alone: 640/16/96/48 and 480/10/2/33, both totals, both polarities, 59.9405 Hz | 4 lines per clock, then 1050 lines |
| `test_golden_frames` | one frame per pattern, pixel exact against `model.py`, all eight pairwise distinct, none flat | 2 457 600 pixels |
| `test_pattern_switch_mid_frame` | `sel` changed at (321,200): sync matches the model on every clock of the frame, and the pixels follow the old then the new pattern | 420 000 clocks |
| `test_von_neumann` | all four pair cases explicitly, then bias and yield over a biased stream | 20 020 samples |
| `test_lfsr_sequence` | state matches the model step by step, free running and with entropy injection | 8 000 steps |
| `test_lfsr_period` | all 65 536 states visited, the all-zero state among them, seed recurs at exactly 65 536 | 65 536 steps |
| `test_health_rct` | fires on the sample completing a run of exactly the cutoff, all four cutoffs, and does not fire on an alternating source at the tightest cutoff | 4 cutoffs + 400 samples |
| `test_health_apt` | fires on 60-of-64 bias at cutoffs 40, 48, 56, ignores it at 62, no false positive on 4096 fair samples, and the repetition flag stays clear throughout | 4 cutoffs + 4096 samples |
| `test_health_sticky` | the flag survives 256 healthy samples, gates the output on every clock where the LFSR bit was 1, clears on `HEALTH_CLR`, then ungates | 330 samples |
| `test_trng_statistics` | bias within a documented bound, run length distribution sane, byte chi-square under bound, and no health test fires on fair input | 262 144 bits |

`tb_ring.v` covers what the cocotb regression deliberately does not: the chain
resolves out of `x` with the enable low, does not oscillate while disabled, starts
when enabled, stops again, both periods equal `2 * STAGES * SIM_DELAY`, the two
rings have different periods, their XOR is not stuck at a constant, and the
`SIM_ENTROPY = 1` path tracks `ENT_IN` exactly.

## Why the entropy source is a pin in simulation

A free running ring oscillator has no meaning in an event driven simulator.
`tb_ring.v` measures the delay annotated loop and gets exactly 30 ns for the 5
stage ring and exactly 28 ns for the 7 stage ring, which is
`2 * STAGES * SIM_DELAY` to the picosecond. That is a jitter free square wave, so
sampling it gives a deterministic sequence and any statistics gathered through it
describe the simulator rather than the design.

So `tb.v` instantiates the tile with `SIM_ENTROPY = 1`, which replaces the
oscillators with `uio_in[0]`. The testbench drives a known stream and the
debiaser, the conditioner and both health tests become bit exact checkable. The
ring oscillator path is what gets taped out and is checked structurally in
`tb_ring.v`. See `../src/entropy_source.v`.

## Waveforms

The regression simulates about 230 ms, so a full hierarchy dump is tens of
megabytes and costs roughly 20% of the runtime. By default only the tile pins are
dumped, which is what you look at for VGA timing. For internals:

```sh
make -B
# then, for a full hierarchy dump:
cd sim_build/rtl && vvp sim.vvp -fst +dump_all
```

View with:

```sh
gtkwave tb.fst
surfer tb.fst
```

## Gate level simulation

Harden the project, then:

```sh
cp ../runs/wokwi/results/final/verilog/gl/tt_um_danieltyukov_vga_trng.v gate_level_netlist.v
make -B GATES=yes
```

The hardened netlist has no parameters, so GL simulation exercises the ring
oscillator path. `test_reset` and `test_vga_timing` are meaningful there. The
entropy pipeline tests are not, because they need the deterministic source, and
the golden frame test is not, because the starfield depends on the conditioner
state which the ring oscillators now perturb.

## Output files

The runs write to `output/`, which is gitignored and consumed by
`../scripts/make_images.py`:

```
output/frames/*.bin      one verified frame per pattern            (make test)
output/anim/*.bin        32 ripple frames                          (make capture)
output/switch/*.bin      32 TRNG selected frames                   (make capture)
output/timing.json       the measured VGA intervals                (make test)
output/stats.json        262144 output bits characterised          (make test)
output/debias.json       bias before and after von Neumann         (make test)
output/switch_seq.json   which pattern the TRNG picked, per frame  (make capture)
```

Each `.bin` is a 4 byte header (width, height as little endian uint16) followed by
one byte per pixel holding the 6 bit colour the tile drove on its pins, packed as
`r<<4 | g<<2 | b`.
