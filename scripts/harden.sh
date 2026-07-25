#!/usr/bin/env bash
# Harden the tile to GDS locally with LibreLane 3.0.0.dev44 on the real IHP PDK,
# then extract the signoff numbers and render the layout.
#
# This is the same tool at the same version that TinyTapeout/tt-gds-action@ttihp26a
# pins with pdk: ihp-sg13g2, so it is the shuttle flow rather than an
# approximation of it. What it is NOT is a shuttle submission: Tiny Tapeout's
# precheck and their harness integration still need their infrastructure.
#
# Writes docs/hardening/:
#   metrics.json      the full LibreLane final metrics
#   summary.json      the subset quoted in the README, plus derived densities
#   signoff.txt       timing summary, DRC, LVS, antenna and manufacturability
#   ../img/layout.png the routed layout render
#
# The run directory itself (runs/) is gitignored: it is about 1 GB.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TAG="${HARDEN_TAG:-local}"
RUN="runs/$TAG"
TOP=tt_um_danieltyukov_vga_trng

if [ "${HARDEN_SKIP_FLOW:-0}" != "1" ]; then
  echo "== librelane, tag $TAG =="
  # --design-dir is the repo root because LibreLane refuses to read files outside
  # the design directory, and dir::../src would escape it.
  librelane --design-dir . --run-tag "$TAG" hardening/config.json
fi

if [ ! -f "$RUN/final/metrics.json" ]; then
  echo "no metrics at $RUN/final/metrics.json; the flow did not finish" >&2
  exit 1
fi

mkdir -p docs/hardening docs/img
cp "$RUN/final/metrics.json" docs/hardening/metrics.json

echo "== signoff summary =="
{
  echo "LibreLane hardening of $TOP"
  echo "tool    : $(librelane --version 2>/dev/null | head -1)"
  echo "pdk     : ihp-sg13g2"
  echo "config  : hardening/config.json"
  echo "sdc     : hardening/constraints.sdc (not the generic fallback)"
  echo
  echo "=== post route timing, all corners ==="
  cat "$RUN"/*-openroad-stapostpnr/summary.rpt 2>/dev/null || echo "(missing)"
  echo
  echo "=== design rule check types ==="
  grep -A6 -i "max fanout\|max slew\|max capacitance" \
    "$RUN"/*-openroad-stapostpnr/nom_slow_1p08V_125C/checks.rpt 2>/dev/null \
    | tail -40 || echo "(missing)"
  echo
  echo "=== manufacturability ==="
  cat "$RUN"/*-misc-reportmanufacturability/manufacturability.rpt 2>/dev/null || echo "(missing)"
} > docs/hardening/signoff.txt

python3 scripts/parse_harden.py "$RUN"

echo "== layout render =="
klayout -b -rm scripts/render_gds.py \
  -rd gds="$RUN/final/gds/$TOP.gds" \
  -rd out=docs/img/layout.png \
  -rd w=1400 -rd h=1000

echo
echo "wrote docs/hardening/{metrics.json,summary.json,signoff.txt} and docs/img/layout.png"
