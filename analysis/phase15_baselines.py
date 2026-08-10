#!/usr/bin/env python3
"""
Phase 15 - Baseline comparison  (Paper 2, Option B)
===================================================
Scores our instance-preserving model against purpose-built instance-segmentation
baselines on the SAME test images, with the SAME matched-F1 protocol and the
SAME confluence bins, so the comparison is apples-to-apples.

Methods compared
    ours        watershed labels written by phase 13 (predictions/instance_final)
    conncomp    connected components on our foreground (the naive pipeline)
    cellpose    Cellpose pretrained 'cyto3' (or --cellpose-model)
    stardist    StarDist2D pretrained '2D_versatile_fluo'

Cellpose and StarDist are optional: if a package is not installed, that method is
skipped with a warning and the rest still runs. Install with
    pip install cellpose
    pip install stardist tensorflow          (StarDist needs TensorFlow)

Outputs
    baseline_comparison.csv     per-method, per-confluence-bin F1 + median recovery
    baseline_comparison.png/pdf grouped curves: F1 vs confluence for every method
    baseline_summary.csv        one row per method (overall F1, mean IoU of matches)

Usage
    python phase15_baselines.py \
        --images data/raw/livecell_test_images \
        --coco   data/raw/livecell/livecell_coco_test.json \
        --ours   predictions/instance_final/labels \
        --model  runs/instance/best.pt \
        --out    baselines --subsample 180
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

from phase13_watershed_infer import (                       # noqa: E402
    read_image, percentile_norm, predict_maps, connected_components)
from phase14_evaluate import match_f1, f1, gt_label_image    # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("baselines")


# --------------------------------------------------------------------------
def load_ours(labels_dir, fn):
    stem = os.path.splitext(fn)[0]
    for ext in (".png", ".tif", ".tiff"):
        p = os.path.join(labels_dir, stem + ext)
        if os.path.isfile(p):
            from PIL import Image
            return np.array(Image.open(p)).astype(np.int32)
    return None


def run_cellpose(images, model_name="cyto3", diameter=None, batch=8, required=True):
    """Return {filename: label image}. Raises when unavailable and required."""
    try:
        from cellpose import models as cp_models
    except Exception as exc:
        msg = (f"Cellpose is not importable ({exc}). Install it, or pass "
               f"--skip-cellpose to leave it out on purpose.")
        if required:
            raise RuntimeError(msg) from exc
        log.warning("%s - skipping", msg)
        return None
    try:
        import torch
        gpu = torch.cuda.is_available()
    except Exception:
        gpu = False
    log.info("running Cellpose '%s' (gpu=%s) on %d images", model_name, gpu, len(images))
    try:
        model = cp_models.CellposeModel(gpu=gpu, model_type=model_name)
    except TypeError:                      # newer cellpose API
        model = cp_models.CellposeModel(gpu=gpu, pretrained_model=model_name)
    out = {}
    names = list(images.keys())
    for i in range(0, len(names), batch):
        chunk = names[i:i + batch]
        imgs = [images[n] for n in chunk]
        try:
            res = model.eval(imgs, diameter=diameter, channels=[0, 0])
        except Exception as exc:
            log.warning("cellpose eval failed: %s", exc)
            return None
        masks = res[0]
        for n, m in zip(chunk, masks):
            out[n] = np.asarray(m).astype(np.int32)
        log.info("  cellpose %d/%d", min(i + batch, len(names)), len(names))
    return out


def run_stardist(images, model_name="2D_versatile_fluo", required=True):
    """Return {filename: label image}.

    Raises when StarDist cannot run and `required` is True. It previously
    returned None after a log.warning, so an uninstalled dependency silently
    dropped the entire method from the results table and nothing downstream
    noticed. Pass --skip-stardist to omit it deliberately.
    """
    try:
        from stardist.models import StarDist2D
        from csbdeep.utils import normalize
    except Exception as exc:
        msg = (f"StarDist is not importable ({exc}). Install it with "
               f"'pip install stardist csbdeep tensorflow', or pass "
               f"--skip-stardist to leave it out on purpose.")
        if required:
            raise RuntimeError(msg) from exc
        log.warning("%s - skipping", msg)
        return None
    log.info("running StarDist '%s' on %d images", model_name, len(images))
    try:
        model = StarDist2D.from_pretrained(model_name)
    except Exception as exc:
        msg = f"could not load StarDist model '{model_name}': {exc}"
        if required:
            raise RuntimeError(msg) from exc
        log.warning("%s - skipping", msg)
        return None
    out, failures = {}, 0
    for k, (n, img) in enumerate(images.items(), 1):
        try:
            lab, _ = model.predict_instances(normalize(img, 1, 99.8))
            out[n] = np.asarray(lab).astype(np.int32)
        except Exception as exc:
            failures += 1
            log.warning("stardist failed on %s: %s", n, exc)
            out[n] = np.zeros(img.shape, np.int32)
        if k % 40 == 0:
            log.info("  stardist %d/%d", k, len(images))
    # An all-zero result scores F1 = 0 and looks like a real measurement.
    if failures and failures > 0.1 * len(images):
        raise RuntimeError(f"StarDist failed on {failures}/{len(images)} images; "
                           f"refusing to report a score built from blank masks")
    return out


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Baseline comparison")
    ap.add_argument("--images", required=True)
    ap.add_argument("--coco", required=True)
    ap.add_argument("--ours", required=True, help="directory of our watershed label PNGs")
    ap.add_argument("--model", default=None, help="our checkpoint (for the conncomp baseline)")
    ap.add_argument("--base-channels", type=int, default=32)
    ap.add_argument("--depth", type=int, default=4)
    ap.add_argument("--out", default="baselines")
    ap.add_argument("--subsample", type=int, default=180)
    ap.add_argument("--bins", type=int, default=6)
    ap.add_argument("--cellpose-model", default="cyto3")
    ap.add_argument("--cellpose-diameter", type=float, default=None)
    ap.add_argument("--stardist-model", default="2D_versatile_fluo")
    ap.add_argument("--skip-cellpose", action="store_true")
    ap.add_argument("--skip-stardist", action="store_true")
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
        anns = coco.loadAnns(coco.getAnnIds(imgIds=iid))
        if not anns:
            continue
        phi = sum(float(x.get("area", 0.0)) for x in anns) / float(info["height"] * info["width"])
        recs.append((iid, fn, phi, info["height"], info["width"]))
    recs.sort(key=lambda r: r[2])
    step = max(1, len(recs) // a.subsample)
    sub = recs[::step][:a.subsample]
    log.info("evaluating %d images spanning phi %.2f-%.2f", len(sub), sub[0][2], sub[-1][2])

    # ---- gather images, GT, and our labels ----
    images, gts, phis, ours = {}, {}, {}, {}
    for iid, fn, phi, H, W in sub:
        img = percentile_norm(read_image(os.path.join(a.images, fn)))
        images[fn] = img
        gts[fn] = gt_label_image(coco, iid, H, W)
        phis[fn] = phi
        lab = load_ours(a.ours, fn)
        if lab is not None:
            ours[fn] = lab
    log.info("loaded %d/%d of our label images", len(ours), len(sub))

    methods = {}
    if ours:
        methods["ours (watershed)"] = ours

    # ---- connected-components baseline from our foreground ----
    if a.model:
        import torch
        from phase11_instance_model import build_instance_model
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        amp = torch.bfloat16 if device.type == "cuda" else torch.float32
        m = build_instance_model(base_channels=a.base_channels, depth=a.depth)
        ck = torch.load(a.model, map_location="cpu", weights_only=False)
        m.load_state_dict(ck.get("model_state_dict", ck)); m.to(device).eval()
        cc = {}
        for k, (fn, img) in enumerate(images.items(), 1):
            fg, _, _ = predict_maps(m, img, device, amp)
            cc[fn] = connected_components(fg, min_size=50)
            if k % 60 == 0:
                log.info("  conncomp %d/%d", k, len(images))
        methods["connected comp."] = cc

    # A baseline that was requested but could not run is an error, not a
    # silent omission: the previous code dropped StarDist from every reported
    # table without anything in the output saying so.
    if not a.skip_cellpose:
        methods["Cellpose"] = run_cellpose(images, a.cellpose_model,
                                           a.cellpose_diameter, required=True)
    if not a.skip_stardist:
        methods["StarDist"] = run_stardist(images, a.stardist_model, required=True)

    if not methods:
        log.error("no methods to evaluate"); return 2

    # ---- score every method with the identical protocol ----
    ph = np.array([phis[fn] for fn in images])
    edges = np.quantile(ph, np.linspace(0, 1, a.bins + 1)); edges[-1] += 1e-6

    rows, summary = [], []
    for name, labels in methods.items():
        TP = FP = FN = 0; ious = []
        for b in range(a.bins):
            lo, hi = edges[b], edges[b + 1]
            sel = [fn for fn in images if lo <= phis[fn] < hi]
            if not sel:
                continue
            t = fp = fn_ = 0; rec = []
            for fnm in sel:
                pred = labels.get(fnm)
                if pred is None:
                    continue
                tp_, fp_, fn2, mi = match_f1(pred, gts[fnm])
                t += tp_; fp += fp_; fn_ += fn2
                if np.isfinite(mi):
                    ious.append(mi)
                rec.append(int(pred.max()) / max(int(gts[fnm].max()), 1))
            TP += t; FP += fp; FN += fn_
            rows.append(dict(method=name, bin=b,
                             phi_mid=round(float((lo + hi) / 2), 3),
                             n_images=len(sel),
                             f1=round(f1(t, fp, fn_), 3),
                             recovery_med=round(float(np.median(rec)) if rec else np.nan, 3)))
        summary.append(dict(method=name, overall_f1=round(f1(TP, FP, FN), 3),
                            mean_matched_iou=round(float(np.mean(ious)), 3) if ious else np.nan,
                            tp=TP, fp=FP, fn=FN))

    import pandas as pd
    df = pd.DataFrame(rows); dfs = pd.DataFrame(summary).sort_values("overall_f1", ascending=False)
    df.to_csv(os.path.join(a.out, "baseline_comparison.csv"), index=False)
    dfs.to_csv(os.path.join(a.out, "baseline_summary.csv"), index=False)

    # ---- figure ----
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    colors = {"ours (watershed)": "#2166AC", "connected comp.": "#B2182B",
              "Cellpose": "#1B7837", "StarDist": "#E08214"}
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.8))
    for name in methods:
        d = df[df["method"] == name].sort_values("phi_mid")
        c = colors.get(name, None)
        ax[0].plot(d["phi_mid"], d["f1"], "-o", ms=4, color=c, label=name)
        ax[1].plot(d["phi_mid"], d["recovery_med"], "-o", ms=4, color=c, label=name)
    ax[0].set_xlabel("confluence  φ"); ax[0].set_ylabel("matched F1 @ IoU 0.5")
    ax[0].set_ylim(0, 1); ax[0].set_title("detection quality vs density", fontsize=9)
    ax[0].legend(frameon=False, fontsize=7.5); ax[0].grid(alpha=0.15)
    ax[1].axhline(1.0, ls="--", lw=0.8, color="#888")
    ax[1].set_xlabel("confluence  φ"); ax[1].set_ylabel("median instance recovery")
    ax[1].set_title("count calibration vs density", fontsize=9); ax[1].grid(alpha=0.15)
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(a.out, f"baseline_comparison.{ext}"), dpi=200, bbox_inches="tight")
    plt.close(fig)

    print("\n" + "=" * 78)
    print(" OVERALL (matched F1 @ IoU 0.5)")
    print(dfs.to_string(index=False))
    print("-" * 78)
    print(" PER-CONFLUENCE-BIN F1")
    piv = df.pivot(index="phi_mid", columns="method", values="f1")
    print(piv.to_string())
    print("=" * 78)
    print(f" csv + figure written to {a.out}/\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
