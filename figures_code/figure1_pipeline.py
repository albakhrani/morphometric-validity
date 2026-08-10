#!/usr/bin/env python3
"""
Figure 1 - Measurement and validation pipeline
==============================================
Replaces figure1_architecture_v2.py, which had four defects:

  1. "vs Cellpose (304.6 M-parameter foundation model)" overprinted a glyph
  2. "connected components rejected - F1 = 0.11" overlapped the green banner
  3. the italic band labels collided with the boxes above them
  4. red arrows ran from the Cellpose banner into the four artifact-control
     boxes, implying a dependency that does not exist
  5. the outcomes box read "5 robust - 2 supported"; Table 4 has
     5 Tier A, 1 Tier B, 2 Tier C

This version uses an explicit coordinate grid with no auto-layout, so every
element's position is fixed and verifiable. Band labels sit in a reserved
left gutter rather than on top of the content. The Cellpose comparison is a
self-contained side panel with no outgoing arrows.

Every number below is sourced from the manuscript; see NUMBERS dict.

Usage:
    python figure1_pipeline.py --out figures
"""
from __future__ import annotations

import argparse
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

# --------------------------------------------------------------------------
# Every figure number, in one place, with its manuscript source.
# If the manuscript changes, change it HERE and regenerate.
# --------------------------------------------------------------------------
NUMBERS = {
    "n_lineages":   "8 lineages",            # Sec 2.1
    "n_images":     "4,875 images",           # Sec 3.5 (all 3 splits)
    "n_cells":      "1.09 M cells",           # Sec 3.5 / Table 4
    "backbone":     "2.22 M parameters",     # Sec 2.2
    "added":        "< 100 added parameters",# Sec 2.3
    "f1_gain":      "F1  0.11 -> 0.71",      # Table 1
    "iou":          "IoU  0.83 -> 0.90",     # Sec 3.1
    "cp_params":    "137x",                  # Sec 3.4
    "cp_speed":     "6.2x",                  # Sec 3.4
    "cp_mem":       "3.8x",                  # Sec 3.4
    "cp_f1":        "87%",                   # Sec 3.4
    "tiers":        "5 robust · 1 supported\n2 rejected",  # Table 4: 5 A, 1 B, 2 C
    "rho_time":     "rho = 0.94",            # Sec 3.5
}

# palette - colour-blind safe, print-safe
C_BLUE   = "#1f4e79"
C_BLUEBG = "#e8eef5"
C_GREY   = "#4a4a4a"
C_GREYBG = "#eeeeee"
C_RED    = "#a02020"
C_REDBG  = "#fbeaea"
C_GREEN  = "#1e6b3a"
C_GREENBG= "#e7f2ea"

# Sizes below are PRINTED sizes: the figure is authored at its placed width
# (see figsize in build()), so LaTeX applies no downscale. Elsevier's artwork
# floor is 6 pt; nothing here is allowed below 7 pt.
FS_TITLE = 8.0
FS_SUB   = 7.8
FS_BAND  = 7.6


def box(ax, x, y, w, h, title, sub, edge, face, fs_title=FS_TITLE,
        fs_sub=FS_SUB, ty=0.62, sy=0.27):
    """Draw one rounded box with a bold title and an optional subtitle.

    ty and sy are the vertical anchors of the title and subtitle as
    fractions of the box height. They are parameters rather than constants
    because a box whose subtitle runs to four lines needs its two blocks
    pushed apart: at the defaults, the fourth line of a subtitle centred at
    0.27h falls outside the box and the first line collides with the title.
    Shrinking the type instead would drop it below the 7 pt floor the rest
    of this figure set holds to.
    """
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0,rounding_size=0.10",
        linewidth=1.1, edgecolor=edge, facecolor=face, zorder=2))
    if sub:
        ax.text(x + w / 2, y + h * ty, title, ha="center", va="center",
                fontsize=fs_title, fontweight="bold", color=edge, zorder=3)
        ax.text(x + w / 2, y + h * sy, sub, ha="center", va="center",
                fontsize=fs_sub, color=C_GREY, zorder=3, linespacing=1.35)
    else:
        ax.text(x + w / 2, y + h / 2, title, ha="center", va="center",
                fontsize=fs_title, fontweight="bold", color=edge, zorder=3)


def arrow(ax, x1, y1, x2, y2, color=C_GREY, lw=1.2, style="-|>"):
    ax.add_patch(FancyArrowPatch(
        (x1, y1), (x2, y2), arrowstyle=style, mutation_scale=11,
        linewidth=lw, color=color, shrinkA=0, shrinkB=0, zorder=4))


def band_label(ax, y, text, color):
    """Band label in the reserved left gutter - never overlaps content."""
    ax.text(9.6, y, text, ha="right", va="center", fontsize=FS_BAND,
            fontweight="bold", color=color, style="italic", zorder=3)


def build(outpath: str) -> None:
    """
    Layout logic (top to bottom = the actual logical flow of the study):

        row 1   two INPUT paths, side by side: expert masks | model masks
        row 2   they converge on ONE measurement code  <- the paper's key claim
        row 3   four artifact controls applied to those measurements
        row 4   the three outcomes
        strip   efficiency vs Cellpose, isolated at the bottom

    Nothing crosses anything. The efficiency strip has no arrows because it
    is a property of the model path alone, not a step in the argument.
    """
    # Authored at the placed width (\textwidth = 494.51 pt); 6.74 in accounts
    # for the padding bbox_inches="tight" adds. The previous 11 in canvas was
    # downscaled to 62%, printing 7.6 pt subtitles at 4.7 pt.
    fig, ax = plt.subplots(figsize=(6.999, 5.190))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 68)
    ax.axis("off")

    GUT = 11.5          # reserved gutter: band labels never touch content
    W = 100 - GUT - 2.0
    GAP = 2.4

    # ================= ROW 1: two input paths side by side =================
    y1, h1 = 53.0, 12.0
    # "primary", not "two": connected-component labelling and Cellpose enter
    # as further mask sources in Baseline comparison, so the paper evaluates
    # four. This row still shows only the two the validation argument is
    # built on -- expert annotation and the extension -- and the label now
    # says so instead of implying there are no others.
    band_label(ax, y1 + h1 / 2, "primary mask\nsources", C_GREY)

    # -- left: expert path (2 boxes)
    LW = (W * 0.35 - GAP) / 2
    for i, (t, s_) in enumerate([
            ("LIVECell", f"{NUMBERS['n_lineages']}\n{NUMBERS['n_images']}"),
            ("Expert masks", f"{NUMBERS['n_cells']}\nground truth")]):
        x = GUT + i * (LW + GAP)
        box(ax, x, y1, LW, h1, t, s_, C_BLUE, C_BLUEBG,
            fs_title=FS_TITLE - 0.9, fs_sub=FS_SUB - 0.8)
        if i == 0:
            arrow(ax, x + LW, y1 + h1 / 2, x + LW + GAP, y1 + h1 / 2, color=C_BLUE)
    x_expert_mid = GUT + (LW + GAP) + LW / 2

    # -- divider
    xdiv = GUT + W * 0.35 + GAP * 1.4
    ax.plot([xdiv, xdiv], [y1 - 1.0, y1 + h1 + 1.0], color="#cccccc",
            lw=0.8, ls=(0, (3, 3)), zorder=1)

    # -- right: model path (3 boxes)
    RX = xdiv + GAP * 1.4
    RW = (100 - 2.0 - RX - 2 * GAP) / 3
    for i, (t, s_) in enumerate([
            ("U-Net++ · CBAM", f"pretrained\n{NUMBERS['backbone']}"),
            ("+ two heads", "distance,\nboundary maps"),
            ("Watershed\ndecoding", "predicted\ninstance masks")]):
        x = RX + i * (RW + GAP)
        box(ax, x, y1, RW, h1, t, s_, C_GREY, C_GREYBG,
            fs_title=FS_TITLE - 0.9, fs_sub=FS_SUB - 0.8)
        if i < 2:
            arrow(ax, x + RW, y1 + h1 / 2, x + RW + GAP, y1 + h1 / 2)
    x_model_mid = RX + 2 * (RW + GAP) + RW / 2

    # ================= ROW 2: the convergence =================
    y2, h2 = 40.5, 7.6
    band_label(ax, y2 + h2 / 2, "one\nmeasurement", C_RED)
    box(ax, GUT, y2, W, h2,
        "Identical geometry and descriptor code",
        "$q = P/\\sqrt{A}$  ·  solidity  ·  extent  ·  eccentricity  ·  confluence $\\varphi$\n"
        "any difference between sources is segmentation, not measurement",
        C_RED, C_REDBG, fs_title=FS_TITLE + 0.6)
    arrow(ax, x_expert_mid, y1, x_expert_mid, y2 + h2, color=C_BLUE, lw=1.5)
    arrow(ax, x_model_mid, y1, x_model_mid, y2 + h2, color=C_GREY, lw=1.5)

    # ================= ROW 3: artifact controls =================
    y3, h3 = 26.5, 9.6
    band_label(ax, y3 + h3 / 2, "four artifact\ncontrols", C_GREY)
    N = 4
    BW = (W - (N - 1) * GAP) / N
    for i, (t, s_) in enumerate([
            ("1  Density definition", "count vs $\\varphi$"),
            ("2  Cell size", "partial $\\rho$ · size strata"),
            ("3  Time since plating", f"$\\varphi \\sim t$ :  {NUMBERS['rho_time']}"),
            ("4  Segmentation error", "expert vs model masks")]):
        x = GUT + i * (BW + GAP)
        box(ax, x, y3, BW, h3, t, s_, C_GREY, "#f6f6f6",
            fs_title=FS_TITLE - 0.8, fs_sub=FS_SUB - 0.8)
        arrow(ax, x + BW / 2, y2, x + BW / 2, y3 + h3, color=C_GREY, lw=0.9)
        arrow(ax, x + BW / 2, y3, x + BW / 2, y3 - 2.4, color=C_GREY, lw=0.9)

    # ================= ROW 4: outcomes =================
    # h4 9.6 -> 12.0, grown DOWNWARD (y4 13.0 -> 10.6) so the top edge stays
    # at 22.6 and keeps its 1.5-unit clearance under the control arrows,
    # which end at 24.1. The gap to the efficiency strip (top 8.8) is 1.8.
    y4, h4 = 10.6, 12.0
    band_label(ax, y4 + h4 / 2, "outcomes", C_BLUE)
    OW = (W - 2 * GAP) / 3
    for i, (t, s_) in enumerate([
            ("Evidence-tiered atlas", NUMBERS["tiers"]),
            ("Detection $\\neq$ measurement", "Pareto-selected\noperating point"),
            # Was: "One rejected phenotype" / "MCF7: fabricated by two
            # unrelated error sources". That claim was retired when the
            # expanded atlas corrected the analysis, but this string lives in
            # a figure asset, so grepping the manuscript could never find it
            # and it survived every batch. The wording below is the claim the
            # Results now make: MCF7 has no trajectory that survives control,
            # and segmentation error manufactures one.
            # Title set on two lines: as one line it is the longest title in
            # the row and overran the box on both sides.
            ("One manufactured\nphenotype",
             "MCF7: no trajectory\nsurvives control;\nsegmentation error\ncreates one")]):
        x = GUT + i * (OW + GAP)
        box(ax, x, y4, OW, h4, t, s_, C_BLUE, C_BLUEBG,
            fs_title=FS_TITLE - 0.4, fs_sub=FS_SUB - 0.4,
            ty=0.77, sy=0.30)

    # ================= efficiency strip (isolated, no arrows) =============
    py, ph = 3.4, 5.4
    band_label(ax, py + ph / 2, "efficiency", C_GREEN)
    ax.add_patch(FancyBboxPatch(
        (GUT, py), W, ph, boxstyle="round,pad=0,rounding_size=0.08",
        linewidth=1.0, edgecolor=C_GREEN, facecolor=C_GREENBG, zorder=2))
    ax.text(GUT + 1.8, py + ph / 2,
            "vs Cellpose\n(304.6 M param.):",
            ha="left", va="center", fontsize=FS_SUB - 0.4,
            fontweight="bold", color=C_GREEN, zorder=3, linespacing=1.3)
    stats = [(NUMBERS["cp_params"], "fewer param."),
             (NUMBERS["cp_speed"], "faster"),
             (NUMBERS["cp_mem"], "less GPU mem."),
             (NUMBERS["cp_f1"], "of its F1")]
    x0, step = GUT + 21.0, (W - 22.0) / len(stats)
    for j, (big, small) in enumerate(stats):
        xs = x0 + j * step
        ax.text(xs, py + ph * 0.66, big, ha="left", va="center",
                fontsize=FS_SUB + 2.2, fontweight="bold", color=C_GREEN, zorder=3)
        ax.text(xs, py + ph * 0.28, small, ha="left", va="center",
                fontsize=FS_SUB - 0.8, color=C_GREEN, zorder=3)

    fig.subplots_adjust(left=0.004, right=0.996, top=0.996, bottom=0.004)
    for ext in ("pdf", "png"):
        fig.savefig(f"{outpath}.{ext}", dpi=600, bbox_inches="tight",
                    facecolor="white")
    plt.close(fig)
    print(f"wrote {outpath}.pdf and {outpath}.png")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=".", help="output directory")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    build(os.path.join(a.out, "Fig1_architecture"))
