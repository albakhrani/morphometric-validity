#!/usr/bin/env python3
"""
Phase 20 - Key evidence figures  (Paper 2, Option B)
=====================================================
Two figures that give the paper's central claims direct visual support,
rather than leaving them stated in prose only.

  micrographs   A real crowded field shown four ways: phase contrast,
               expert instances, connected-component labeling (merged),
               and marker-controlled watershed (ours). This is the
               mechanism behind Sections res-dissociation / disc-mechanism
               made visible rather than asserted.

  envelope_v2   Two stacked panels sharing one confluence axis: foreground
               IoU on top (flat/rising -- identical for both pipelines,
               since they share one backbone prediction) and matched-
               detection F1 below (collapsing for connected components,
               holding up for the instance-preserving extension). This is
               the paper's founding dissociation (Section res-dissociation)
               in one figure, which no existing figure currently shows.

Both figures use the SAME cached predictions and the SAME watershed
parameters as the rest of the paper, so nothing here is a new evaluation
run -- it is the existing analysis, visualized.

Usage
    python phase20_key_figures.py \
        --model runs/instance/best.pt \
        --images data/raw/livecell_test_images \
        --coco   data/raw/livecell/livecell_coco_test.json \
        --out    figures --subsample 180 \
        --seed-thr 0.45 --min-distance 6 --min-size 50
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
    read_image, percentile_norm, predict_maps, watershed_instances,
    connected_components, celltype_of)
from phase14_evaluate import match_f1, f1, gt_label_image    # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("keyfigs")

NAVY = "#08306B"
CRIM = "#B2182B"
BLUE = "#2166AC"
GREY = "#555555"


# ============================================================== helpers ===
def load_model(model_path, base_channels, depth):
    import torch
    from phase11_instance_model import build_instance_model
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    amp = torch.bfloat16 if device.type == "cuda" else torch.float32
    model = build_instance_model(base_channels=base_channels, depth=depth)
    ck = torch.load(model_path, map_location="cpu", weights_only=False)
    model.load_state_dict(ck.get("model_state_dict", ck))
    model.to(device).eval()
    log.info("loaded %s (epoch %s)", model_path, ck.get("epoch", "?"))
    return model, device, amp


def collect_items(coco, image_dir, subsample, min_hours=0.0):
    from phase17_atlas_from_instances import parse_hours
    on_disk = set(os.listdir(image_dir))
    recs = []
    for iid in coco.getImgIds():
        info = coco.loadImgs(iid)[0]
        fn = info["file_name"]
        if fn not in on_disk:
            continue
        anns = coco.loadAnns(coco.getAnnIds(imgIds=iid))
        if not anns:
            continue
        hrs = parse_hours(fn)
        if min_hours and np.isfinite(hrs) and hrs < min_hours:
            continue
        phi = sum(float(a.get("area", 0.0)) for a in anns) / float(info["height"] * info["width"])
        recs.append((iid, fn, phi, info["height"], info["width"]))
    recs.sort(key=lambda r: r[2])
    if subsample and len(recs) > subsample:
        step = max(1, len(recs) // subsample)
        recs = recs[::step][:subsample]
    return recs


def foreground_iou(fg_prob, gt_mask, thr=0.5):
    pred = fg_prob > thr
    inter = np.logical_and(pred, gt_mask).sum()
    union = np.logical_or(pred, gt_mask).sum()
    return float(inter) / float(union) if union > 0 else float("nan")


def color_label(labels, rng):
    n = int(labels.max())
    lut = np.vstack([[0, 0, 0], rng.random((max(n, 1), 3)).clip(0.25, 1.0)])
    return lut[labels]


# ========================================================= micrographs ===
def fig_micrographs(model, device, amp, coco, images_dir, out_dir,
                    seed_thr, min_distance, min_size,
                    preferred_lineage=None, target_phi=0.85, crop=420):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    on_disk = set(os.listdir(images_dir))
    best, best_d = None, 1e9
    for iid in coco.getImgIds():
        info = coco.loadImgs(iid)[0]
        fn = info["file_name"]
        if fn not in on_disk:
            continue
        if preferred_lineage and celltype_of(fn) != preferred_lineage:
            continue
        anns = coco.loadAnns(coco.getAnnIds(imgIds=iid))
        if len(anns) < 40:
            continue
        phi = sum(float(a.get("area", 0.0)) for a in anns) / float(info["height"] * info["width"])
        d = abs(phi - target_phi)
        if d < best_d:
            best_d, best = d, (iid, fn, phi, info["height"], info["width"])
    if best is None:
        log.warning("no suitable crowded image found for micrographs")
        return None
    iid, fn, phi, H, W = best
    log.info("micrograph source: %s (phi=%.2f, lineage=%s)", fn, phi, celltype_of(fn))

    img = percentile_norm(read_image(os.path.join(images_dir, fn)))
    gt = gt_label_image(coco, iid, H, W)
    fg, dist, bnd = predict_maps(model, img, device, amp)
    cc = connected_components(fg, min_size=min_size)
    ws = watershed_instances(fg, dist, bnd, seed_thr=seed_thr,
                             min_distance=min_distance, min_size=min_size)

    # center-crop all arrays identically for a legible, zoomed view.
    # crop <= 0 keeps the full field, so the printed counts describe exactly
    # what the reader sees. Cropping and then counting is what produced the
    # incommensurable 351-vs-315 pair in an earlier version.
    def cc_crop(a, n):
        if n is None or n <= 0:
            return a
        h, w = a.shape[:2]
        n = min(n, h, w)
        y0, x0 = (h - n) // 2, (w - n) // 2
        return a[y0:y0 + n, x0:x0 + n]
    img_c, gt_c, cc_c, ws_c = (cc_crop(a, crop) for a in (img, gt, cc, ws))

    rng = np.random.default_rng(0)

    # Count distinct labels surviving the crop. Using .max() instead returns the
    # highest label ID that happens to fall inside the crop, which is neither the
    # crop count nor the whole-image count -- that is where the published 351
    # came from (whole image has 370 watershed instances; this crop has 193).
    def n_labels(a):
        return int(np.count_nonzero(np.unique(a)))

    n_gt, n_cc, n_ws = n_labels(gt_c), n_labels(cc_c), n_labels(ws_c)

    # Authored at the placed width (\textwidth = 494.51 pt = 6.87 in, less the
    # padding bbox_inches="tight" adds) so LaTeX applies no downscale and the
    # sizes below are the sizes that print. The old 13.5 in canvas was scaled
    # to 51%, printing these labels at 4.1-4.6 pt.
    fig, ax = plt.subplots(1, 4, figsize=(6.6, 2.15))
    ax[0].imshow(img_c, cmap="gray")
    ax[0].set_title("phase contrast", fontsize=7.5)

    ax[1].imshow(color_label(gt_c, rng))
    ax[1].set_title(f"expert instances  (n={n_gt})", fontsize=7.5)

    ax[2].imshow(color_label(cc_c, rng))
    ax[2].set_title(f"connected comp.  (n={n_cc})", fontsize=7.5, color=CRIM)
    rec_cc = n_cc / max(n_gt, 1)
    ax[2].text(0.5, -0.055, f"recovers {rec_cc:.1%}\nof expert instances",
              transform=ax[2].transAxes, ha="center", va="top",
              fontsize=7.2, color=CRIM, linespacing=1.3)

    ax[3].imshow(color_label(ws_c, rng))
    ax[3].set_title(f"watershed (ours)  (n={n_ws})", fontsize=7.5, color=BLUE)
    rec_ws = n_ws / max(n_gt, 1)
    ax[3].text(0.5, -0.055, f"recovers {rec_ws:.1%}\nof expert instances",
              transform=ax[3].transAxes, ha="center", va="top",
              fontsize=7.2, color=BLUE, linespacing=1.3)

    for a in ax:
        a.set_xticks([]); a.set_yticks([])
        for sp in a.spines.values():
            sp.set_visible(False)
    fig.suptitle(f"{celltype_of(fn)}   \u03c6 = {phi:.2f}", fontsize=7.8, y=1.03)
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(out_dir, f"Fig2_micrographs.{ext}"), dpi=220,
                    bbox_inches="tight")
    plt.close(fig)
    log.info("wrote Fig2_micrographs.pdf / .png  (source: %s)", fn)
    return dict(file=fn, phi=phi, n_gt=n_gt, n_cc=n_cc, n_ws=n_ws)


# ========================================================= envelope v2 ===
def fig_envelope_v2(model, device, amp, coco, images_dir, out_dir, items,
                    seed_thr, min_distance, min_size, bins=6):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd

    rows = []
    for k, (iid, fn, phi, H, W) in enumerate(items, 1):
        img = percentile_norm(read_image(os.path.join(images_dir, fn)))
        gt = gt_label_image(coco, iid, H, W)
        fg, dist, bnd = predict_maps(model, img, device, amp)

        gt_fg = gt > 0
        iou = foreground_iou(fg, gt_fg)

        ws = watershed_instances(fg, dist, bnd, seed_thr=seed_thr,
                                 min_distance=min_distance, min_size=min_size)
        cc = connected_components(fg, min_size=min_size)
        tp_w, fp_w, fn_w, _ = match_f1(ws, gt)
        tp_c, fp_c, fn_c, _ = match_f1(cc, gt)

        rows.append(dict(file=fn, phi=phi, iou=iou,
                         tp_w=tp_w, fp_w=fp_w, fn_w=fn_w,
                         tp_c=tp_c, fp_c=fp_c, fn_c=fn_c))
        if k % 40 == 0:
            log.info("  %d/%d", k, len(items))

    df = pd.DataFrame(rows)
    edges = np.quantile(df["phi"], np.linspace(0, 1, bins + 1))
    edges[-1] += 1e-6
    binned = []
    for b in range(bins):
        lo, hi = edges[b], edges[b + 1]
        sub = df[(df["phi"] >= lo) & (df["phi"] < hi)]
        if sub.empty:
            continue
        f1_w = f1(sub["tp_w"].sum(), sub["fp_w"].sum(), sub["fn_w"].sum())
        f1_c = f1(sub["tp_c"].sum(), sub["fp_c"].sum(), sub["fn_c"].sum())
        binned.append(dict(phi_mid=float((lo + hi) / 2), n=len(sub),
                           iou_mean=float(sub["iou"].mean()), f1_ws=f1_w, f1_cc=f1_c))
    bdf = pd.DataFrame(binned)
    bdf.to_csv(os.path.join(out_dir, "envelope_v2_data.csv"), index=False)

    fig, (axT, axB) = plt.subplots(2, 1, figsize=(6.0, 5.8), sharex=True,
                                   gridspec_kw=dict(height_ratios=[1, 1.3], hspace=0.08))
    axT.plot(bdf["phi_mid"], bdf["iou_mean"], "-o", color=NAVY, ms=5, lw=1.6)
    axT.set_ylim(0.6, 1.0)
    axT.set_ylabel("foreground IoU")
    axT.axhspan(0.80, 0.85, color=NAVY, alpha=0.08, zorder=0)
    axT.set_title("Same foreground prediction throughout \u2014 IoU does not warn of the failure below",
                 fontsize=8.5, color=NAVY)
    axT.grid(alpha=0.15)

    axB.plot(bdf["phi_mid"], bdf["f1_ws"], "-o", color=BLUE, ms=5, lw=1.6,
             label="instance-preserving extension (ours)")
    axB.plot(bdf["phi_mid"], bdf["f1_cc"], "-s", color=CRIM, ms=5, lw=1.6,
             label="connected components")
    axB.set_ylim(0, 1.0)
    axB.set_xlabel("confluence  $\\varphi$")
    axB.set_ylabel("matched-instance F1")
    axB.legend(frameon=False, fontsize=8, loc="upper right")
    axB.grid(alpha=0.15)

    fig.align_ylabels([axT, axB])
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(out_dir, f"Fig4_envelope.{ext}"), dpi=220,
                    bbox_inches="tight")
    plt.close(fig)
    log.info("wrote Fig4_envelope.pdf / .png")
    return bdf


# =============================================================== main ====
def main():
    ap = argparse.ArgumentParser(description="Key evidence figures")
    ap.add_argument("--model", required=True)
    ap.add_argument("--images", required=True)
    ap.add_argument("--coco", required=True)
    ap.add_argument("--out", default="figures")
    ap.add_argument("--base-channels", type=int, default=32)
    ap.add_argument("--depth", type=int, default=4)
    ap.add_argument("--subsample", type=int, default=180)
    ap.add_argument("--min-hours", type=float, default=0.0)
    ap.add_argument("--seed-thr", type=float, default=0.45)
    ap.add_argument("--min-distance", type=int, default=6)
    ap.add_argument("--min-size", type=int, default=50)
    ap.add_argument("--micrograph-lineage", default=None,
                    help="restrict the micrograph panel to one lineage, e.g. SK-OV-3")
    ap.add_argument("--micrograph-phi", type=float, default=0.85)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    from pycocotools.coco import COCO
    coco = COCO(a.coco)
    model, device, amp = load_model(a.model, a.base_channels, a.depth)

    log.info("=== micrographs ===")
    micro_info = fig_micrographs(model, device, amp, coco, a.images, a.out,
                                 a.seed_thr, a.min_distance, a.min_size,
                                 preferred_lineage=a.micrograph_lineage,
                                 target_phi=a.micrograph_phi)

    log.info("=== envelope v2 (IoU + F1) ===")
    items = collect_items(coco, a.images, a.subsample, a.min_hours)
    log.info("%d images, phi %.2f-%.2f", len(items), items[0][2], items[-1][2])
    bdf = fig_envelope_v2(model, device, amp, coco, a.images, a.out, items,
                          a.seed_thr, a.min_distance, a.min_size)

    print("\n" + "=" * 78)
    if micro_info:
        print(f" MICROGRAPH SOURCE: {micro_info['file']}  (phi={micro_info['phi']:.2f})")
        print(f"   expert n={micro_info['n_gt']}  conn.comp n={micro_info['n_cc']}"
              f"  watershed n={micro_info['n_ws']}")
    print("-" * 78)
    print(" ENVELOPE (IoU + F1 by confluence bin)")
    print(bdf.to_string(index=False))
    print("=" * 78)
    print(f" figures written to {a.out}/\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
