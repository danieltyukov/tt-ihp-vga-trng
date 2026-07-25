"""Independent Python reference model of tt_um_danieltyukov_vga_trng.

This is written from the design intent, not transliterated from the Verilog, and
it is the thing the RTL is compared against pixel by pixel. Every quirk the RTL
has on purpose is reproduced here on purpose, and each one is called out where it
happens (the off-by-one absolute value in the ripple, the de Bruijn correction in
the LFSR, the "emit the first bit of the pair" von Neumann convention).

Nothing in here imports cocotb, so it can be exercised standalone:

    .venv/bin/python -m pytest test/test_model.py
"""

# ---------------------------------------------------------------------------
# VGA 640x480 @ 59.94 Hz
# ---------------------------------------------------------------------------
H_ACTIVE, H_FRONT, H_SYNC, H_BACK = 640, 16, 96, 48
V_ACTIVE, V_FRONT, V_SYNC, V_BACK = 480, 10, 2, 33
H_TOTAL = H_ACTIVE + H_FRONT + H_SYNC + H_BACK  # 800
V_TOTAL = V_ACTIVE + V_FRONT + V_SYNC + V_BACK  # 525
H_SYNC_ON, H_SYNC_OFF = H_ACTIVE + H_FRONT, H_ACTIVE + H_FRONT + H_SYNC
V_SYNC_ON, V_SYNC_OFF = V_ACTIVE + V_FRONT, V_ACTIVE + V_FRONT + V_SYNC

PIXEL_CLOCK_HZ = 25_175_000
LFSR_SEED = 0xACE1

NUM_PATTERNS = 8
PATTERN_NAMES = [
    "xor_field",
    "smpte_bars",
    "sierpinski",
    "ripple",
    "plasma",
    "bouncing_box",
    "starfield",
    "rule30",
]


# ---------------------------------------------------------------------------
# TinyVGA PMOD packing. uo_out = {hsync, B0, G0, R0, vsync, B1, G1, R1}
# ---------------------------------------------------------------------------
def pack_uo(hsync_n, vsync_n, r, g, b):
    """Build the expected uo_out byte from sync levels and 2 bit channels."""
    return (
        (hsync_n << 7)
        | ((b & 1) << 6)
        | ((g & 1) << 5)
        | ((r & 1) << 4)
        | (vsync_n << 3)
        | (((b >> 1) & 1) << 2)
        | (((g >> 1) & 1) << 1)
        | ((r >> 1) & 1)
    )


def unpack_uo(v):
    """Inverse of pack_uo. Returns (hsync_n, vsync_n, r, g, b)."""
    hsync_n = (v >> 7) & 1
    vsync_n = (v >> 3) & 1
    r = (((v >> 0) & 1) << 1) | ((v >> 4) & 1)
    g = (((v >> 1) & 1) << 1) | ((v >> 5) & 1)
    b = (((v >> 2) & 1) << 1) | ((v >> 6) & 1)
    return hsync_n, vsync_n, r, g, b


RGB666_TO_RGB888 = [0, 85, 170, 255]


def to_rgb888(r, g, b):
    return (RGB666_TO_RGB888[r], RGB666_TO_RGB888[g], RGB666_TO_RGB888[b])


# ---------------------------------------------------------------------------
# Stateless patterns
# ---------------------------------------------------------------------------
def pat_xor(x, y, frame):
    t = (((x & 0xFF) ^ (y & 0xFF)) + frame) & 0xFF
    return ((t >> 6) & 3, (t >> 4) & 3, (t >> 2) & 3)


BAR_PALETTE = [
    (3, 3, 3),  # white
    (3, 3, 0),  # yellow
    (0, 3, 3),  # cyan
    (0, 3, 0),  # green
    (3, 0, 3),  # magenta
    (3, 0, 0),  # red
    (0, 0, 3),  # blue
    (0, 0, 0),  # black
]


def pat_bars(x, y, frame):
    q = (x >> 4) & 0x3F
    # (x >> 4) / 5, done as a compare chain in hardware
    bar = 0
    for thresh, val in ((35, 7), (30, 6), (25, 5), (20, 4), (15, 3), (10, 2), (5, 1)):
        if q >= thresh:
            bar = val
            break
    idx = (bar + ((frame >> 5) & 7)) & 7
    if ((y >> 8) & 1) and ((y >> 7) & 1):  # y >= 384 for y < 512
        lum = (x >> 7) & 3
        return (lum, lum, lum)
    return BAR_PALETTE[idx]


def pat_sierp(x, y, frame):
    a = (x & 0x1FF) & (y & 0x1FF)
    g0 = a == 0
    g1 = (a & 0x3F) == 0
    g2 = (a & 0x07) == 0
    f = (frame >> 6) & 3
    r = 3 if g0 else 2 if g1 else 1 if g2 else 0
    g = f if g0 else (1 if g1 else 0)
    b = (~f) & 3 if g0 else (2 if g2 else 0)
    return (r, g, b)


def pat_ripple(x, y, frame):
    dx = (x - 320) & 0x3FF
    dy = (y - 240) & 0x3FF
    # ~d rather than -d: one pixel of asymmetry, two fewer incrementers.
    ax = (~dx) & 0x1FF if (dx >> 9) & 1 else dx & 0x1FF
    ay = (~dy) & 0x1FF if (dy >> 9) & 1 else dy & 0x1FF
    d = (ax + ay) & 0x3FF
    p = (d - frame) & 0xFF
    return ((p >> 6) & 3, (p >> 5) & 3, (p >> 4) & 3)


# Rising quarter of a sine, 8 entries of 3 bits. See src/sine_q.v.
SINE_QLUT = [0, 2, 3, 5, 6, 7, 7, 7]


def sine_q(phase):
    phase &= 0x1F
    f = (~phase) & 7 if (phase >> 3) & 1 else phase & 7
    q = SINE_QLUT[f]
    return (7 - q) if (phase >> 4) & 1 else (8 + q)


def pat_plasma(x, y, frame):
    ph0 = (((x >> 4) & 0x1F) + ((frame >> 1) & 0x1F)) & 0x1F
    ph1 = (((y >> 4) & 0x1F) - ((frame >> 2) & 0x1F)) & 0x1F
    ph2 = (((x >> 3) & 0x1F) + ((y >> 3) & 0x1F)) & 0x1F
    s = sine_q(ph0) + sine_q(ph1) + sine_q(ph2)
    return ((s >> 4) & 3, (s >> 3) & 3, (s >> 2) & 3)


def pat_stars(rnd):
    star = (rnd & 0x3FF) == 0
    lum = 3 if (rnd >> 12) & 1 else 1
    tint = (rnd >> 13) & 7
    en = 7 if tint == 0 else tint
    return (
        lum if star and (en >> 2) & 1 else 0,
        lum if star and (en >> 1) & 1 else 0,
        lum if star and (en >> 0) & 1 else 0,
    )


# ---------------------------------------------------------------------------
# Stateful patterns
# ---------------------------------------------------------------------------
BOX_PALETTE = [(3, 0, 0), (0, 3, 0), (1, 1, 3), (3, 3, 0)]
BOX_X_MAX = 608  # 640 - 32
BOX_Y_MAX = 448  # 480 - 32


class BouncingBox:
    """32x32 box, 2 pixels per frame, colour cycles on every wall collision."""

    def __init__(self):
        self.x = 100
        self.y = 80
        self.dx = 1
        self.dy = 1
        self.col = 0

    def step(self):
        bounce_x = self.x >= BOX_X_MAX - 2 if self.dx else self.x <= 2
        bounce_y = self.y >= BOX_Y_MAX - 2 if self.dy else self.y <= 2
        self.x = (self.x + 2 if self.dx else self.x - 2) & 0x3FF
        self.y = (self.y + 2 if self.dy else self.y - 2) & 0x3FF
        if bounce_x:
            self.dx ^= 1
        if bounce_y:
            self.dy ^= 1
        if bounce_x or bounce_y:
            self.col = (self.col + 1) & 3

    def pixel(self, x, y):
        rel_x = (x - self.x) & 0x3FF
        rel_y = (y - self.y) & 0x3FF
        in_box = (rel_x >> 5) == 0 and (rel_y >> 5) == 0
        border = (x >> 3) == 0 or (x >> 3) == 79 or (y >> 3) == 0 or (y >> 3) == 59
        if border:
            return (3, 3, 3)
        if in_box:
            return BOX_PALETTE[self.col]
        return (0, 0, 1) if ((x >> 5) & 1) ^ ((y >> 5) & 1) else (1, 0, 1)


class Rule30:
    """40 cell rule 30 automaton, one generation every 32 scanlines."""

    N = 40
    MASK = (1 << 40) - 1
    SEED = 1 << 20
    LINES_PER_GEN = 32

    def __init__(self):
        self.row = self.SEED

    def reset(self):
        self.row = self.SEED

    def step(self):
        c = self.row
        left = ((c << 1) | ((c >> (self.N - 1)) & 1)) & self.MASK
        right = ((c >> 1) | ((c & 1) << (self.N - 1))) & self.MASK
        self.row = (left ^ (c | right)) & self.MASK

    def pixel(self, x, frame):
        on = (self.row >> (x >> 4)) & 1 if (x >> 4) < self.N else 0
        if on:
            sh = (frame >> 6) & 3
            return (sh, sh, 3)
        return (0, 0, 0)


# ---------------------------------------------------------------------------
# Entropy pipeline
# ---------------------------------------------------------------------------
class Lfsr:
    """x^16 + x^15 + x^13 + x^4 + 1 with the de Bruijn all-zero correction."""

    def __init__(self, seed=LFSR_SEED):
        self.s = seed & 0xFFFF

    def feedback(self, inject=0):
        s = self.s
        return (
            ((s >> 15) & 1)
            ^ ((s >> 14) & 1)
            ^ ((s >> 12) & 1)
            ^ ((s >> 3) & 1)
            ^ (1 if (s & 0x7FFF) == 0 else 0)
            ^ (inject & 1)
        )

    def step(self, inject=0):
        self.s = ((self.s << 1) | self.feedback(inject)) & 0xFFFF
        return self.s

    @property
    def out_bit(self):
        return (self.s >> 15) & 1


class VonNeumann:
    """Emits the first bit of every unequal pair, discards equal pairs.

    Registered outputs, so out_stb is asserted the clock after the pair
    completes. That one cycle of latency matters for the LFSR injection timing
    and is modelled explicitly in Tile.step.
    """

    def __init__(self):
        self.have_first = 0
        self.first_bit = 0
        self.out_bit = 0
        self.out_stb = 0

    def step(self, in_bit, in_stb):
        nxt_stb = 0
        nxt_bit = self.out_bit
        nxt_have = self.have_first
        nxt_first = self.first_bit
        if in_stb:
            if not self.have_first:
                nxt_have = 1
                nxt_first = in_bit
            else:
                nxt_have = 0
                if self.first_bit != in_bit:
                    nxt_bit = self.first_bit
                    nxt_stb = 1
        self.have_first, self.first_bit = nxt_have, nxt_first
        self.out_bit, self.out_stb = nxt_bit, nxt_stb


def von_neumann_stream(bits):
    """Pure functional debiaser over a list of raw bits, for cross checking."""
    out = []
    for i in range(0, len(bits) - 1, 2):
        if bits[i] != bits[i + 1]:
            out.append(bits[i])
    return out


RCT_CUTOFFS = [4, 8, 16, 32]
APT_CUTOFFS = [40, 48, 56, 62]
APT_WINDOW = 64


class HealthMonitor:
    """SP 800-90B style repetition count and adaptive proportion tests."""

    def __init__(self, rct_sel=3, apt_sel=3):
        self.rct_cut = RCT_CUTOFFS[rct_sel]
        self.apt_cut = APT_CUTOFFS[apt_sel]
        self.prev_bit = 0
        self.prev_val = 0
        self.run_len = 1
        self.apt_ref = 0
        self.win_cnt = 0
        self.match_cnt = 0
        self.rct_fail = 0
        self.apt_fail = 0

    def step(self, bit, stb, clr=0):
        if clr:
            self.rct_fail = 0
            self.apt_fail = 0
        if not stb:
            return
        run_next = self.run_len + 1 if (self.prev_val and bit == self.prev_bit) else 1
        self.prev_bit = bit
        self.prev_val = 1
        self.run_len = run_next
        if run_next >= self.rct_cut:
            self.rct_fail = 1

        win_start = self.win_cnt == 0
        ref = bit if win_start else self.apt_ref
        match_next = (0 if win_start else self.match_cnt) + (1 if bit == ref else 0)
        self.apt_ref = ref
        self.match_cnt = match_next
        last = self.win_cnt == APT_WINDOW - 1
        self.win_cnt = 0 if last else self.win_cnt + 1
        if last and match_next > self.apt_cut:
            self.apt_fail = 1

    @property
    def fail(self):
        return self.rct_fail | self.apt_fail


def rct_expected_fail(bits, cutoff):
    """Independent RCT: does any run of identical samples reach the cutoff?"""
    run = 1
    for i in range(1, len(bits)):
        run = run + 1 if bits[i] == bits[i - 1] else 1
        if run >= cutoff:
            return True
    return False


def apt_expected_fail(bits, cutoff, window=APT_WINDOW):
    """Independent APT: any full window where the count matching the window's
    first sample exceeds the cutoff."""
    for start in range(0, len(bits) - window + 1, window):
        chunk = bits[start : start + window]
        if chunk.count(chunk[0]) > cutoff:
            return True
    return False


# ---------------------------------------------------------------------------
# Whole tile, stepped one pixel clock at a time
# ---------------------------------------------------------------------------
class Tile:
    """Cycle accurate model of the tile with SIM_ENTROPY = 1.

    Construct it at the moment reset is released: every field starts at the
    value the RTL loads while rst_n is low. One call to step() is one rising
    clock edge. Read the pixel outputs before stepping, exactly as a testbench
    sampling mid-cycle would.
    """

    def __init__(self, rct_sel=3, apt_sel=3):
        self.x = 0
        self.y = 0
        self.frame = 0
        self.div = 0
        self.sel_rand = 0
        self.box = BouncingBox()
        self.ca = Rule30()
        self.lfsr = Lfsr()
        self.vn = VonNeumann()
        self.health = HealthMonitor(rct_sel, apt_sel)

    # -- combinational views of the current state --------------------------
    @property
    def active(self):
        return self.x < H_ACTIVE and self.y < V_ACTIVE

    @property
    def hsync_n(self):
        return 0 if H_SYNC_ON <= self.x < H_SYNC_OFF else 1

    @property
    def vsync_n(self):
        return 0 if V_SYNC_ON <= self.y < V_SYNC_OFF else 1

    @property
    def line_end(self):
        return self.x == H_TOTAL - 1

    @property
    def frame_end(self):
        return self.line_end and self.y == V_TOTAL - 1

    def rgb(self, sel):
        """Colour before blanking is applied."""
        if sel == 0:
            return pat_xor(self.x, self.y, self.frame)
        if sel == 1:
            return pat_bars(self.x, self.y, self.frame)
        if sel == 2:
            return pat_sierp(self.x, self.y, self.frame)
        if sel == 3:
            return pat_ripple(self.x, self.y, self.frame)
        if sel == 4:
            return pat_plasma(self.x, self.y, self.frame)
        if sel == 5:
            return self.box.pixel(self.x, self.y)
        if sel == 6:
            return pat_stars(self.lfsr.s)
        return self.ca.pixel(self.x, self.frame)

    def uo_out(self, sel):
        r, g, b = self.rgb(sel) if self.active else (0, 0, 0)
        return pack_uo(self.hsync_n, self.vsync_n, r, g, b)

    def uio_out(self):
        rnd = self.lfsr.out_bit & (0 if self.health.fail else 1)
        return (
            (rnd << 7)
            | (self.health.apt_fail << 6)
            | (self.health.rct_fail << 5)
        )

    def effective_sel(self, sel_manual, rand_en):
        return self.sel_rand if rand_en else sel_manual

    # -- one rising clock edge ---------------------------------------------
    def step(self, ext_bit=0, sample_fast=0, freeze=0, health_clr=0, fast_sw=0):
        raw_stb = 1 if (sample_fast or self.div == 7) else 0
        raw_bit = ext_bit & 1  # SIM_ENTROPY = 1: the oscillator term is 0

        # The LFSR sees the von Neumann outputs as they stand before this edge.
        inject = self.vn.out_stb & self.vn.out_bit

        line_end = self.line_end
        frame_end = self.frame_end
        frame_upd = frame_end and not freeze
        # The RTL derives gen_end from pix_y before the counters advance, so the
        # pre-edge y has to be captured here too.
        gen_end = line_end and (self.y & (Rule30.LINES_PER_GEN - 1)) == Rule30.LINES_PER_GEN - 1

        reload_sel = frame_upd and (
            (self.frame & 7) == 7 if fast_sw else (self.frame & 63) == 63
        )

        # Sequential updates, all from pre-edge state.
        if line_end:
            self.x = 0
            self.y = 0 if frame_end else self.y + 1
        else:
            self.x += 1
        if frame_upd:
            self.frame = (self.frame + 1) & 0xFF
        if frame_upd:
            self.box.step()
        if frame_end:
            self.ca.reset()
        elif gen_end:
            self.ca.step()
        if reload_sel and not self.health.fail:
            self.sel_rand = self.lfsr.s & 7

        self.lfsr.step(inject)
        self.vn.step(raw_bit, raw_stb)
        self.health.step(raw_bit, raw_stb, health_clr)
        self.div = (self.div + 1) & 7
