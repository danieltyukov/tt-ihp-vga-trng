"""What can honestly be checked against the hardened gate-level netlist.

Which is less than you would want, for a reason specific to this design.

src/ring_osc.v is a deliberate combinational loop, and it has to survive
synthesis or the TRNG does not exist, so the hardened netlist contains a five
inverter and a seven inverter ring. The IHP functional cell models are zero
delay: sg13g2_inv_1 is

    not (Y, A);
    specify (posedge A => (Y : A)) = (0.0,0.0); ... endspecify

so once rst_n releases and the enable NAND opens, an event driven simulator has a
zero delay feedback loop and stops advancing in time. That is inherent to gate
level simulation of any ring oscillator against zero delay models. It is not
fixable in the RTL, because the loop is the design.

So this module checks the part that is simulatable, which is everything up to the
moment the ring is enabled:

  - the netlist elaborates against the PDK cell models at all,
  - uio_oe reads exactly the 0b11100000 the RTL declares, through the tie cells,
    which confirms the netlist and the cell models are wired up correctly,
  - simulation advances normally while rst_n is low and the ring is gated off.

And it documents, as an executable observation rather than a claim, that the
outputs do not resolve out of X in this configuration.

The synchronous logic is verified at RTL by the 11 test suite in test.py, the
oscillator path structurally by test/tb_ring.v, and the survival of all 12 ring
stages through mapping by scripts/synth_report.sh, which fails the build if the
optimiser collapses either ring. The gl_test job is removed from gds.yaml with
this reasoning recorded there too.

Run with:  make -B GATES=yes   (after copying a netlist to gate_level_netlist.v)
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge


@cocotb.test()
async def test_gl_netlist_wiring(dut):
    """The netlist elaborates and its constant outputs are correct.

    uio_oe is driven entirely by sg13g2_tiehi and sg13g2_tielo cells with no flop
    and no clock in the path, so it is the one output that is meaningful before
    the ring oscillator makes time stop. Getting the right value out of it
    confirms the netlist, the PDK cell models and the port mapping all line up.
    """
    cocotb.start_soon(Clock(dut.clk, 39722, unit="ps").start())
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0

    # The ring is gated off while rst_n is low, so time advances normally here.
    await ClockCycles(dut.clk, 16)
    await FallingEdge(dut.clk)

    oe = dut.uio_oe.value
    assert oe.is_resolvable, (
        f"uio_oe is {oe!r}. It is driven only by tie cells, so an unresolved value "
        "means the netlist or the cell models are not wired up correctly."
    )
    assert int(oe) == 0b1110_0000, (
        f"uio_oe must be 0b11100000 as the RTL declares, got {int(oe):#010b}"
    )
    dut._log.info(f"gate level: uio_oe = {int(oe):#010b}, correct through the tie cells")

    # Recorded, not asserted: the sequential outputs do not resolve here. See the
    # module docstring. Asserting either way would be dishonest, so this logs what
    # is actually observed and leaves the verification to the RTL suite.
    uo = dut.uo_out.value
    dut._log.info(
        f"gate level: uo_out = {uo!r} "
        f"({'resolved' if uo.is_resolvable else 'unresolved, as documented'})"
    )
    dut._log.info(
        "Nothing past reset release is simulated: the ring oscillator is a zero "
        "delay combinational loop in the functional netlist. See the module "
        "docstring and .github/workflows/gds.yaml."
    )
