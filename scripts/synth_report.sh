#!/usr/bin/env bash
# Yosys area report against the real IHP sg13g2 standard cell library.
#
# Writes docs/synth/:
#   total.txt        flattened whole-tile stat, this is the number that decides
#                    the tile count
#   modules.txt      per submodule stat, one synth run per module
#   area.json        machine readable summary, consumed by scripts/make_images.py
#   check.txt        hierarchy check: no blackboxes, no inferred latches
#
# The liberty file is not vendored (1.7 MB of PDK). It is fetched once into
# build/ and cached there; build/ is gitignored.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

LIB_DIR="$ROOT/build"
LIB="$LIB_DIR/sg13g2_stdcell_typ_1p20V_25C.lib"
LIB_URL="https://raw.githubusercontent.com/IHP-GmbH/IHP-Open-PDK/main/ihp-sg13g2/libs.ref/sg13g2_stdcell/lib/sg13g2_stdcell_typ_1p20V_25C.lib"

mkdir -p "$LIB_DIR" docs/synth

if [ ! -f "$LIB" ]; then
  echo "fetching IHP sg13g2 liberty into build/ (one time, needs network)"
  curl -sSL -o "$LIB" "$LIB_URL"
fi

TOP=tt_um_danieltyukov_vga_trng
SRC=(src/*.v)

# Submodules to report individually. Order is bottom up so the bar chart reads
# as a cost breakdown.
MODULES=(
  vga_sync
  pat_xor pat_bars pat_sierp pat_ripple sine_q pat_plasma
  pat_ball pat_stars pat_rule30
  pattern_mux
  ring_inv ring_gate ring_osc entropy_source von_neumann lfsr_whitener health_monitor trng
)

echo "== flattened top level =="
yosys -q -p "
read_verilog ${SRC[*]}
hierarchy -top $TOP
synth -top $TOP -flatten
dfflibmap -liberty $LIB
abc -liberty $LIB
opt_clean -purge
tee -o docs/synth/total.txt stat -liberty $LIB
" 2>&1 | grep -viE '^(Warning|  *\$)' || true

echo "== hierarchy, blackbox, loop and latch check =="
yosys -p "
read_verilog ${SRC[*]}
hierarchy -top $TOP -check
proc
opt
flatten
opt
check
" > docs/synth/check.raw 2>&1

# Count inside the "design hierarchy" block only. Yosys repeats the instance
# list further down, and counting both copies doubles every figure.
count_stage() {
  awk -v pat="$1" '
    /^=== design hierarchy ===/ { h = 1 }
    /Number of wires/           { h = 0 }
    h && $0 ~ pat               { s += $2 }
    END                         { print s + 0 }
  ' docs/synth/total.txt
}
INV_COUNT=$(count_stage 'ring_inv')
GATE_COUNT=$(count_stage 'ring_gate')

{
  echo "hierarchy -top $TOP -check"
  if grep -qE 'is not part of the design|referenced in module|blackbox' docs/synth/check.raw; then
    grep -E 'is not part of the design|referenced in module|blackbox' docs/synth/check.raw
    echo "  FAIL: undefined module or blackbox reference"
    exit 1
  fi
  echo "  passed: every instantiated module is defined, no blackboxes."
  echo
  echo "check pass (run after flatten):"
  grep -E 'Found and reported' docs/synth/check.raw | sed 's/^/  /'
  echo "  Note on the ring oscillators. They are genuine combinational cycles,"
  echo "  but each stage is its own (* keep_hierarchy *) module, so no single"
  echo "  module contains a cycle and neither 'check' nor 'abc' reports a loop."
  echo "  The cycle exists only across module boundaries. Static timing in the"
  echo "  physical flow works on the fully flattened netlist and will report it,"
  echo "  which is expected: the ring is not on the clock tree and its only"
  echo "  consumer is the synchroniser in entropy_source.v."
  echo
  echo "ring oscillator stage survival (5 stage + 7 stage = 12 cells expected):"
  echo "  ring_inv instances:  $INV_COUNT"
  echo "  ring_gate instances: $GATE_COUNT"
  if [ "$((INV_COUNT + GATE_COUNT))" -ne 12 ]; then
    echo "  FAIL: expected 12 surviving ring stages, got $((INV_COUNT + GATE_COUNT))."
    echo "  Without the keep attributes the mapper collapses the chains and both"
    echo "  oscillators end up identical, which makes their XOR a constant."
    exit 1
  fi
  echo "  passed: all 12 stages survived mapping."
  echo
  echo "inferred latch check (any \$_DLATCH_ / latch cell below is a bug):"
  if grep -qiE '_dlatch_|dlatch|_latch|sg13g2_[a-z0-9_]*latch' docs/synth/total.txt; then
    grep -iE '_dlatch_|dlatch|_latch|sg13g2_[a-z0-9_]*latch' docs/synth/total.txt
    echo "  FAIL: latch cells present"
    exit 1
  fi
  echo "  none: all $(awk '/sg13g2_dfrbpq_1/ {print $2; exit}' docs/synth/total.txt) sequential cells are sg13g2_dfrbpq_1 edge triggered flops"
} > docs/synth/check.txt
cat docs/synth/check.txt

: > docs/synth/modules.txt
for m in "${MODULES[@]}"; do
  echo "== $m =="
  yosys -q -p "
    read_verilog ${SRC[*]}
    hierarchy -top $m
    synth -top $m -flatten
    dfflibmap -liberty $LIB
    abc -liberty $LIB
    opt_clean -purge
    tee -q -o docs/synth/.mod.txt stat -liberty $LIB
  " > /dev/null 2>&1
  {
    echo "===== $m"
    cat docs/synth/.mod.txt
  } >> docs/synth/modules.txt
done
rm -f docs/synth/.mod.txt

python3 scripts/parse_synth.py

echo
echo "wrote docs/synth/{total.txt,modules.txt,area.json,check.txt}"
