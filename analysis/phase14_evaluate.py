#!/usr/bin/env python3
"""
Phase 14 - Density-resolved instance evaluation + auto-tuning  (Paper 2, Option B)
==================================================================================
Answers the question the mean recovery cannot: does watershed recover instances
correctly ACROSS THE DENSITY GRADIENT, and does it beat plain connected
components where it matters (crowded fields)?

It also removes the manual tuning: because matched-detection F1 penalises both
over-segmentation (false positives) and merging (false negatives), the script
grid-searches the watershed parameters and picks the setting that maximises F1 -
no eyeballing of overlays required.

Pipeline
  1. Run the trained model ONCE on a confluence-stratified subsample; cache the
     predicted (foreground, distance, boundary) maps.
  2. Grid-search watershed params (seed threshold x min distance x min size) on
     the cached maps, scoring by matched F1 @ IoU 0.5 against expert instances.
  3. With the best params, report per-confluence-bin:
       expert count, recovery (pred/expert), and F1@0.5,
       for watershed vs connected-components.
  4. Write a CSV and the before/after figure, and print the exact phase-13
     command to regenerate the FULL test set with the chosen params.

Matched F1 cannot be gamed by count cancellation (unlike the recovery ratio), so
it is the number to report in the paper.

Usage
  python phase14_evaluate.py \
      --model runs/instance/best.pt \
      --images data/raw/livecell_test_images \
      --coco   data/raw/livecell/livecell_coco_test.json \
      --out    eval_instance --subsample 180
"""
from __future__ import annotations

import argparse
import itertools
import logging
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from phase13_watershed_infer import (                          # noqa: E402
    read_image, percentile_norm, predict_maps,
    watershed_instances, connected_components, celltype_of)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("evaluate")


# --------------------------------------------------------------------------
def gt_label_image(coco, iid, H, W):
    lab = np.zeros((H, W), np.int32)
    for i, ann in enumerate(coco.loadAnns(coco.getAnnIds(imgIds=iid)), start=1):
        m = coco.annToMask(ann)
        lab[m > 0] = i
    return lab


def match_f1(pred, gt, iou_thr=0.5):
    """Greedy instance matching. Returns (tp, fp, fn, mean_matched_iou)."""
    pred = pred.astype(np.int64)
    gt = gt.astype(np.int64)
    npred, ngt = int(pred.max()), int(gt.max())
    if npred == 0 and ngt == 0:
        return 0, 0, 0, float("nan")
    if npred == 0:
        return 0, 0, ngt, float("nan")
    if ngt == 0:
        return 0, npred, 0, float("nan")

    area_p = np.bincount(pred.ravel(), minlength=npred + 1)
    area_g = np.bincount(gt.ravel(), minlength=ngt + 1)
    both = (pred > 0) & (gt > 0)
    pair = pred[both] * (ngt + 1) + gt[both]
    inter = np.bincount(pair, minlength=(npred + 1) * (ngt + 1))

    cand = []
    for ii in np.nonzero(inter)[0]:
        p, g = divmod(int(ii), ngt + 1)
        if p == 0 or g == 0:
            continue
        i = inter[ii]
        u = area_p[p] + area_g[g] - i
        iou = i / u if u > 0 else 0.0
        if iou >= iou_thr:
            cand.append((iou, p, g))
    cand.sort(reverse=True)
    used_p, used_g, ious = set(), set(), []
    for iou, p, g in cand:
        if p in used_p or g in used_g:
            continue
        used_p.add(p); used_g.add(g); ious.append(iou)
    tp = len(ious)
    return tp, npred - tp, ngt - tp, (float(np.mean(ious)) if ious else float("nan"))


def f1(tp, fp, fn):
    return 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) > 0 else 0.0


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Density-resolved instance evaluation")
    ap.add_argument("--model", required=True)
    ap.add_argument("--images", required=True)
    ap.add_argument("--coco", required=True)
    ap.add_argument("--out", default="eval_instance")
    ap.add_argument("--base-channels", type=int, default=32)
    ap.add_argument("--depth", type=int, default=4)
    ap.add_argument("--subsample", type=int, default=180,
                    help="confluence-stratified images used for tuning + evaluation")
    ap.add_argument("--bins", type=int, default=6)
    ap.add_argument("--seed-grid", type=float, nargs="*", default=[0.35, 0.45, 0.55])
    ap.add_argument("--dist-grid", type=int, nargs="*", default=[4, 6, 8])
    ap.add_argument("--size-grid", type=int, nargs="*", default=[20, 50])
    a = ap.parse_args()

    import torch
    from pycocotools.coco import COCO
    from phase11_instance_model import build_instance_model
    os.makedirs(a.out, exist_ok=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    amp_dtype = torch.bfloat16 if device.type == "cuda" else torch.float32

    model = build_instance_model(base_channels=a.base_channels, depth=a.depth)
    ck = torch.load(a.model, map_location="cpu", weights_only=False)
    model.load_state_dict(ck.get("model_state_dict", ck))
    model.to(device).eval()
    log.info("loaded %s (epoch %s)", a.model, ck.get("epoch", "?"))

    coco = COCO(a.coco)
    fn_to_id = {coco.loadImgs(i)[0]["file_name"]: i for i in coco.getImgIds()}
    on_disk = set(os.listdir(a.images))

    recs = []
    for fn, iid in fn_to_id.items():
        if fn not in on_disk:
            continue
        info = coco.loadImgs(iid)[0]
        anns = coco.loadAnns(coco.getAnnIds(imgIds=iid))
        if not anns:
            continue
        phi = sum(float(x.get("area", 0.0)) for x in anns) / float(info["height"] * info["width"])
        recs.append((iid, fn, phi, info["height"], info["width"]))
    recs.sort(key=lambda r: r[2])
    if not recs:
        log.error("no images matched between %s and the COCO file", a.images); return 2

    # confluence-stratified subsample
    step = max(1, len(recs) // a.subsample)
    sub = recs[::step][:a.subsample]
    log.info("subsample: %d images spanning phi %.2f-%.2f", len(sub), sub[0][2], sub[-1][2])

    # ---- pass 1: cache predicted maps + expert labels ----
    cache = []
    for k, (iid, fn, phi, H, W) in enumerate(sub, 1):
        img = percentile_norm(read_image(os.path.join(a.images, fn)))
        fg, dist, bnd = predict_maps(model, img, device, amp_dtype)
        gt = gt_label_image(coco, iid, H, W)
        cache.append(dict(fn=fn, phi=phi, fg=fg.astype(np.float16),
                          dist=dist.astype(np.float16), bnd=bnd.astype(np.float16),
                          gt=gt, n_gt=int(gt.max())))
        if k % 40 == 0:
            log.info("  cached %d/%d", k, len(sub))

    # ---- pass 2: grid-search watershed params by matched F1 ----
    log.info("tuning watershed over %d combinations ...",
             len(a.seed_grid) * len(a.dist_grid) * len(a.size_grid))
    results = []
    for st, md, ms in itertools.product(a.seed_grid, a.dist_grid, a.size_grid):
        TP = FP = FN = 0
        for c in cache:
            ws = watershed_instances(c["fg"].astype(np.float32), c["dist"].astype(np.float32),
                                     c["bnd"].astype(np.float32),
                                     seed_thr=st, min_distance=md, min_size=ms)
            tp, fp, fn, _ = match_f1(ws, c["gt"])
            TP += tp; FP += fp; FN += fn
        results.append((f1(TP, FP, FN), st, md, ms, TP, FP, FN))
    results.sort(reverse=True)
    best_f1, bst, bmd, bms = results[0][:4]

    print("\n" + "=" * 78)
    print(" WATERSHED PARAMETER SEARCH  (matched F1 @ IoU 0.5, higher = better)")
    print(f" {'seed_thr':>9} {'min_dist':>9} {'min_size':>9} {'F1':>8}")
    for r in results[:8]:
        star = "  <- best" if r[:4] == (best_f1, bst, bmd, bms) else ""
        print(f" {r[1]:9.2f} {r[2]:9d} {r[3]:9d} {r[0]:8.3f}{star}")
    print("=" * 78)

    # connected-components baseline F1 (params-independent, for reference)
    TPc = FPc = FNc = 0
    for c in cache:
        cc = connected_components(c["fg"].astype(np.float32), min_size=bms)
        tp, fp, fn, _ = match_f1(cc, c["gt"])
        TPc += tp; FPc += fp; FNc += fn
    print(f" connected-components baseline F1 = {f1(TPc, FPc, FNc):.3f}"
          f"   |   watershed (best) F1 = {best_f1:.3f}\n")

    # ---- pass 3: per-confluence-bin metrics with best params ----
    phis = np.array([c["phi"] for c in cache])
    edges = np.quantile(phis, np.linspace(0, 1, a.bins + 1))
    edges[-1] += 1e-6
    rows = []
    for b in range(a.bins):
        lo, hi = edges[b], edges[b + 1]
        idx = [i for i, p in enumerate(phis) if lo <= p < hi]
        if not idx:
            continue
        tW = fW = nW = tC = fC = nC = 0
        recW, recC = [], []
        for i in idx:
            c = cache[i]
            ws = watershed_instances(c["fg"].astype(np.float32), c["dist"].astype(np.float32),
                                     c["bnd"].astype(np.float32),
                                     seed_thr=bst, min_distance=bmd, min_size=bms)
            cc = connected_components(c["fg"].astype(np.float32), min_size=bms)
            a1, b1, d1, _ = match_f1(ws, c["gt"]); tW += a1; fW += b1; nW += d1
            a2, b2, d2, _ = match_f1(cc, c["gt"]); tC += a2; fC += b2; nC += d2
            ng = max(c["n_gt"], 1)
            recW.append(int(ws.max()) / ng)
            recC.append(int(cc.max()) / ng)
        rows.append(dict(bin=b, phi_lo=round(float(lo), 3), phi_hi=round(float(hi), 3),
                         phi_mid=round(float((lo + hi) / 2), 3), n_images=len(idx),
                         recov_ws_med=round(float(np.median(recW)), 3),
                         recov_cc_med=round(float(np.median(recC)), 3),
                         recov_ws_mean=round(float(np.mean(recW)), 3),
                         recov_cc_mean=round(float(np.mean(recC)), 3),
                         f1_ws=round(f1(tW, fW, nW), 3),
                         f1_cc=round(f1(tC, fC, nC), 3)))

    import pandas as pd
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(a.out, "density_resolved_instances.csv"), index=False)

    # ---- figure: recovery vs phi and F1 vs phi ----
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(9.5, 3.6))
    ax[0].axhline(1.0, ls="--", lw=0.8, color="#888")
    ax[0].plot(df["phi_mid"], df["recov_ws_med"], "-o", color="#2166AC", ms=4, label="watershed")
    ax[0].plot(df["phi_mid"], df["recov_cc_med"], "-s", color="#B2182B", ms=4, label="connected comp.")
    ax[0].set_xlabel("confluence  φ"); ax[0].set_ylabel("median instance recovery (pred / expert)")
    ax[0].set_title("recovery vs density", fontsize=9); ax[0].legend(frameon=False, fontsize=8)
    ax[0].grid(alpha=0.15)
    ax[1].plot(df["phi_mid"], df["f1_ws"], "-o", color="#2166AC", ms=4, label="watershed")
    ax[1].plot(df["phi_mid"], df["f1_cc"], "-s", color="#B2182B", ms=4, label="connected comp.")
    ax[1].set_xlabel("confluence  φ"); ax[1].set_ylabel("matched F1 @ IoU 0.5")
    ax[1].set_ylim(0, 1); ax[1].set_title("detection quality vs density", fontsize=9)
    ax[1].legend(frameon=False, fontsize=8); ax[1].grid(alpha=0.15)
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(a.out, f"density_resolved_instances.{ext}"),
                    dpi=200, bbox_inches="tight")
    plt.close(fig)

    print("=" * 78)
    print(" PER-CONFLUENCE-BIN RESULT  (best watershed params)")
    print(df.to_string(index=False))
    print("-" * 78)
    print(f" BEST PARAMS:  --seed-thr {bst}  --min-distance {bmd}  --min-size {bms}")
    print(" regenerate the full test set with these settings:")
    print(f"   python phase13_watershed_infer.py --model {a.model} \\")
    print(f"       --images {a.images} --coco {a.coco} \\")
    print(f"       --out predictions/instance_final \\")
    print(f"       --seed-thr {bst} --min-distance {bmd} --min-size {bms} --overlays 12")
    print(f" figure + csv written to {a.out}/")
    print("=" * 78 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
