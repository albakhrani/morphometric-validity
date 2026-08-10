#!/usr/bin/env python3
"""
Run StarDist over a fixed image list and save 16-bit label PNGs.

StarDist needs TensorFlow, which has no wheel for the Python 3.14 interpreter
the rest of this project runs on, so it lives in a separate Python 3.12
environment (.venv_stardist). This script therefore does ONE thing -- produce
label images -- and deliberately does no scoring. Scoring happens back in the
main environment with the same match_f1 every other method is scored by, so
the comparison protocol is identical and there is no second implementation of
the metric to drift.

    .venv_stardist/Scripts/python.exe phase27_stardist_masks.py \
        --images data/raw/livecell_test_images \
        --list stats/sample_180.txt \
        --out predictions/stardist_180
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np


def read_image(path: str) -> np.ndarray:
    from PIL import Image
    return np.asarray(Image.open(path)).astype(np.float32)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", required=True)
    ap.add_argument("--list", required=True, help="one file name per line")
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="2D_versatile_fluo")
    a = ap.parse_args()

    from stardist.models import StarDist2D
    from csbdeep.utils import normalize
    from PIL import Image

    names = [ln.strip() for ln in open(a.list, encoding="utf8") if ln.strip()]
    os.makedirs(a.out, exist_ok=True)
    print(f"{len(names)} images; loading StarDist '{a.model}'", flush=True)

    try:
        model = StarDist2D.from_pretrained(a.model)
    except OSError as exc:
        # csbdeep's downloader finishes by symlinking the extracted folder,
        # which needs a privilege Windows withholds unless Developer Mode is
        # on. The download and extraction themselves succeed, so load the
        # extracted folder directly rather than requiring elevation.
        base = os.path.join(os.path.expanduser("~"), ".keras", "models",
                            "StarDist2D", a.model)
        extracted = os.path.join(base, a.model + "_extracted")
        if not os.path.isdir(extracted):
            raise
        print(f"  from_pretrained failed ({exc.__class__.__name__}); "
              f"loading extracted weights from {extracted}", flush=True)
        model = StarDist2D(None, name=a.model + "_extracted", basedir=base)

    failures = 0
    for k, n in enumerate(names, 1):
        p = os.path.join(a.images, n)
        if not os.path.exists(p):
            print(f"MISSING {n}", flush=True)
            failures += 1
            continue
        try:
            img = read_image(p)
            lab, _ = model.predict_instances(normalize(img, 1, 99.8))
            lab = np.asarray(lab).astype(np.uint16)
        except Exception as exc:                       # noqa: BLE001
            failures += 1
            print(f"FAILED {n}: {exc}", flush=True)
            continue
        Image.fromarray(lab).save(
            os.path.join(a.out, os.path.splitext(n)[0] + ".png"))
        if k % 20 == 0:
            print(f"  {k}/{len(names)}", flush=True)

    print(f"done: {len(names) - failures} written, {failures} failed", flush=True)
    if failures > 0.1 * len(names):
        print("ABORT: too many failures to report a score", flush=True)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
