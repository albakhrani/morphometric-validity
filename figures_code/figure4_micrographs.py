#!/usr/bin/env python3
"""
Figure 4 -- the instance-recovery failure in one crowded field.

Runs only the micrograph panel of phase20_key_figures.py, with the centre
crop disabled, so every count printed in the figure describes the whole
704 x 520 field the reader is looking at. The earlier 420 x 420 crop is why
the published watershed count (351) was not commensurable with the expert
count (315): the crop was taken first and the label maximum read afterwards.

    python figure4_micrographs.py --model ../runs/instance/best.pt \
        --images ../data/raw/livecell_test_images \
        --coco ../data/raw/livecell/livecell_coco_test.json --out .
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pycocotools.coco import COCO                       # noqa: E402
from phase20_key_figures import fig_micrographs, load_model   # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--images", required=True)
    ap.add_argument("--coco", required=True)
    ap.add_argument("--out", default=".")
    ap.add_argument("--base-channels", type=int, default=32)
    ap.add_argument("--depth", type=int, default=4)
    ap.add_argument("--seed-thr", type=float, default=0.45)
    ap.add_argument("--min-distance", type=int, default=6)
    ap.add_argument("--min-size", type=int, default=50)
    ap.add_argument("--lineage", default="A172")
    ap.add_argument("--phi", type=float, default=0.85)
    a = ap.parse_args()

    print("operating point: seed_thr=%.2f min_distance=%d min_size=%d "
          "(detection-optimal, Section 3.3)"
          % (a.seed_thr, a.min_distance, a.min_size))

    model, device, amp = load_model(a.model, a.base_channels, a.depth)
    coco = COCO(a.coco)
    os.makedirs(a.out, exist_ok=True)

    info = fig_micrographs(
        model, device, amp, coco, a.images, a.out,
        seed_thr=a.seed_thr, min_distance=a.min_distance,
        min_size=a.min_size, preferred_lineage=a.lineage,
        target_phi=a.phi, crop=0)

    if info is None:
        raise SystemExit("no suitable field found")

    over = (info["n_ws"] - info["n_gt"]) / max(info["n_gt"], 1) * 100.0
    rec = info["n_cc"] / max(info["n_gt"], 1) * 100.0
    print("\n---- counts over the FULL field (these belong in the caption) ----")
    print("  file            %s" % info["file"])
    print("  phi             %.2f" % info["phi"])
    print("  expert          %d" % info["n_gt"])
    print("  conn. comp.     %d   (recovers %.1f%%)" % (info["n_cc"], rec))
    print("  watershed       %d   (over-count %+.1f%%)" % (info["n_ws"], over))


if __name__ == "__main__":
    main()
