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
    """Load a captured frame as a PIL image, optionally downscaled by max pooling.

    Max pooling rather than the obvious choices, because both of them lose real
    content from these particular patterns:

      - Box averaging dims a single pixel star to a quarter of its brightness,
        which makes the starfield look almost empty.
      - Nearest neighbour drops the Sierpinski gasket completely. The gasket
        lives on specific pixel parities, and at scale 2 nearest neighbour
        samples exactly the parity that is always off.

    Taking the brightest pixel of each block keeps one pixel wide features
    visible at full brightness, which is what these images are for.
    """
    import numpy as np
    from PIL import Image

    w, h, px = load(name, directory)
    arr = np.array(px, dtype=np.uint8).reshape(h, w, 3)
    if scale != 1:
        assert w % scale == 0 and h % scale == 0, f"{w}x{h} is not divisible by {scale}"
        arr = arr.reshape(h // scale, scale, w // scale, scale, 3).max(axis=(1, 3))
    return Image.fromarray(arr)


def available(directory=None):
    d = pathlib.Path(directory) if directory else FRAME_DIR
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.bin"))
