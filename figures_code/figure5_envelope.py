#!/usr/bin/env python3
"""
Figure 5 -- the accuracy/validity envelope.

Top:    per-image mean foreground IoU across six confluence bins.
Bottom: matched-instance F1 at IoU 0.5 for the instance-preserving
        extension and for connected-component labelling of the identical
        foreground.

Re-plots directly from the binned data written by
phase20_key_figures.py::fig_envelope_v2, so it cannot drift from the
numbers quoted in Section 3.1. No model, no GPU, no re-inference.

    python figure5_envelope.py --data ../figures/envelope_v2_data.csv --out .

Sized for single-column reproduction (86 mm), so type is set at the size it
will actually print rather than being scaled down by LaTeX.
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

EXPECTED = {
    "iou_mean": [0.832, 0.850, 0.852, 0.860, 0.886, 0.905],
    "f1_ws": [0.783, 0.764, 0.749, 0.713, 0.708, 0.652],
    "f1_cc": [0.416, 0.222, 0.159, 0.086, 0.042, 0.017],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="../figures/envelope_v2_data.csv")
    ap.add_argument("--out", default=".")
    a = ap.parse_args()

    d = pd.read_csv(a.data)

    # Refuse to draw a figure that disagrees with the manuscript.
    for col, want in EXPECTED.items():
        got = [round(v, 3) for v in d[col]]
        if got != want:
            raise SystemExit(
                f"ABORT: {col} on disk is {got}, manuscript Section 3.1 says "
                f"{want}. Do not ship a figure that contradicts the text."
            )
    print(f"verified against Section 3.1: {len(d)} bins, n = {int(d['n'].sum())} images")

    lo, hi = d["iou_mean"].min(), d["iou_mean"].max()

    plt.rcParams.update({"font.size": 7.5, "axes.labelsize": 7.5,
                         "xtick.labelsize": 7, "ytick.labelsize": 7})

    fig, (axT, axB) = plt.subplots(
        2, 1, figsize=(3.4, 3.5), sharex=True,
        gridspec_kw=dict(height_ratios=[1, 1.25], hspace=0.10))

    axT.axhspan(lo, hi, color=NAVY, alpha=0.08, zorder=0)
    axT.plot(d["phi_mid"], d["iou_mean"], "-o", color=NAVY, ms=3.5, lw=1.4)
    axT.set_ylim(0.60, 1.0)
    axT.set_ylabel("foreground IoU")
    axT.grid(alpha=0.15)
    axT.annotate(f"{lo:.3f}–{hi:.3f}", xy=(d["phi_mid"].iloc[0], hi),
                 xytext=(2, 5), textcoords="offset points",
                 fontsize=6.5, color=NAVY)

    axB.plot(d["phi_mid"], d["f1_ws"], "-o", color=BLUE, ms=3.5, lw=1.4,
             label="instance-preserving extension (ours)")
    axB.plot(d["phi_mid"], d["f1_cc"], "-s", color=CRIM, ms=3.5, lw=1.4,
             label="connected components")
    axB.set_ylim(0, 1.0)
    axB.set_xlabel("confluence  $\\varphi$")
    axB.set_ylabel("matched-instance F1")
    axB.legend(frameon=False, fontsize=6.5, loc="upper right")
    axB.grid(alpha=0.15)

    fig.align_ylabels([axT, axB])
    os.makedirs(a.out, exist_ok=True)
    for ext in ("pdf", "png"):
        p = os.path.join(a.out, f"Fig4_envelope.{ext}")
        fig.savefig(p, dpi=400, bbox_inches="tight")
        print("wrote", p)
    plt.close(fig)


if __name__ == "__main__":
    main()
