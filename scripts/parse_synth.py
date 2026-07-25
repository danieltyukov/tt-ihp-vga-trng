#!/usr/bin/env python3
"""Turn the Yosys stat output in docs/synth/ into docs/synth/area.json.

Called by scripts/synth_report.sh. Kept separate so make_images.py can consume a
stable schema instead of re-parsing Yosys text.
"""

import json
import pathlib
import re

# TinyTapeout IHP shuttle geometry, from their own floorplan template
# tt/tech/ihp-sg13g2/def/tt_block_1x1_pgvdd.def, which is the die tt-gds-action
# hands the floorplanner. Not the "about 167x108 uM" the project template's
# info.yaml comment gives: that is 42% smaller and does not match any run.
TILE_W_UM = 202.08
TILE_H_UM = 154.98
TILE_AREA = TILE_W_UM * TILE_H_UM

# Librelane places at PL_TARGET_DENSITY_PCT, which src/config.json leaves at the
# Tiny Tapeout default of 60. Anything above that will not place and route.
TARGET_DENSITY = 0.60

DOCS = pathlib.Path(__file__).resolve().parent.parent / "docs" / "synth"


def parse_stat(text):
    """Pull cell counts and chip area out of one Yosys 'stat -liberty' block."""
    cells = {}
    area = None
    top_area = None
    total = None
    for line in text.splitlines():
        # 'top module' includes kept-hierarchy submodules (the ring oscillator
        # stages); plain 'module' does not. Prefer the inclusive figure.
        m = re.match(r"\s+Chip area for top module '\\?(\S+?)':\s+([0-9.]+)", line)
        if m:
            top_area = float(m.group(2))
            continue
        m = re.match(r"\s+Chip area for module '\\?(\S+?)':\s+([0-9.]+)", line)
        if m:
            if area is None:
                area = float(m.group(2))
            continue
        m = re.match(r"\s+Number of cells:\s+(\d+)", line)
        if m:
            total = int(m.group(1))
            continue
        m = re.match(r"\s+(sg13g2_\S+)\s+(\d+)\s*$", line)
        if m:
            cells[m.group(1)] = int(m.group(2))
    return {
        "cells": cells,
        "cell_count": total,
        "area_um2": top_area if top_area is not None else area,
    }


def main():
    total = parse_stat((DOCS / "total.txt").read_text())

    modules = {}
    blocks = (DOCS / "modules.txt").read_text().split("===== ")
    for block in blocks[1:]:
        name = block.splitlines()[0].strip()
        modules[name] = parse_stat(block)

    flops = sum(n for c, n in total["cells"].items() if "df" in c)

    out = {
        "top": {
            "cell_count": total["cell_count"],
            "area_um2": round(total["area_um2"], 2),
            "flop_count": flops,
            "cells": total["cells"],
        },
        "modules": {
            k: {
                "cell_count": v["cell_count"],
                "area_um2": round(v["area_um2"], 2) if v["area_um2"] else 0.0,
                "flop_count": sum(n for c, n in v["cells"].items() if "df" in c),
            }
            for k, v in modules.items()
        },
        "tile": {
            "tile_w_um": TILE_W_UM,
            "tile_h_um": TILE_H_UM,
            "tile_area_um2": TILE_AREA,
            "target_density": TARGET_DENSITY,
            "usable_area_per_tile_um2": round(TILE_AREA * TARGET_DENSITY, 2),
            "tiles_required": None,
            "density_1x1": None,
            "density_1x2": None,
        },
    }

    area = out["top"]["area_um2"]
    out["tile"]["density_1x1"] = round(area / TILE_AREA, 4)
    out["tile"]["density_1x2"] = round(area / (2 * TILE_AREA), 4)
    need = area / (TILE_AREA * TARGET_DENSITY)
    out["tile"]["tiles_required"] = round(need, 3)

    (DOCS / "area.json").write_text(json.dumps(out, indent=2) + "\n")

    print(f"top: {out['top']['cell_count']} cells, {flops} flops, {area} um2")
    print(
        f"1x1 density {out['tile']['density_1x1']*100:.1f}%  "
        f"1x2 density {out['tile']['density_1x2']*100:.1f}%  "
        f"tiles needed at {TARGET_DENSITY*100:.0f}%: {need:.2f}"
    )


if __name__ == "__main__":
    main()
