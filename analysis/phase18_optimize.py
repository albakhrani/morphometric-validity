#!/usr/bin/env python3
"""
Phase 18 - Multi-objective post-processing optimisation  (Paper 2, Option B)
============================================================================
Improves the method for a real reason, and does so defensibly.

WHY THIS EXISTS
    Phase 14 tuned watershed to maximise detection F1. Phase 17 then showed that
    the F1-optimal setting over-segments: predicted trajectories keep the right
    DIRECTION but their AMPLITUDE is compressed (~4x for SK-OV-3), because
    fragments are rounder than whole cells. Detection-optimal is therefore not
    measurement-optimal - a finding in its own right.

WHAT IT DOES
    Sweeps the watershed parameters and scores each setting on three objectives:
        f1              matched detection F1 @ IoU 0.5          (higher better)
        abs_bias        |mean q - expert mean q|                (lower  better)
        amplitude_ratio predicted trajectory range / expert range (target 1.0)
    then reports the Pareto front, so the operating point is CHOSEN and REPORTED
    rather than silently optimised.

METHODOLOGICAL DISCIPLINE (important for the paper)
    Parameters are selected on the VALIDATION split and the chosen setting is
    then evaluated once on TEST. Tuning and reporting on the same images would
    inflate the result and would not survive review. Use --val-* for selection
    and --test-* for the frozen evaluation.

Usage
    # select on validation, then freeze and evaluate on test
    python phase18_optimize.py \
        --model runs/instance/best.pt \
        --val-images data/raw/livecell_train_val_images \
        --val-coco   data/raw/livecell/livecell_coco_val.json \
        --test-images data/raw/livecell_test_images \
        --test-coco   data/raw/livecell/livecell_coco_test.json \
        --out optimize --subsample 150
"""
from __future__ import annotations

import argparse
import itertools
import logging
import math
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from phase13_watershed_infer import (                      # noqa: E402
    read_image, percentile_norm, predict_maps, watershed_instances,
    connected_components, celltype_of)
from phase14_evaluate import match_f1, f1, gt_label_image  # noqa: E402
from phase17_atlas_from_instances import (                 # noqa: E402
    geometry_from_labels, parse_hours)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("optimize")


# --------------------------------------------------------------------------
def build_cache(model, coco, image_dir, items, device, amp, min_area):
    """Predict maps once per image; also store expert labels and expert mean q."""
    cache = []
    for k, (iid, fn, phi, H, W) in enumerate(items, 1):
        img = percentile_norm(read_image(os.path.join(image_dir, fn)))
        fg, dist, bnd = predict_maps(model, img, device, amp)
        gt = gt_label_image(coco, iid, H, W)
        g = geometry_from_labels(gt, min_area=min_area)
        cache.append(dict(fn=fn, phi=phi, cell_type=celltype_of(fn),
                          fg=fg.astype(np.float16), dist=dist.astype(np.float16),
                          bnd=bnd.astype(np.float16), gt=gt,
                          gt_meanq=(float(np.mean([d["q"] for d in g])) if g else np.nan)))
        if k % 50 == 0:
            log.info("  cached %d/%d", k, len(items))
    return cache


def amplitude_ratio(cache, meanq_pred):
    """Per-lineage ratio of predicted trajectory range to expert range.

    Trajectory range = (mean q in the top confluence tercile) minus
    (mean q in the bottom tercile). Ratio 1.0 = amplitude preserved;
    <1 = compressed (over-segmentation); the median over lineages is returned.
    """
    ratios = []
    by_ct = {}
    for i, c in enumerate(cache):
        by_ct.setdefault(c["cell_type"], []).append(i)
    for ct, idx in by_ct.items():
        phis = np.array([cache[i]["phi"] for i in idx])
        gtq = np.array([cache[i]["gt_meanq"] for i in idx])
        pq = np.array([meanq_pred[i] for i in idx])
        ok = np.isfinite(gtq) & np.isfinite(pq)
        if ok.sum() < 9:
            continue
        phis, gtq, pq = phis[ok], gtq[ok], pq[ok]
        lo_t, hi_t = np.quantile(phis, [1 / 3, 2 / 3])
        lo = phis <= lo_t
        hi = phis >= hi_t
        if lo.sum() < 2 or hi.sum() < 2:
            continue
        gt_range = float(np.mean(gtq[hi]) - np.mean(gtq[lo]))
        pr_range = float(np.mean(pq[hi]) - np.mean(pq[lo]))
        if abs(gt_range) < 0.05:          # expert trend too small to be a reference
            continue
        ratios.append(pr_range / gt_range)
    return float(np.median(ratios)) if ratios else float("nan")


def score_setting(cache, st, md, ms, min_area):
    """Return (f1, abs_bias, amplitude_ratio, mean_recovery) for one setting."""
    TP = FP = FN = 0
    biases, meanq_pred, recs = [], [], []
    for c in cache:
        ws = watershed_instances(c["fg"].astype(np.float32), c["dist"].astype(np.float32),
                                 c["bnd"].astype(np.float32),
                                 seed_thr=st, min_distance=md, min_size=ms)
        tp, fp, fn_, _ = match_f1(ws, c["gt"])
        TP += tp; FP += fp; FN += fn_
        g = geometry_from_labels(ws, min_area=min_area)
        mq = float(np.mean([d["q"] for d in g])) if g else np.nan
        meanq_pred.append(mq)
        if np.isfinite(mq) and np.isfinite(c["gt_meanq"]):
            biases.append(mq - c["gt_meanq"])
        ng = max(int(c["gt"].max()), 1)
        recs.append(int(ws.max()) / ng)
    return (f1(TP, FP, FN),
            float(np.mean(np.abs(biases))) if biases else float("nan"),
            amplitude_ratio(cache, meanq_pred),
            float(np.median(recs)) if recs else float("nan"))


def pareto_front(df, cols_max, cols_min):
    """Boolean mask of non-dominated rows."""
    vals = df[cols_max + cols_min].to_numpy(float).copy()
    for j in range(len(cols_max), vals.shape[1]):
        vals[:, j] = -vals[:, j]                      # minimise -> maximise
    n = len(vals)
    keep = np.ones(n, bool)
    for i in range(n):
        if not keep[i]:
            continue
        for j in range(n):
            if i == j or not keep[j]:
                continue
            if np.all(vals[j] >= vals[i]) and np.any(vals[j] > vals[i]):
                keep[i] = False
                break
    return keep


def collect_items(coco, image_dir, subsample, min_hours):
    on_disk = set(os.listdir(image_dir))
    recs = []
    for iid in coco.getImgIds():
        info = coco.loadImgs(iid)[0]
        fn = info["file_name"]
        if fn not in on_disk:
            continue
        anns = coco.loadAnns(coco.getAnnIds(imgIds=iid))
        if not anns:
            continue
        hrs = parse_hours(fn)
        if min_hours and np.isfinite(hrs) and hrs < min_hours:
            continue
        phi = sum(float(x.get("area", 0.0)) for x in anns) / float(info["height"] * info["width"])
        recs.append((iid, fn, phi, info["height"], info["width"]))
    recs.sort(key=lambda r: r[2])
    step = max(1, len(recs) // subsample)
    return recs[::step][:subsample]


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Multi-objective watershed optimisation")
    ap.add_argument("--model", required=True)
    ap.add_argument("--val-images", required=True)
    ap.add_argument("--val-coco", required=True)
    ap.add_argument("--test-images", default=None)
    ap.add_argument("--test-coco", default=None)
    ap.add_argument("--out", default="optimize")
    ap.add_argument("--base-channels", type=int, default=32)
    ap.add_argument("--depth", type=int, default=4)
    ap.add_argument("--subsample", type=int, default=150)
    ap.add_argument("--min-area", type=int, default=150)
    ap.add_argument("--min-hours", type=float, default=8.0)
    ap.add_argument("--seed-grid", type=float, nargs="*",
                    default=[0.35, 0.45, 0.55, 0.65, 0.75])
    ap.add_argument("--dist-grid", type=int, nargs="*", default=[4, 6, 8, 10, 12])
    ap.add_argument("--size-grid", type=int, nargs="*", default=[50, 150, 300])
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    import torch
    import pandas as pd
    from pycocotools.coco import COCO
    from phase11_instance_model import build_instance_model

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    amp = torch.bfloat16 if device.type == "cuda" else torch.float32
    model = build_instance_model(base_channels=a.base_channels, depth=a.depth)
    ck = torch.load(a.model, map_location="cpu", weights_only=False)
    model.load_state_dict(ck.get("model_state_dict", ck))
    model.to(device).eval()
    log.info("loaded %s (epoch %s)", a.model, ck.get("epoch", "?"))

    # ---------------- selection on VALIDATION ----------------
    log.info("=== selection split (validation) ===")
    vcoco = COCO(a.val_coco)
    vitems = collect_items(vcoco, a.val_images, a.subsample, a.min_hours)
    log.info("validation: %d images, phi %.2f-%.2f",
             len(vitems), vitems[0][2], vitems[-1][2])
    vcache = build_cache(model, vcoco, a.val_images, vitems, device, amp, a.min_area)

    combos = list(itertools.product(a.seed_grid, a.dist_grid, a.size_grid))
    log.info("evaluating %d settings on validation ...", len(combos))
    rows = []
    for n, (st, md, ms) in enumerate(combos, 1):
        f1v, bias, amp_r, rec = score_setting(vcache, st, md, ms, a.min_area)
        rows.append(dict(seed_thr=st, min_distance=md, min_size=ms,
                         f1=round(f1v, 4), abs_bias=round(bias, 4),
                         amp_ratio=round(amp_r, 4) if np.isfinite(amp_r) else np.nan,
                         amp_err=round(abs(1 - amp_r), 4) if np.isfinite(amp_r) else np.nan,
                         recovery_med=round(rec, 3)))
        if n % 15 == 0:
            log.info("  %d/%d", n, len(combos))
    dfv = pd.DataFrame(rows)
    dfv.to_csv(os.path.join(a.out, "validation_sweep.csv"), index=False)

    ok = dfv.dropna(subset=["f1", "abs_bias", "amp_err"]).copy()
    mask = pareto_front(ok, cols_max=["f1"], cols_min=["abs_bias", "amp_err"])
    front = ok[mask].sort_values("f1", ascending=False)
    front.to_csv(os.path.join(a.out, "pareto_front.csv"), index=False)

    best_f1 = ok.loc[ok["f1"].idxmax()]
    best_bias = ok.loc[ok["abs_bias"].idxmin()]
    best_amp = ok.loc[ok["amp_err"].idxmin()]
    # balanced pick: best F1 among settings within 20% of the best bias
    thr = best_bias["abs_bias"] * 1.2
    cand = ok[ok["abs_bias"] <= thr]
    balanced = cand.loc[cand["f1"].idxmax()] if len(cand) else best_f1

    print("\n" + "=" * 92)
    print(" VALIDATION SWEEP - PARETO FRONT (non-dominated on F1 / bias / amplitude)")
    print(front.head(12).to_string(index=False))
    print("-" * 92)
    print(" objective-optimal settings on VALIDATION")
    for name, r in (("max F1", best_f1), ("min |bias|", best_bias),
                    ("best amplitude", best_amp), ("balanced", balanced)):
        print(f"   {name:16s} seed {r['seed_thr']:.2f}  dist {int(r['min_distance']):2d}  "
              f"size {int(r['min_size']):3d}  ->  F1 {r['f1']:.3f}  "
              f"|bias| {r['abs_bias']:.3f}  amp {r['amp_ratio']:.2f}")
    print("=" * 92)

    # ---------------- frozen evaluation on TEST ----------------
    if a.test_images and a.test_coco:
        log.info("=== frozen evaluation (test) ===")
        tcoco = COCO(a.test_coco)
        titems = collect_items(tcoco, a.test_images, a.subsample, a.min_hours)
        tcache = build_cache(model, tcoco, a.test_images, titems, device, amp, a.min_area)

        trows = []
        for name, r in (("max F1", best_f1), ("min |bias|", best_bias),
                        ("best amplitude", best_amp), ("balanced", balanced)):
            f1t, biast, ampt, rect = score_setting(
                tcache, float(r["seed_thr"]), int(r["min_distance"]),
                int(r["min_size"]), a.min_area)
            trows.append(dict(selected_for=name, seed_thr=float(r["seed_thr"]),
                              min_distance=int(r["min_distance"]),
                              min_size=int(r["min_size"]),
                              test_f1=round(f1t, 4), test_abs_bias=round(biast, 4),
                              test_amp_ratio=round(ampt, 4) if np.isfinite(ampt) else np.nan,
                              test_recovery_med=round(rect, 3)))
        # connected-components reference on the same test cache
        TP = FP = FN = 0; bl = []
        for c in tcache:
            cc = connected_components(c["fg"].astype(np.float32), min_size=50)
            tp, fp, fn_, _ = match_f1(cc, c["gt"]); TP += tp; FP += fp; FN += fn_
            g = geometry_from_labels(cc, min_area=a.min_area)
            mq = float(np.mean([d["q"] for d in g])) if g else np.nan
            if np.isfinite(mq) and np.isfinite(c["gt_meanq"]):
                bl.append(mq - c["gt_meanq"])
        trows.append(dict(selected_for="connected components (reference)",
                          seed_thr=np.nan, min_distance=np.nan, min_size=50,
                          test_f1=round(f1(TP, FP, FN), 4),
                          test_abs_bias=round(float(np.mean(np.abs(bl))), 4) if bl else np.nan,
                          test_amp_ratio=np.nan, test_recovery_med=np.nan))
        dft = pd.DataFrame(trows)
        dft.to_csv(os.path.join(a.out, "test_frozen.csv"), index=False)
        print("\n" + "=" * 92)
        print(" FROZEN TEST RESULT  (parameters chosen on validation, evaluated once here)")
        print(dft.to_string(index=False))
        print("=" * 92)

    # ---------------- figure ----------------
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.9))
    sc = ax[0].scatter(ok["abs_bias"], ok["f1"], c=ok["amp_ratio"], cmap="viridis",
                       s=26, edgecolor="none")
    ax[0].scatter(front["abs_bias"], front["f1"], facecolors="none",
                  edgecolors="#B2182B", s=70, linewidths=1.2, label="Pareto front")
    ax[0].set_xlabel("|bias| in mean $q$  (lower better)")
    ax[0].set_ylabel("matched F1 @ IoU 0.5  (higher better)")
    ax[0].set_title("detection vs measurement trade-off", fontsize=9)
    ax[0].legend(frameon=False, fontsize=8); ax[0].grid(alpha=0.15)
    plt.colorbar(sc, ax=ax[0], label="amplitude ratio")
    ax[1].axhline(1.0, ls="--", lw=0.8, color="#888")
    ax[1].scatter(ok["f1"], ok["amp_ratio"], s=26, color="#2166AC", edgecolor="none")
    ax[1].set_xlabel("matched F1 @ IoU 0.5")
    ax[1].set_ylabel("trajectory amplitude ratio (1.0 = preserved)")
    ax[1].set_title("does the F1-optimal setting preserve amplitude?", fontsize=9)
    ax[1].grid(alpha=0.15)
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(a.out, f"tradeoff.{ext}"), dpi=200, bbox_inches="tight")
    plt.close(fig)

    print(f"\n csv + figure written to {a.out}/")
    print(" Report the chosen operating point explicitly in the paper, and note that")
    print(" the F1-optimal and bias-optimal settings differ - that is a finding.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
