#!/usr/bin/env python3
"""
Build the per-image table for the EXPANDED expert-only atlas.

phase7_figures.py draws its trajectory panel from time_out/time_per_image.csv,
which was produced for the test split alone. Figure 7 must now show the same
atlas as Table 4, which spans all three LIVECell splits, so the same
aggregation is redone over the expanded per-cell file.

Filters match phase4_final_table.py exactly: minimum cell area 150 px,
post-attachment (>= 8 h), confluence and elapsed time taken from the COCO
files. No model prediction is involved anywhere here.

    python phase32_expanded_perimage.py
"""
from __future__ import annotations

import argparse
import os

import pandas as pd

from phase4_final_table import phi_from_coco_multi, DEFAULT_MIN_AREA, DEFAULT_MIN_HOURS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="phase1_out_all/atlas_features_percell.csv")
    ap.add_argument("--coco", nargs="+", default=[
        "data/raw/livecell/livecell_coco_train.json",
        "data/raw/livecell/livecell_coco_val.json",
        "data/raw/livecell/livecell_coco_test.json"])
    ap.add_argument("--min-area", type=int, default=DEFAULT_MIN_AREA)
    ap.add_argument("--min-hours", type=float, default=DEFAULT_MIN_HOURS)
    ap.add_argument("--out", default="fig7_expanded/time_out")
    a = ap.parse_args()

    phi_map, hours_map = phi_from_coco_multi(a.coco)
    df = pd.read_csv(a.csv, low_memory=False)
    n0 = len(df)
    df = df[df.cell_area >= a.min_area]
    df["phi"] = df.image_id.map(phi_map)
    df["hours"] = df.image_id.map(hours_map)
    df = df.dropna(subset=["phi", "q", "cell_area"])
    known = df.hours.notna()
    df = df[(~known) | (df.hours >= a.min_hours)]
    print(f"cells {n0:,} -> {len(df):,} after >= {a.min_area} px and >= {a.min_hours} h")

    img = (df.groupby("image_id")
             .agg(cell_type=("cell_type", "first"), mean_q=("q", "mean"),
                  mean_area=("cell_area", "mean"), n=("q", "size"),
                  phi=("phi", "first"), hours=("hours", "first"))
             .reset_index())
    img["file_name"] = ""
    img = img[["image_id", "cell_type", "mean_q", "mean_area", "n",
               "file_name", "phi", "hours"]]

    os.makedirs(a.out, exist_ok=True)
    p = os.path.join(a.out, "time_per_image.csv")
    img.to_csv(p, index=False)
    print(f"wrote {p}: {len(img):,} images, {int(img['n'].sum()):,} cells")
    print(img.groupby("cell_type").agg(images=("n", "size"), cells=("n", "sum")).to_string())


if __name__ == "__main__":
    main()
