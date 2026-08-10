#!/usr/bin/env python3
"""
Per-image detection counts for the three operating points of Table 2.

phase18_optimize.py reports only pooled F1 for each frozen operating point,
so Table 2 has no basis for a confidence interval. This reproduces its frozen
test evaluation -- same collect_items sampling, same min_hours, same
subsample, same watershed parameters -- and saves tp/fp/fn per image.

    python phase25_tradeoff_ci.py --images data/raw/livecell_test_images \
      --coco data/raw/livecell/livecell_coco_test.json \
      --model runs/instance/best.pt --out stats
"""
from __future__ import annotations

import argparse
import logging
import os

import numpy as np
import pandas as pd

from phase13_watershed_infer import (
    read_image, percentile_norm, predict_maps, connected_components,
    watershed_instances)
from phase14_evaluate import match_f1, f1, gt_label_image
from phase18_optimize import collect_items

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("tradeoff-ci")

# The three points named in Section 3.3, read from optimize/test_frozen.csv.
POINTS = [("detection-optimal", 0.45, 6, 50),
          ("balanced", 0.65, 6, 50),
          ("measurement-optimal", 0.75, 8, 50)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", required=True)
    ap.add_argument("--coco", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--base-channels", type=int, default=32)
    ap.add_argument("--depth", type=int, default=4)
    ap.add_argument("--subsample", type=int, default=150)
    ap.add_argument("--min-hours", type=float, default=8.0)
    ap.add_argument("--out", default="stats")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    import torch
    from pycocotools.coco import COCO
    from phase11_instance_model import build_instance_model

    coco = COCO(a.coco)
    items = collect_items(coco, a.images, a.subsample, a.min_hours)
    log.info("frozen test sample: %d images, phi %.3f-%.3f",
             len(items), items[0][2], items[-1][2])

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    amp = torch.bfloat16 if device.type == "cuda" else torch.float32
    m = build_instance_model(base_channels=a.base_channels, depth=a.depth)
    ck = torch.load(a.model, map_location="cpu", weights_only=False)
    m.load_state_dict(ck.get("model_state_dict", ck))
    m.to(device).eval()

    rows = []
    for k, (iid, fn, phi, H, W) in enumerate(items, 1):
        img = percentile_norm(read_image(os.path.join(a.images, fn)))
        gt = gt_label_image(coco, iid, H, W)
        fg, dist, bnd = predict_maps(m, img, device, amp)
        for name, st, md, ms in POINTS:
            ws = watershed_instances(fg, dist, bnd, seed_thr=st,
                                     min_distance=md, min_size=ms)
            tp, fp, fn_, miou = match_f1(ws, gt)
            rows.append(dict(setting=name, file=fn, phi=phi, tp=tp, fp=fp,
                             fn=fn_, f1=f1(tp, fp, fn_), matched_iou=miou))
        cc = connected_components(fg, min_size=50)
        tp, fp, fn_, miou = match_f1(cc, gt)
        rows.append(dict(setting="connected components", file=fn, phi=phi,
                         tp=tp, fp=fp, fn=fn_, f1=f1(tp, fp, fn_),
                         matched_iou=miou))
        if k % 40 == 0:
            log.info("  %d/%d", k, len(items))

    df = pd.DataFrame(rows)
    p = os.path.join(a.out, "per_image_tradeoff.csv")
    df.to_csv(p, index=False)
    log.info("wrote %s (%d rows)", p, len(df))

    rng = np.random.default_rng(0)
    files = sorted(df.file.unique())
    draws = rng.integers(0, len(files), size=(1000, len(files)))
    print("\npooled F1 with bootstrap 95% CI (must match test_frozen.csv):")
    out = []
    for name, g in df.groupby("setting", sort=False):
        g = g.set_index("file").reindex(files)
        tp, fp, fn_ = g.tp.to_numpy(), g.fp.to_numpy(), g.fn.to_numpy()
        point = f1(tp.sum(), fp.sum(), fn_.sum())
        bs = np.array([f1(tp[d].sum(), fp[d].sum(), fn_[d].sum()) for d in draws])
        lo, hi = np.percentile(bs, [2.5, 97.5])
        print(f"  {name:24s} F1 = {point:.4f}   [{lo:.3f}, {hi:.3f}]")
        out.append(dict(setting=name, f1=round(point, 4), ci_lo=round(lo, 4),
                        ci_hi=round(hi, 4), n_images=len(files), reps=1000))
    pd.DataFrame(out).to_csv(os.path.join(a.out, "tradeoff_ci.csv"), index=False)


if __name__ == "__main__":
    main()
