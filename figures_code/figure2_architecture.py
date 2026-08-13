#!/usr/bin/env python3
"""
Figure 2 - Network architecture and the instance-preserving extension
=====================================================================
The manuscript currently describes the architecture in prose only. Every
comparable paper in this space (HoVer-Net, CBAM-ResAttUNet, CBAM-NucleiSeg,
U-Net++) devotes a dedicated figure to it. This supplies that figure.

Panel A  U-Net++ nested decoder with CBAM, deep supervision, and the two
         added 1x1 heads highlighted
Panel B  CBAM block detail (channel attention then spatial attention)
Panel C  loss composition

ARCHITECTURE RECONSTRUCTED FROM THE MANUSCRIPT
----------------------------------------------
Everything drawn here is fixed by two statements in Sections 2.2-2.3 plus
one arithmetic constraint. Nothing is invented, but PLEASE VERIFY against
your actual model code before submitting:

  Sec 2.2  "encoder depth of four and 32 base channels
            (channel widths 32/64/128/256)"        -> 4 levels, grid below
  Sec 2.2  "deep supervision through three decoder
            output heads"                          -> heads at X01, X02, X03
  Sec 2.3  "two lightweight output heads to the
            backbone's deepest decoder feature map,
            the same feature map read by the
            existing foreground head"              -> both attach at X03
  Sec 2.3  "fewer than 100 parameters"             -> 2 x (C+1) < 100
                                                      => C = 32, giving 66.
                                                      C = 64 would give 130,
                                                      which contradicts the
                                                      text. So X03 is the
                                                      32-channel node.

  Resulting U-Net++ grid (row = resolution level, col = nested stage):
      row 0   32 ch    X00 -- X01 -- X02 -- X03      <- 3 DS heads + 2 new
      row 1   64 ch    X10 -- X11 -- X12
      row 2  128 ch    X20 -- X21
      row 3  256 ch    X30

If your implementation differs (e.g. a separate bottleneck level, or heads
at a different node), edit GRID and HEADS below and regenerate.

Usage:
    python figure2_architecture.py --out figures
"""
from __future__ import annotations

import argparse
import os

import matplotlib
matplotlib.rcParams['pdf.fonttype'] = 42   # TrueType, not Type 3
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch

# --- edit these two if your implementation differs -------------------------
GRID = {0: (4, 32), 1: (3, 64), 2: (2, 128), 3: (1, 256)}  # row: (n_nodes, channels)
HEADS_DS = [(0, 1), (0, 2), (0, 3)]   # deep-supervision foreground heads
HEADS_NEW = (0, 3)                    # distance + boundary heads attach here
# ---------------------------------------------------------------------------

C_ENC   = "#1f4e79"; C_ENCBG  = "#dce6f1"
C_NEST  = "#4a4a4a"; C_NESTBG = "#ededed"
C_NEW   = "#a02020"; C_NEWBG  = "#fbe9e9"
# Lightened from #1e6b3a. Against C_NEW (#a02020) the old green sat at
# near-identical luminance (78 vs 70 on the 0-255 grey axis), which is
# the classic deuteranope confusion pair -- and the two are adjacent
# swatches in the legend, with nothing but hue to separate them.
C_DS    = "#2e9e57"; C_DSBG   = "#e4f0e8"
C_CBAM  = "#8a5a00"; C_CBAMBG = "#fdf2dd"


def rbox(ax, x, y, w, h, txt, edge, face, fs=7.4, bold=True, z=3, ls="-"):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                 boxstyle="round,pad=0,rounding_size=0.35",
                 linewidth=1.0, edgecolor=edge, facecolor=face, zorder=z,
                 linestyle=ls))
    ax.text(x + w / 2, y + h / 2, txt, ha="center", va="center", fontsize=fs,
            fontweight="bold" if bold else "normal", color=edge, zorder=z + 1,
            linespacing=1.25)


def arr(ax, p, q, color, lw=1.0, style="-|>", rad=0.0, ls="-"):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle=style, mutation_scale=8,
                 linewidth=lw, color=color, shrinkA=1.5, shrinkB=1.5,
                 zorder=2, linestyle=ls,
                 connectionstyle=f"arc3,rad={rad}"))


def build(outpath: str) -> None:
    # Authored at the width it is PLACED at: \textwidth = 494.51 pt = 6.87 in.
    # The previous 11 in canvas was downscaled to 62% by LaTeX, which printed
    # every label at 3.7-4.5 pt -- below Elsevier's 6 pt artwork floor. At this
    # width the scale factor is ~1, so the sizes set below are the sizes that
    # print. Nothing here may go below 7 pt.
    # 6.74 not 6.87: bbox_inches="tight" adds ~9 pt of padding, so this yields
    # a 494.5 pt artwork that LaTeX places at scale 1.000.
    fig = plt.figure(figsize=(7.169, 4.712))
    # Panel A occupies the top ~68%, B and C share the bottom
    axA = fig.add_axes([0.005, 0.335, 0.99, 0.655]); axA.axis("off")
    axB = fig.add_axes([0.005, 0.015, 0.60, 0.295]); axB.axis("off")
    axC = fig.add_axes([0.625, 0.015, 0.37, 0.295]); axC.axis("off")
    for a, lim in ((axA, (100, 46)), (axB, (100, 30)), (axC, (100, 30))):
        a.set_xlim(0, lim[0]); a.set_ylim(0, lim[1])

    # ==================== PANEL A: U-Net++ grid ====================
    axA.text(0.5, 44.0, "A", fontsize=10, fontweight="bold", va="top")

    # 9.6 wide, not 8.6: at 10 pt the node label "X^{r,c}" reaches the CBAM
    # badge in the top-right corner. The extra width restores the clearance.
    NW, NH = 9.6, 5.4          # node size
    X0, Y0 = 14.0, 29.5        # top-left node centre-ish
    DX, DY = 13.4, 8.0         # spacing

    def pos(r, c):
        return X0 + c * DX, Y0 - r * DY

    # input
    rbox(axA, 1.5, Y0 - 1.0, 9.5, NH + 2.0,
         "phase\ncontrast\n$512\\times512$", C_ENC, "#ffffff", fs=7.2)

    # nodes
    centres = {}
    for r, (n, ch) in GRID.items():
        for c in range(n):
            x, y = pos(r, c)
            is_enc = (c == 0)
            edge, face = (C_ENC, C_ENCBG) if is_enc else (C_NEST, C_NESTBG)
            if (r, c) == HEADS_NEW:
                edge, face = C_NEW, C_NEWBG
            rbox(axA, x, y, NW, NH,
                 f"X$^{{{r},{c}}}$\n{ch} ch", edge, face, fs=10.0)
            centres[(r, c)] = (x + NW / 2, y + NH / 2)
            # CBAM marker on every conv block
            axA.add_patch(Circle((x + NW - 1.3, y + NH - 1.3), 1.3,
                          facecolor=C_CBAMBG, edgecolor=C_CBAM,
                          linewidth=0.7, zorder=5))
            axA.text(x + NW - 1.3, y + NH - 1.3, "C", ha="center", va="center",
                     fontsize=7.5, color=C_CBAM, fontweight="bold", zorder=6)

    # input -> X00
    arr(axA, (11.0, centres[(0, 0)][1]), (X0, centres[(0, 0)][1]), C_ENC, 1.3)

    # encoder down-path
    for r in range(3):
        arr(axA, (centres[(r, 0)][0], pos(r, 0)[1]),
                 (centres[(r + 1, 0)][0], pos(r + 1, 0)[1] + NH), C_ENC, 1.3)
    axA.text(centres[(1, 0)][0] - 5.6, (centres[(0, 0)][1] + centres[(1, 0)][1]) / 2,
             "down\n$2\\times$", ha="center", va="center", fontsize=7.0,
             color=C_ENC, style="italic")

    # dense nested skips (horizontal) and up-samples (diagonal)
    for r, (n, _) in GRID.items():
        for c in range(1, n):
            # every earlier node on the same row feeds this one (dense skips)
            for c0 in range(c):
                rad = 0.0 if c0 == c - 1 else -0.24
                lw = 1.15 if c0 == c - 1 else 0.6
                ls = "-" if c0 == c - 1 else (0, (2.5, 2.0))
                arr(axA, centres[(r, c0)], centres[(r, c)], C_NEST, lw,
                    rad=rad, ls=ls)
            # up-sample from the level below
            if (r + 1, c - 1) in centres:
                arr(axA, centres[(r + 1, c - 1)], centres[(r, c)],
                    "#8899aa", 1.05)

    # deep-supervision heads, each directly above the node it reads
    hx = X0 + 3 * DX + NW + 6.0
    ds_y = Y0 + NH + 5.2
    for k, node in enumerate(HEADS_DS):
        nx, _ = pos(*node)
        rbox(axA, nx, ds_y, NW, 4.0, f"DS head {k+1}", C_DS, C_DSBG, fs=7.0)
        arr(axA, (centres[node][0], Y0 + NH), (centres[node][0], ds_y),
            C_DS, 0.95, ls=(0, (3, 2)))
    axA.text(pos(*HEADS_DS[0])[0] + NW / 2, ds_y + 6.0,
             "existing foreground path: BCE + Dice, averaged over the three heads",
             ha="left", va="center", fontsize=7.0, color=C_DS, style="italic")

    # The two added heads are NOT symmetric, and the asymmetry is the finding:
    # the distance head drives the watershed decoder, while the boundary head
    # only ever contributes a loss term (Section 3.3). Drawing them as two
    # equivalent outputs, as an earlier version did, asserts something false.
    ny = centres[HEADS_NEW][1]
    HEADS = [("distance head", "$1\\times1$ conv · 33 param.", "-",
              "seeds the watershed decoder", 35.0),
             ("boundary head", "$1\\times1$ conv · 33 param.", (0, (3, 2)),
              "auxiliary loss term only — see C", 26.5)]
    for lab, sub, ls, note, yy in HEADS:
        rbox(axA, hx, yy - 2.6, 19.0, 5.2, f"{lab}\n{sub}", C_NEW, C_NEWBG,
             fs=7.0, ls=ls)
        arr(axA, centres[HEADS_NEW], (hx, yy), C_NEW, 1.5, rad=-0.10, ls=ls)
        axA.text(hx + 9.5, yy - 3.7, note, ha="center", va="center",
                 fontsize=7.0, color=C_NEW, style="italic")
    axA.text(hx + 9.5, 18.6,
             "33 parameters used at inference\n(66 trained, on a 2.22 M backbone)",
             ha="center", va="center", fontsize=7.0, color=C_NEW,
             fontweight="bold", linespacing=1.3)

    # legend
    lg = [(C_ENC, C_ENCBG, "encoder"), (C_NEST, C_NESTBG, "nested decoder"),
          (C_NEW, C_NEWBG, "added heads"), (C_DS, C_DSBG, "deep supervision")]
    for i, (e, f, t) in enumerate(lg):
        x = 1.0 + i * 16.5
        axA.add_patch(FancyBboxPatch((x, 0.4), 2.2, 2.1,
                      boxstyle="round,pad=0,rounding_size=0.3",
                      linewidth=0.9, edgecolor=e, facecolor=f))
        axA.text(x + 3.0, 1.45, t, ha="left", va="center", fontsize=7.0, color=e)
    axA.add_patch(Circle((67.5, 1.45), 1.3, facecolor=C_CBAMBG,
                  edgecolor=C_CBAM, linewidth=0.7))
    axA.text(67.5, 1.45, "C", ha="center", va="center", fontsize=7.5,
             color=C_CBAM, fontweight="bold")
    axA.text(69.4, 1.45, "CBAM in every conv block",
             ha="left", va="center", fontsize=7.0, color=C_CBAM)

    # ==================== PANEL B: CBAM detail ====================
    axB.text(0.5, 28.0, "B", fontsize=10, fontweight="bold", va="top")
    axB.text(6.0, 27.5, "CBAM block (inside every conv block)",
             fontsize=7.4, fontweight="bold", color=C_CBAM, va="top")
    # Labels are abbreviated relative to the 11 in version: at 7.2 pt on this
    # canvas a 15-character line no longer fits the box.
    # Base sizes here are set so that MATHTEXT SUBSCRIPTS clear 6 pt.
    # Matplotlib renders sub/superscripts at ~0.7x the base, so a 7 pt base
    # puts $M_c$'s subscript at 4.9 pt -- below Elsevier's artwork floor.
    bw, bh, by = 18.0, 9.0, 9.5
    steps = [("input\nfeature $F$", C_NEST, C_NESTBG),
             ("channel\nattn. $M_c$", C_CBAM, C_CBAMBG),
             ("$\\otimes$", C_CBAM, "#ffffff"),
             ("spatial\nattn. $M_s$", C_CBAM, C_CBAMBG),
             ("$\\otimes$", C_CBAM, "#ffffff"),
             ("refined\nfeature $F''$", C_NEST, C_NESTBG)]
    xs = 1.0
    for i, (t, e, f) in enumerate(steps):
        w = 6.5 if t == "$\\otimes$" else bw
        rbox(axB, xs, by, w, bh, t, e, f, fs=10.0)
        if i < len(steps) - 1:
            arr(axB, (xs + w, by + bh / 2), (xs + w + 1.7, by + bh / 2), C_NEST, 0.9)
        xs += w + 1.7
    axB.text(1.0, 4.6,
             "channel: avg- and max-pool $\\rightarrow$ shared MLP $\\rightarrow$ sigmoid\n"
             "spatial: pool across channels $\\rightarrow$ $7\\times7$ conv $\\rightarrow$ sigmoid",
             fontsize=7.2, color=C_NEST, va="center", linespacing=1.5)

    # ==================== PANEL C: loss ====================
    axC.text(0.5, 28.0, "C", fontsize=10, fontweight="bold", va="top")
    axC.text(8.0, 27.5, "Training objective", fontsize=7.4,
             fontweight="bold", color=C_NEST, va="top")
    axC.text(50, 20.0,
             r"$\mathcal{L}=\mathcal{L}_{\mathrm{fg}}"
             r"+w_d\,\mathcal{L}_{\mathrm{dist}}"
             r"+w_b\,\mathcal{L}_{\mathrm{bnd}}$",
             ha="center", va="center", fontsize=10.0, color=C_NEST)
    # The three boxes carry the DESCRIPTION only. Repeating the symbols here
    # would mean three more deeply-subscripted labels in the narrowest panel
    # of the figure, and the equation directly above already names them.
    terms = [("BCE + Dice,\n3 DS heads", C_DS, C_DSBG, "-"),
             ("L1 on the\ndist. map", C_NEW, C_NEWBG, "-"),
             ("pos-weighted\nBCE (aux.)", C_NEW, C_NEWBG, (0, (3, 2)))]
    tw = 30.5
    for i, (txt, e, f, ls) in enumerate(terms):
        x = 2.0 + i * (tw + 2.0)
        rbox(axC, x, 3.6, tw, 11.0, txt, e, f, fs=7.2, bold=False, ls=ls)
        arr(axC, (50, 16.5), (x + tw / 2, 14.6), e, 0.8, rad=0.0, ls=ls)
    axC.text(50, 0.8, "weights 1.0; the boundary term trains only",
             ha="center", va="center", fontsize=7.0, color=C_NEST, style="italic")

    for ext in ("pdf", "png"):
        fig.savefig(f"{outpath}.{ext}", dpi=600, bbox_inches="tight",
                    facecolor="white")
    plt.close(fig)
    print(f"wrote {outpath}.pdf and {outpath}.png")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=".")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    build(os.path.join(a.out, "Fig2_architecture"))
