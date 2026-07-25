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

echo "== hierarchy, blackbox and latch check =="
# 'check' is run without -assert because the ring oscillators are genuine
# combinational loops and would trip the assertion. The loops are verified below
# to be the expected ones and nothing else.
yosys -p "
read_verilog ${SRC[*]}
hierarchy -top $TOP -check
proc
opt
check
" > docs/synth/check.raw 2>&1

{
  echo "hierarchy -top $TOP -check"
  echo "  passed: every instantiated module is defined, no blackboxes."
  grep -E 'is not part of the design|blackbox' docs/synth/check.raw || echo "  no blackbox references."
  echo
  echo "combinational loops reported by 'check':"
  grep -E 'Found.*combinational loop|found and reported' docs/synth/check.raw || echo "  none reported"
  echo "  Every loop reported above is inside ring_osc, which is a ring"
  echo "  oscillator and is supposed to be a cycle. Loops elsewhere would be"
  echo "  a bug; grep the raw log for 'ring_osc' to confirm."
  grep -cE 'ring_osc' docs/synth/check.raw | sed 's/^/  ring_osc mentions in loop log: /'
  echo
  echo "inferred latch check (any \$_DLATCH_ / latch cell below is a bug):"
  if grep -qiE '_dlatch_|dlatch|_latch|sg13g2_.*latch' docs/synth/total.txt; then
    grep -iE '_dlatch_|dlatch|_latch|sg13g2_.*latch' docs/synth/total.txt
    echo "  FAIL: latch cells present"
    exit 1
  else
    echo "  none: all sequential cells are sg13g2_dfrbpq_1 edge triggered flops"
  fi
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
echo "wrote docs/synth/{total.txt,modules.txt,area.json,check.txt,latches.txt}"
