#!/usr/bin/env python3
"""
Quantify the morphometric bias introduced by rasterizing overlapping COCO
annotations into a single integer label image.

phase17_atlas_from_instances.py builds expert masks with

    for i, ann in enumerate(anns, start=1):
        lab[coco.annToMask(ann) > 0] = i

so where two annotations overlap, the later one wins and the earlier one is
silently truncated. Truncation changes both area and perimeter, and therefore
the shape index q = perimeter / sqrt(area) that the whole paper measures.

This script measures, over exactly the images the atlas uses:
  - how many measured cells lose any pixels
  - how much area they lose
  - how q shifts as a result
  - how the per-image MEAN q shifts, which is the quantity actually correlated
    against confluence in Table 4 and Section 3.6

Writes overlap_bias/overlap_bias_percell.csv and _perimage.csv, and prints a
summary block.

CPU only. No model needed.
"""
from __future__ import annotations

import argparse
import math
import os

import numpy as np
import pandas as pd
from skimage.measure import regionprops

MIN_AREA = 150       # Section 2.5
EXCLUDE_BORDER = True


def q_of(area, perim):
    if area <= 0 or perim <= 0:
        return float("nan")
    return perim / math.sqrt(area)


def props_of_binary(m):
    """area and perimeter of a single binary mask, cropped for speed."""
    ys, xs = np.nonzero(m)
    if ys.size == 0:
        return None
    y0, y1 = ys.min(), ys.max() + 1
    x0, x1 = xs.min(), xs.max() + 1
    sub = np.zeros((y1 - y0 + 2, x1 - x0 + 2), np.uint8)
    sub[1:-1, 1:-1] = m[y0:y1, x0:x1]
    r = regionprops(sub.astype(np.int32))
    if not r:
        return None
    return float(r[0].area), float(r[0].perimeter), (y0, x0, y1, x1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coco", default="data/raw/livecell/livecell_coco_test.json")
    ap.add_argument("--images", default="data/raw/livecell_test_images")
    ap.add_argument("--out", default="overlap_bias")
    ap.add_argument("--min-hours", type=float, default=8.0)
    ap.add_argument("--limit", type=int, default=0, help="debug: cap images")
    a = ap.parse_args()

    from pycocotools.coco import COCO
    from phase17_atlas_from_instances import parse_hours

    os.makedirs(a.out, exist_ok=True)
    coco = COCO(a.coco)
    on_disk = set(os.listdir(a.images))

    iids = []
    for iid in coco.getImgIds():
        info = coco.loadImgs(iid)[0]
        fn = info["file_name"]
        if fn not in on_disk:
            continue
        if not coco.getAnnIds(imgIds=iid):
            continue
        h = parse_hours(fn)
        if a.min_hours and np.isfinite(h) and h < a.min_hours:
            continue
        iids.append((iid, fn, info["height"], info["width"]))
    if a.limit:
        iids = iids[:a.limit]
    print(f"images in the atlas sample: {len(iids)}")

    cells, per_img = [], []
    for k, (iid, fn, H, W) in enumerate(iids, 1):
        anns = coco.loadAnns(coco.getAnnIds(imgIds=iid))
        phi = sum(float(x.get("area", 0.0)) for x in anns) / float(H * W)
        lab = np.zeros((H, W), np.int32)
        before = {}
        for i, ann in enumerate(anns, start=1):
            m = coco.annToMask(ann)
            p = props_of_binary(m)
            if p is not None:
                area_b, per_b, bbox = p
                before[i] = (area_b, per_b, bbox)
            lab[m > 0] = i

        after = {int(r.label): (float(r.area), float(r.perimeter), r.bbox)
                 for r in regionprops(lab)}

        qs_b, qs_a = [], []
        for i, (area_b, per_b, bb) in before.items():
            # Section 2.5 filters, applied on the ORIGINAL geometry so that we
            # ask "of the cells the paper intends to measure, how many are
            # damaged", not the other way round.
            y0, x0, y1, x1 = bb
            on_border = (y0 <= 0 or x0 <= 0 or y1 >= H or x1 >= W)
            if area_b < MIN_AREA or (EXCLUDE_BORDER and on_border):
                continue
            aft = after.get(i)
            area_a = aft[0] if aft else 0.0
            per_a = aft[1] if aft else 0.0
            lost = area_b - area_a
            qb, qa = q_of(area_b, per_b), q_of(area_a, per_a)
            cells.append(dict(file=fn, label=i, area_before=area_b,
                              area_after=area_a, frac_lost=lost / area_b,
                              q_before=qb, q_after=qa,
                              survives_filter=bool(aft and area_a >= MIN_AREA)))
            qs_b.append(qb)
            if aft and area_a >= MIN_AREA and np.isfinite(qa):
                qs_a.append(qa)

        if qs_b:
            per_img.append(dict(file=fn, phi=phi, n_before=len(qs_b), n_after=len(qs_a),
                                meanq_before=float(np.nanmean(qs_b)),
                                meanq_after=float(np.nanmean(qs_a)) if qs_a else np.nan))
        if k % 100 == 0:
            print(f"  {k}/{len(iids)}")

    dc = pd.DataFrame(cells)
    di = pd.DataFrame(per_img)
    dc.to_csv(os.path.join(a.out, "overlap_bias_percell.csv"), index=False)
    di.to_csv(os.path.join(a.out, "overlap_bias_perimage.csv"), index=False)

    dmg = dc[dc.frac_lost > 0]
    gone = dc[~dc.survives_filter]
    print("\n" + "=" * 68)
    print("OVERLAP / RASTERIZATION BIAS  (expert annotations, atlas sample)")
    print("=" * 68)
    print(f"  measured cells (pass 150 px + non-border, pre-raster) : {len(dc):,}")
    print(f"  cells losing >=1 px to a later annotation             : {len(dmg):,} "
          f"({100*len(dmg)/max(len(dc),1):.2f}%)")
    print(f"  cells dropped from measurement entirely               : {len(gone):,} "
          f"({100*len(gone)/max(len(dc),1):.2f}%)")
    if len(dmg):
        print(f"  area lost, among damaged cells: median {100*dmg.frac_lost.median():.2f}%"
              f"  mean {100*dmg.frac_lost.mean():.2f}%  max {100*dmg.frac_lost.max():.2f}%")
        print(f"  total area lost / total area  : "
              f"{100*(dc.area_before-dc.area_after).sum()/dc.area_before.sum():.3f}%")
        dq = (dmg.q_after - dmg.q_before).dropna()
        if len(dq):
            print(f"  delta q among damaged cells   : median {dq.median():+.4f}"
                  f"  mean {dq.mean():+.4f}")
    d = (di.meanq_after - di.meanq_before).dropna()
    print(f"  per-image MEAN q shift        : median {d.median():+.4f}"
          f"  mean {d.mean():+.4f}  (n = {len(d)} images)")
    print(f"  per-image mean q  before {di.meanq_before.mean():.4f} "
          f"-> after {di.meanq_after.mean():.4f}")

    # The decisive question for Section 3.6: a uniform shift in mean q cannot
    # change a rank correlation against confluence. Only a CONFLUENCE-DEPENDENT
    # shift can. Test that directly.
    from scipy.stats import spearmanr
    dd = di.dropna(subset=["meanq_before", "meanq_after", "phi"]).copy()
    # NOT dd.shift -- that is DataFrame.shift, the method, and column access by
    # attribute silently returns it instead of this column.
    dd["dq"] = dd.meanq_after - dd.meanq_before
    print("-" * 68)
    print("  is the damage confluence-dependent?")
    print(f"    rho(phi, shift in mean q) = {spearmanr(dd.phi, dd['dq']).statistic:+.4f}"
          f"   p = {spearmanr(dd.phi, dd['dq']).pvalue:.3g}")
    print(f"    rho(phi, mean q)  BEFORE raster = "
          f"{spearmanr(dd.phi, dd.meanq_before).statistic:+.4f}")
    print(f"    rho(phi, mean q)  AFTER  raster = "
          f"{spearmanr(dd.phi, dd.meanq_after).statistic:+.4f}")
    print("=" * 68)


if __name__ == "__main__":
    main()
