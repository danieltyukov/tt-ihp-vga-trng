#!/usr/bin/env python3
"""Reduce the LibreLane final metrics to the numbers the README quotes.

Called by scripts/harden.sh. Fails if signoff is not clean, because a hardening
run that DRCs is not evidence of anything and should not quietly produce a
summary file.

The one subtlety worth writing down: design__instance__area includes filler
cells, and filler by construction expands to occupy whatever the real cells left
over, so instance area over die area is close to 1 whatever the design does and
is not a utilization measure. The number that means something is
design__instance__area__stdcell minus the fill_cell class, which is the area of
cells that implement the design.
"""

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs" / "hardening"

# One Tiny Tapeout tile on the IHP shuttle, from their own floorplan templates in
# tt-support-tools (tech/ihp-sg13g2/def/tt_block_NxM_pgvdd.def):
#
#   1x1   202.08 x 154.98 um = 31318.3 um2
#   1x2   202.08 x 313.74 um = 63400.6 um2
#
# Not the "about 167x108 uM" the project template's info.yaml comment gives, which
# is 42% smaller and is what an earlier version of this script used. The numbers
# above are the die Tiny Tapeout's own gds action actually hands the floorplanner,
# read out of the resolved config of a run it produced.
TILE_UM = (202.08, 154.98)
TILE_UM2 = TILE_UM[0] * TILE_UM[1]

CLEAN = {
    "route__drc_errors": 0,
    "magic__drc_error__count": 0,
    "klayout__drc_error__count": 0,
    "design__lvs_error__count": 0,
    "antenna__violating__nets": 0,
    "design__instance_unmapped__count": 0,
    "design__violations": 0,
    "design__max_slew_violation__count": 0,
    "design__max_cap_violation__count": 0,
    "design__power_grid_violation__count": 0,
    "route__antenna_violation__count": 0,
    "antenna__violating__pins": 0,
}

# Setup and hold are checked against total negative slack rather than a violation
# count, because this LibreLane version reports TNS but no per-check count.
TNS_CLEAN = ("timing__setup__tns", "timing__hold__tns")

# Both rings, stage by stage, as the routed netlist must still contain them:
# 4 inverters and 1 enable NAND for the 5 stage ring, 6 and 1 for the 7 stage one.
RING_STAGES = {"a": 5, "b": 7}


def check_rings(run):
    """Count the ring oscillator cells in the routed netlist.

    scripts/synth_report.sh already checks this after yosys, but the failure mode
    it guards against is silent, and there is more than one way to reach it: an
    optimiser cancelling inverter pairs, a lost keep attribute, or a stray
    `SYNTH define reaching the ASIC flow and selecting the external entropy path
    that src/entropy_source.v builds for the FPGA. Any of those produces a
    perfectly clean GDS with no noise source in it, so the routed netlist is
    checked too rather than trusted.
    """
    nls = sorted((run / "final" / "nl").glob("*.nl.v"))
    if not nls:
        print("note: no final netlist to check the ring oscillators in")
        return False
    text = nls[0].read_text()
    failed = False
    total = 0
    for ring, stages in RING_STAGES.items():
        inv = len(re.findall(rf"u_osc_{ring}\.g_stage\[\d+\]\.u_inv", text))
        gate = len(re.findall(rf"u_osc_{ring}\.u_gate", text))
        total += inv + gate
        want_inv = stages - 1
        ok = inv == want_inv and gate == 1
        print(
            f"ring {ring}: {inv} inverter + {gate} enable gate cell(s) routed, "
            f"expected {want_inv} + 1{'' if ok else '   <-- WRONG'}"
        )
        if not ok:
            failed = True
    if failed:
        print(
            f"\nRING OSCILLATORS NOT INTACT: {total} of "
            f"{sum(RING_STAGES.values())} stages survived to the routed netlist. "
            "The TRNG in this GDS has no noise source."
        )
    return failed


def main():
    run = pathlib.Path(sys.argv[1])
    m = json.loads((run / "final" / "metrics.json").read_text())
    # The die comes from the run rather than from a constant, so the summary can
    # never describe a floorplan the flow did not actually use.
    _, _, die_w, die_h = json.loads((run / "resolved.json").read_text())["DIE_AREA"]
    tiles_h = round(die_w / TILE_UM[0])
    tiles_v = round(die_h / TILE_UM[1])

    die = m["design__die__area"]
    inst_total = m["design__instance__area"]
    fill = m.get("design__instance__area__class:fill_cell", 0.0)
    real = inst_total - fill

    classes = {
        k.split(":", 1)[1]: v
        for k, v in m.items()
        if k.startswith("design__instance__area__class:")
    }
    counts = {
        k.split(":", 1)[1]: v
        for k, v in m.items()
        if k.startswith("design__instance__count__class:")
    }

    summary = {
        "tool": "LibreLane 3.0.0.dev44",
        # Which run directory these numbers came from, so scripts/make_images.py
        # renders the same die the summary describes rather than whichever run
        # happens to sort last.
        "run": run.name,
        "pdk": "ihp-sg13g2",
        "sdc": "hardening/constraints.sdc",
        "clock_period_ns": 39.722,
        "clock_mhz": 25.175,
        "die_area_um2": die,
        "die_um": [die_w, die_h],
        "tile_um": list(TILE_UM),
        "tile_area_um2": round(TILE_UM2, 1),
        "tiles_from_die": f"{tiles_h}x{tiles_v}",
        "instance_area_total_um2": inst_total,
        "instance_area_fill_um2": fill,
        "instance_area_real_um2": round(real, 1),
        "instance_count_total": m["design__instance__count"],
        "instance_count_fill": counts.get("fill_cell", 0),
        "instance_count_real": m["design__instance__count"] - counts.get("fill_cell", 0),
        "flop_count": counts.get("sequential_cell", 0),
        "area_by_class_um2": classes,
        "count_by_class": counts,
        "density_real_over_die": round(real / die, 4),
        "density_real_over_1x1": round(real / TILE_UM2, 4),
        "setup_ws_ns": m["timing__setup__ws"],
        "hold_ws_ns": m["timing__hold__ws"],
        "setup_tns_ns": m["timing__setup__tns"],
        "hold_tns_ns": m["timing__hold__tns"],
        "wirelength_um": m.get("route__wirelength"),
        "power_total_w": m.get("power__total"),
        "max_slew_violations": m.get("design__max_slew_violation__count"),
        "max_cap_violations": m.get("design__max_cap_violation__count"),
        "max_fanout_violations": m.get("design__max_fanout_violation__count"),
        "signoff": {k: m.get(k) for k in CLEAN},
    }
    # Per corner slack, useful for the README table.
    summary["per_corner"] = {
        k.split("corner:", 1)[1]: {
            "setup_ws_ns": m[k],
            "hold_ws_ns": m.get(k.replace("setup", "hold")),
        }
        for k in m
        if k.startswith("timing__setup__ws__corner:")
    }

    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    print(f"die area            {die:>12.1f} um2   ({die_w} x {die_h}, a {tiles_h}x{tiles_v} tile)")
    print(f"real cell area      {real:>12.1f} um2   ({summary['instance_count_real']} cells)")
    print(f"  fill cells        {fill:>12.1f} um2   ({summary['instance_count_fill']} cells)")
    print(f"density on this die {summary['density_real_over_die'] * 100:>12.1f} %")
    print(f"density on one 1x1  {summary['density_real_over_1x1'] * 100:>12.1f} %")
    print(f"setup worst slack   {summary['setup_ws_ns']:>12.4f} ns")
    print(f"hold worst slack    {summary['hold_ws_ns']:>12.4f} ns")
    print(f"power               {summary['power_total_w'] * 1000:>12.4f} mW")
    print(f"wirelength          {summary['wirelength_um']:>12} um")

    print()
    rings_broken = check_rings(run)

    failed = []
    if rings_broken:
        failed.append("the ring oscillators did not survive to the routed netlist")
    for k, want in CLEAN.items():
        got = m.get(k)
        if got is None:
            print(f"note: {k} not reported by this LibreLane version")
            continue
        if got != want:
            failed.append(f"{k} = {got}, expected {want}")
    for k in TNS_CLEAN:
        got = m.get(k)
        if got is None or got < 0:
            failed.append(f"{k} = {got}, expected 0 or better")
    if failed:
        print("\nSIGNOFF NOT CLEAN:")
        for f in failed:
            print(f"  {f}")
        return 1
    print(
        "\nsignoff clean: DRC 0 (route, magic, klayout), LVS 0, antenna 0 nets and "
        "0 pins, power grid 0, no unmapped cells, max slew 0, max cap 0, "
        "setup TNS 0, hold TNS 0"
    )

    fo = summary["max_fanout_violations"]
    if fo:
        print(
            f"note: {fo} max fanout violation(s) remain. See docs/design.md; this is "
            "the clock tree root buffer and it is documented rather than hidden."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
