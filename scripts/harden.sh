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

# KLayout DRC and XOR are single threaded unless told otherwise, and the maximal
# sg13g2 DRC runset can take longer than every other stage combined. Compute a
# default from the machine rather than hardcoding one, leaving two cores for
# everything else. KLAYOUT_THREADS overrides it, which is what to use when
# several place and route runs share a machine: oversubscribing cores across
# concurrent runs is slower than running single threaded.
NCPU="$(nproc 2>/dev/null || echo 4)"
DEFAULT_THREADS=$(( NCPU > 3 ? NCPU - 2 : 1 ))
THREADS="${KLAYOUT_THREADS:-$DEFAULT_THREADS}"

if [ "${HARDEN_SKIP_FLOW:-0}" != "1" ]; then
  echo "== librelane, tag $TAG, KLayout threads $THREADS of $NCPU cores =="
  mkdir -p build
  # Merge the computed thread counts over the committed config. The committed file
  # has to carry fixed numbers because it is JSON, so the computed values are
  # applied here instead of being baked in.
  python3 - "$THREADS" > build/harden_config.json <<'PYEOF'
import json, sys, re, pathlib
raw = pathlib.Path("hardening/config.json").read_text()
# strip the "//" comment keys, which are legal for LibreLane but not for json.load
# when duplicated, so load with a hook that keeps the last of each key
cfg = json.loads(raw, object_pairs_hook=lambda pairs: {k: v for k, v in pairs})
n = int(sys.argv[1])
cfg["KLAYOUT_DRC_THREADS"] = n
cfg["KLAYOUT_XOR_THREADS"] = n
cfg.pop("//", None)
json.dump(cfg, sys.stdout, indent=2)
PYEOF
  # --design-dir is the repo root because LibreLane refuses to read files outside
  # the design directory, and dir::../src would escape it. The generated config
  # lives in build/, so dir:: still resolves from the repo root.
  librelane --design-dir . --run-tag "$TAG" build/harden_config.json
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

echo "== layout renders =="
# Two views on purpose. A full die view of a routed tile is close to unreadable
# on its own, because every metal layer overlaps at that scale, so the full die
# carries the outline, the pin frame and the power straps, and a 12 x 12 um box
# near the centre carries the cell rows, contacts and routing.
GDS="$RUN/final/gds/$TOP.gds"
klayout -b -rm scripts/render_gds.py -rd gds="$GDS" \
  -rd out=docs/img/layout.png -rd w=880 -rd h=1140
klayout -b -rm scripts/render_gds.py -rd gds="$GDS" \
  -rd out=docs/img/layout_detail.png -rd w=900 -rd h=900 -rd box=76,104,88,116
# Recompress: KLayout writes uncompressed RGB, and the full die view lands over
# Tiny Tapeout's 512 kB per image docs limit otherwise.
python3 - <<'PYEOF'
import pathlib
try:
    from PIL import Image
except ImportError:
    raise SystemExit("pillow not available, skipping recompression")
for n in ("layout.png", "layout_detail.png"):
    p = pathlib.Path("docs/img") / n
    Image.open(p).convert("RGB").save(p, optimize=True)
    print(f"  {n}: {p.stat().st_size // 1024} kB")
PYEOF

echo
echo "wrote docs/hardening/{metrics.json,summary.json,signoff.txt}"
echo "wrote docs/img/{layout.png,layout_detail.png}"
