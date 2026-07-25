"""Regression for tt_um_danieltyukov_vga_trng.

Every test in here asserts. There is no cocotb.pass_test() anywhere and no test
whose body is unreachable. What is covered:

  test_reset                     outputs defined and deterministic after reset,
                                 and a mid frame reset returns to a known state
  test_vga_timing                numeric conformance of all eight 640x480
                                 timing intervals, both polarities, both totals
                                 and the implied frame rate, measured black box
                                 from the pins
  test_golden_frames             all eight patterns compared pixel exact against
                                 the independent model in test/model.py, and
                                 asserted pairwise distinct
  test_pattern_switch_mid_frame  sel changed mid frame: sync stays exact and the
                                 pixels really do change to the new pattern
  test_von_neumann               debiaser against a Python model on a known
                                 stream, plus the raw and debiased bias measured
  test_lfsr_sequence             conditioner state against a Python model
  test_lfsr_period               all 65536 states visited, seed does not recur
                                 early
  test_health_rct                repetition count test fires on a stuck source,
                                 at the right sample, for all four cutoffs
  test_health_apt                adaptive proportion test fires on a biased
                                 source that never trips the repetition test
  test_health_sticky             flags latch until cleared, and the conditioned
                                 output is gated while a failure is latched
  test_trng_statistics           long output stream characterised: bias, runs,
                                 byte chi-square. Bias is asserted within a
                                 documented bound.

The entropy source is the SIM_ENTROPY = 1 path, driven from uio_in[0]. The ring
oscillator path is covered separately by test/tb_ring.v because a delay
annotated inverter loop in an event simulator is a periodic square wave and
statistics measured through it would be a property of the timewheel. See
src/entropy_source.v.
"""

import random

import cocotb
from cocotb.triggers import ClockCycles, FallingEdge

import model as M
import tbutil as T

# Documented bound for the output bias assertion. For 262144 fair bits the
# standard error of the mean is 0.5/sqrt(262144) = 0.00098, so 0.01 is about
# ten sigma: loose enough never to flake, tight enough that a broken whitener
# or a stuck output fails it immediately.
BIAS_BOUND = 0.01

# 255 degrees of freedom. The chi-square critical value at p = 0.001 is 330.5;
# 2 * df is used as the assertion so a mildly non-uniform conditioner passes and
# a structurally broken one cannot.
CHI2_BOUND = 510.0


def max_run(bits):
    """Longest run of identical values in a bit list."""
    best = cur = 1
    for i in range(1, len(bits)):
        cur = cur + 1 if bits[i] == bits[i - 1] else 1
        best = max(best, cur)
    return best


def run_histogram(bits):
    """Map of run length to count over the whole sequence."""
    hist = {}
    cur, length = bits[0], 1
    for b in bits[1:]:
        if b == cur:
            length += 1
        else:
            hist[length] = hist.get(length, 0) + 1
            cur, length = b, 1
    hist[length] = hist.get(length, 0) + 1
    return hist


# ---------------------------------------------------------------------------
# 1. reset behaviour
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_reset(dut):
    model = await T.reset(dut, T.ui(sel=0))

    # Nothing on any output may be x or z after reset.
    for name, sig in (("uo_out", dut.uo_out), ("uio_out", dut.uio_out), ("uio_oe", dut.uio_oe)):
        val = sig.value
        assert val.is_resolvable, f"{name} contains x or z after reset: {val!r}"

    assert int(dut.uio_oe.value) == 0b1110_0000, (
        f"uio_oe must be 0b11100000, got {int(dut.uio_oe.value):#010b}"
    )

    # Reset state is pixel (0,0): active, so hsync and vsync both idle high.
    hs, vs, r, g, b = M.unpack_uo(int(dut.uo_out.value))
    assert (hs, vs) == (1, 1), f"both syncs must idle high at pixel 0,0, got hs={hs} vs={vs}"
    assert int(dut.uo_out.value) == model.uo_out(0), "reset pixel does not match the model"

    # Health flags clear, and the conditioned output is not stuck.
    assert int(dut.uio_out.value) & T.UIO_RCT_FAIL == 0, "RCT flag set straight out of reset"
    assert int(dut.uio_out.value) & T.UIO_APT_FAIL == 0, "APT flag set straight out of reset"

    # Reset is deterministic: run a while, reset again, compare.
    await T.bulk_step(dut, model, 3000)
    snap_a = int(dut.uo_out.value)

    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    model2 = M.Tile()
    assert int(dut.uo_out.value) == model2.uo_out(0), (
        "a mid frame reset must return the tile to the pixel (0,0) state"
    )
    lfsr = int(dut.user_project.u_trng.u_white.state.value)
    assert lfsr == M.LFSR_SEED, f"LFSR must reload its seed on reset, got {lfsr:#06x}"

    await T.bulk_step(dut, model2, 3000)
    snap_b = int(dut.uo_out.value)
    assert snap_a == snap_b, (
        f"the same number of clocks after reset must give the same pixel: "
        f"{snap_a:#04x} then {snap_b:#04x}"
    )
    dut._log.info("reset: outputs defined, uio_oe correct, mid frame reset returns to (0,0)")


# ---------------------------------------------------------------------------
# 2. VGA timing conformance, measured from the pins only
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_vga_timing(dut):
    """Derive all eight timing intervals from uo_out and check the numbers.

    Pattern 5 is used as the probe because every pixel of its visible area is
    non-black (white border, coloured box, two tone checkerboard background), so
    the black to non-black transition marks the active window exactly. No
    internal signal is read anywhere in this test.
    """
    model = await T.reset(dut, T.ui(sel=5))

    # ---- horizontal: sample every clock over four complete lines ----------
    # Start from a line well inside the visible area.
    await T.align_to_frame(dut, model)
    await T.bulk_step(dut, model, 100 * M.H_TOTAL)
    assert model.x == 0 and model.y == 100

    hs_trace, nonblack = [], []
    for _ in range(4 * M.H_TOTAL):
        v = int(dut.uo_out.value)
        hs, vs, r, g, b = M.unpack_uo(v)
        hs_trace.append(hs)
        nonblack.append(1 if (r or g or b) else 0)
        assert vs == 1, "vsync must be idle high on visible lines"
        await T.step(dut, model)

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

    hs_runs = runs(hs_trace)
    # first and last runs are partial, drop them
    hs_mid = hs_runs[1:-1]
    lows = [n for lvl, n in hs_mid if lvl == 0]
    highs = [n for lvl, n in hs_mid if lvl == 1]
    assert lows, "no hsync pulse seen in four lines"
    assert set(lows) == {M.H_SYNC}, f"hsync low width must be {M.H_SYNC}, measured {sorted(set(lows))}"
    assert set(highs) == {M.H_TOTAL - M.H_SYNC}, (
        f"hsync high width must be {M.H_TOTAL - M.H_SYNC}, measured {sorted(set(highs))}"
    )
    assert hs_trace[0] == 1, "hsync polarity is wrong: it must idle high and pulse low"

    nb_runs = runs(nonblack)
    active_widths = [n for lvl, n in nb_runs[1:-1] if lvl == 1]
    assert set(active_widths) == {M.H_ACTIVE}, (
        f"horizontal active must be {M.H_ACTIVE}, measured {sorted(set(active_widths))}"
    )

    # front porch = clocks from the end of active video to the start of sync,
    # back porch = clocks from the end of sync to the start of the next active.
    idx_active_end = None
    fronts, backs, totals = [], [], []
    prev_active_start = None
    for i in range(1, len(nonblack)):
        if nonblack[i - 1] == 1 and nonblack[i] == 0:
            idx_active_end = i
        if nonblack[i - 1] == 0 and nonblack[i] == 1:
            if prev_active_start is not None:
                totals.append(i - prev_active_start)
            prev_active_start = i
        if hs_trace[i - 1] == 1 and hs_trace[i] == 0 and idx_active_end is not None:
            fronts.append(i - idx_active_end)
        if hs_trace[i - 1] == 0 and hs_trace[i] == 1:
            nxt = next((j for j in range(i, len(nonblack)) if nonblack[j] == 1), None)
            if nxt is not None:
                backs.append(nxt - i)

    assert set(fronts) == {M.H_FRONT}, f"h front porch must be {M.H_FRONT}, measured {sorted(set(fronts))}"
    assert set(backs) == {M.H_BACK}, f"h back porch must be {M.H_BACK}, measured {sorted(set(backs))}"
    assert set(totals) == {M.H_TOTAL}, f"h total must be {M.H_TOTAL}, measured {sorted(set(totals))}"
    dut._log.info(
        f"horizontal: active={M.H_ACTIVE} front={sorted(set(fronts))[0]} "
        f"sync={sorted(set(lows))[0]} back={sorted(set(backs))[0]} total={sorted(set(totals))[0]}"
    )

    # ---- vertical: one sample per line for two whole frames ---------------
    # Start 300 lines into a frame so the trace contains two complete vertical
    # periods rather than starting exactly on an active run, which would leave
    # only one active-to-active transition and nothing to measure the total from.
    await T.align_to_frame(dut, model)
    await T.bulk_step(dut, model, 300 * M.H_TOTAL)
    assert model.x == 0 and model.y == 300

    line_active, line_vs = [], []
    for _ in range(2 * M.V_TOTAL):
        # sample at x = 300, comfortably inside the active window
        await T.bulk_step(dut, model, 300)
        v = int(dut.uo_out.value)
        hs, vs, r, g, b = M.unpack_uo(v)
        line_active.append(1 if (r or g or b) else 0)
        line_vs.append(vs)
        assert hs == 1, "hsync must be idle high at x = 300"
        await T.bulk_step(dut, model, M.H_TOTAL - 300)

    va_runs = runs(line_active)
    vs_runs = runs(line_vs)
    # first and last runs are partial, drop them
    active_heights = [n for lvl, n in va_runs[1:-1] if lvl == 1]
    assert active_heights, "no complete active region seen in two frames"
    assert set(active_heights) == {M.V_ACTIVE}, (
        f"vertical active must be {M.V_ACTIVE} lines, measured {sorted(set(active_heights))}"
    )
    vs_lows = [n for lvl, n in vs_runs[1:-1] if lvl == 0]
    assert vs_lows, "no vsync pulse seen in two frames"
    assert set(vs_lows) == {M.V_SYNC}, (
        f"vsync low width must be {M.V_SYNC} lines, measured {sorted(set(vs_lows))}"
    )
    assert line_vs[0] == 1, "vsync polarity is wrong: it must idle high and pulse low"

    v_fronts, v_backs, v_totals = [], [], []
    last_active_end = None
    prev_start = None
    for i in range(1, len(line_active)):
        if line_active[i - 1] == 1 and line_active[i] == 0:
            last_active_end = i
        if line_active[i - 1] == 0 and line_active[i] == 1:
            if prev_start is not None:
                v_totals.append(i - prev_start)
            prev_start = i
        if line_vs[i - 1] == 1 and line_vs[i] == 0 and last_active_end is not None:
            v_fronts.append(i - last_active_end)
        if line_vs[i - 1] == 0 and line_vs[i] == 1:
            nxt = next((j for j in range(i, len(line_active)) if line_active[j] == 1), None)
            if nxt is not None:
                v_backs.append(nxt - i)

    assert set(v_fronts) == {M.V_FRONT}, f"v front porch must be {M.V_FRONT}, measured {sorted(set(v_fronts))}"
    assert set(v_backs) == {M.V_BACK}, f"v back porch must be {M.V_BACK}, measured {sorted(set(v_backs))}"
    assert set(v_totals) == {M.V_TOTAL}, f"v total must be {M.V_TOTAL}, measured {sorted(set(v_totals))}"
    dut._log.info(
        f"vertical: active={M.V_ACTIVE} front={sorted(set(v_fronts))[0]} "
        f"sync={sorted(set(vs_lows))[0]} back={sorted(set(v_backs))[0]} total={sorted(set(v_totals))[0]}"
    )

    # ---- frame rate implied by the measured totals -------------------------
    clocks_per_frame = sorted(set(totals))[0] * sorted(set(v_totals))[0]
    assert clocks_per_frame == 800 * 525 == 420000
    fps = M.PIXEL_CLOCK_HZ / clocks_per_frame
    assert abs(fps - 60.0) < 0.1, (
        f"frame rate from {M.PIXEL_CLOCK_HZ} Hz over {clocks_per_frame} clocks is "
        f"{fps:.4f} Hz, which is not within 0.1 Hz of 60"
    )
    dut._log.info(f"frame rate: {clocks_per_frame} clocks per frame -> {fps:.4f} Hz")

    T.write_json(
        "timing.json",
        {
            "h": {"active": M.H_ACTIVE, "front": M.H_FRONT, "sync": M.H_SYNC, "back": M.H_BACK, "total": M.H_TOTAL},
            "v": {"active": M.V_ACTIVE, "front": M.V_FRONT, "sync": M.V_SYNC, "back": M.V_BACK, "total": M.V_TOTAL},
            "pixel_clock_hz": M.PIXEL_CLOCK_HZ,
            "clocks_per_frame": clocks_per_frame,
            "frame_rate_hz": round(fps, 4),
            "hsync_polarity": "negative",
            "vsync_polarity": "negative",
        },
    )


# ---------------------------------------------------------------------------
# 3. golden frame comparison, one frame per pattern
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_golden_frames(dut):
    """Capture a full frame per pattern and assert pixel exact model equality.

    uio_in[0] is held at 0 for the whole test. That makes every von Neumann
    pair (0,0), so the debiaser never emits, nothing is injected into the
    conditioner, and the LFSR free runs from its reset seed. The starfield is
    therefore exactly predictable, which is the only way to golden test it.
    """
    model = await T.reset(dut, T.ui(sel=0))
    frames = {}

    for sel in range(M.NUM_PATTERNS):
        await T.align_to_frame(dut, model)
        dut.ui_in.value = T.ui(sel=sel)
        await T.settle()
        frame_no = model.frame
        fb, mism = await T.capture_frame(dut, model, sel)
        name = M.PATTERN_NAMES[sel]
        assert not mism, (
            f"pattern {sel} ({name}) frame {frame_no}: "
            f"{len(mism)} mismatch(es), first few "
            + ", ".join(f"(x={x},y={y},f={f}) got {g:#04x} want {e:#04x}" for x, y, f, g, e in mism)
        )
        frames[name] = bytes(fb)
        T.write_frame(name, fb, {"sel": sel, "pattern": name, "frame": frame_no})
        dut._log.info(f"pattern {sel} {name}: frame {frame_no} matches the model on all 307200 pixels")

    # The point of having eight patterns is that they are eight patterns.
    names = list(frames)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            assert frames[names[i]] != frames[names[j]], (
                f"patterns {names[i]} and {names[j]} produced identical frames"
            )

    # And none of them may be a blank screen.
    for name, fb in frames.items():
        assert len(set(fb)) > 1, f"pattern {name} produced a single flat colour"
    dut._log.info(f"all {len(frames)} patterns are pairwise distinct and none is flat")


# ---------------------------------------------------------------------------
# 4. changing sel mid frame
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_pattern_switch_mid_frame(dut):
    """Switch sel in the middle of a visible line.

    Two things are asserted: the sync outputs follow the model on every single
    clock of the frame, including the clock the switch lands on, and the pixels
    before and after the switch match the old and the new pattern respectively.
    """
    sel_a, sel_b = 1, 3
    switch_y, switch_x = 200, 321

    model = await T.reset(dut, T.ui(sel=sel_a))
    await T.align_to_frame(dut, model)
    await T.bulk_step(dut, model, M.H_TOTAL)  # start the checked frame on line 1
    await T.align_to_frame(dut, model)

    sel = sel_a
    before_ok = after_ok = 0
    sync_errors = []
    pix_errors = []

    for line in range(M.V_TOTAL):
        for px in range(M.H_TOTAL):
            v = int(dut.uo_out.value)
            hs, vs, r, g, b = M.unpack_uo(v)
            if (hs, vs) != (model.hsync_n, model.vsync_n) and len(sync_errors) < 8:
                sync_errors.append((model.x, model.y, hs, vs, model.hsync_n, model.vsync_n))
            if model.active:
                exp = model.uo_out(sel)
                if v != exp:
                    if len(pix_errors) < 8:
                        pix_errors.append((model.x, model.y, sel, v, exp))
                elif sel == sel_a:
                    before_ok += 1
                else:
                    after_ok += 1
            await T.step(dut, model)
            if model.y == switch_y and model.x == switch_x and sel == sel_a:
                dut.ui_in.value = T.ui(sel=sel_b)
                await T.settle()
                sel = sel_b

    assert not sync_errors, (
        "changing sel disturbed the sync outputs: "
        + ", ".join(
            f"(x={x},y={y}) got hs={hs} vs={vs} want hs={ehs} vs={evs}"
            for x, y, hs, vs, ehs, evs in sync_errors
        )
    )
    assert not pix_errors, (
        "pixels do not follow the selected pattern across the switch: "
        + ", ".join(f"(x={x},y={y},sel={s}) got {g:#04x} want {e:#04x}" for x, y, s, g, e in pix_errors)
    )
    assert before_ok > 100000, f"only {before_ok} pixels checked against pattern {sel_a}"
    assert after_ok > 100000, f"only {after_ok} pixels checked against pattern {sel_b}"
    dut._log.info(
        f"switch at (x={switch_x}, y={switch_y}): {before_ok} pixels matched pattern "
        f"{sel_a}, {after_ok} matched pattern {sel_b}, sync exact on all 420000 clocks"
    )


# ---------------------------------------------------------------------------
# 5. von Neumann debiaser
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_von_neumann(dut):
    """Drive a known raw stream and compare the debiaser output bit for bit.

    Two streams are used: a hand written pattern that covers all four pair
    cases explicitly, and a long deliberately biased random stream that also
    measures the bias before and after debiasing.
    """
    model = await T.reset(dut, T.ui(samp_fast=1), rct_sel=3, apt_sel=3)
    vn = dut.user_project.u_trng.u_vn

    # 00 discard, 01 emit 0, 10 emit 1, 11 discard, then a mix.
    hand = [0, 0, 0, 1, 1, 0, 1, 1, 0, 1, 1, 0, 1, 1, 0, 0, 1, 0, 0, 1]
    got = []
    for bit in hand:
        dut.uio_in.value = T.uio(ent_bit=bit)
        await T.step(dut, model, ext_bit=bit, sample_fast=1)
        if int(vn.out_stb.value):
            got.append(int(vn.out_bit.value))
    # one more clock for the final pair's registered output
    await T.step(dut, model, ext_bit=hand[-1], sample_fast=1)
    if int(vn.out_stb.value):
        got.append(int(vn.out_bit.value))

    want = M.von_neumann_stream(hand)
    assert got == want, f"debiaser output {got} does not match the model {want}"
    dut._log.info(f"von Neumann on the hand written stream: {got} as expected")

    # Long biased stream: P(1) = 0.75, so raw bias is 0.25 and the debiased
    # stream should be essentially unbiased. Reset first, because the extra
    # clock above left the debiaser holding the first bit of a pair and the
    # pure function model pairs from index 0.
    model = await T.reset(dut, T.ui(samp_fast=1), rct_sel=3, apt_sel=3)
    rng = random.Random(0xC0FFEE)
    n = 20000
    raw_bits, out_bits = [], []
    for _ in range(n):
        bit = 1 if rng.random() < 0.75 else 0
        dut.uio_in.value = T.uio(ent_bit=bit)
        await T.step(dut, model, ext_bit=bit, sample_fast=1)
        raw_bits.append(bit)
        if int(vn.out_stb.value):
            out_bits.append(int(vn.out_bit.value))

    want_out = M.von_neumann_stream(raw_bits)
    # The DUT lags the pure function by at most one registered output.
    assert out_bits == want_out[: len(out_bits)], (
        "debiaser diverged from the model on the long biased stream at index "
        f"{next(i for i, (a, b) in enumerate(zip(out_bits, want_out)) if a != b)}"
    )
    assert len(want_out) - len(out_bits) <= 1, (
        f"debiaser dropped bits: model produced {len(want_out)}, DUT produced {len(out_bits)}"
    )

    raw_bias = sum(raw_bits) / len(raw_bits) - 0.5
    out_bias = sum(out_bits) / len(out_bits) - 0.5
    yield_ratio = len(out_bits) / len(raw_bits)
    assert abs(raw_bias) > 0.2, f"the raw stream was supposed to be biased, measured {raw_bias:+.4f}"
    assert abs(out_bias) < 0.02, (
        f"von Neumann failed to remove the bias: raw {raw_bias:+.4f} -> debiased {out_bias:+.4f}"
    )
    # p(1-p) = 0.1875 expected yield per input bit for p = 0.75
    assert 0.15 < yield_ratio < 0.23, f"debiaser yield {yield_ratio:.4f} is far from the expected 0.1875"
    dut._log.info(
        f"von Neumann on {n} biased samples: bias {raw_bias:+.4f} -> {out_bias:+.4f}, "
        f"yield {yield_ratio:.4f} against the theoretical 0.1875"
    )

    T.write_json(
        "debias.json",
        {
            "n_raw": len(raw_bits),
            "n_out": len(out_bits),
            "p_one_target": 0.75,
            "raw_bias": raw_bias,
            "debiased_bias": out_bias,
            "yield": yield_ratio,
            "theoretical_yield": 0.1875,
            "raw_ones": sum(raw_bits),
            "out_ones": sum(out_bits),
        },
    )


# ---------------------------------------------------------------------------
# 6. conditioner: sequence and period
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_lfsr_sequence(dut):
    """Compare the conditioner state against the Python model step by step,
    both free running and while entropy is being injected."""
    model = await T.reset(dut, T.ui(samp_fast=1))
    state = dut.user_project.u_trng.u_white.state

    assert int(state.value) == M.LFSR_SEED, (
        f"LFSR seed must be {M.LFSR_SEED:#06x}, got {int(state.value):#06x}"
    )

    # 4000 clocks with no injection (ext_bit held low so no pair ever differs)
    for i in range(4000):
        await T.step(dut, model, sample_fast=1)
        got, want = int(state.value), model.lfsr.s
        assert got == want, f"free running LFSR diverged at step {i}: {got:#06x} != {want:#06x}"
    dut._log.info("LFSR matches the model for 4000 free running steps")

    # 4000 clocks with a pseudorandom entropy stream, which exercises the
    # injection path and its one cycle of von Neumann latency.
    rng = random.Random(12345)
    for i in range(4000):
        bit = rng.getrandbits(1)
        dut.uio_in.value = T.uio(ent_bit=bit)
        await T.step(dut, model, ext_bit=bit, sample_fast=1)
        got, want = int(state.value), model.lfsr.s
        assert got == want, (
            f"LFSR diverged from the model at injection step {i}: {got:#06x} != {want:#06x}"
        )
    dut._log.info("LFSR matches the model for 4000 steps with entropy injection")


@cocotb.test()
async def test_lfsr_period(dut):
    """Walk the whole cycle. All 65536 states must be visited exactly once.

    The de Bruijn correction in src/lfsr_whitener.v folds the all-zero state
    into the cycle, so the period is 2^16 and not 2^16 - 1. Both facts are
    checked: the seed must not recur before step 65536, and it must recur
    exactly there.
    """
    model = await T.reset(dut, T.ui(samp_fast=1))
    state = dut.user_project.u_trng.u_white.state

    seen = bytearray(65536)
    first = int(state.value)
    seen[first] = 1
    saw_zero = False
    recur = None

    for i in range(1, 65537):
        await T.step(dut, model, sample_fast=1)
        s = int(state.value)
        if s == 0:
            saw_zero = True
        if s == first and recur is None:
            recur = i
            if i != 65536:
                break
        if seen[s] and s != first:
            raise AssertionError(f"state {s:#06x} repeated at step {i}, period is short")
        seen[s] = 1

    assert recur == 65536, f"seed recurred at step {recur}, expected exactly 65536"
    assert saw_zero, "the all-zero state was never visited, so the de Bruijn correction is not working"
    assert sum(seen) == 65536, f"only {sum(seen)} of 65536 states were visited"
    dut._log.info("LFSR visits all 65536 states including zero and repeats at exactly step 65536")


# ---------------------------------------------------------------------------
# 7. health tests
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_health_rct(dut):
    """Repetition count test on a stuck-at source, for every cutoff.

    The flag must fire on the sample that completes a run of exactly the cutoff
    length, and not one sample earlier.
    """
    for sel, cutoff in enumerate(M.RCT_CUTOFFS):
        model = await T.reset(dut, T.ui(samp_fast=1), rct_sel=sel, apt_sel=3)
        stuck = sel & 1  # alternate stuck-at-0 and stuck-at-1 across cutoffs
        dut.uio_in.value = T.uio(ent_bit=stuck, rct_sel=sel, apt_sel=3)

        fired_at = None
        for n in range(1, cutoff + 4):
            await T.step(dut, model, ext_bit=stuck, sample_fast=1)
            flag = bool(int(dut.uio_out.value) & T.UIO_RCT_FAIL)
            assert flag == bool(model.health.rct_fail), (
                f"RCT cutoff {cutoff}: DUT flag {flag} disagrees with the model at sample {n}"
            )
            if flag and fired_at is None:
                fired_at = n
        # The run length including the current sample is compared against the
        # cutoff on the same edge, so the flag becomes visible immediately after
        # the sample that completes a run of exactly `cutoff`.
        assert fired_at is not None, f"RCT cutoff {cutoff}: flag never fired on a stuck-at-{stuck} source"
        assert fired_at == cutoff, (
            f"RCT cutoff {cutoff}: flag fired after {fired_at} samples, expected {cutoff}"
        )
        assert M.rct_expected_fail([stuck] * cutoff, cutoff), "model disagrees that this should fail"
        assert not M.rct_expected_fail([stuck] * (cutoff - 1), cutoff), (
            "a run one sample short of the cutoff must not be a failure"
        )
        dut._log.info(f"RCT cutoff {cutoff}: fired on the run of {cutoff} stuck-at-{stuck} samples")

    # A source that never repeats must not trip the test at all.
    model = await T.reset(dut, T.ui(samp_fast=1), rct_sel=0, apt_sel=3)
    for n in range(400):
        bit = n & 1
        dut.uio_in.value = T.uio(ent_bit=bit, rct_sel=0, apt_sel=3)
        await T.step(dut, model, ext_bit=bit, sample_fast=1)
        assert not (int(dut.uio_out.value) & T.UIO_RCT_FAIL), (
            f"RCT false positive on a perfectly alternating source at sample {n}"
        )
    assert not M.rct_expected_fail([n & 1 for n in range(400)], 4)
    dut._log.info("RCT at its tightest cutoff of 4 does not fire on an alternating source")


@cocotb.test()
async def test_health_apt(dut):
    """Adaptive proportion test on a heavily biased source.

    The stream is 15 ones then a zero, repeated: 60 ones in every window of 64,
    with a longest run of 15. That is well short of the repetition count cutoff
    of 32 used here, so the repetition test provably cannot catch this source and
    only the proportion test can. The repetition flag is asserted to stay clear
    throughout, which is what makes the two tests demonstrably independent.
    """
    rng = random.Random(4242)
    pattern = ([1] * 15 + [0]) * 8
    assert max_run(pattern) == 15, "the biased stream must not contain a long run"
    assert not M.rct_expected_fail(pattern, 32), (
        "the biased stream must be invisible to the repetition test at cutoff 32"
    )

    for sel, cutoff in ((0, 40), (1, 48), (2, 56)):
        model = await T.reset(dut, T.ui(samp_fast=1), rct_sel=3, apt_sel=sel)
        fired = False
        i = -1
        for i, bit in enumerate(pattern):
            dut.uio_in.value = T.uio(ent_bit=bit, rct_sel=3, apt_sel=sel)
            await T.step(dut, model, ext_bit=bit, sample_fast=1)
            flags = int(dut.uio_out.value)
            assert not (flags & T.UIO_RCT_FAIL), (
                f"APT cutoff {cutoff}: the repetition test fired at sample {i}, so this "
                "stream does not isolate the proportion test"
            )
            assert bool(flags & T.UIO_APT_FAIL) == bool(model.health.apt_fail), (
                f"APT cutoff {cutoff}: DUT flag disagrees with the model at sample {i}"
            )
            if flags & T.UIO_APT_FAIL:
                fired = True
                break
        assert fired, f"APT cutoff {cutoff}: flag never fired on a stream with 60 ones per 64"
        assert M.apt_expected_fail(pattern, cutoff), "model disagrees that this should fail"
        assert i + 1 >= M.APT_WINDOW, f"APT fired at sample {i + 1}, before a full window of {M.APT_WINDOW}"
        dut._log.info(f"APT cutoff {cutoff}: fired at sample {i + 1} on 60-of-64 bias")

    # The loosest cutoff of 62 must not fire on this stream: 60 is not > 62.
    model = await T.reset(dut, T.ui(samp_fast=1), rct_sel=3, apt_sel=3)
    for bit in pattern:
        dut.uio_in.value = T.uio(ent_bit=bit, rct_sel=3, apt_sel=3)
        await T.step(dut, model, ext_bit=bit, sample_fast=1)
        assert not (int(dut.uio_out.value) & T.UIO_APT_FAIL), (
            "APT cutoff 62 fired on 60-of-64, which is inside the cutoff"
        )
    assert not M.apt_expected_fail(pattern, 62)
    dut._log.info("APT cutoff 62 correctly ignores 60-of-64 bias")

    # An unbiased source must not trip it, and the RCT must stay quiet too so
    # the two tests are demonstrably independent.
    model = await T.reset(dut, T.ui(samp_fast=1), rct_sel=3, apt_sel=3)
    bits = [rng.getrandbits(1) for _ in range(4096)]
    for i, bit in enumerate(bits):
        dut.uio_in.value = T.uio(ent_bit=bit, rct_sel=3, apt_sel=3)
        await T.step(dut, model, ext_bit=bit, sample_fast=1)
        flags = int(dut.uio_out.value)
        assert not (flags & T.UIO_APT_FAIL), f"APT false positive on a fair source at sample {i}"
        assert not (flags & T.UIO_RCT_FAIL), f"RCT false positive on a fair source at sample {i}"
    assert not M.apt_expected_fail(bits, 62)
    assert not M.rct_expected_fail(bits, 32)
    dut._log.info("neither health test fires on 4096 fair samples at the loosest cutoffs")


@cocotb.test()
async def test_health_sticky(dut):
    """The flags latch after the fault has gone, the clear input works, and a
    latched failure gates the conditioned output.

    The key part is the second phase: the source is switched to a perfectly
    alternating stream, so the failure condition is provably absent and the flag
    can only still be set because it latched.
    """
    state = dut.user_project.u_trng.u_white.state
    model = await T.reset(dut, T.ui(samp_fast=1), rct_sel=0, apt_sel=3)
    dut.uio_in.value = T.uio(ent_bit=0, rct_sel=0, apt_sel=3)

    # Phase 1: stick the source at 0 until the cutoff-4 repetition test trips.
    for _ in range(6):
        await T.step(dut, model, ext_bit=0, sample_fast=1)
    assert int(dut.uio_out.value) & T.UIO_RCT_FAIL, "RCT did not fire on a stuck source"

    # Phase 2: healthy alternating source. The run length is 1 on every sample,
    # so nothing can be re-triggering the flag. It must stay set anyway, and the
    # conditioned output must stay gated while it is.
    lfsr_high_seen = 0
    for i in range(256):
        bit = i & 1
        dut.uio_in.value = T.uio(ent_bit=bit, rct_sel=0, apt_sel=3)
        await T.step(dut, model, ext_bit=bit, sample_fast=1)
        if (int(state.value) >> 15) & 1:
            lfsr_high_seen += 1
        flags = int(dut.uio_out.value)
        assert flags & T.UIO_RCT_FAIL, (
            f"the RCT flag is not sticky: it cleared itself at sample {i} on a healthy source"
        )
        assert not (flags & T.UIO_RND), (
            f"the conditioned output must be gated while a health failure is latched, "
            f"but it was high at sample {i}"
        )
    assert lfsr_high_seen > 64, (
        f"the LFSR only had bit 15 set {lfsr_high_seen} times in 256 clocks, so the "
        "gating assertion above did not actually prove anything"
    )
    dut._log.info(
        f"flag stayed latched through 256 healthy samples and gated the output on "
        f"{lfsr_high_seen} clocks where the LFSR output bit was 1"
    )

    # Phase 3: clear it while the source stays healthy.
    dut.ui_in.value = T.ui(samp_fast=1, health_clr=1)
    for i in range(4):
        bit = i & 1
        dut.uio_in.value = T.uio(ent_bit=bit, rct_sel=0, apt_sel=3)
        await T.step(dut, model, ext_bit=bit, sample_fast=1, health_clr=1)
    assert not (int(dut.uio_out.value) & T.UIO_RCT_FAIL), "HEALTH_CLR did not clear the RCT flag"
    assert not model.health.rct_fail, "the model disagrees that the flag should be clear"

    # Phase 4: release the clear. The flag stays clear and the output ungates.
    dut.ui_in.value = T.ui(samp_fast=1, health_clr=0)
    rnd_seen = 0
    for i in range(64):
        bit = i & 1
        dut.uio_in.value = T.uio(ent_bit=bit, rct_sel=0, apt_sel=3)
        await T.step(dut, model, ext_bit=bit, sample_fast=1)
        assert not (int(dut.uio_out.value) & T.UIO_RCT_FAIL), "RCT re-fired on a healthy source"
        if int(dut.uio_out.value) & T.UIO_RND:
            rnd_seen += 1
    assert rnd_seen > 10, f"the conditioned output stayed low after clearing ({rnd_seen} ones in 64)"
    dut._log.info(f"after clearing, the output ungated and produced {rnd_seen} ones in 64 clocks")


# ---------------------------------------------------------------------------
# 8. statistical characterisation of the conditioned output
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_trng_statistics(dut):
    """Collect a long output stream and characterise it.

    Read the header of this file and the README before drawing conclusions
    from these numbers. The entropy input here is a Python
    pseudorandom generator driven into uio_in[0], so what is being measured is
    the debiaser and the LFSR conditioner, not silicon entropy. The value of
    the test is that a broken conditioner, a stuck output or a wrong tap set
    all fail it.
    """
    n_bits = 262144
    await T.reset(dut, T.ui(samp_fast=1), rct_sel=3, apt_sel=3)
    rng = random.Random(0xBADC0DE)

    bits = bytearray(n_bits)
    ent_bits = bytearray(n_bits)
    for i in range(n_bits):
        ent = rng.getrandbits(1)
        ent_bits[i] = ent
        dut.uio_in.value = T.uio(ent_bit=ent, rct_sel=3, apt_sel=3)
        await FallingEdge(dut.clk)
        v = int(dut.uio_out.value)
        bits[i] = (v >> 7) & 1
        assert not (v & (T.UIO_RCT_FAIL | T.UIO_APT_FAIL)), (
            f"a health test fired on a fair source at sample {i}, so the output "
            "would have been gated and every number below would be meaningless"
        )

    ones = sum(bits)
    bias = ones / n_bits - 0.5
    assert abs(bias) < BIAS_BOUND, (
        f"output bias {bias:+.5f} exceeds the documented bound of {BIAS_BOUND}"
        f" ({ones} ones in {n_bits} bits)"
    )

    # runs
    run_hist = run_histogram(bits)
    total_runs = sum(run_hist.values())
    # For a fair stream, half of all runs have length 1, a quarter length 2, ...
    frac1 = run_hist.get(1, 0) / total_runs
    assert 0.45 < frac1 < 0.55, (
        f"{frac1:.4f} of runs have length 1, expected about 0.5; the output is "
        "either correlated or over-alternating"
    )
    assert max(run_hist) < 40, f"longest run is {max(run_hist)} bits, which is far past plausible"

    # byte value chi-square over non-overlapping bytes
    n_bytes = n_bits // 8
    hist = [0] * 256
    for i in range(n_bytes):
        v = 0
        for j in range(8):
            v = (v << 1) | bits[i * 8 + j]
        hist[v] += 1
    expected = n_bytes / 256.0
    chi2 = sum((c - expected) ** 2 / expected for c in hist)
    assert chi2 < CHI2_BOUND, (
        f"byte value chi-square {chi2:.1f} over 255 degrees of freedom exceeds "
        f"the bound of {CHI2_BOUND}; the byte distribution is not uniform"
    )
    assert min(hist) > 0, "some byte value never appeared in 32768 bytes"

    dut._log.info(
        f"statistics over {n_bits} bits: bias {bias:+.5f} (bound {BIAS_BOUND}), "
        f"{total_runs} runs with {frac1:.4f} of length 1, longest {max(run_hist)}, "
        f"byte chi-square {chi2:.1f} over 255 df (bound {CHI2_BOUND})"
    )

    T.write_json(
        "stats.json",
        {
            "n_bits": n_bits,
            "ones": ones,
            "bias": bias,
            "bias_bound": BIAS_BOUND,
            "runs": {str(k): v for k, v in sorted(run_hist.items())},
            "total_runs": total_runs,
            "frac_runs_len1": frac1,
            "byte_hist": hist,
            "n_bytes": n_bytes,
            "chi2": chi2,
            "chi2_df": 255,
            "chi2_bound": CHI2_BOUND,
            "bias_window": 4096,
            "bias_over_time": [
                sum(bits[k : k + 4096]) / 4096 - 0.5 for k in range(0, n_bits, 4096)
            ],
            "entropy_input_bias": sum(ent_bits) / n_bits - 0.5,
            "note": (
                "The entropy input for this run came from a Python pseudorandom "
                "generator on uio_in[0]. These numbers characterise the debiaser "
                "and the LFSR conditioner, not silicon entropy."
            ),
        },
    )
