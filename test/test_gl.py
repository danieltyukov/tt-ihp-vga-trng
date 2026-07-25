"""Reduced regression for the hardened gate-level netlist.

Why a separate module instead of running test.py against the netlist:

  1. Runtime. test.py captures eight full 640x480 frames, 3.4 million pixel
     clocks, plus a 65536 step LFSR walk and 262144 statistics samples. Gate
     level simulation of a 1767 cell netlist is one to two orders of magnitude
     slower than RTL, so that suite does not finish in any reasonable CI budget.
     The Tiny Tapeout gl_test job on this repo sat in_progress for 1h51m before
     this module existed.

  2. Several of those tests cannot be meaningful at gate level anyway. The
     hardened netlist has no parameters, so SIM_ENTROPY is 0 and the entropy
     source is the ring oscillators rather than the uio_in[0] pin. Every test
     that drives a known entropy stream, and the starfield golden frame that
     depends on the conditioner state, are checking something that does not
     exist in this netlist.

What this module does check, which is exactly what gate level simulation is for:
that synthesis, placement, clock tree insertion and routing did not break the
synchronous logic. Sync timing, blanking, the pattern mux and reset behaviour all
come through the same flops and combinational cones that PnR rebuilt.

The RTL suite remains the real verification. This is a post-implementation
sanity check on the netlist.
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge

import model as M

CLOCK_PS = 39722


async def gl_reset(dut, ui_val=0, cycles=16):
    """Bring the netlist up. Longer than the RTL reset on purpose.

    Every flop in this design has a synchronous reset, so one clock with rst_n
    low is enough in principle. At gate level the flops power up at X and the
    hold-fixing delay chain (233 sg13g2_dlygate4sd3_1 cells) means an X can take
    several clocks to be flushed out of the longer paths, so this holds reset for
    16 clocks and then checks the outputs have resolved.
    """
    cocotb.start_soon(Clock(dut.clk, CLOCK_PS, unit="ps").start())
    dut.ena.value = 1
    dut.ui_in.value = ui_val
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, cycles)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1


@cocotb.test()
async def test_gl_reset(dut):
    """Outputs resolve out of X and uio_oe is exactly what the RTL declares."""
    await gl_reset(dut)

    # uio_oe first: it is driven entirely by tie cells with no flop or clock in
    # the path, so if it is X the problem is netlist or cell modelling rather than
    # anything to do with reset.
    dut._log.info(f"uio_oe = {dut.uio_oe.value!r}   uo_out = {dut.uo_out.value!r}")
    assert dut.uio_oe.value.is_resolvable, (
        f"uio_oe is {dut.uio_oe.value!r}, and it is driven only by tie cells"
    )
    assert dut.uo_out.value.is_resolvable, (
        f"uo_out is still {dut.uo_out.value!r} after reset. At gate level the "
        "flops power up at X; if this does not resolve, the synchronous reset did "
        "not survive synthesis."
    )
    assert int(dut.uio_oe.value) == 0b1110_0000, (
        f"uio_oe must be 0b11100000, got {int(dut.uio_oe.value):#010b}"
    )

    hs, vs, r, g, b = M.unpack_uo(int(dut.uo_out.value))
    assert (hs, vs) == (1, 1), f"both syncs must idle high at pixel 0,0, got hs={hs} vs={vs}"
    dut._log.info(
        f"gate level reset: uo_out = {int(dut.uo_out.value):#04x}, "
        f"uio_oe = {int(dut.uio_oe.value):#010b}"
    )


@cocotb.test()
async def test_gl_hsync_timing(dut):
    """Measure hsync from the pins over three scanlines and check the numbers.

    Three lines is 2400 clocks, which is affordable at gate level and is enough
    for two complete high and low intervals.
    """
    await gl_reset(dut, ui_val=5)  # pattern 5, every visible pixel non-black

    trace = []
    for _ in range(3 * M.H_TOTAL):
        v = int(dut.uo_out.value)
        hs, vs, r, g, b = M.unpack_uo(v)
        trace.append((hs, 1 if (r or g or b) else 0))
        await FallingEdge(dut.clk)

    def runs(seq):
        out, cur, n = [], seq[0], 0
        for s in seq:
            if s == cur:
                n += 1
            else:
                out.append((cur, n))
                cur, n = s, 1
        out.append((cur, n))
        return out

    hs_runs = runs([t[0] for t in trace])[1:-1]
    lows = [n for lvl, n in hs_runs if lvl == 0]
    highs = [n for lvl, n in hs_runs if lvl == 1]
    assert lows, "no complete hsync pulse in three scanlines"
    assert set(lows) == {M.H_SYNC}, f"hsync low must be {M.H_SYNC}, measured {sorted(set(lows))}"
    assert set(highs) == {M.H_TOTAL - M.H_SYNC}, (
        f"hsync high must be {M.H_TOTAL - M.H_SYNC}, measured {sorted(set(highs))}"
    )

    nb_runs = runs([t[1] for t in trace])[1:-1]
    active = [n for lvl, n in nb_runs if lvl == 1]
    assert set(active) == {M.H_ACTIVE}, (
        f"horizontal active must be {M.H_ACTIVE}, measured {sorted(set(active))}"
    )
    dut._log.info(
        f"gate level horizontal timing: active={M.H_ACTIVE} sync={M.H_SYNC} "
        f"total={M.H_TOTAL}, measured over three scanlines"
    )


@cocotb.test()
async def test_gl_patterns_differ(dut):
    """The pattern mux survived PnR: each sel gives a different scanline.

    One scanline per pattern rather than a whole frame. A full golden frame
    comparison is not possible here regardless, because this netlist has
    SIM_ENTROPY = 0 and the starfield depends on the conditioner state that the
    ring oscillators now perturb.
    """
    await gl_reset(dut, ui_val=0)

    # Advance to the middle of the visible area so the captured line has content.
    await ClockCycles(dut.clk, 100 * M.H_TOTAL, rising=False)

    lines = {}
    for sel in range(M.NUM_PATTERNS):
        dut.ui_in.value = sel
        # settle the combinational mux, then align to the start of a line
        await FallingEdge(dut.clk)
        row = []
        for _ in range(M.H_ACTIVE):
            row.append(int(dut.uo_out.value) & 0x77)  # colour bits only
            await FallingEdge(dut.clk)
        await ClockCycles(dut.clk, M.H_TOTAL - M.H_ACTIVE, rising=False)
        lines[sel] = bytes(row)
        assert len(set(lines[sel])) > 1 or sel == 6, (
            f"pattern {sel} produced a flat scanline at gate level"
        )

    # The starfield can legitimately be almost empty on any given line, so it is
    # excluded from the distinctness check rather than given a weaker assertion.
    checked = [s for s in lines if s != 6]
    for i, a in enumerate(checked):
        for b in checked[i + 1 :]:
            assert lines[a] != lines[b], (
                f"patterns {a} and {b} produced identical scanlines at gate level, "
                "so the mux may not have survived synthesis"
            )
    dut._log.info(
        f"gate level: {len(checked)} patterns produced pairwise distinct scanlines "
        "(starfield excluded, it is sparse by construction)"
    )
