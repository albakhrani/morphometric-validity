#!/usr/bin/env python3
"""
Per-image matched-instance counts for every method in Table 1.

phase15_baselines.py reports only pooled totals and per-bin F1, so the
manuscript has no basis for a confidence interval or a paired test. This
script re-runs the IDENTICAL protocol -- same sample, same stored
predictions, same match_f1 -- and saves tp/fp/fn PER IMAGE, which is what
bootstrap resampling and a signed-rank test need.

Sampling is copied from phase15_baselines.py exactly (sort every annotated
test image by confluence, take every k-th, cap at --subsample), so the
images here are the images behind Table 1.

    python phase23_perimage_f1.py --images data/raw/livecell_test_images \
      --coco data/raw/livecell/livecell_coco_test.json \
      --ours predictions/instance_final/labels \
      --model runs/instance/best.pt --out stats
"""
from __future__ import annotations

import argparse
import logging
import os

import numpy as np
import pandas as pd

from phase13_watershed_infer import (
    read_image, percentile_norm, predict_maps, connected_components)
from phase14_evaluate import match_f1, f1, gt_label_image
from phase15_baselines import load_ours, run_cellpose

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("perimage")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", required=True)
    ap.add_argument("--coco", required=True)
    ap.add_argument("--ours", required=True)
    ap.add_argument("--model", default=None)
    ap.add_argument("--base-channels", type=int, default=32)
    ap.add_argument("--depth", type=int, default=4)
    ap.add_argument("--out", default="stats")
    ap.add_argument("--subsample", type=int, default=180)
    ap.add_argument("--cellpose-model", default="cyto3")
    ap.add_argument("--skip-cellpose", action="store_true")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    from pycocotools.coco import COCO
    coco = COCO(a.coco)
    on_disk = set(os.listdir(a.images))

    recs = []
    for iid in coco.getImgIds():
        info = coco.loadImgs(iid)[0]
        fn = info["file_name"]
        if fn not in on_disk:
            continue
        if not coco.getAnnIds(imgIds=iid):
            continue
        anns = coco.loadAnns(coco.getAnnIds(imgIds=iid))
        phi = sum(float(x.get("area", 0.0)) for x in anns) / float(info["height"] * info["width"])
        recs.append((iid, fn, phi, info["height"], info["width"]))
    recs.sort(key=lambda r: r[2])
    step = max(1, len(recs) // a.subsample)
    sub = recs[::step][:a.subsample]
    log.info("sample: %d images, phi %.3f-%.3f", len(sub), sub[0][2], sub[-1][2])

    images, gts, phis, ours = {}, {}, {}, {}
    for iid, fn, phi, H, W in sub:
        images[fn] = percentile_norm(read_image(os.path.join(a.images, fn)))
        gts[fn] = gt_label_image(coco, iid, H, W)
        phis[fn] = phi
        lab = load_ours(a.ours, fn)
        if lab is not None:
            ours[fn] = lab
    log.info("loaded %d/%d stored prediction maps", len(ours), len(sub))

    methods = {}
    if ours:
        methods["ours (watershed)"] = ours

    if a.model:
        import torch
        from phase11_instance_model import build_instance_model
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        amp = torch.bfloat16 if device.type == "cuda" else torch.float32
        m = build_instance_model(base_channels=a.base_channels, depth=a.depth)
        ck = torch.load(a.model, map_location="cpu", weights_only=False)
        m.load_state_dict(ck.get("model_state_dict", ck))
        m.to(device).eval()
        cc = {}
        for k, (fn, img) in enumerate(images.items(), 1):
            fg, _, _ = predict_maps(m, img, device, amp)
            cc[fn] = connected_components(fg, min_size=50)
            if k % 60 == 0:
                log.info("  conncomp %d/%d", k, len(images))
        methods["connected comp."] = cc

    if not a.skip_cellpose:
        cp = run_cellpose(images, model_name=a.cellpose_model)
        if cp:
            methods["Cellpose"] = cp
        else:
            log.warning("Cellpose unavailable -- no Cellpose rows will be written")

    rows = []
    for name, labs in methods.items():
        for fn, lab in labs.items():
            tp, fp, fn_, miou = match_f1(lab, gts[fn])
            rows.append(dict(method=name, file=fn, phi=phis[fn],
                             tp=tp, fp=fp, fn=fn_,
                             f1=f1(tp, fp, fn_), matched_iou=miou,
                             n_pred=int(lab.max()), n_gt=int(gts[fn].max())))
    df = pd.DataFrame(rows)
    p = os.path.join(a.out, "per_image_f1.csv")
    df.to_csv(p, index=False)
    log.info("wrote %s (%d rows)", p, len(df))

    print("\npooled F1 (must match baseline_summary.csv):")
    for name, g in df.groupby("method"):
        print(f"  {name:20s} F1 = {f1(g.tp.sum(), g.fp.sum(), g.fn.sum()):.3f}"
              f"   n = {len(g)} images")


if __name__ == "__main__":
    main()
