"""Shared cocotb helpers for the regression and the image capture run.

Kept out of test.py so capture.py can reuse the reset sequence, the frame
capture loop and the output file layout without importing a module full of
@cocotb.test functions.
"""

import json
import pathlib
import struct

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, Timer

import model as M

# 1 / 39722 ps = 25.1750 MHz, the 640x480 pixel clock.
CLOCK_PS = 39722

OUT = pathlib.Path(__file__).resolve().parent / "output"


# ---------------------------------------------------------------------------
# input packing
# ---------------------------------------------------------------------------
def ui(sel=0, rand_en=0, health_clr=0, fast_sw=0, freeze=0, samp_fast=0):
    return (
        (sel & 7)
        | (rand_en << 3)
        | (health_clr << 4)
        | (fast_sw << 5)
        | (freeze << 6)
        | (samp_fast << 7)
    )


def uio(ent_bit=0, rct_sel=3, apt_sel=3):
    return (ent_bit & 1) | ((rct_sel & 3) << 1) | ((apt_sel & 3) << 3)


UIO_RCT_FAIL = 1 << 5
UIO_APT_FAIL = 1 << 6
UIO_RND = 1 << 7


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------
async def reset(dut, ui_val=0, uio_val=None, rct_sel=3, apt_sel=3):
    """Start the clock, reset, and return a Tile model aligned to the DUT.

    Reset is released just after a falling edge, so the flops still hold their
    reset values and the next rising edge is the first real step. The returned
    model is therefore in exactly the DUT's state and one call to model.step()
    corresponds to one rising edge.
    """
    if uio_val is None:
        uio_val = uio(0, rct_sel, apt_sel)
    cocotb.start_soon(Clock(dut.clk, CLOCK_PS, unit="ps").start())
    dut.ena.value = 1
    dut.ui_in.value = ui_val
    dut.uio_in.value = uio_val
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 8)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    return M.Tile(rct_sel=rct_sel, apt_sel=apt_sel)


async def settle():
    """Let a just written input propagate through combinational logic.

    A cocotb value assignment is a deposit that lands at the end of the current
    time step, so reading a combinational output in the same step still returns
    the old value. Anywhere an input is written and then read back without an
    intervening clock edge, this has to be called. One picosecond is far inside
    the 39722 ps clock period, so no edge is crossed.
    """
    await Timer(1, unit="ps")


# ---------------------------------------------------------------------------
# frame capture
# ---------------------------------------------------------------------------
async def step(dut, model, **kw):
    """Advance exactly one pixel clock and keep the model in lockstep."""
    await FallingEdge(dut.clk)
    model.step(**kw)


async def bulk_step(dut, model, n, **kw):
    """Advance n pixel clocks. One simulator trigger instead of n."""
    if n <= 0:
        return
    await ClockCycles(dut.clk, n, rising=False)
    for _ in range(n):
        model.step(**kw)


async def align_to_frame(dut, model, **kw):
    """Advance until the model (and therefore the DUT) is at pixel (0, 0)."""
    while not (model.x == 0 and model.y == 0):
        remaining = (M.H_TOTAL - model.x) % M.H_TOTAL
        if remaining:
            await bulk_step(dut, model, remaining, **kw)
        else:
            await bulk_step(dut, model, M.H_TOTAL, **kw)


async def capture_frame(dut, model, sel, check=True, max_report=12, **kw):
    """Capture one 640x480 frame starting at pixel (0, 0).

    Returns (framebuffer, mismatches). The framebuffer is a bytearray of
    640*480 packed 6 bit colours, r<<4 | g<<2 | b, taken from the DUT pins.
    When check is true every active pixel and a sample of the blanking is
    compared against the model.
    """
    assert model.x == 0 and model.y == 0, "capture_frame must start at (0, 0)"
    fb = bytearray(M.H_ACTIVE * M.V_ACTIVE)
    mism = []

    for line in range(M.V_TOTAL):
        if line < M.V_ACTIVE:
            base = line * M.H_ACTIVE
            for px in range(M.H_ACTIVE):
                got = int(dut.uo_out.value)
                if check:
                    exp = model.uo_out(sel)
                    if got != exp and len(mism) < max_report:
                        mism.append((model.x, model.y, model.frame, got, exp))
                _, _, r, g, b = M.unpack_uo(got)
                fb[base + px] = (r << 4) | (g << 2) | b
                await step(dut, model, **kw)
            # horizontal blanking: check the midpoint of each porch and the
            # sync pulse, then skip the rest in bulk
            for chunk in (8, 40, 40, 40, 32):
                await bulk_step(dut, model, chunk, **kw)
                if check:
                    got = int(dut.uo_out.value)
                    exp = model.uo_out(sel)
                    if got != exp and len(mism) < max_report:
                        mism.append((model.x, model.y, model.frame, got, exp))
            await bulk_step(dut, model, M.H_TOTAL - M.H_ACTIVE - 160, **kw)
        else:
            # vertical blanking: one check per line, rest in bulk
            await bulk_step(dut, model, 400, **kw)
            if check:
                got = int(dut.uo_out.value)
                exp = model.uo_out(sel)
                if got != exp and len(mism) < max_report:
                    mism.append((model.x, model.y, model.frame, got, exp))
            await bulk_step(dut, model, M.H_TOTAL - 400, **kw)

    return fb, mism


# ---------------------------------------------------------------------------
# output files consumed by scripts/make_images.py
# ---------------------------------------------------------------------------
def out_dir(name):
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_frame(name, fb, meta):
    """Store one frame as a tiny header plus raw 6 bit colour bytes."""
    d = out_dir("frames")
    with open(d / f"{name}.bin", "wb") as f:
        f.write(struct.pack("<HH", M.H_ACTIVE, M.V_ACTIVE))
        f.write(bytes(fb))
    (d / f"{name}.json").write_text(json.dumps(meta, indent=2) + "\n")


def write_json(name, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(obj, indent=2) + "\n")
