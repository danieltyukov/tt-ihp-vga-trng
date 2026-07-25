"""Netlist specific checks that run before the regression at gate level.

The regression itself is test.py, which runs unchanged against the hardened
netlist. This module checks the two things test.py cannot, because they are
properties of the netlist rather than of the design:

  1. The constant outputs. uio_oe comes entirely from sg13g2_tiehi and
     sg13g2_tielo cells with no flop and no clock in the path, so it is the one
     output whose correct value proves the netlist, the PDK cell models and the
     port mapping all line up before any sequential behaviour is involved.

  2. That the ring oscillator force in test/tb.v left the entropy path in the
     state the rest of the run assumes. test.py drives a known entropy stream
     into uio_in[0] and compares the debiaser and the conditioner bit for bit
     against test/model.py, which is only valid if the sampled oscillator bit is
     a constant 0 so that raw_bit = 0 ^ ext_bit. That follows from the force, but
     "follows from" is not the same as "was checked", so it is checked here:
     every chain net, both settled ring outputs, and the synchroniser output that
     feeds the sampler.

Both rings are held broken for the whole gate level run, so the oscillator path
itself is not verified here and cannot be. See test/tb.v for why an event driven
simulator cannot run a zero delay ring at all, src/entropy_source.v for why a
delay annotated one would prove nothing about randomness, and test/tb_ring.v for
the structural check that does cover it.

Run with:  ./scripts/run_gl.sh
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge

import tbutil as T

# Stage counts from src/entropy_source.v: coprime, both odd.
STAGES_A = 5
STAGES_B = 7


def chain(dut, ring, i):
    return T.net(dut, f"u_trng.u_src.g_ring_source.u_osc_{ring}.chain[{i}]")


@cocotb.test()
async def test_gl_tie_cells(dut):
    """uio_oe is correct through the tie cells, before any clock edge matters."""
    cocotb.start_soon(Clock(dut.clk, T.CLOCK_PS, unit="ps").start())
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 4)
    await FallingEdge(dut.clk)

    oe = dut.uio_oe.value
    assert oe.is_resolvable, (
        f"uio_oe is {oe!r}. It is driven only by tie cells, so an unresolved value "
        "means the netlist or the PDK cell models are not wired up correctly."
    )
    assert int(oe) == 0b1110_0000, (
        f"uio_oe must be 0b11100000 as the RTL declares, got {int(oe):#010b}"
    )
    dut._log.info(f"uio_oe = {int(oe):#010b} through the tie cells")


@cocotb.test()
async def test_gl_rings_are_broken_as_documented(dut):
    """The forced rings settle where test.py needs them to.

    Every chain net must be resolved and alternating from the forced node, both
    ring outputs must be 0, and the two stage synchroniser that samples them must
    settle to 0, which is what makes raw_bit equal to uio_in[0].
    """
    cocotb.start_soon(Clock(dut.clk, T.CLOCK_PS, unit="ps").start())
    dut.ena.value = 1
    dut.ui_in.value = T.ui(samp_fast=1)
    dut.uio_in.value = T.uio(ent_bit=0)
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 8)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    # Long enough for the two synchroniser flops and the /8 prescaler.
    await ClockCycles(dut.clk, 32, rising=False)

    for ring, stages in (("a", STAGES_A), ("b", STAGES_B)):
        for i in range(stages):
            v = chain(dut, ring, i).value
            assert v.is_resolvable, (
                f"ring {ring} chain[{i}] is {v!r}. The force in test/tb.v is meant to "
                "resolve the whole chain; an x here means it did not take, and the "
                "simulation is about to stop advancing in time."
            )
            # chain[0] is forced low and each later stage is one more inversion.
            want = i & 1
            assert int(v) == want, (
                f"ring {ring} chain[{i}] is {int(v)}, expected {want} from a chain "
                "forced low at stage 0"
            )

    osc_a = int(chain(dut, "a", STAGES_A - 1).value)
    osc_b = int(chain(dut, "b", STAGES_B - 1).value)
    assert (osc_a, osc_b) == (0, 0), (
        f"both ring outputs must settle to 0, got osc_a={osc_a} osc_b={osc_b}. "
        "test.py's entropy comparisons assume raw_bit = 0 ^ ext_bit."
    )

    sync_q = T.net(dut, "u_trng.u_src.g_ring_source.sync_q").value
    assert sync_q.is_resolvable and int(sync_q) == 0, (
        f"the entropy synchroniser output must be 0 with both rings held broken, "
        f"got {sync_q!r}"
    )
    dut._log.info(
        "rings held broken: osc_a = osc_b = 0, sampled bit = 0, so raw_bit is "
        "exactly uio_in[0] and the regression's model comparisons are valid"
    )
