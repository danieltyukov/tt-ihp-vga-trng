#!/usr/bin/env bash
# Synthesise, place, route and pack this tile for an ICE40UP5K with the open
# source flow: yosys, nextpnr-ice40, icepack, icetime.
#
# What this validates: the RTL is implementable on the device Tiny Tapeout's FPGA
# emulator uses, it fits, and it meets the 25.175 MHz pixel clock there. It builds
# with -DSYNTH, so the entropy path is the same one the `fpga` workflow builds. It
# is still not a substitute for that workflow: this uses its own board wrapper and
# no PCF, while the workflow builds Tiny Tapeout's tt_fpga_top against their
# FabricFox pin assignment. Both are green, see README.
#
# No PCF is given, so nextpnr picks the I/O sites itself. Inventing pin numbers
# for a board nobody has would be worse than not constraining them, and the
# question here is fit and timing, not a specific board.
#
# Writes docs/fpga/{synth.txt,pnr.txt,timing.txt,summary.json}.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DEV="${FPGA_DEV:-up5k}"
PKG="${FPGA_PKG:-sg48}"
FREQ=25.175
TOP=fpga_top

mkdir -p build/fpga docs/fpga

echo "== yosys, synth_ice40 =="
# -DSYNTH is what tt_fpga.py passes, and it is what selects the no-ring entropy
# path in src/entropy_source.v. Passing it here too is the point: without it this
# script would validate a different netlist from the one the fpga workflow builds.
yosys -DSYNTH -p "
  read_verilog src/*.v fpga/fpga_top.v
  synth_ice40 -top $TOP -json build/fpga/$TOP.json
" 2>&1 | grep -viE "sdfrbp|unsupported expression" > build/fpga/synth.log

sed -n '/=== fpga_top ===/,/^$/p' build/fpga/synth.log | tail -30 > docs/fpga/synth.txt
grep -E "SB_LUT4|SB_CARRY|SB_DFF|Number of cells" docs/fpga/synth.txt || true

echo "== nextpnr-ice40, $DEV $PKG =="
nextpnr-ice40 --"$DEV" --package "$PKG" \
  --json "build/fpga/$TOP.json" \
  --asc "build/fpga/$TOP.asc" \
  --freq "$FREQ" \
  --seed 1 \
  > build/fpga/pnr.log 2>&1
grep -E "Info: Device utilisation|ICESTORM_LC|ICESTORM_RAM|SB_IO|SB_GB|PLL|Max frequency|Info: Max delay|critical path" build/fpga/pnr.log \
  | sed 's/^Info: //' > docs/fpga/pnr.txt
cat docs/fpga/pnr.txt

echo "== icepack =="
icepack "build/fpga/$TOP.asc" "build/fpga/$TOP.bin"
ls -l "build/fpga/$TOP.bin"

echo "== icetime =="
icetime -d "$DEV" -P "$PKG" -t -m "build/fpga/$TOP.asc" > docs/fpga/timing.txt 2>&1 || true
tail -5 docs/fpga/timing.txt

python3 scripts/parse_fpga.py "$DEV" "$PKG" "$FREQ"
echo
echo "wrote docs/fpga/{synth.txt,pnr.txt,timing.txt,summary.json}"
