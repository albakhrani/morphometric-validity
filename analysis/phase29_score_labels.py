#!/usr/bin/env python3
"""
Score a directory of precomputed label images through the SAME matched-F1 path
every other method uses, and append the per-image rows to stats/per_image_f1.csv.

This exists so a method that must run in a different Python environment
(StarDist needs TensorFlow, which has no wheel for this project's Python 3.14)
is still scored by the identical metric, from the identical sample, rather than
by a second implementation that can quietly disagree.

Sampling is copied from phase15_baselines.py / phase23_perimage_f1.py verbatim.

    python phase29_score_labels.py --name StarDist \
        --labels predictions/stardist_180 \
        --images data/raw/livecell_test_images \
        --coco data/raw/livecell/livecell_coco_test.json
"""
from __future__ import annotations

import argparse
import logging
import os

import numpy as np
import pandas as pd

from phase14_evaluate import match_f1, f1, gt_label_image
from phase15_baselines import load_ours

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("score")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, help="method name for the CSV")
    ap.add_argument("--labels", required=True)
    ap.add_argument("--images", required=True)
    ap.add_argument("--coco", required=True)
    ap.add_argument("--subsample", type=int, default=180)
    ap.add_argument("--per-image", default="stats/per_image_f1.csv")
    a = ap.parse_args()

    from pycocotools.coco import COCO
    coco = COCO(a.coco)
    on_disk = set(os.listdir(a.images))

    recs = []
    for iid in coco.getImgIds():
        info = coco.loadImgs(iid)[0]
        fn = info["file_name"]
        if fn not in on_disk or not coco.getAnnIds(imgIds=iid):
            continue
        anns = coco.loadAnns(coco.getAnnIds(imgIds=iid))
        phi = sum(float(x.get("area", 0.0)) for x in anns) / float(info["height"] * info["width"])
        recs.append((iid, fn, phi, info["height"], info["width"]))
    recs.sort(key=lambda r: r[2])
    step = max(1, len(recs) // a.subsample)
    sub = recs[::step][:a.subsample]
    log.info("sample: %d images, phi %.3f-%.3f", len(sub), sub[0][2], sub[-1][2])

    rows, missing = [], 0
    for iid, fn, phi, H, W in sub:
        lab = load_ours(a.labels, fn)
        if lab is None:
            missing += 1
            continue
        gt = gt_label_image(coco, iid, H, W)
        tp, fp, fn_, miou = match_f1(lab, gt)
        rows.append(dict(method=a.name, file=fn, phi=phi, tp=tp, fp=fp, fn=fn_,
                         f1=f1(tp, fp, fn_), matched_iou=miou,
                         n_pred=int(lab.max()), n_gt=int(gt.max())))
    if missing:
        log.warning("%d/%d label images missing from %s", missing, len(sub), a.labels)
    if not rows:
        raise SystemExit("no label images found - nothing scored")

    df = pd.DataFrame(rows)
    pooled = f1(df.tp.sum(), df.fp.sum(), df.fn.sum())
    log.info("%s: pooled F1 = %.4f over %d images", a.name, pooled, len(df))
    log.info("  mean matched IoU = %.4f", float(np.nanmean(df.matched_iou)))
    log.info("  images where nothing matched: %d", int((df.tp == 0).sum()))

    if os.path.exists(a.per_image):
        old = pd.read_csv(a.per_image)
        old = old[old.method != a.name]           # replace, do not duplicate
        df = pd.concat([old, df], ignore_index=True)
    os.makedirs(os.path.dirname(a.per_image) or ".", exist_ok=True)
    df.to_csv(a.per_image, index=False)
    log.info("wrote %s (%d rows, %d methods)", a.per_image, len(df), df.method.nunique())


if __name__ == "__main__":
    main()
