#!/usr/bin/env python3
"""Read the raw frame dumps written by the cocotb run.

Each .bin is a 4 byte header (width, height as little endian uint16) followed by
one byte per pixel holding the 6 bit colour the tile actually drove on its pins,
packed as r<<4 | g<<2 | b. Nothing here invents pixels: if a file is missing,
the caller is told to run the simulation.
"""

import json
import pathlib
import struct

ROOT = pathlib.Path(__file__).resolve().parent.parent
FRAME_DIR = ROOT / "test" / "output" / "frames"

# 2 bit channel to 8 bit, matching what a TinyVGA PMOD resistor ladder produces
LEVELS = [0, 85, 170, 255]


def load(name, directory=None):
    """Return (width, height, list of (r,g,b) tuples) for one captured frame."""
    d = pathlib.Path(directory) if directory else FRAME_DIR
    path = d / f"{name}.bin"
    if not path.exists():
        raise SystemExit(
            f"missing {path}\n"
            "Run the simulation first: make test (patterns) and make capture (sequences)."
        )
    raw = path.read_bytes()
    w, h = struct.unpack("<HH", raw[:4])
    body = raw[4:]
    assert len(body) == w * h, f"{path}: expected {w * h} pixels, got {len(body)}"
    px = [
        (LEVELS[(v >> 4) & 3], LEVELS[(v >> 2) & 3], LEVELS[v & 3])
        for v in body
    ]
    return w, h, px


def meta(name, directory=None):
    d = pathlib.Path(directory) if directory else FRAME_DIR
    path = d / f"{name}.json"
    return json.loads(path.read_text()) if path.exists() else {}


def to_image(name, directory=None, scale=1):
    """Load a captured frame as a PIL image."""
    from PIL import Image

    w, h, px = load(name, directory)
    img = Image.new("RGB", (w, h))
    img.putdata(px)
    if scale != 1:
        img = img.resize((w // scale, h // scale), Image.BOX)
    return img


def available(directory=None):
    d = pathlib.Path(directory) if directory else FRAME_DIR
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.bin"))
