#!/usr/bin/env python3
"""Compare the committed area report against a freshly generated one.

scripts/synth_report.sh has already overwritten docs/synth/area.json by the time
this runs, so the committed version is read back out of git.

Compared with a tolerance rather than byte for byte on purpose. Yosys cell counts
move a little between versions, and pinning CI to one version just to protect an
exact match would turn this into a test of the runner image. What actually needs
protecting is the number the tile decision rests on: 18040 um2 against a 10822 um2
single tile budget is a 67% overshoot, so a 2% tolerance still catches any real
change to the design while ignoring mapper noise.

Also re-derives the tile count and asserts it agrees with info.yaml, so the
declared tile size can never drift away from the measurement. Two derivations run,
and the post route one is the one that decides:

  post synthesis  mapped cell area against the tile area at LibreLane's placement
                  density target. A forecast, and on this design a bad one: 18040
                  um2 of cells against 18036 um2 of gross 1x1 tile is a dead heat,
                  which is exactly where a synthesis-only estimate is worthless.

  post route      real cell area from docs/hardening/summary.json against the die
                  that was actually hardened. 25940 um2 of cells is 143.8% of a
                  gross 1x1 tile, so 1x1 is ruled out arithmetically rather than
                  by a density convention. This check runs whenever the hardening
                  summary is committed, which it is.
"""

import json
import math
import pathlib
import re
import subprocess
import sys

TOL = 0.02

ROOT = pathlib.Path(__file__).resolve().parent.parent
AREA = "docs/synth/area.json"
HARDENING = "docs/hardening/summary.json"


def committed():
    try:
        blob = subprocess.run(
            ["git", "show", f"HEAD:{AREA}"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except subprocess.CalledProcessError:
        print(f"note: {AREA} is not committed yet, nothing to compare against")
        return None
    return json.loads(blob)


def declared_tiles():
    text = (ROOT / "info.yaml").read_text()
    m = re.search(r'^\s*tiles:\s*"([0-9]+x[0-9]+)"', text, re.M)
    assert m, "could not find the tiles field in info.yaml"
    return m.group(1)


def check_post_route(declared_count):
    """Derive the tile count from the hardened die, not from a synthesis estimate.

    Returns True on failure, matching the caller's convention.
    """
    path = ROOT / HARDENING
    if not path.exists():
        print(f"note: {HARDENING} is not present, skipping the post route check")
        return False

    h = json.loads(path.read_text())
    tile_area = h["tile_area_um2"]
    real = h["instance_area_real_um2"]
    die = h["die_area_um2"]
    failed = False

    print()
    print("post route, from " + HARDENING + ":")
    print(f"  real cell area      {real:.1f} um2, {h['instance_count_real']} cells")
    print(f"  gross 1x1 tile area {tile_area:.1f} um2")
    print(f"  hardened die area   {die:.1f} um2 ({h['die_um'][0]} x {h['die_um'][1]})")

    # A tile count whose gross area is smaller than the placed cell area cannot
    # work whatever the density target is, so this is the hard floor.
    floor = max(1, math.ceil(real / tile_area))
    print(
        f"  cells are {real / tile_area * 100:.1f}% of one gross tile "
        f"-> at least {floor} tile(s) before any routing space"
    )
    if declared_count < floor:
        print(
            f"FAIL: info.yaml declares {declared_count} tile(s) but the placed cells "
            f"alone need {floor}."
        )
        failed = True

    # And the die that was hardened has to be the die that was declared.
    die_tiles = die / tile_area
    if abs(die_tiles - declared_count) > 0.01:
        print(
            f"FAIL: the hardened die is {die_tiles:.2f} tiles but info.yaml declares "
            f"{declared_count}. The two have to be the same die."
        )
        failed = True
    else:
        print(
            f"  hardened die is {die_tiles:.0f} tiles, info.yaml declares "
            f"{declared_count}, utilisation {real / die * 100:.1f}%"
        )
    return failed


def main():
    fresh = json.loads((ROOT / AREA).read_text())
    old = committed()

    f_area = fresh["top"]["area_um2"]
    f_cells = fresh["top"]["cell_count"]
    f_flops = fresh["top"]["flop_count"]
    print(f"fresh:     {f_cells} cells, {f_flops} flops, {f_area} um2")

    failed = False

    if old is not None:
        o_area = old["top"]["area_um2"]
        o_cells = old["top"]["cell_count"]
        o_flops = old["top"]["flop_count"]
        print(f"committed: {o_cells} cells, {o_flops} flops, {o_area} um2")
        drift = abs(f_area - o_area) / o_area
        print(f"area drift: {drift * 100:.3f}% (tolerance {TOL * 100:.0f}%)")
        if drift > TOL:
            print(
                f"FAIL: mapped area moved by {drift * 100:.2f}%. Re-run `make synth`, "
                "check the numbers quoted in README.md and docs/design.md, and commit."
            )
            failed = True
        if f_flops != o_flops:
            print(
                f"FAIL: flip-flop count changed from {o_flops} to {f_flops}. "
                "That is a design change, not mapper noise."
            )
            failed = True

    # The tile count has to follow the measurement, not the other way round.
    tile = fresh["tile"]
    needed = f_area / (tile["tile_area_um2"] * tile["target_density"])
    min_tiles = max(1, math.ceil(needed))
    declared = declared_tiles()
    declared_count = int(declared.split("x")[0]) * int(declared.split("x")[1])
    print(
        f"post synthesis forecast at {tile['target_density'] * 100:.0f}% density: "
        f"{needed:.2f} -> at least {min_tiles}; info.yaml declares {declared} = "
        f"{declared_count}"
    )
    if declared_count < min_tiles:
        print(
            f"FAIL: info.yaml declares {declared_count} tile(s) but the measured area "
            f"needs at least {min_tiles} at the configured placement density."
        )
        failed = True

    if check_post_route(declared_count):
        failed = True

    print("FAIL" if failed else "OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
