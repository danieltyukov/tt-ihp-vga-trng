#!/usr/bin/env bash
# Run the cocotb regression against the hardened gate level netlist, locally,
# with the same simulator the Tiny Tapeout gl_test job uses.
#
# Why a script instead of just `make -B GATES=yes`
# ------------------------------------------------
# Two things have to be true before a gate level run of this netlist works, and
# neither is true of a stock apt install:
#
#  1. The simulator has to drive the delayed_* signals that the IHP cell models
#     take from their $setuphold and $recrem timing checks. sg13g2_dfrbpq_1 clocks
#     ihp_dff_r from delayed_CLK, not from CLK. Stock Icarus 12 prints
#     "Timing checks are not supported and delayed signal delayed_CLK will not be
#     driven" and then every flop in the design holds x forever, so the netlist
#     elaborates and simulates and reports nothing. Tiny Tapeout ship a patched
#     Icarus 13 that drives them, and their gl_test job installs it. This script
#     fetches the same .deb and unpacks it under build/ rather than installing it,
#     so the system iverilog is left alone.
#
#  2. The ring oscillators have to be cut, or time stops. See test/tb.v.
#
# Usage:
#   ./scripts/run_gl.sh [path/to/netlist.v]
#
# With no argument it uses the newest netlist from a local `make harden` run.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

IVL_VERSION="13.0-1"
IVL_URL="https://github.com/TinyTapeout/iverilog/releases/download/v13.0/iverilog_${IVL_VERSION}_amd64.deb"
IVL_DIR="$ROOT/build/iverilog-tt"

NETLIST="${1:-}"
if [ -z "$NETLIST" ]; then
  NETLIST=$(ls -t runs/*/final/nl/*.nl.v 2>/dev/null | head -1 || true)
fi
if [ -z "$NETLIST" ] || [ ! -f "$NETLIST" ]; then
  echo "No gate level netlist. Run ./scripts/harden.sh first, or pass one:" >&2
  echo "  ./scripts/run_gl.sh path/to/tt_um_danieltyukov_vga_trng.nl.v" >&2
  exit 1
fi

: "${PDK_ROOT:=$HOME/.local/share/pdk/IHP-Open-PDK}"
export PDK_ROOT
if [ ! -d "$PDK_ROOT/ihp-sg13g2/libs.ref/sg13g2_stdcell/verilog" ]; then
  echo "PDK_ROOT=$PDK_ROOT has no ihp-sg13g2 cell models" >&2
  exit 1
fi

# ---- Tiny Tapeout's Icarus, unpacked but not installed ---------------------
if [ ! -x "$IVL_DIR/usr/bin/iverilog" ]; then
  mkdir -p build
  if [ ! -f "build/iverilog-tt.deb" ]; then
    echo "== fetching Tiny Tapeout Icarus $IVL_VERSION =="
    curl -fsSL "$IVL_URL" -o "build/iverilog-tt.deb.part"
    mv "build/iverilog-tt.deb.part" "build/iverilog-tt.deb"
  fi
  rm -rf "$IVL_DIR"
  mkdir -p "$IVL_DIR"
  dpkg -x "build/iverilog-tt.deb" "$IVL_DIR"
fi

# -B is not optional. Without it the unpacked driver picks up /usr/lib/ivl, which
# belongs to whatever Icarus apt installed, and the two do not mix.
mkdir -p "$IVL_DIR/bin"
cat > "$IVL_DIR/bin/iverilog" <<EOF
#!/bin/sh
exec "$IVL_DIR/usr/bin/iverilog" -B "$IVL_DIR/usr/lib/ivl" "\$@"
EOF
cat > "$IVL_DIR/bin/vvp" <<EOF
#!/bin/sh
exec "$IVL_DIR/usr/bin/vvp" -M "$IVL_DIR/usr/lib/ivl" "\$@"
EOF
chmod +x "$IVL_DIR/bin/iverilog" "$IVL_DIR/bin/vvp"
"$IVL_DIR/bin/iverilog" -V | head -1

# ---- run ------------------------------------------------------------------
echo "== netlist: $NETLIST =="
cp "$NETLIST" test/gate_level_netlist.v

VENV_BIN="$ROOT/.venv/bin"
export PATH="$IVL_DIR/bin:$VENV_BIN:$PATH"

cd test
rm -f results.xml tb.fst tb.vcd
GATES=yes make -B
test -f results.xml
if grep -q "<failure" results.xml; then
  echo "GATE LEVEL TEST FAILURES in test/results.xml" >&2
  exit 1
fi
grep -o '<testcase [^>]*' results.xml | sed -n 's/.*name="\([^"]*\)".*/  pass  \1/p'
echo "gate level regression: $(grep -c '<testcase' results.xml) tests, all passed"
