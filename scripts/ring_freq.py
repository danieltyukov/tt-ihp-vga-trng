#!/usr/bin/env python3
"""Estimate the ring oscillator frequency from IHP sg13g2 Liberty delay data.

This is a hand calculation, not a measurement. It cannot be a measurement: a ring
oscillator's frequency depends on the routed parasitics, the local supply, the die
temperature and the process corner of the individual part, and its whole purpose
is to jitter. What this gives is a defensible range for what to expect on a bench,
which is what the sample rate control on ui_in[7] has to be set against.

Method
------
A ring of N stages toggles every node once per half period, so

    T = 2 * (t_gate + (N - 1) * t_inv)
    f = 1 / T

with t_gate the delay of the enable NAND at stage 0 and t_inv the delay of an
inverter. Each stage drives exactly one identical stage, so the load is that
cell's own input capacitance, which is the self-loaded case. The delay used is the
mean of cell_rise and cell_fall, bilinearly interpolated in the Liberty 7x7 table
at that load and at the output transition the previous stage produces, solved by
fixed point so the input slew is self consistent rather than assumed.

Interconnect is not included. On a real die the routing between stages adds
capacitance and slows the ring, so these figures are an upper bound on frequency.
"""

import json
import pathlib
import re
import sys

PDK = pathlib.Path(
    "/home/danieltyukov/.local/share/pdk/IHP-Open-PDK/ihp-sg13g2"
)
LIBDIR = PDK / "libs.ref" / "sg13g2_stdcell" / "lib"
CORNERS = [
    "slow_1p08V_125C",
    "typ_1p20V_25C",
    "fast_1p65V_m40C",
]
# src/entropy_source.v instantiates these two.
RINGS = [5, 7]
OUT = pathlib.Path(__file__).resolve().parent.parent / "docs" / "sta" / "ring_freq.json"


def cell_block(text, name):
    """Return the source text of one cell block."""
    start = text.index(f"\n  cell ({name}) {{")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ValueError(f"unterminated cell block for {name}")


def table(block, kind, related=None):
    """Parse one 7x7 timing table: returns (index_1, index_2, values)."""
    scope = block
    if related is not None:
        # narrow to the timing group for the requested related_pin
        groups = re.split(r"\n      timing \(\) \{", block)
        scope = next(g for g in groups[1:] if f'related_pin : "{related}"' in g)
    m = re.search(
        rf"{kind} \([^)]*\) \{{\s*"
        r'index_1 \("([^"]+)"\);\s*'
        r'index_2 \("([^"]+)"\);\s*'
        r"values \( \\\s*(.*?)\s*\);",
        scope,
        re.S,
    )
    if not m:
        raise ValueError(f"no {kind} table found")
    idx1 = [float(x) for x in m.group(1).split(",")]
    idx2 = [float(x) for x in m.group(2).split(",")]
    rows = []
    for line in m.group(3).split("\\"):
        line = line.strip().strip(",").strip()
        if not line:
            continue
        rows.append([float(x) for x in line.strip('"').split(",")])
    assert len(rows) == len(idx1), f"{kind}: {len(rows)} rows for {len(idx1)} indices"
    return idx1, idx2, rows


def interp1(xs, i):
    """Index and weight for bilinear interpolation, clamped at both ends."""
    if i <= xs[0]:
        return 0, 0.0
    if i >= xs[-1]:
        return len(xs) - 2, 1.0
    k = max(j for j in range(len(xs) - 1) if xs[j] <= i)
    return k, (i - xs[k]) / (xs[k + 1] - xs[k])


def lookup(tbl, slew, load):
    idx1, idx2, vals = tbl
    a, wa = interp1(idx1, slew)
    b, wb = interp1(idx2, load)
    v00, v01 = vals[a][b], vals[a][b + 1]
    v10, v11 = vals[a + 1][b], vals[a + 1][b + 1]
    return (
        v00 * (1 - wa) * (1 - wb)
        + v01 * (1 - wa) * wb
        + v10 * wa * (1 - wb)
        + v11 * wa * wb
    )


def input_cap(block, pin):
    m = re.search(
        rf'pin \({pin}\) \{{(?:(?!pin \()[\s\S])*?capacitance : ([0-9.]+);', block
    )
    if not m:
        raise ValueError(f"no capacitance on pin {pin}")
    return float(m.group(1))


def stage_delay(block, related, load, iters=25):
    """Self consistent mean delay and output slew for one stage.

    The input slew of a stage is the output slew of the previous one, which in a
    uniform ring is the same stage, so it is a fixed point. Twenty five passes is
    far more than it needs; it settles in about five.
    """
    d_r = table(block, "cell_rise", related)
    d_f = table(block, "cell_fall", related)
    s_r = table(block, "rise_transition", related)
    s_f = table(block, "fall_transition", related)
    slew = 0.1
    for _ in range(iters):
        out = 0.5 * (lookup(s_r, slew, load) + lookup(s_f, slew, load))
        if abs(out - slew) < 1e-9:
            slew = out
            break
        slew = out
    delay = 0.5 * (lookup(d_r, slew, load) + lookup(d_f, slew, load))
    return delay, slew


def main():
    if not LIBDIR.exists():
        raise SystemExit(f"IHP PDK not found at {PDK}")

    result = {"method": __doc__.strip().splitlines()[0], "corners": {}}

    for corner in CORNERS:
        text = (LIBDIR / f"sg13g2_stdcell_{corner}.lib").read_text()
        inv = cell_block(text, "sg13g2_inv_1")
        nand = cell_block(text, "sg13g2_nand2_1")

        c_inv = input_cap(inv, "A")
        # Stage 0 of the ring is the NAND; the stage before it is an inverter
        # driving the NAND's A pin.
        c_nand = input_cap(nand, "A")

        t_inv, slew_inv = stage_delay(inv, "A", c_inv)
        t_inv_into_nand, _ = stage_delay(inv, "A", c_nand)
        t_nand, _ = stage_delay(nand, "A", c_inv)

        entry = {
            "cap_inv_A_pF": c_inv,
            "cap_nand2_A_pF": c_nand,
            "t_inv_ns": round(t_inv, 5),
            "t_inv_driving_nand_ns": round(t_inv_into_nand, 5),
            "t_nand2_ns": round(t_nand, 5),
            "settled_slew_ns": round(slew_inv, 5),
            "rings": {},
        }
        for n in RINGS:
            # one NAND, one inverter loaded by the NAND, and N-2 inverters loaded
            # by an inverter
            total = t_nand + t_inv_into_nand + (n - 2) * t_inv
            period = 2 * total
            entry["rings"][str(n)] = {
                "stages": n,
                "loop_delay_ns": round(total, 5),
                "period_ns": round(period, 5),
                "freq_mhz": round(1000.0 / period, 2),
            }
        result["corners"][corner] = entry

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2) + "\n")

    print(f"{'corner':20s} {'t_inv ns':>9s} {'t_nand ns':>10s}", end="")
    for n in RINGS:
        print(f" {'f' + str(n) + ' MHz':>10s}", end="")
    print(f" {'beat MHz':>9s} {'samples/bit':>12s}")
    for corner, e in result["corners"].items():
        print(f"{corner:20s} {e['t_inv_ns']:9.4f} {e['t_nand2_ns']:10.4f}", end="")
        fs = []
        for n in RINGS:
            f = e["rings"][str(n)]["freq_mhz"]
            fs.append(f)
            print(f" {f:10.1f}", end="")
        beat = abs(fs[0] - fs[1])
        # How many oscillator periods fit in one sample interval at the default
        # divide by 8 of the 25.175 MHz pixel clock.
        cycles = fs[1] * (8 / 25.175)
        print(f" {beat:9.1f} {cycles:12.1f}")
        e["beat_mhz"] = round(beat, 2)
        e["osc_periods_per_sample_div8"] = round(cycles, 1)

    OUT.write_text(json.dumps(result, indent=2) + "\n")
    print(f"\nwrote {OUT.relative_to(OUT.parent.parent.parent)}")
    print(
        "\nHand calculation from Liberty tables, no interconnect. On silicon the "
        "routing between stages adds capacitance, so real rings will be slower "
        "than these figures. Nothing here is a measurement."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
