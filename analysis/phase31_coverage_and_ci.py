#!/usr/bin/env python3
"""
Coverage-corrected cross-source comparison, with bootstrap intervals.

Two defects in the earlier comparison are repaired here.

1. LISTWISE DELETION. A mask source that returns no measurable cell in an
   image contributes no per-image mean, so its correlation was computed over
   a different -- and non-random -- subset of images than the expert's. For
   connected components this is severe: it measures mainly the sparse fields,
   and the expert trajectory restricted to those fields is nearly flat, so a
   "direction failure" was being reported where there was really a coverage
   failure. Every cross-source quantity is therefore recomputed on the
   COMPLETE-CASE set: images where every source produced a measurable cell.

2. NO UNCERTAINTY. Per-lineage coefficients carried no interval, and a
   one-lineage margin was about to become the paper's headline. Every
   coefficient now gets a percentile bootstrap CI, resampling images within
   lineage.

Coverage is reported as a result in its own right, not as a footnote.

    python phase31_coverage_and_ci.py --per-image atlas_5src/atlas_per_image.csv
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np
import pandas as pd
from scipy import stats

SOURCES = [("conncomp", "connected components", 0.111),
           ("oursalt", "ours, measurement-optimal", 0.575),
           ("ours", "ours, detection-optimal", 0.709),
           ("cellpose", "Cellpose", 0.815)]

# Evidence tier from Table 4; C = trajectory not supported under control.
TIER = {"SkBr3": "A", "Huh7": "A", "BT474": "B", "BV2": "C",
        "MCF7": "C", "A172": "A", "SH-SY5Y": "A", "SK-OV-3": "A"}


def boot_rho(x, y, reps=2000, seed=0):
    """Percentile CI for Spearman rho, resampling pairs."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    if len(x) < 8:
        return np.nan, np.nan, np.nan, len(x)
    point = stats.spearmanr(x, y).statistic
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(x), size=(reps, len(x)))
    vals = np.array([stats.spearmanr(x[i], y[i]).statistic for i in idx])
    vals = vals[np.isfinite(vals)]
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return point, lo, hi, len(x)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-image", default="atlas_5src/atlas_per_image.csv")
    ap.add_argument("--reps", type=int, default=2000)
    ap.add_argument("--out", default="stats")
    a = ap.parse_args()

    d = pd.read_csv(a.per_image)
    os.makedirs(a.out, exist_ok=True)
    cols = {s: f"meanq_{s}" for s, _, _ in SOURCES}
    cols["expert"] = "meanq_expert"

    print("=" * 78)
    print("COVERAGE: fraction of images in which each source yields a measurable cell")
    print("=" * 78)
    cov_rows = []
    hdr = f"{'lineage':10s} {'n':>5s} " + "".join(f"{lab.split(',')[0][:11]:>13s}"
                                                  for _, lab, _ in SOURCES)
    print(hdr); print("-" * len(hdr))
    for ct, g in d.groupby("cell_type"):
        line = f"{ct:10s} {len(g):5d} "
        rec = dict(cell_type=ct, n_images=len(g))
        for s, lab, _ in SOURCES:
            frac = g[cols[s]].notna().mean()
            rec[f"cov_{s}"] = round(float(frac), 4)
            line += f"{100*frac:12.1f}%"
        cov_rows.append(rec)
        print(line)
    line = f"{'ALL':10s} {len(d):5d} "
    for s, _, _ in SOURCES:
        line += f"{100*d[cols[s]].notna().mean():12.1f}%"
    print(line)

    print("\nWhat gets dropped, and is it random?")
    for s, lab, _ in SOURCES:
        kept, drop = d[d[cols[s]].notna()], d[d[cols[s]].isna()]
        if len(drop) == 0:
            print(f"  {lab:26s} complete coverage")
            continue
        u = stats.mannwhitneyu(kept.phi, drop.phi, alternative="two-sided")
        print(f"  {lab:26s} dropped {len(drop):4d}/{len(d)}  "
              f"median phi kept {kept.phi.median():.3f} vs dropped {drop.phi.median():.3f}  "
              f"Mann-Whitney p = {u.pvalue:.3g}")

    # ---------------- complete-case set ----------------
    need = [cols[s] for s, _, _ in SOURCES] + [cols["expert"]]
    cc = d.dropna(subset=need)
    print("\n" + "=" * 78)
    print(f"COMPLETE-CASE SET: {len(cc)} of {len(d)} images have all "
          f"{len(SOURCES)} sources + expert")
    print("=" * 78)
    print(f"  median phi complete-case {cc.phi.median():.3f} vs full set {d.phi.median():.3f}")
    print("  per lineage: " + ", ".join(f"{ct} {len(g)}" for ct, g in cc.groupby("cell_type")))

    # ---------------- per-lineage rho with CIs ----------------
    print("\n" + "=" * 78)
    print("PER-LINEAGE rho ON THE COMPLETE-CASE SET, with bootstrap 95% CIs")
    print("=" * 78)
    traj_rows = []
    for ct, g in cc.groupby("cell_type"):
        e, elo, ehi, n = boot_rho(g.phi, g[cols["expert"]], a.reps)
        print(f"\n{ct}  (tier {TIER.get(ct,'?')}, n = {n})")
        print(f"   {'expert':26s} {e:+.3f}  [{elo:+.3f}, {ehi:+.3f}]")
        rec = dict(cell_type=ct, tier=TIER.get(ct), n=n,
                   rho_expert=round(e, 4), expert_lo=round(elo, 4), expert_hi=round(ehi, 4))
        for s, lab, _ in SOURCES:
            r, lo, hi, _ = boot_rho(g.phi, g[cols[s]], a.reps)
            agree = np.sign(r) == np.sign(e)
            excl0 = (lo > 0) or (hi < 0)
            rec[f"rho_{s}"] = round(r, 4)
            rec[f"{s}_lo"] = round(lo, 4)
            rec[f"{s}_hi"] = round(hi, 4)
            rec[f"{s}_agree"] = bool(agree)
            rec[f"{s}_excl0"] = bool(excl0)
            print(f"   {lab:26s} {r:+.3f}  [{lo:+.3f}, {hi:+.3f}]  "
                  f"{'sign OK ' if agree else 'SIGN OFF'}  "
                  f"{'CI excludes 0' if excl0 else 'CI spans 0'}")
        traj_rows.append(rec)

    t = pd.DataFrame(traj_rows)
    t.to_csv(os.path.join(a.out, "coverage_corrected_trajectories.csv"), index=False)
    pd.DataFrame(cov_rows).to_csv(os.path.join(a.out, "coverage_by_lineage.csv"), index=False)

    # ---------------- direction counts ----------------
    print("\n" + "=" * 78)
    print("DIRECTIONS RECOVERED (complete-case set)")
    print("=" * 78)
    sup = t[t.tier != "C"]
    print(f"{'source':28s} {'F1':>6s} {'all 8':>8s} {'tier A/B (6)':>14s} "
          f"{'A/B, expert CI excl 0':>24s}")
    print("-" * 82)
    strict = t[(t.tier != "C") & ((t.expert_lo > 0) | (t.expert_hi < 0))]
    summary = []
    for s, lab, f1 in SOURCES:
        a8 = int(t[f"{s}_agree"].sum())
        a6 = int(sup[f"{s}_agree"].sum())
        ast = int(strict[f"{s}_agree"].sum())
        print(f"{lab:28s} {f1:6.3f} {a8:6d}/8 {a6:12d}/6 {ast:22d}/{len(strict)}")
        summary.append(dict(source=lab, f1=f1, dir_all8=a8, dir_tierAB=a6,
                            dir_strict=ast, n_strict=len(strict)))
    pd.DataFrame(summary).to_csv(os.path.join(a.out, "direction_counts.csv"), index=False)
    print(f"\n  strict set = tier A/B lineages whose EXPERT rho CI excludes zero: "
          f"{', '.join(strict.cell_type)}")

    # ---------------- the BT-474 claim ----------------
    bt = t[t.cell_type == "BT474"]
    if len(bt):
        r = bt.iloc[0]
        print("\n" + "=" * 78)
        print("THE BT-474 'ERASURE' CLAIM, examined")
        print("=" * 78)
        print(f"  expert    {r.rho_expert:+.3f}  [{r.expert_lo:+.3f}, {r.expert_hi:+.3f}]")
        print(f"  Cellpose  {r.rho_cellpose:+.3f}  [{r.cellpose_lo:+.3f}, {r.cellpose_hi:+.3f}]"
              f"   CI {'EXCLUDES' if r.cellpose_excl0 else 'SPANS'} zero")
        print(f"  ours      {r.rho_ours:+.3f}  [{r.ours_lo:+.3f}, {r.ours_hi:+.3f}]"
              f"   CI {'EXCLUDES' if r.ours_excl0 else 'SPANS'} zero")
        overlap = not (r.cellpose_hi < r.ours_lo or r.ours_hi < r.cellpose_lo)
        print(f"  Cellpose and ours CIs {'OVERLAP' if overlap else 'DO NOT overlap'}")
        print("  -> the erasure claim is "
              + ("NOT supportable as stated" if overlap else "supportable"))

    print(f"\nwrote {a.out}/coverage_by_lineage.csv, "
          f"{a.out}/coverage_corrected_trajectories.csv, {a.out}/direction_counts.csv")


if __name__ == "__main__":
    main()
