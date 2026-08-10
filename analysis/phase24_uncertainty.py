#!/usr/bin/env python3
"""
Bootstrap confidence intervals and paired significance tests for Table 1.

Resampling is over IMAGES, which is the unit of independence: cells within a
field are not independent, so resampling cells would understate the interval.
For each replicate the images are drawn with replacement and F1 is recomputed
from the POOLED tp/fp/fn of the draw, matching how the manuscript computes F1
in the first place (it is not a mean of per-image F1 scores).

The paired tests use per-image F1 and the Wilcoxon signed-rank statistic,
which does not assume normality -- per-image F1 is bounded in [0, 1] and
strongly skewed for connected components.

    python phase24_uncertainty.py --per-image stats/per_image_f1.csv
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon


def f1_from(tp, fp, fn):
    d = 2 * tp + fp + fn
    return float(2 * tp / d) if d > 0 else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-image", default="stats/per_image_f1.csv")
    ap.add_argument("--reps", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="stats/uncertainty.csv")
    a = ap.parse_args()

    df = pd.read_csv(a.per_image)
    methods = list(df.method.unique())
    files = sorted(df.file.unique())
    n = len(files)
    print(f"{n} images, {len(methods)} methods, {a.reps} bootstrap replicates\n")

    # index tp/fp/fn as [method][image] so a replicate is a single fancy-index
    idx = {m: df[df.method == m].set_index("file").reindex(files) for m in methods}

    rng = np.random.default_rng(a.seed)
    draws = rng.integers(0, n, size=(a.reps, n))

    rows = []
    print(f"{'method':22s} {'F1':>6s}   {'95% CI':>16s}   {'mean matched IoU':>16s}")
    print("-" * 70)
    for m in methods:
        g = idx[m]
        tp, fp, fn = g.tp.to_numpy(), g.fp.to_numpy(), g.fn.to_numpy()
        point = f1_from(tp.sum(), fp.sum(), fn.sum())
        bs = np.array([f1_from(tp[d].sum(), fp[d].sum(), fn[d].sum()) for d in draws])
        lo, hi = np.percentile(bs, [2.5, 97.5])
        miou = float(np.nanmean(g.matched_iou.to_numpy()))
        print(f"{m:22s} {point:6.3f}   [{lo:.3f}, {hi:.3f}]   {miou:16.3f}")
        rows.append(dict(method=m, f1=round(point, 4), ci_lo=round(lo, 4),
                         ci_hi=round(hi, 4), mean_matched_iou=round(miou, 4),
                         n_images=n, reps=a.reps))

    pd.DataFrame(rows).to_csv(a.out, index=False)
    print(f"\nwrote {a.out}")

    print("\nWilcoxon signed-rank on per-image F1 (two-sided)")
    print("-" * 70)
    ours = "ours (watershed)"
    for other in [m for m in methods if m != ours]:
        x = idx[ours].f1.to_numpy()
        y = idx[other].f1.to_numpy()
        ok = np.isfinite(x) & np.isfinite(y)
        st = wilcoxon(x[ok], y[ok], zero_method="wilcox")
        nz = int((x[ok] != y[ok]).sum())
        med = float(np.median(x[ok] - y[ok]))
        print(f"  {ours} vs {other}")
        print(f"    W = {st.statistic:.1f}   p = {st.pvalue:.3g}   "
              f"n = {int(ok.sum())} images ({nz} non-tied)   "
              f"median per-image difference = {med:+.3f}")


if __name__ == "__main__":
    main()
