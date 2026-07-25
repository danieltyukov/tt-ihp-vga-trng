"""Frame sequence capture for the animated images in docs/img.

This is separate from test.py because it is slow: every frame is 420000 pixel
clocks and Icarus runs this design at roughly 30000 clocks per second, so a
frame costs about 14 seconds no matter how few pixels are read. The regression
should not pay for that.

Everything captured here is still checked against test/model.py, so these are
real tests as well as image sources. Run with:

    make -C test capture       (or make images, which runs it for you)

Two sequences are produced:

  anim/     32 consecutive frames of the ripple pattern, for the animation GIF
  switch/   32 frames with RAND_EN set and FAST_SW set, so the TRNG reselects
            the pattern every 8 frames. Entropy is driven into uio_in[0] during
            vertical blanking, which is where it has to arrive to influence the
            reselect at the frame boundary. The pattern the DUT chose is read
            back from sel_rand and asserted against the model, then used as the
            expected pattern for the pixel comparison.
"""

import random

import cocotb

import model as M
import tbutil as T

N_ANIM = 32
N_SWITCH = 32
ANIM_SEL = 3  # ripple: the rings move one step per frame


@cocotb.test()
async def capture_animation(dut):
    """32 consecutive ripple frames, each verified against the model."""
    model = await T.reset(dut, T.ui(sel=ANIM_SEL))
    await T.align_to_frame(dut, model)

    for i in range(N_ANIM):
        frame_no = model.frame
        fb, mism = await T.capture_frame(dut, model, ANIM_SEL)
        assert not mism, f"animation frame {i} (frame counter {frame_no}): {mism}"
        T.write_frame(
            f"{i:03d}",
            fb,
            {"sel": ANIM_SEL, "pattern": M.PATTERN_NAMES[ANIM_SEL], "frame": frame_no},
            subdir="anim",
        )
        if i % 8 == 0:
            dut._log.info(f"animation frame {i}/{N_ANIM} (frame counter {frame_no}) verified")
    dut._log.info(f"captured and verified {N_ANIM} ripple frames")


@cocotb.test()
async def capture_trng_switching(dut):
    """32 frames of TRNG driven pattern selection, each verified.

    FAST_SW makes the reselect happen every 8 frames, so 32 frames contain four
    reselects. The pattern index is not chosen by the testbench: it is read out
    of the DUT's sel_rand register, asserted equal to the model's, and then used
    as the expected pattern for the pixel comparison. If the selection logic and
    the model disagreed by even one reselect, every pixel of the following frame
    would mismatch.
    """
    rng = random.Random(0x5EED)
    ui_val = T.ui(rand_en=1, fast_sw=1, samp_fast=1)
    model = await T.reset(dut, ui_val)
    await T.align_to_frame(dut, model)

    seq = []
    for i in range(N_SWITCH):
        frame_no = model.frame
        dut_sel = int(dut.user_project.sel_rand.value)
        assert dut_sel == model.sel_rand, (
            f"frame {i}: DUT selected pattern {dut_sel} but the model says "
            f"{model.sel_rand}, so the TRNG select path diverged"
        )
        fb, mism = await T.capture_frame(
            dut,
            model,
            dut_sel,
            ext_fn=lambda: rng.getrandbits(1),
            sample_fast=1,
        )
        assert not mism, f"switching frame {i} (sel {dut_sel}): {mism}"
        seq.append(dut_sel)
        T.write_frame(
            f"{i:03d}",
            fb,
            {
                "sel": dut_sel,
                "pattern": M.PATTERN_NAMES[dut_sel],
                "frame": frame_no,
                "rand_en": 1,
            },
            subdir="switch",
        )
        if i % 8 == 0:
            dut._log.info(f"switching frame {i}/{N_SWITCH}: TRNG selected {dut_sel} "
                          f"({M.PATTERN_NAMES[dut_sel]})")

    distinct = sorted(set(seq))
    assert len(distinct) >= 2, (
        f"the TRNG held the same pattern for all {N_SWITCH} frames ({seq[0]}), so "
        "the reselect never took effect"
    )
    # Reselect fires when frame_cnt[2:0] == 7, so the value may only change on a
    # frame whose index is a multiple of 8 relative to the first reselect.
    changes = [i for i in range(1, len(seq)) if seq[i] != seq[i - 1]]
    for i in changes:
        assert (i % 8) == (changes[0] % 8), (
            f"pattern changed at frame {i}, which is not on the 8 frame reselect "
            f"boundary established at frame {changes[0]}"
        )
    dut._log.info(
        f"TRNG selection over {N_SWITCH} frames: {seq}, "
        f"{len(distinct)} distinct patterns, changes at frames {changes}"
    )
    T.write_json("switch_seq.json", {"sequence": seq, "changes": changes, "fast_sw": 1})
