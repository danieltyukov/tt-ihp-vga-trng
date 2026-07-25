#!/usr/bin/env bash
# Static timing analysis of the tile against the real IHP sg13g2 corners.
#
# Answers one question with evidence: does the 25.175 MHz pixel clock declared in
# info.yaml actually close, at the corner that matters for a shuttle
# (slow, 1.08 V, 125 C)?
#
# Writes docs/sta/:
#   <corner>_39.72ns.txt   full report_checks output per corner
#   summary.json           worst slack and Fmax per corner, for the README
#
# Synthesis is redone per corner because dfflibmap and abc pick cells from the
# liberty they are given, so a slow-corner timing report has to be run on a
# slow-corner mapped netlist.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PDK="${PDK_ROOT_IHP:-/home/danieltyukov/.local/share/pdk/IHP-Open-PDK/ihp-sg13g2}"
LIBDIR="$PDK/libs.ref/sg13g2_stdcell/lib"
TOP=tt_um_danieltyukov_vga_trng

# 1 / 25175000 = 39.7220 ns
PERIOD="${STA_PERIOD:-39.7220}"

if [ ! -d "$LIBDIR" ]; then
  echo "IHP PDK not found at $PDK" >&2
  echo "set PDK_ROOT_IHP to the ihp-sg13g2 directory" >&2
  exit 1
fi

mkdir -p build/sta docs/sta

# corner name -> liberty file
CORNERS=(
  "slow_1p08V_125C"
  "typ_1p20V_25C"
  "fast_1p65V_m40C"
)

for corner in "${CORNERS[@]}"; do
  lib="$LIBDIR/sg13g2_stdcell_${corner}.lib"
  nl="build/sta/netlist_${corner}.v"

  echo "== synthesising against $corner =="
  # The scan flop warnings are noise: yosys skips sg13g2_sdfrbpq_* because it
  # cannot parse their scan mux expression, which is fine, this design has no
  # scan chain.
  yosys -q -p "
    read_verilog src/*.v
    synth -top $TOP
    dfflibmap -liberty $lib
    abc -liberty $lib
    write_verilog -noattr $nl
  " 2>&1 | grep -viE "unsupported expression|sg13g2_sdfrbp" || true

  echo "== STA at ${PERIOD} ns, $corner =="
  wrapper="build/sta/run_${corner}.tcl"
  {
    echo "set pdk     \"$PDK\""
    echo "set lib     \"$lib\""
    echo "set netlist \"$nl\""
    echo "set period  $PERIOD"
    echo "source scripts/sta.tcl"
  } > "$wrapper"

  # report_checks writes to stdout, so the report file is built by redirecting
  # rather than by capturing inside Tcl. Any combinational loop warning here
  # would come from the ring oscillators, which is expected: OpenSTA breaks the
  # loop and the register to register paths are unaffected. The count is recorded
  # in the summary so the report can state it plainly.
  openroad -no_init -exit "$wrapper" 2>&1 \
    | grep -viE "unsupported expression|sg13g2_sdfrbp" \
    > "build/sta/stdout_${corner}.txt" || true
  cp "build/sta/stdout_${corner}.txt" "docs/sta/${corner}_${PERIOD}ns.txt"
  grep -E "^(PERIOD|WORST_SETUP|WORST_HOLD|FMAX_MHZ|TNS_MAX) " \
    "build/sta/stdout_${corner}.txt" || true
done

python3 scripts/parse_sta.py "$PERIOD" "${CORNERS[@]}"
echo
echo "wrote docs/sta/{summary.json,<corner>_${PERIOD}ns.txt}"
