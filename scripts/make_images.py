#!/usr/bin/env python3
"""Regenerate every raster image in docs/img from simulation and synthesis output.

Nothing here draws a mockup. Every pixel of every pattern PNG and every frame of
every GIF came off the tile's uo_out pins in an Icarus simulation and was checked
against test/model.py before being written. Every number on the plots came out of
the cocotb run or out of Yosys mapped against the real IHP sg13g2 library.

Inputs, all produced by the simulation and synthesis steps:

    test/output/frames/*.bin    one verified frame per pattern      (make test)
    test/output/anim/*.bin      32 ripple frames                    (make capture)
    test/output/switch/*.bin    32 TRNG selected frames             (make capture)
    test/output/stats.json      262144 output bits characterised    (make test)
    test/output/debias.json     bias before and after von Neumann   (make test)
    test/output/timing.json     measured VGA intervals              (make test)
    docs/synth/area.json        per module cell counts and areas    (make synth)
    docs/hardening/summary.json post route area and signoff           (make harden)

Run with: make images
"""

import json
import pathlib
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import frames as F  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
IMG = ROOT / "docs" / "img"
OUT = ROOT / "test" / "output"
SYNTH = ROOT / "docs" / "synth"

PATTERN_ORDER = [
    ("xor_field", "0  XOR munching field"),
    ("smpte_bars", "1  SMPTE bars + ramp"),
    ("sierpinski", "2  Sierpinski fractal"),
    ("ripple", "3  Manhattan ripple"),
    ("plasma", "4  Plasma"),
    ("bouncing_box", "5  Bouncing box"),
    ("starfield", "6  Starfield"),
    ("rule30", "7  Rule 30 automaton"),
]

# A colour per plot series. Deliberately conservative: these end up in a README
# that people read on both light and dark backgrounds.
INK = "#1c2128"
ACCENT = "#2f5d8c"
ACCENT2 = "#9a5a1c"
BAD = "#963232"
GOOD = "#3f6b32"
GRID = "#d0d7de"


def need(path, how):
    if not pathlib.Path(path).exists():
        raise SystemExit(f"missing {path}\nrun `{how}` first")
    return pathlib.Path(path)


def load_json(name, how):
    return json.loads(need(name, how).read_text())


def font(size):
    for cand in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if pathlib.Path(cand).exists():
            return ImageFont.truetype(cand, size)
    return ImageFont.load_default()


def style(ax):
    ax.set_facecolor("white")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK, labelsize=9)
    ax.grid(True, color=GRID, linewidth=0.7, alpha=0.9)
    ax.set_axisbelow(True)


# ---------------------------------------------------------------------------
# pattern stills and contact sheet
# ---------------------------------------------------------------------------
def pattern_pngs():
    made = []
    for name, _ in PATTERN_ORDER:
        need(F.FRAME_DIR / f"{name}.bin", "make test")
        img = F.to_image(name)
        path = IMG / f"pattern_{name}.png"
        img.save(path, optimize=True)
        made.append(path)
    print(f"  {len(made)} pattern stills at 640x480")
    return made


def contact_sheet():
    cols, rows = 4, 2
    tw, th = 320, 240
    label_h = 28
    pad = 8
    sheet = Image.new(
        "RGB",
        (cols * tw + pad * (cols + 1), rows * (th + label_h) + pad * (rows + 1)),
        (255, 255, 255),
    )
    draw = ImageDraw.Draw(sheet)
    fnt = font(15)
    for i, (name, label) in enumerate(PATTERN_ORDER):
        cx, cy = i % cols, i // cols
        x = pad + cx * (tw + pad)
        y = pad + cy * (th + label_h + pad)
        sheet.paste(F.to_image(name, scale=2), (x, y))
        # a thin outline, or the white SMPTE bar and the box's white border
        # disappear into the page
        draw.rectangle([x - 1, y - 1, x + tw, y + th], outline=(140, 150, 160), width=1)
        draw.text((x, y + th + 5), label, fill=(28, 33, 40), font=fnt)
        draw.text(
            (x + tw - 74, y + th + 6),
            f"frame {F.meta(name).get('frame', '?')}",
            fill=(90, 100, 110),
            font=font(12),
        )
    path = IMG / "pattern_gallery.png"
    sheet.save(path, optimize=True)
    print(f"  contact sheet {sheet.size[0]}x{sheet.size[1]}")
    return path


# ---------------------------------------------------------------------------
# animated GIFs
# ---------------------------------------------------------------------------
def gif_from(subdir, out_name, scale=2, duration=90, label_fn=None):
    d = OUT / subdir
    names = sorted(p.stem for p in d.glob("*.bin")) if d.exists() else []
    if not names:
        raise SystemExit(
            f"no frames in {d}\nrun `make -C test capture` first (about 15 minutes)"
        )
    imgs = []
    fnt = font(14)
    for n in names:
        img = F.to_image(n, directory=d, scale=scale)
        if label_fn:
            img = img.convert("RGB")
            draw = ImageDraw.Draw(img)
            text = label_fn(F.meta(n, directory=d))
            draw.rectangle([0, 0, img.size[0], 22], fill=(0, 0, 0))
            draw.text((6, 3), text, fill=(255, 255, 255), font=fnt)
        imgs.append(img.convert("P", palette=Image.ADAPTIVE, colors=64))
    path = IMG / out_name
    imgs[0].save(
        path,
        save_all=True,
        append_images=imgs[1:],
        duration=duration,
        loop=0,
        optimize=True,
    )
    print(f"  {out_name}: {len(imgs)} frames at {imgs[0].size[0]}x{imgs[0].size[1]}")
    return path


# ---------------------------------------------------------------------------
# TRNG characterisation plots
# ---------------------------------------------------------------------------
def plot_bias_over_time(stats):
    series = stats["bias_over_time"]
    win = stats["bias_window"]
    fig, ax = plt.subplots(figsize=(8.4, 3.4), dpi=140)
    style(ax)
    x = [i * win for i in range(len(series))]
    overall = stats["bias"]
    bound = stats["bias_bound"]
    # Two sigma for a single window, not the overall bound. A 4096 bit window has
    # a standard error of 0.5/sqrt(4096) = 0.0078, so window excursions of one or
    # two hundredths are expected and say nothing about the overall figure.
    sigma = 0.5 / (win ** 0.5)
    ax.axhspan(-2 * sigma, 2 * sigma, color=GOOD, alpha=0.10)
    ax.axhline(2 * sigma, color=GOOD, linewidth=1, linestyle="--")
    ax.axhline(-2 * sigma, color=GOOD, linewidth=1, linestyle="--")
    ax.plot(x, series, color=ACCENT, linewidth=1.4)
    ax.axhline(0, color=INK, linewidth=1)
    ax.axhline(overall, color=ACCENT2, linewidth=1.6, linestyle=":")
    span = max(max(abs(v) for v in series), 2 * sigma)
    ax.set_ylim(-span * 1.75, span * 1.3)
    ax.set_xlabel(f"output bit index (window = {win} bits)")
    ax.set_ylabel("bias, P(1) - 0.5")
    ax.set_title(
        f"Conditioned output bias over {stats['n_bits']} bits\n"
        f"overall {overall:+.5f}, asserted within +/-{bound}",
        fontsize=11,
        color=INK,
    )
    ax.legend(
        [
            plt.Line2D([], [], color=ACCENT, lw=1.4),
            plt.Line2D([], [], color=ACCENT2, lw=1.6, ls=":"),
            plt.Line2D([], [], color=GOOD, lw=1, ls="--"),
        ],
        [
            f"per {win} bit window",
            f"overall {overall:+.5f}, assertion bound +/-{bound}",
            f"+/-2 sigma for one {win} bit window ({2 * sigma:.4f})",
        ],
        fontsize=8,
        frameon=False,
        loc="lower left",
    )
    fig.tight_layout()
    path = IMG / "trng_bias.png"
    fig.savefig(path, facecolor="white")
    plt.close(fig)
    return path


def plot_runs(stats):
    hist = {int(k): v for k, v in stats["runs"].items()}
    total = stats["total_runs"]
    ks = sorted(hist)
    fig, ax = plt.subplots(figsize=(8.4, 3.6), dpi=140)
    style(ax)
    ax.bar([k for k in ks], [hist[k] for k in ks], color=ACCENT, width=0.72,
           label="measured")
    ideal = [total * 0.5 ** k for k in ks]
    ax.plot(ks, ideal, color=BAD, linewidth=1.6, marker="o", markersize=3.2,
            label="ideal fair source, total * 2^-k")
    ax.set_yscale("log")
    ax.set_xticks(ks)
    ax.set_xlabel("run length in bits")
    ax.set_ylabel("number of runs (log scale)")
    ax.set_title(
        f"Run length distribution, {total} runs over {stats['n_bits']} bits\n"
        f"{stats['frac_runs_len1']:.4f} of runs have length 1, longest run {max(ks)}",
        fontsize=11,
        color=INK,
    )
    ax.legend(fontsize=8, frameon=False)
    fig.tight_layout()
    path = IMG / "trng_runs.png"
    fig.savefig(path, facecolor="white")
    plt.close(fig)
    return path


def plot_bytes(stats):
    hist = stats["byte_hist"]
    n = stats["n_bytes"]
    expected = n / 256.0
    fig, ax = plt.subplots(figsize=(8.4, 3.6), dpi=140)
    style(ax)
    ax.bar(range(256), hist, color=ACCENT, width=1.0)
    ax.axhline(expected, color=BAD, linewidth=1.4, label=f"expected {expected:.1f}")
    ax.set_xlabel("byte value from non-overlapping 8 bit groups")
    ax.set_ylabel("count")
    ax.set_xlim(-1, 256)
    chi2 = stats["chi2"]
    ax.set_title(
        f"Byte value distribution, {n} bytes\n"
        f"chi-square {chi2:.1f} on {stats['chi2_df']} df "
        f"(critical value 330.5 at p=0.001, assertion bound {stats['chi2_bound']})",
        fontsize=11,
        color=INK,
    )
    ax.annotate(
        f"min {min(hist)}   max {max(hist)}",
        xy=(0.99, 0.94),
        xycoords="axes fraction",
        ha="right",
        fontsize=8.5,
        color=INK,
    )
    ax.legend(fontsize=8, frameon=False, loc="lower right")
    fig.tight_layout()
    path = IMG / "trng_bytes.png"
    fig.savefig(path, facecolor="white")
    plt.close(fig)
    return path


def plot_debias(deb):
    fig, ax = plt.subplots(figsize=(6.6, 3.8), dpi=140)
    style(ax)
    raw, out = deb["raw_bias"], deb["debiased_bias"]
    bars = ax.bar(
        ["raw source\n(P(1) = 0.75 driven in)", "after von Neumann"],
        [raw, out],
        color=[BAD, GOOD],
        width=0.5,
    )
    ax.axhline(0, color=INK, linewidth=1)
    for b, v in zip(bars, (raw, out)):
        ax.annotate(
            f"{v:+.4f}",
            xy=(b.get_x() + b.get_width() / 2, v),
            xytext=(0, 6 if v >= 0 else -14),
            textcoords="offset points",
            ha="center",
            fontsize=10,
            color=INK,
        )
    ax.set_ylabel("bias, P(1) - 0.5")
    ax.set_title(
        f"Von Neumann debiasing, {deb['n_raw']} raw samples\n"
        f"{deb['n_out']} bits out, yield {deb['yield']:.4f} "
        f"against the theoretical p(1-p) = {deb['theoretical_yield']}",
        fontsize=11,
        color=INK,
    )
    fig.tight_layout()
    path = IMG / "trng_debias.png"
    fig.savefig(path, facecolor="white")
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# synthesis area chart
# ---------------------------------------------------------------------------
def plot_area(area, harden=None):
    tile = area["tile"]
    mods = area["modules"]

    # Leaf modules only: the two group modules and the ring wrapper would double
    # count their children.
    groups = {"pattern_mux", "trng", "ring_osc"}
    leaves = {k: v for k, v in mods.items() if k not in groups}
    order = sorted(leaves, key=lambda k: leaves[k]["area_um2"])

    labels = [f"{k}  ({leaves[k]['flop_count']} ff)" for k in order]
    areas = [leaves[k]["area_um2"] for k in order]
    cells = [leaves[k]["cell_count"] for k in order]

    fig, (ax, ax2) = plt.subplots(
        1, 2, figsize=(11.4, 6.2), dpi=140, gridspec_kw={"width_ratios": [2.1, 1]}
    )
    style(ax)
    style(ax2)

    colours = [ACCENT2 if leaves[k]["flop_count"] else ACCENT for k in order]
    ax.barh(labels, areas, color=colours, height=0.72)
    for y, (a, c) in enumerate(zip(areas, cells)):
        ax.annotate(
            f"{a:.0f} um2 / {c} cells",
            xy=(a, y),
            xytext=(5, 0),
            textcoords="offset points",
            va="center",
            fontsize=8,
            color=INK,
        )
    ax.set_xlim(0, max(areas) * 1.42)
    ax.set_xlabel("mapped standard cell area, um2 (IHP sg13g2)")
    ax.set_title(
        "Per submodule area, Yosys mapped to the real PDK library\n"
        "orange = holds state, blue = purely combinational",
        fontsize=11,
        color=INK,
    )

    # tile budget panel: what the design needs against what a tile provides
    synth = area["top"]["area_um2"]
    tile_area = tile["tile_area_um2"]

    bars = [("post\nsynthesis", synth, ACCENT)]
    subtitle = f"{area['top']['cell_count']} cells, {area['top']['flop_count']} flops"
    if harden:
        route = harden["instance_area_real_um2"]
        bars.append(("post\nroute", route, ACCENT2))
        subtitle += f"\npost route {harden['instance_count_real']} cells, DRC/LVS clean"
    labels = [b[0] for b in bars]
    vals = [b[1] for b in bars]
    ax2.bar(labels, vals, color=[b[2] for b in bars], width=0.5)
    for x, v in enumerate(vals):
        ax2.annotate(
            f"{v:.0f}",
            xy=(x, v),
            xytext=(0, 5),
            textcoords="offset points",
            ha="center",
            fontsize=9.5,
            color=INK,
        )

    # the two tile footprints as reference lines, named in the legend rather
    # than annotated in place: the panel is too narrow for the text to fit.
    ax2.axhline(tile_area, color=BAD, linewidth=1.8, linestyle="--")
    ax2.axhline(2 * tile_area, color=GOOD, linewidth=1.8, linestyle="--")
    ax2.legend(
        [
            plt.Line2D([], [], color=BAD, lw=1.8, ls="--"),
            plt.Line2D([], [], color=GOOD, lw=1.8, ls="--"),
        ],
        [f"1x1 tile, {tile_area:.0f} um2", f"1x2 tile, {2 * tile_area:.0f} um2"],
        fontsize=8.5,
        frameon=False,
        loc="upper left",
    )
    if harden:
        ax2.annotate(
            f"post route cells are\n"
            f"{harden['density_real_over_1x1'] * 100:.0f}% of a 1x1 tile\n"
            f"{harden['density_real_over_1x2'] * 100:.0f}% of a 1x2 tile",
            xy=(0.5, tile_area),
            xytext=(0, -46),
            textcoords="offset points",
            ha="center",
            fontsize=9,
            color=INK,
        )
    ax2.set_ylim(0, 2 * tile_area * 1.18)
    ax2.set_ylabel("cell area, um2")
    ax2.set_title("Area against the tile footprint\n" + subtitle, fontsize=10.5, color=INK)

    fig.tight_layout()
    path = IMG / "synth_area.png"
    fig.savefig(path, facecolor="white")
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
def main():
    IMG.mkdir(parents=True, exist_ok=True)
    made = []

    print("pattern stills from verified RTL frames:")
    made += pattern_pngs()
    made.append(contact_sheet())

    print("animated GIFs from verified RTL frame sequences:")
    made.append(
        gif_from(
            "anim",
            "anim_ripple.gif",
            duration=80,
            label_fn=lambda m: f"pattern 3 ripple   frame {m['frame']}",
        )
    )
    made.append(
        gif_from(
            "switch",
            "anim_trng_switch.gif",
            duration=140,
            label_fn=lambda m: f"RAND_EN=1  sel={m['sel']}  {m['pattern']}   frame {m['frame']}",
        )
    )

    print("TRNG characterisation plots:")
    stats = load_json(OUT / "stats.json", "make test")
    deb = load_json(OUT / "debias.json", "make test")
    made.append(plot_bias_over_time(stats))
    made.append(plot_runs(stats))
    made.append(plot_bytes(stats))
    made.append(plot_debias(deb))
    for p in made[-4:]:
        print(f"  {p.name}")

    print("synthesis and hardening area chart:")
    area = load_json(SYNTH / "area.json", "make synth")
    hard_path = ROOT / "docs" / "hardening" / "summary.json"
    harden = json.loads(hard_path.read_text()) if hard_path.exists() else None
    if harden is None:
        print("  note: no docs/hardening/summary.json, run `make harden` for the")
        print("        post route bar. Falling back to post synthesis only.")
    made.append(plot_area(area, harden))
    print(f"  {made[-1].name}")
    layout = IMG / "layout.png"
    if layout.exists():
        made.append(layout)
        print(f"  {layout.name} (rendered by scripts/harden.sh)")

    total_kb = sum(p.stat().st_size for p in made) / 1024
    print(f"\n{len(made)} images written to docs/img ({total_kb:.0f} kB)")
    print("hand written SVGs (not regenerated): block_diagram.svg, vga_timing.svg")


if __name__ == "__main__":
    main()
