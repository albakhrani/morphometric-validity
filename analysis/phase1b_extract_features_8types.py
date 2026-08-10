#!/usr/bin/env python3
"""
Phase 1b - Extended shape-feature extraction across 8 lineages
==============================================================
Superset of phase1_extract_8types.py. Same masks, same geometry method, but
pulls a fuller regionprops panel so we can test MULTI-FEATURE convergence of
the jammer/non-jammer dichotomy. Features are mask-only (no images needed).

Panel (per cell):
    q            = P/sqrt(A)                 [q-family; defines the classes]
    circularity  = 4*pi*A/P^2                [q-family; redundant, for context]
    eccentricity                              [INDEPENDENT: ellipse elongation]
    solidity     = area / convex_area         [INDEPENDENT: concavity]
    extent       = area / bbox_area           [INDEPENDENT: bbox filling]
    aspect_ratio = major / minor axis         [elongation, partly q-correlated]
    cell_area, cell_perimeter, centroid_x/y, density

Density = ALL annotations per image (unbiased). exclude_border for clean shapes.

Usage
    python phase1b_extract_features_8types.py \
        --coco "D:/paper1_mechanobiology - Copy (2)/data/raw/livecell/livecell_coco_test.json" \
        --out  phase1_out
"""
from __future__ import annotations
import argparse, logging, math, os, sys
import numpy as np
import pandas as pd

try:
    from pycocotools.coco import COCO
except Exception:
    print("ERROR: pycocotools required (Paper 1 dependency)."); sys.exit(1)
from skimage import measure

MIN_CELL_SIZE = 50
EXCLUDE_BORDER = True
CANON = {"A172": "A172", "BT474": "BT474", "BV2": "BV2", "HUH7": "Huh7",
         "MCF7": "MCF7", "SHSY5Y": "SH-SY5Y", "SKBR3": "SkBr3", "SKOV3": "SK-OV-3"}
FOUR_PI = 4.0 * math.pi

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("phase1b")


def _get(r, *names):
    for n in names:
        if hasattr(r, n):
            return getattr(r, n)
    return math.nan


def celltype_from_name(fn):
    return CANON.get(os.path.basename(fn).split("_")[0].upper())


def geom(mask):
    lab = measure.label(mask, connectivity=2)
    props = measure.regionprops(lab)
    if not props:
        return None
    r = max(props, key=lambda p: p.area)
    if r.area < MIN_CELL_SIZE:
        return None
    major = _get(r, "axis_major_length", "major_axis_length")
    minor = _get(r, "axis_minor_length", "minor_axis_length")
    return dict(area=float(r.area), perim=float(r.perimeter),
                ecc=float(r.eccentricity), sol=float(r.solidity),
                ext=float(r.extent), major=float(major), minor=float(minor),
                cy=float(r.centroid[0]), cx=float(r.centroid[1]), bbox=r.bbox)


def extract(coco_paths, max_images=None):
    rows = []
    for cp in coco_paths:
        log.info("Loading %s", cp)
        coco = COCO(cp)
        ids = coco.getImgIds()
        if max_images:
            ids = ids[:max_images]
        dens = {i: len(coco.getAnnIds(imgIds=i)) for i in ids}
        done = 0
        for iid in ids:
            info = coco.loadImgs(iid)[0]
            ct = celltype_from_name(info["file_name"])
            if ct is None:
                continue
            H, W = info["height"], info["width"]
            for ann in coco.loadAnns(coco.getAnnIds(imgIds=iid)):
                g = geom(coco.annToMask(ann))
                if g is None:
                    continue
                minr, minc, maxr, maxc = g["bbox"]
                if EXCLUDE_BORDER and (minr <= 0 or minc <= 0 or maxr >= H or maxc >= W):
                    continue
                A_, P_ = g["area"], g["perim"]
                if A_ <= 0 or P_ <= 0:
                    continue
                q = P_ / math.sqrt(A_)
                circ = FOUR_PI * A_ / (P_ * P_)
                ar = (g["major"] / g["minor"]) if g["minor"] and g["minor"] > 0 else math.nan
                rows.append(dict(cell_type=ct, image_id=iid, annotation_id=ann["id"],
                                 cell_area=A_, cell_perimeter=P_,
                                 q=q, circularity=circ, eccentricity=g["ecc"],
                                 solidity=g["sol"], extent=g["ext"], aspect_ratio=ar,
                                 centroid_x=g["cx"], centroid_y=g["cy"],
                                 density=float(dens[iid])))
            done += 1
            if done % 200 == 0:
                log.info("  %d/%d images | %d cells", done, len(ids), len(rows))
        log.info("  finished %s: %d images", cp, done)
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coco", nargs="+", required=True)
    ap.add_argument("--out", default="phase1_out")
    ap.add_argument("--max-images", type=int, default=None)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    df = extract(a.coco, a.max_images)
    if df.empty:
        log.error("No cells extracted."); return 3
    out = os.path.join(a.out, "atlas_features_percell.csv")
    df.to_csv(out, index=False)
    log.info("Extracted %d cells x %d types -> %s", len(df), df["cell_type"].nunique(), out)
    print("\nPer-type cell counts:")
    print(df.groupby("cell_type").size().to_string())
    print("\nFeature means by cell type:")
    print(df.groupby("cell_type")[["q", "eccentricity", "solidity", "extent", "aspect_ratio"]]
            .mean().round(3).to_string())
    print("\nNext: python phase2b_multifeature_convergence.py "
          f"--csv {out} --pertype phase2_out/p2_per_type.csv --out final_out\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
