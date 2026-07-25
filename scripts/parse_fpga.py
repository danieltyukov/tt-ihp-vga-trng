#!/usr/bin/env python3
"""Collect the iCE40 flow results into docs/fpga/summary.json.

Called by scripts/run_fpga.sh. Fails if the design does not meet the pixel clock
on the FPGA, because a bitstream that misses 25.175 MHz will not drive a monitor.
"""

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUILD = ROOT / "build" / "fpga"
DOCS = ROOT / "docs" / "fpga"


def main():
    dev, pkg, target = sys.argv[1], sys.argv[2], float(sys.argv[3])
    pnr = (BUILD / "pnr.log").read_text()
    synth = (DOCS / "synth.txt").read_text()

    util = {}
    for m in re.finditer(r"^Info:\s+(\S+):\s+(\d+)/\s*(\d+)\s+(\d+)%", pnr, re.M):
        util[m.group(1)] = {
            "used": int(m.group(2)),
            "available": int(m.group(3)),
            "percent": int(m.group(4)),
        }

    # nextpnr prints one estimate per clock, last one wins after routing
    fmax = None
    for m in re.finditer(r"Max frequency for clock\s+'([^']+)':\s+([0-9.]+)\s+MHz", pnr):
        fmax = float(m.group(2))

    # nextpnr also reports the unconstrained clock to pad path. It is not what
    # decides whether the design runs, but quoting only the register to register
    # figure would be selective.
    clk_to_pad = None
    for m in re.finditer(
        r"Max delay posedge \S+\s+-> <async>\s+:\s+([0-9.]+) ns", pnr
    ):
        clk_to_pad = float(m.group(1))

    icetime = (DOCS / "timing.txt").read_text() if (DOCS / "timing.txt").exists() else ""
    m = re.search(r"Total path delay:\s+([0-9.]+) ns", icetime)
    icetime_path_ns = float(m.group(1)) if m else None

    cells = {}
    for m in re.finditer(r"^\s+(SB_\S+)\s+(\d+)\s*$", synth, re.M):
        cells[m.group(1)] = int(m.group(2))

    summary = {
        "device": dev,
        "package": pkg,
        "target_mhz": target,
        "achieved_mhz": fmax,
        "margin": round(fmax / target, 3) if fmax else None,
        "clk_to_pad_ns": clk_to_pad,
        "pixel_period_ns": round(1000.0 / target, 4),
        "icetime_longest_path_ns": icetime_path_ns,
        "utilisation": util,
        "synth_cells": cells,
        "bitstream_bytes": (BUILD / "fpga_top.bin").stat().st_size
        if (BUILD / "fpga_top.bin").exists()
        else None,
        "note": (
            "Validates that the RTL is implementable on the device Tiny Tapeout's "
            "FPGA emulator uses, fits it, and meets the pixel clock. Does NOT "
            "validate the fpga GitHub workflow, which needs Tiny Tapeout's "
            "container and board harness. Built through fpga/fpga_top.v with "
            "SIM_ENTROPY=1, because the ring oscillators are combinational loops "
            "that synth_ice40 will not build, and because an FPGA cannot host a "
            "usable ring oscillator TRNG anyway. achieved_mhz is the register to "
            "register frequency, which is what decides whether the design runs. "
            "clk_to_pad_ns is the unconstrained clock to output pad delay, which "
            "exceeds one pixel period here; on a real board that path needs pin "
            "constraints and probably an output register stage."
        ),
    }
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    print()
    for k, v in sorted(util.items()):
        print(f"{k:18s} {v['used']:6d} / {v['available']:6d}  {v['percent']:3d}%")
    if fmax is None:
        raise SystemExit("nextpnr did not report a max frequency")
    print(f"\nregister to register: {fmax:.2f} MHz against a {target} MHz target, "
          f"{fmax / target:.2f}x")
    if clk_to_pad:
        period = 1000.0 / target
        print(
            f"clock to output pad:  {clk_to_pad:.2f} ns against a {period:.2f} ns "
            f"pixel period ({'over' if clk_to_pad > period else 'within'} budget, "
            "unconstrained: no PCF and no output delay constraint)"
        )
    if fmax < target:
        raise SystemExit(
            f"FAIL: {fmax:.2f} MHz does not meet the {target} MHz pixel clock, so the "
            "bitstream would not drive a monitor"
        )
    print("OK: the pixel clock closes on the FPGA")
    return 0


if __name__ == "__main__":
    sys.exit(main())
