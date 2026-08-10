#!/usr/bin/env python3
"""
Figure 8 -- recovery of per-lineage trajectories from segmented masks.

Re-plots directly from atlas_instance/atlas_per_image.csv, the file that backs
Section 3.6 and Table 4, so the figure cannot drift from the text. Running
phase17_atlas_from_instances.py instead would recompute the whole atlas and
overwrite those CSVs, which is not something a figure rebuild should do.

Authored at the placed width (\\textwidth), so LaTeX applies no downscale and
the font sizes set here are the sizes that print. The previous asset was 12 in
wide and was scaled to 58%, printing tick labels at 3.7 pt.

    python figure8_recovery.py --data ../atlas_instance/atlas_per_image.csv --out .
"""
from __future__ import annotations

import argparse
import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import MaxNLocator

STYLE = {"expert":   ("#222222", "-",  "expert"),
         "ours":     ("#2166AC", "-",  "ours (instance-preserving)"),
         "conncomp": ("#B2182B", "--", "connected components")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="../atlas_instance/atlas_per_image.csv")
    ap.add_argument("--out", default=".")
    ap.add_argument("--bins", type=int, default=5)
    a = ap.parse_args()

    d = pd.read_csv(a.data)
    cts = sorted(d.cell_type.dropna().unique())
    ncol = min(4, max(1, len(cts)))
    nrow = int(math.ceil(len(cts) / ncol))

    plt.rcParams.update({"font.family": "sans-serif",
                         "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"]})
    fig, axes = plt.subplots(nrow, ncol, figsize=(1.72 * ncol, 1.58 * nrow),
                             squeeze=False)

    for i, ct in enumerate(cts):
        ax = axes[i // ncol][i % ncol]
        g = d[d.cell_type == ct]
        for s, (c, ls, lab) in STYLE.items():
            sub = g.dropna(subset=[f"meanq_{s}", "phi"])
            if len(sub) < 6:
                continue
            try:
                b = pd.qcut(sub["phi"], a.bins, labels=False, duplicates="drop")
            except Exception:
                continue
            agg = (sub.assign(_b=b).groupby("_b", as_index=False)
                      .agg(phi=("phi", "median"), m=(f"meanq_{s}", "mean")))
            ax.plot(agg["phi"], agg["m"], ls, color=c, marker="o",
                    ms=2.4, lw=1.1, label=lab)
        ax.set_title(ct, fontsize=8.0, pad=2.5)
        ax.tick_params(labelsize=7.0, length=2.2, width=0.6, pad=1.5)
        ax.grid(alpha=0.15)
        ax.xaxis.set_major_locator(MaxNLocator(nbins=4, prune="both"))
        ax.yaxis.set_major_locator(MaxNLocator(nbins=4))
        for sp in ax.spines.values():
            sp.set_linewidth(0.6)
        if i % ncol == 0:
            ax.set_ylabel("mean $q$", fontsize=7.5)
        if i // ncol == nrow - 1:
            ax.set_xlabel("confluence $\\varphi$", fontsize=7.5)

    for j in range(len(cts), nrow * ncol):
        axes[j // ncol][j % ncol].axis("off")

    h, l = axes[0][0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=3, frameon=False, fontsize=7.5)
    fig.tight_layout(rect=[0, 0.075, 1, 1])
    os.makedirs(a.out, exist_ok=True)
    for ext in ("pdf", "png"):
        p = os.path.join(a.out, f"atlas_comparison.{ext}")
        fig.savefig(p, dpi=400, bbox_inches="tight")
        print("wrote", p)
    plt.close(fig)
    print(f"{len(cts)} lineages, {len(d)} image records, {a.bins} confluence bins")


if __name__ == "__main__":
    main()
