#!/usr/bin/env python3
"""
EXPERIMENT: Figures 5 and 6 merged into one four-panel float.

Both concern the operating point -- the top row is the accuracy/validity
dissociation, the bottom row is the trade-off that dissociation forces -- so
combining them removes a full-width float and puts the argument in one place.

Top row  reads figures/envelope_v2_data.csv (same source as figure5_envelope.py)
Bottom row reads optimize/validation_sweep.csv, pareto_front.csv, test_frozen.csv

    python figure5_merged.py --out .

Writes Fig5_merged.{pdf,png}. Aborts if the envelope numbers stop matching
Section 3.1.
"""
from __future__ import annotations

import argparse
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

NAVY = "#08306B"
CRIM = "#B2182B"
BLUE = "#2166AC"
GREY = "#555555"

EXPECTED = {
    "iou_mean": [0.832, 0.850, 0.852, 0.860, 0.886, 0.905],
    "f1_ws": [0.783, 0.764, 0.749, 0.713, 0.708, 0.652],
    "f1_cc": [0.416, 0.222, 0.159, 0.086, 0.042, 0.017],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default="../figures/envelope_v2_data.csv")
    ap.add_argument("--sweep", default="../optimize/validation_sweep.csv")
    ap.add_argument("--pareto", default="../optimize/pareto_front.csv")
    ap.add_argument("--frozen", default="../optimize/test_frozen.csv")
    ap.add_argument("--out", default=".")
    a = ap.parse_args()

    e = pd.read_csv(a.env)
    for col, want in EXPECTED.items():
        got = [round(v, 3) for v in e[col]]
        if got != want:
            raise SystemExit(f"ABORT: {col} is {got}, Section 3.1 says {want}")
    sw = pd.read_csv(a.sweep)
    pf = pd.read_csv(a.pareto)

    plt.rcParams.update({"font.family": "sans-serif",
                         "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
                         "font.size": 7.5, "axes.labelsize": 7.5,
                         "xtick.labelsize": 7.2, "ytick.labelsize": 7.2,
                         "axes.linewidth": 0.6})

    fig, axs = plt.subplots(2, 2, figsize=(6.75, 4.95),
                            gridspec_kw=dict(hspace=0.62, wspace=0.30))
    (aA, aB), (aC, aD) = axs

    # ---- A: foreground IoU -------------------------------------------------
    lo, hi = e.iou_mean.min(), e.iou_mean.max()
    aA.axhspan(lo, hi, color=NAVY, alpha=0.08, zorder=0)
    aA.plot(e.phi_mid, e.iou_mean, "-o", color=NAVY, ms=3.4, lw=1.4)
    aA.set_ylim(0.60, 1.0)
    aA.set_xlabel("confluence  $\\varphi$")
    aA.set_ylabel("foreground IoU")
    aA.grid(alpha=0.15)
    aA.set_title(f"pixel accuracy rises ({lo:.3f}$\\rightarrow${hi:.3f})",
                 fontsize=7.6, color=NAVY, pad=3)

    # ---- B: matched-instance F1 -------------------------------------------
    aB.plot(e.phi_mid, e.f1_ws, "-o", color=BLUE, ms=3.4, lw=1.4,
            label="instance-preserving (ours)")
    aB.plot(e.phi_mid, e.f1_cc, "-s", color=CRIM, ms=3.4, lw=1.4,
            label="connected components")
    aB.set_ylim(0, 1.0)
    aB.set_xlabel("confluence  $\\varphi$")
    aB.set_ylabel("matched-instance F1")
    aB.legend(frameon=False, fontsize=6.9, loc="upper right")
    aB.grid(alpha=0.15)
    aB.set_title("instance detection collapses beneath it",
                 fontsize=7.6, color=CRIM, pad=3)

    # ---- C and D: the trade-off the dissociation forces --------------------
    # pf is the front in the FULL three-objective space, so projecting it onto
    # two axes and joining the points in order produces a sawtooth that is not
    # a front at all. Each panel therefore gets its own 2-D non-dominated set.
    def front_2d(df, xcol, lower_x_is_better):
        pts = df[[xcol, "f1"]].to_numpy()
        keep = []
        for i, (xi, yi) in enumerate(pts):
            dominated = False
            for j, (xj, yj) in enumerate(pts):
                if i == j:
                    continue
                bx = (xj <= xi) if lower_x_is_better else (xj >= xi)
                sx = (xj < xi) if lower_x_is_better else (xj > xi)
                if bx and yj >= yi and (sx or yj > yi):
                    dominated = True
                    break
            if not dominated:
                keep.append(i)
        return df.iloc[keep].sort_values(xcol)

    for ax, xcol, xlab, lo_better in (
            (aC, "abs_bias", "mean $|$shape-index bias$|$", True),
            (aD, "amp_ratio", "trajectory amplitude ratio", False)):
        s = ax.scatter(sw[xcol], sw.f1, c=sw.amp_ratio, cmap="viridis",
                       s=13, linewidths=0.3, edgecolors="white", zorder=2)
        fr = front_2d(sw, xcol, lo_better)
        ax.plot(fr[xcol], fr.f1, "-", color=GREY, lw=1.0, alpha=0.85,
                zorder=1, label="Pareto front")
        ax.scatter(fr[xcol], fr.f1, facecolors="none", edgecolors=GREY,
                   s=34, linewidths=0.7, zorder=3)
        ax.set_xlabel(xlab)
        ax.set_ylabel("detection F1")
        ax.grid(alpha=0.15)
        ax.legend(frameon=False, fontsize=6.9, loc="lower left")
    aC.set_title("detection-optimal is not measurement-optimal",
                 fontsize=7.6, color=GREY, pad=3)
    aD.set_title("amplitude is preserved only off the F1 peak",
                 fontsize=7.6, color=GREY, pad=3)
    cb = fig.colorbar(s, ax=[aC, aD], fraction=0.035, pad=0.02)
    cb.set_label("amplitude ratio", fontsize=7.2)
    cb.ax.tick_params(labelsize=6.9)

    for k, ax in enumerate((aA, aB, aC, aD)):
        ax.text(-0.19, 1.20, "ABCD"[k], transform=ax.transAxes,
                fontsize=9, fontweight="bold", va="top", ha="left")

    os.makedirs(a.out, exist_ok=True)
    for ext in ("pdf", "png"):
        p = os.path.join(a.out, f"Fig5_merged.{ext}")
        fig.savefig(p, dpi=400, bbox_inches="tight")
        print("wrote", p)
    plt.close(fig)
    print(f"envelope verified: {len(e)} bins, n = {int(e['n'].sum())} images; "
          f"sweep: {len(sw)} settings, {len(pf)} on the Pareto front")


if __name__ == "__main__":
    main()
