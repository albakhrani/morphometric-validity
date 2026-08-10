#!/usr/bin/env python3
"""
Evaluate each ablation checkpoint on the metrics the paper actually claims.

Validation IoU and distance MAE come free from training, but the paper's claim
is about instance detection and the morphometry derived from it, so each
configuration is decoded and scored on the frozen test sample at the
detection-optimal operating point, exactly as Table 2 is.

Run B has no distance head, so marker-controlled watershed cannot seed. It is
decoded instead by removing the predicted boundary from the foreground and
labelling what remains -- the natural decoder for a boundary-only model, and
the fair way to ask whether the boundary map alone can separate touching cells.

    python phase30_ablation_eval.py --images data/raw/livecell_test_images \
        --coco data/raw/livecell/livecell_coco_test.json
"""
from __future__ import annotations

import argparse
import logging
import os

import numpy as np
import pandas as pd

from phase13_watershed_infer import (
    read_image, percentile_norm, predict_maps, connected_components,
    watershed_instances, celltype_of)
from phase14_evaluate import match_f1, f1, gt_label_image
from phase17_atlas_from_instances import geometry_from_labels
from phase18_optimize import collect_items

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("abl")

RUNS = [("C  both heads (reference)", "runs/abl_C_both/best.pt", True, True, True),
        ("A  distance head only", "runs/abl_A_dist/best.pt", True, False, True),
        ("B  boundary head only", "runs/abl_B_bnd/best.pt", False, True, True),
        ("D  both heads, from scratch", "runs/abl_D_scratch/best.pt", True, True, False)]


def boundary_decode(fg, bnd, fg_thr=0.5, bnd_thr=0.5, min_size=50):
    """Instances = confident foreground with the predicted boundary removed."""
    core = (fg > fg_thr) & (bnd < bnd_thr)
    return connected_components(core.astype(np.float32), min_size=min_size)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", required=True)
    ap.add_argument("--coco", required=True)
    ap.add_argument("--subsample", type=int, default=150)
    ap.add_argument("--min-hours", type=float, default=8.0)
    ap.add_argument("--seed-thr", type=float, default=0.45)
    ap.add_argument("--min-distance", type=int, default=6)
    ap.add_argument("--min-size", type=int, default=50)
    ap.add_argument("--out", default="stats/ablation_eval.csv")
    a = ap.parse_args()

    import torch
    from pycocotools.coco import COCO
    from phase11_instance_model import build_instance_model

    coco = COCO(a.coco)
    items = collect_items(coco, a.images, a.subsample, a.min_hours)
    log.info("frozen test sample: %d images", len(items))

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    amp = torch.bfloat16 if device.type == "cuda" else torch.float32

    cache = {}
    for iid, fn, phi, H, W in items:
        cache[fn] = (iid, phi, H, W,
                     percentile_norm(read_image(os.path.join(a.images, fn))))

    rows = []
    for label, ckpt, use_d, use_b, transfer in RUNS:
        if not os.path.exists(ckpt):
            log.warning("%s: %s missing - skipped", label, ckpt)
            continue
        m = build_instance_model(base_channels=32, depth=4,
                                 use_distance_head=use_d, use_boundary_head=use_b)
        ck = torch.load(ckpt, map_location="cpu", weights_only=False)
        m.load_state_dict(ck["model_state_dict"])
        m.to(device).eval()
        added = sum(p.numel() for h in (m.dist_head, m.bnd_head)
                    if h is not None for p in h.parameters())

        tp = fp = fn_ = 0
        per_img = []
        for k, (fname, (iid, phi, H, W, img)) in enumerate(cache.items(), 1):
            out = predict_maps(m, img, device, amp)
            fg = out[0]
            dist = out[1] if use_d else None
            bnd = out[2] if use_b else None
            if use_d:
                lab = watershed_instances(fg, dist, bnd, seed_thr=a.seed_thr,
                                          min_distance=a.min_distance,
                                          min_size=a.min_size)
            else:
                lab = boundary_decode(fg, bnd, min_size=a.min_size)
            gt = gt_label_image(coco, iid, H, W)
            t, f_, n_, _ = match_f1(lab, gt)
            tp += t; fp += f_; fn_ += n_
            ge = geometry_from_labels(gt, min_area=150)
            gp = geometry_from_labels(lab, min_area=150)
            per_img.append(dict(file=fname, cell_type=celltype_of(fname), phi=phi,
                                q_gt=np.mean([x["q"] for x in ge]) if ge else np.nan,
                                q_pred=np.mean([x["q"] for x in gp]) if gp else np.nan))
            if k % 50 == 0:
                log.info("  %s %d/%d", label.split()[0], k, len(cache))

        d = pd.DataFrame(per_img).dropna(subset=["q_gt", "q_pred"])
        bias = float((d.q_pred - d.q_gt).abs().mean())
        amps = []
        for ct, g in d.groupby("cell_type"):
            if len(g) < 9:
                continue
            lo_t, hi_t = g.phi.quantile([1 / 3, 2 / 3])
            lo, hi = g[g.phi <= lo_t], g[g.phi >= hi_t]
            se = hi.q_gt.mean() - lo.q_gt.mean()
            if abs(se) >= 0.15:
                amps.append((hi.q_pred.mean() - lo.q_pred.mean()) / se)
        rows.append(dict(config=label, added_params=added,
                         transfer_init=transfer,
                         val_iou=None, val_mae=None,
                         test_f1=round(f1(tp, fp, fn_), 4),
                         abs_bias=round(bias, 4),
                         amp_ratio=round(float(np.median(amps)), 4) if amps else np.nan,
                         n_amp_lineages=len(amps), n_images=len(d)))
        log.info("%s -> F1 %.4f  |bias| %.4f  amp %s  (+%d params)",
                 label, rows[-1]["test_f1"], bias, rows[-1]["amp_ratio"], added)
        del m
        torch.cuda.empty_cache()

    df = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    df.to_csv(a.out, index=False)
    print("\n" + df.to_string(index=False))
    print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
