#!/usr/bin/env bash
# SymbiYosys formal verification of the two blocks where a proof is worth more
# than a test: the von Neumann debiaser and the sync generator.
#
# Why these two:
#   - The debiaser's whole reason to exist is a symmetry argument (01 emits 0,
#     10 emits 1, equal pairs discarded). Checking it against two streams shows
#     it works twice. Proving the symmetry shows it works always, which is what
#     the unbiasedness claim in the README actually rests on.
#   - A sync counter that only misbehaves from a state one captured frame never
#     visits is exactly the bug a single golden frame cannot catch, and on a VGA
#     output it means a monitor that loses lock.
#
# Also runs a mutation check, because a proof that passes on a broken design is
# worthless: two specific bugs are injected and the proof has to fail on each.
#
# Writes docs/formal/summary.txt.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/formal"

MUTATE="${FORMAL_MUTATE:-1}"

run() {
  local sby="$1"
  local base="${sby%.sby}"
  say "== $sby =="
  # Trailing slash so the glob can only match directories. Without it,
  # "rm -rf von_neumann_*" matches von_neumann_fv.v and deletes the harness,
  # which is exactly what happened once while writing this.
  rm -rf "$base"_*/ "$base"/
  sby -f "$sby" 2>&1 | grep -E "summary: engine|DONE|Unreached|Assert failed" | tee -a "$LOG"
  # sby exits non zero on failure, and the pipe hides that, so check explicitly
  if grep -q "DONE (FAIL\|DONE (ERROR" "$LOG"; then
    say "   a task failed, see formal/${sby%.sby}_*/logfile.txt"
    exit 1
  fi
}

mkdir -p "$ROOT/docs/formal"
LOG="$ROOT/docs/formal/summary.txt"
{
  echo "SymbiYosys formal verification"
  echo "solver: $(z3 --version 2>/dev/null | head -1)"
  echo
} > "$LOG"

# Everything from here is both printed and appended to the summary. A plain
# function is used rather than exec with a process substitution, because that
# swallows output when the script is itself in a pipeline.
say() { echo "$@" | tee -a "$LOG"; }

run von_neumann.sby
run vga_sync.sby

if [ "$MUTATE" = "1" ]; then
  say ""
  say "== mutation check: the proofs must fail on a broken design =="
  cp "$ROOT/src/vga_sync.v" /tmp/vga_sync.orig.$$
  cp "$ROOT/src/von_neumann.v" /tmp/von_neumann.orig.$$
  restore() {
    cp /tmp/vga_sync.orig.$$ "$ROOT/src/vga_sync.v"
    cp /tmp/von_neumann.orig.$$ "$ROOT/src/von_neumann.v"
    rm -f /tmp/vga_sync.orig.$$ /tmp/von_neumann.orig.$$
  }
  trap restore EXIT

  say "-- mutation 1: line_end fires one pixel early"
  sed -i "s/H_TOTAL\[9:0\] - 10'd1);/H_TOTAL[9:0] - 10'd2);/" "$ROOT/src/vga_sync.v"
  rm -rf vga_sync_step/
  if sby -f vga_sync.sby step > /dev/null 2>&1; then
    say "   FAIL: the proof passed on a design with a broken line wrap"
    exit 1
  fi
  say "   caught, as required"
  cp /tmp/vga_sync.orig.$$ "$ROOT/src/vga_sync.v"

  say "-- mutation 2: the debiaser emits the second bit of the pair"
  sed -i "s/out_bit <= first_bit;/out_bit <= in_bit;/" "$ROOT/src/von_neumann.v"
  rm -rf von_neumann_bmc/
  if sby -f von_neumann.sby bmc > /dev/null 2>&1; then
    say "   FAIL: the proof passed on a debiaser with the wrong convention"
    exit 1
  fi
  say "   caught, as required"

  restore
  trap - EXIT
  say "sources restored"
fi

say ""
say "formal: all tasks passed and both mutations were caught"
