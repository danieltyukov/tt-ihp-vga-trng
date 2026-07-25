#!/usr/bin/env python3
"""Collect the per corner OpenSTA results into docs/sta/summary.json.

Called by scripts/run_sta.sh. Reads the tagged lines run_sta.sh captured from
each OpenSTA run, and fails if the slow corner does not close, because that is
the claim info.yaml's clock_hz rests on.
"""

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUILD = ROOT / "build" / "sta"
DOCS = ROOT / "docs" / "sta"

TARGET_MHZ = 25.175
# The corner that decides whether a shuttle part works: slowest silicon, lowest
# supply, hottest junction.
SIGNOFF_CORNER = "slow_1p08V_125C"


def parse(corner):
    text = (BUILD / f"stdout_{corner}.txt").read_text()
    out = {}
    for key, cast in (
        ("PERIOD", float),
        ("WORST_SETUP", float),
        ("WORST_HOLD", float),
        ("FMAX_MHZ", float),
        ("TNS_MAX", float),
    ):
        m = re.search(rf"^{key} (\S+)$", text, re.M)
        if not m:
            raise SystemExit(f"{corner}: OpenSTA did not report {key}")
        out[key.lower()] = cast(m.group(1))
    # Count the combinational loop warnings so the report can state plainly that
    # they exist, how many, and that they are the ring oscillators.
    out["loop_warnings"] = len(re.findall(r"combinational loop", text, re.I))
    return out


def main():
    period = float(sys.argv[1])
    corners = sys.argv[2:]
    DOCS.mkdir(parents=True, exist_ok=True)

    res = {c: parse(c) for c in corners}
    summary = {
        "period_ns": period,
        "target_mhz": TARGET_MHZ,
        "signoff_corner": SIGNOFF_CORNER,
        "corners": res,
        "note": (
            "Post synthesis STA on a Yosys mapped netlist, no placement or "
            "routing, so interconnect is estimated by the liberty wireload model "
            "rather than extracted. The post route numbers are in "
            "docs/hardening/metrics.json."
        ),
    }
    (DOCS / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    print()
    print(f"{'corner':20s} {'setup slack':>12s} {'hold slack':>11s} {'fmax MHz':>10s} {'margin':>8s}")
    for c in corners:
        r = res[c]
        print(
            f"{c:20s} {r['worst_setup']:12.4f} {r['worst_hold']:11.4f} "
            f"{r['fmax_mhz']:10.2f} {r['fmax_mhz'] / TARGET_MHZ:7.2f}x"
        )

    sign = res[SIGNOFF_CORNER]
    if sign["worst_setup"] < 0:
        raise SystemExit(
            f"FAIL: setup does not close at {SIGNOFF_CORNER}, worst slack "
            f"{sign['worst_setup']:.4f} ns at a {period} ns period. "
            "info.yaml declares clock_hz 25175000, which would not be honest."
        )
    if sign["worst_hold"] < 0:
        print(
            f"note: hold slack at {SIGNOFF_CORNER} is {sign['worst_hold']:.4f} ns "
            "pre-CTS, which the placement flow fixes with hold buffers. See "
            "docs/hardening/ for the post route number."
        )
    print(
        f"\nOK: setup closes at {SIGNOFF_CORNER} with "
        f"{sign['worst_setup']:.4f} ns of slack at {period} ns "
        f"({sign['fmax_mhz']:.2f} MHz, {sign['fmax_mhz'] / TARGET_MHZ:.2f}x the "
        f"{TARGET_MHZ} MHz target)"
    )


if __name__ == "__main__":
    main()
