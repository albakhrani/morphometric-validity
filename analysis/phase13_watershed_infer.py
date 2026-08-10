#!/usr/bin/env python3
"""
Phase 13 - Watershed instance inference  (Paper 2, Option B)
============================================================
Loads the trained instance model (runs/instance/best.pt), predicts foreground +
per-cell distance + boundary for each test image, and recovers INSTANCES by
marker-controlled watershed:

    markers = local maxima of the predicted distance map  (one seed per cell)
    surface = -distance                                    (basins at cell centres)
    mask    = predicted foreground, minus predicted boundary                (region)
    labels  = watershed(surface, markers, mask)

This is the step that separates touching cells, which plain connected-components
on the foreground cannot do. Output is one label PNG per image (16-bit, one
integer id per cell) plus an optional colour overlay for eyeballing.

Compares, per image, the instance count from watershed against the naive
connected-components count on the same foreground, so the improvement is explicit.

Usage
    python phase13_watershed_infer.py \
        --model runs/instance/best.pt \
        --images data/raw/livecell_test_images \
        --coco   data/raw/livecell/livecell_coco_test.json \
        --out    predictions/instance_test \
        --overlays 8

The --coco is optional; if given, the printout also reports the expert instance
count per image so you can see recovery directly.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("watershed")


# --------------------------------------------------------------------------
def read_image(path):
    errs = []
    for loader in ("imageio", "PIL", "tifffile"):
        try:
            if loader == "imageio":
                import imageio.v2 as iio
                a = iio.imread(path)
            elif loader == "PIL":
                from PIL import Image
                a = np.array(Image.open(path))
            else:
                import tifffile
                a = tifffile.imread(path)
            return a[..., 0] if a.ndim == 3 else a
        except Exception as e:
            errs.append(f"{loader}: {e}")
    raise RuntimeError(f"cannot read {path} | " + "; ".join(errs))


def percentile_norm(img, lo=1.0, hi=99.0):
    a = img.astype(np.float32)
    p1, p99 = np.percentile(a, lo), np.percentile(a, hi)
    return np.clip((a - p1) / (p99 - p1 + 1e-6), 0, 1) if p99 > p1 else a * 0


def predict_maps(model, img, device, amp_dtype):
    """Return foreground prob, distance prob, boundary prob (all HxW float32)."""
    import torch
    import torch.nn.functional as F
    h, w = img.shape
    ph, pw = (32 - h % 32) % 32, (32 - w % 32) % 32
    arr = np.pad(img, ((0, ph), (0, pw)), mode="reflect")
    x = torch.from_numpy(arr)[None, None].float().to(device)
    with torch.no_grad():
        with torch.autocast(device_type=device.type, dtype=amp_dtype,
                            enabled=(device.type == "cuda")):
            out = model(x)
    fg = out["fg"][-1] if isinstance(out["fg"], (list, tuple)) else out["fg"]
    fg = torch.sigmoid(fg[0, 0]).float().cpu().numpy()[:h, :w]

    # An ablation model may be built with only one instance head, in which case
    # the other key is absent rather than zero. Return None for it instead of
    # raising, so a caller can decide what to do; the shipped model has both
    # heads and is unaffected.
    def head(name):
        if name not in out:
            return None
        return torch.sigmoid(out[name][0, 0]).float().cpu().numpy()[:h, :w]

    return fg, head("dist"), head("bnd")


def watershed_instances(fg, dist, bnd,
                        fg_thr=0.5, seed_thr=0.4, min_distance=4,
                        bnd_thr=0.5, min_size=20, min_mean_fg=0.5):
    """Marker-controlled watershed on confident foreground. Returns int32 labels.

    Two guards suppress background phantoms in near-empty fields:
      - seeds must sit on confident foreground (fg > fg_thr), so faint distance
        noise in the background cannot plant a marker;
      - each resulting instance is kept only if its mean predicted foreground
        probability exceeds min_mean_fg, dropping regions the model is not
        actually confident are cells.
    """
    from scipy import ndimage as ndi
    from skimage.feature import peak_local_max
    from skimage.segmentation import watershed
    from skimage.measure import label as sklabel

    mask = fg > fg_thr
    if not mask.any():
        return np.zeros(dist.shape, dtype=np.int32)

    # seeds: distance peaks that are ALSO on confident foreground
    seed_ok = mask & (dist > seed_thr)
    coords = peak_local_max(dist, min_distance=min_distance,
                            threshold_abs=seed_thr, labels=seed_ok)
    if coords.shape[0] == 0:
        lab, _ = ndi.label(mask)
    else:
        markers = np.zeros(dist.shape, dtype=np.int32)
        for idx, (r, c) in enumerate(coords, start=1):
            markers[r, c] = idx
        lab = watershed(-dist, markers=markers, mask=mask)

    lab = _drop_small(lab, min_size)

    # drop instances the model is not confident are foreground (background phantoms)
    if min_mean_fg > 0 and lab.max() > 0:
        keep = np.ones(int(lab.max()) + 1, dtype=bool); keep[0] = False
        sums = np.bincount(lab.ravel(), weights=fg.ravel(), minlength=int(lab.max()) + 1)
        cnts = np.bincount(lab.ravel(), minlength=int(lab.max()) + 1)
        with np.errstate(invalid="ignore", divide="ignore"):
            means = np.where(cnts > 0, sums / np.maximum(cnts, 1), 0.0)
        for i in range(1, len(keep)):
            if means[i] < min_mean_fg:
                lab[lab == i] = 0
    return sklabel(lab)


def _drop_small(labels, min_size):
    """Remove instances with fewer than min_size pixels (version-safe)."""
    import numpy as _np
    out = labels.copy()
    if out.max() == 0:
        return out
    counts = _np.bincount(out.ravel())
    for lab_id, cnt in enumerate(counts):
        if lab_id != 0 and cnt < min_size:
            out[out == lab_id] = 0
    return out


def connected_components(fg, fg_thr=0.5, min_size=20):
    from scipy import ndimage as ndi
    lab, _ = ndi.label(fg > fg_thr)
    return _drop_small(lab, min_size)


def colour_overlay(img, labels):
    rng = np.random.default_rng(0)
    n = int(labels.max())
    lut = np.vstack([[0, 0, 0], rng.random((max(n, 1), 3)).clip(0.25, 1.0)])
    rgb = lut[labels]
    base = np.dstack([img, img, img])
    return (0.45 * base + 0.55 * rgb)


def celltype_of(fn):
    canon = {"A172": "A172", "BT474": "BT474", "BV2": "BV2", "HUH7": "Huh7",
             "MCF7": "MCF7", "SHSY5Y": "SH-SY5Y", "SKBR3": "SkBr3", "SKOV3": "SK-OV-3"}
    return canon.get(os.path.basename(fn).split("_")[0].upper(), "?")


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Watershed instance inference")
    ap.add_argument("--model", required=True)
    ap.add_argument("--images", required=True)
    ap.add_argument("--coco", default=None)
    ap.add_argument("--out", default="predictions/instance_test")
    ap.add_argument("--base-channels", type=int, default=32)
    ap.add_argument("--depth", type=int, default=4)
    ap.add_argument("--fg-thr", type=float, default=0.5)
    ap.add_argument("--seed-thr", type=float, default=0.4)
    ap.add_argument("--min-distance", type=int, default=4)
    ap.add_argument("--bnd-thr", type=float, default=0.5)
    ap.add_argument("--min-size", type=int, default=20)
    ap.add_argument("--min-mean-fg", type=float, default=0.5,
                    help="drop instances whose mean foreground prob is below this")
    ap.add_argument("--overlays", type=int, default=8, help="save N colour overlays")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    import torch
    from phase11_instance_model import build_instance_model

    os.makedirs(a.out, exist_ok=True)
    lbl_dir = os.path.join(a.out, "labels"); os.makedirs(lbl_dir, exist_ok=True)
    ov_dir = os.path.join(a.out, "overlays"); os.makedirs(ov_dir, exist_ok=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    amp_dtype = torch.bfloat16 if device.type == "cuda" else torch.float32

    model = build_instance_model(base_channels=a.base_channels, depth=a.depth)
    ck = torch.load(a.model, map_location="cpu", weights_only=False)
    sd = ck.get("model_state_dict", ck)
    model.load_state_dict(sd)
    model.to(device).eval()
    log.info("loaded %s (epoch %s)", a.model, ck.get("epoch", "?"))

    gt_counts = {}
    if a.coco:
        from pycocotools.coco import COCO
        coco = COCO(a.coco)
        for iid in coco.getImgIds():
            info = coco.loadImgs(iid)[0]
            gt_counts[info["file_name"]] = len(coco.getAnnIds(imgIds=iid))

    from PIL import Image
    files = sorted(f for f in os.listdir(a.images)
                   if f.lower().endswith((".tif", ".tiff", ".png")))
    if a.limit:
        files = files[:a.limit]
    log.info("%d images", len(files))

    rows = []
    for k, fn in enumerate(files, 1):
        img = percentile_norm(read_image(os.path.join(a.images, fn)))
        fg, dist, bnd = predict_maps(model, img, device, amp_dtype)
        ws = watershed_instances(fg, dist, bnd, a.fg_thr, a.seed_thr,
                                 a.min_distance, a.bnd_thr, a.min_size, a.min_mean_fg)
        cc = connected_components(fg, a.fg_thr, a.min_size)
        n_ws, n_cc = int(ws.max()), int(cc.max())
        n_gt = gt_counts.get(fn, None)
        rows.append((fn, n_ws, n_cc, n_gt))

        Image.fromarray(ws.astype(np.uint16)).save(os.path.join(lbl_dir, os.path.splitext(fn)[0] + ".png"))
        if k <= a.overlays:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            ov = colour_overlay(img, ws)
            fig, ax = plt.subplots(1, 3, figsize=(11, 3.6))
            ax[0].imshow(img, cmap="gray"); ax[0].set_title("phase", fontsize=8)
            ax[1].imshow(cc, cmap="nipy_spectral"); ax[1].set_title(f"connected comp. (n={n_cc})", fontsize=8)
            ax[2].imshow(np.clip(ov, 0, 1)); ax[2].set_title(f"watershed (n={n_ws})", fontsize=8)
            for x in ax:
                x.set_xticks([]); x.set_yticks([])
            fig.tight_layout()
            fig.savefig(os.path.join(ov_dir, os.path.splitext(fn)[0] + ".png"), dpi=120,
                        bbox_inches="tight")
            plt.close(fig)
        if k % 100 == 0:
            log.info("  %d/%d", k, len(files))

    import pandas as pd
    df = pd.DataFrame(rows, columns=["file", "n_watershed", "n_conncomp", "n_expert"])
    df["cell_type"] = df["file"].map(celltype_of)
    df.to_csv(os.path.join(a.out, "instance_counts.csv"), index=False)

    print("\n" + "=" * 74)
    print(f" wrote {len(files)} label images to {lbl_dir}")
    print(f" {min(a.overlays, len(files))} overlays in {ov_dir}")
    print("-" * 74)
    print(f" mean instances/image  watershed {df['n_watershed'].mean():.1f}"
          f"   vs connected-comp {df['n_conncomp'].mean():.1f}")
    if df["n_expert"].notna().any():
        d = df.dropna(subset=["n_expert"])
        rec_ws = (d["n_watershed"] / d["n_expert"]).replace([np.inf], np.nan).mean()
        rec_cc = (d["n_conncomp"] / d["n_expert"]).replace([np.inf], np.nan).mean()
        print(f" mean recovery vs expert   watershed {rec_ws:.2f}"
              f"   vs connected-comp {rec_cc:.2f}")
        print(" (watershed should be much closer to 1.0, especially on crowded images)")
    print("=" * 74 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
