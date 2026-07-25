# Contributing

Two kinds of contribution are useful here.

**Changes to this tile.** Bug fixes, a cheaper pattern, a tighter test, a
correction to a number that stopped being true. That is what the rest of this
file is about.

**Forking it as a template.** The design is a Tiny Tapeout tile with a full local
flow attached: cocotb regression, an independent reference model, Yosys area
reporting, OpenSTA across three corners, LibreLane hardening to a DRC and LVS
clean GDS, gate level simulation of that netlist, an iCE40 build and two
SymbiYosys proofs. If you want your own design in that harness, read
[docs/ADAPTING.md](docs/ADAPTING.md) instead. It covers adding a pattern,
changing the video timing, retuning the entropy pipeline, retargeting the tile
size and re-running the hardening flow.

## Ground rules

These are the ones that actually get a change rejected:

1. **Every number in the documentation comes from a run.** If your change moves a
   number, re-run the thing that produced it and commit the regenerated report.
   The reports live in `docs/synth/`, `docs/sta/`, `docs/hardening/`,
   `docs/fpga/` and `docs/formal/`, and they are committed on purpose so a reader
   can check the prose against the tool output.
2. **A claim needs a check that fails when the claim stops being true.** The
   pattern already used throughout: `scripts/synth_report.sh` fails the build if
   fewer than 12 ring oscillator stages survive mapping, `scripts/check_area.py`
   fails if `tiles:` in `info.yaml` stops agreeing with the measured die, and
   `scripts/parse_sta.py` fails if setup stops closing at the signoff corner. Add
   the check in the same commit as the claim.
3. **Nothing here has been fabricated.** The tile hardens to a clean GDS locally
   and in CI. It has not been submitted to a shuttle and no silicon exists. Do
   not write anything that reads as though it has.
4. **The ring oscillator is not a simulated entropy source.** Statistics gathered
   through a delay annotated inverter loop in an event simulator describe the
   simulator. Every statistical figure in this repository was produced with a
   Python pseudorandom stream driven into `ENT_IN`, and says so where it is
   quoted. Keep that distinction in anything you add.

## Setting up

Everything runs out of a repo local virtualenv, so no shell activation is needed
and nothing is installed system wide.

```sh
sudo apt-get install -y iverilog verilator yosys python3-venv
make venv
make check          # lint + ring + formal + test + synth
```

`make check` is the gate. If it passes on a clean checkout, your environment is
good enough for everything except the physical flow.

| what you want to run | additionally needs |
| --- | --- |
| `make test`, `make lint`, `make ring`, `make capture` | Icarus 12+, Verilator, the venv |
| `make synth` | Yosys 0.33+. Fetches one Liberty file into `build/` if no PDK is installed, so it needs the network once |
| `make sta` | `openroad` (OpenSTA 3.1.0) and an installed `ihp-sg13g2` PDK |
| `make harden` | `librelane` 3.0.0.dev44, `klayout`, `magic`, `netgen`, the PDK |
| `make gl` | the PDK cell models. Downloads Tiny Tapeout's patched Icarus 13 into `build/` itself |
| `make fpga` | `yosys`, `nextpnr-ice40`, `fpga-icestorm` |
| `make formal` | `sby` (SymbiYosys) and `z3` |

The PDK defaults to `/home/danieltyukov/.local/share/pdk/IHP-Open-PDK/ihp-sg13g2`
and is overridden with `PDK_ROOT_IHP` (`make sta`, `make synth`) or `PDK_ROOT`
(`make gl`, which wants the parent directory). Tested with Icarus 12.0 and Tiny
Tapeout's Icarus 13.0 for gate level, Verilator 5.020, Yosys 0.33, cocotb 2.0.1,
LibreLane 3.0.0.dev44, OpenSTA 3.1.0 and z3 4.8.12.

## The targets

| target | what it does | roughly |
| --- | --- | --- |
| `make test` | the cocotb regression, 11 tests | 8 min |
| `make lint` | `verilator --lint-only -Wall`, zero warnings expected | seconds |
| `make ring` | plain Icarus structural testbench for the oscillator path | seconds |
| `make formal` | two SymbiYosys proofs plus a mutation check | 1 min |
| `make synth` | Yosys area report against the real IHP Liberty | 2 min |
| `make check` | all five of the above | 12 min |
| `make capture` | 64 further model verified frames for the animations | 17 min |
| `make images` | regenerate every PNG and GIF in `docs/img` | 1 min |
| `make sta` | OpenSTA at three corners, per corner remapped netlists | 3 min |
| `make harden` | LibreLane to GDS, signoff extract, layout renders | 25 min |
| `make gl` | the regression again on the hardened netlist | 15 min |
| `make fpga` | Yosys, nextpnr-ice40, icepack, icetime for an ICE40UP5K | 1 min |
| `make ring-freq` | ring frequency from the Liberty delay tables | seconds |

## Running the tests

`make test` cleans first, so it always runs from scratch. It fails the build on
any `<failure` in `test/results.xml` rather than trusting the make exit code,
because cocotb returns success even when a test fails.

To iterate on one test, work in `test/` with the venv on `PATH`:

```sh
source .venv/bin/activate
cd test
COCOTB_TEST_FILTER=test_health_apt make -B
```

`COCOTB_TEST_FILTER` takes a regex, so `test_health_.*` runs the three health
tests. The four longest tests are `test_golden_frames`, `test_vga_timing`,
`test_lfsr_period` and `test_trng_statistics`; the rest finish in seconds.

By default only the tile pins are dumped, because a full hierarchy dump of a
230 ms simulation is tens of megabytes and costs about 20% of the runtime. For
internals:

```sh
cd test/sim_build/rtl && vvp sim.vvp -fst +dump_all
gtkwave ../../tb.fst
```

**Every RTL change needs the matching change in `test/model.py`.** The model is
an independent implementation written from the design intent, and
`test_golden_frames` compares 2 457 600 pixels against it. If you change the RTL
and the model together in a way that makes them agree on the same wrong answer,
the golden frames stop meaning anything, so change the model from the intent
rather than by copying the Verilog.

Tests assert. There is no `cocotb.pass_test()` in this repository and no test
whose body is unreachable. Do not add one.

## Synthesis, timing and hardening

`make synth` writes `docs/synth/` and fails on a blackbox, an inferred latch, or
a lost ring oscillator stage. CI then runs `scripts/check_area.py`, which
compares the fresh report against the committed one within 2% and re-derives the
tile count from both the synthesis estimate and the hardened die. Commit the
regenerated `docs/synth/` with any RTL change.

`make sta` proves that the `clock_hz` in `info.yaml` closes, on netlists remapped
per corner because `dfflibmap` and `abc` pick cells from whichever Liberty they
are handed. `scripts/parse_sta.py` fails the run if setup does not close at the
signoff corner.

`make harden` is the one that takes real time. It runs the same LibreLane version
`TinyTapeout/tt-gds-action@ttihp26a` pins, writes `docs/hardening/` and both
layout renders, and takes these environment overrides:

```sh
HARDEN_TAG=experiment   # run directory under runs/, default "local"
HARDEN_DIE="202.08 313.74"   # override DIE_AREA, how the 1x2 comparison was run
HARDEN_DENSITY=80       # override PL_TARGET_DENSITY_PCT
HARDEN_SKIP_REPORT=1    # run the flow but do not overwrite the committed reports
HARDEN_SKIP_FLOW=1      # re-extract reports from an existing run directory
KLAYOUT_THREADS=4       # default is nproc-2, lower it if you share the machine
```

Use `HARDEN_SKIP_REPORT=1` for any experiment. Without it an exploratory run
overwrites the committed signoff numbers and the layout renders with results from
a floorplan the README does not describe.

`runs/` is gitignored and each run is about 1 GB. Only the extracted reports are
committed.

## Regenerating the figures

No image in `docs/img` is drawn by hand and none is a mockup. The pattern PNGs
and the two GIFs are frames captured off `uo_out` in simulation and checked pixel
by pixel against the model before being written; the plots are drawn from the
JSON the same runs produce. So the order matters:

```sh
make test      # writes test/output/frames/, stats.json, debias.json, timing.json
make capture   # writes test/output/anim/ and test/output/switch/
make images    # reads all of the above plus docs/synth/area.json
               # and docs/hardening/summary.json
```

`make images` fails with a message naming the missing input rather than silently
skipping a figure. `test/output/` is gitignored, so a fresh clone has to run the
simulations before it can regenerate an image. The two layout renders come from
`make harden` instead, through `scripts/render_gds.py`.

If you add a figure, add it to `scripts/make_images.py` and derive it from
committed data or from simulation output. Do not commit a PNG that no script can
reproduce.

## Adding a source file

Five lists have to stay in sync, and nothing checks four of them for you:

| file | why |
| --- | --- |
| `info.yaml` `source_files` | what Tiny Tapeout hands the hardening flow |
| `test/Makefile` `PROJECT_SOURCES` | what the RTL simulation compiles |
| `hardening/config.json` `VERILOG_FILES` | what the local LibreLane run reads |
| `scripts/synth_report.sh` `MODULES` | per module area, if it is worth reporting |
| `README.md` repository layout | so the file list stays honest |

Missing the first one produces a hardening run against RTL that does not contain
your module; missing the second produces a regression that does not test it.

## What CI runs

| workflow | jobs | trigger |
| --- | --- | --- |
| `test.yaml` | lint, ring, cocotb, synth | push and pull request |
| `gds.yaml` | gds, precheck, gl_test, viewer | push |
| `fpga.yaml` | ice40 bitstream | push |
| `docs.yaml` | datasheet render | push |

All of them run on plain `ubuntu-24.04` with no secrets and no Tiny Tapeout API
access. Note the trigger column: **a pull request only runs `test.yaml`**. The
physical flow will not have been exercised on your branch, so if you touched RTL,
`src/config.json` or `info.yaml`, either run `make harden` locally or push the
branch to your own fork, where `gds.yaml` will run on the push and take about 25
minutes.

`gds.yaml` runs `gl_test`, which re-runs the whole cocotb regression against the
post place and route netlist. Two things about that job are specific to this
design and are documented at the top of the workflow file: stock Icarus leaves
every IHP flop at `x` forever because it does not drive the `delayed_*` signals
the cell models clock from, and the ring oscillators have to be forced or a zero
delay combinational loop stops the simulator's timewheel.

## Pull requests

- One topic per pull request. A pattern change and a hardening config change are
  two pull requests.
- Conventional Commit prefixes: `feat:`, `fix:`, `docs:`, `test:`, `chore:`,
  `refactor:`. The message describes the change and nothing else. No attribution
  trailers, no generated-by notices, no session links.
- Say what you ran. Paste the relevant lines of the tool output for any number
  you changed. "Re-ran `make synth`" without the numbers is not enough, because
  the point of the committed reports is that they can be checked.
- If you cannot run part of the flow (no PDK, no LibreLane), say so in the pull
  request rather than leaving the reports stale. Someone else can run it.

Before opening one:

```sh
make check       # lint, ring, formal, test, synth
git status       # docs/synth/ regenerated and committed if the RTL moved
```

## Style

Prose: plain and direct. No emoji anywhere, including headings and tables. No
marketing tone. State what was measured and how.

Verilog: `` `default_nettype none `` at the top of every file, one module per
file, snake_case, a header comment that explains why the module is the way it is
rather than restating what the code does. Zero `verilator --lint-only -Wall`
warnings, including unused signal warnings, which the existing files silence with
an explicit `wire _unused = &{...}` rather than by disabling the check. No
inferred latches: `make synth` fails on one.

Python: the standard library plus what is already in `test/requirements.txt`.
A new dependency needs a reason in the pull request.
