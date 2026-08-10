#!/usr/bin/env python3
"""
Phase 17 - Atlas re-derivation from instance-preserved masks  (Paper 2, Option B)
=================================================================================
Closes the loop between the architecture contribution and the biology.

Earlier (phase 5/7) the per-lineage morphological trajectories could only be
recovered from model masks over the SUB-CONFLUENT range, because
connected-components fused touching cells and instance recovery collapsed to
~0.01 in crowded fields. With the instance-preserving head + watershed, recovery
holds near 1.0 at every density, so the same measurement should now be valid
across the FULL gradient.

This script measures that directly. For every test image it computes per-cell
geometry from three mask sources using IDENTICAL code:

    expert      ground-truth COCO instances          (reference)
    ours        watershed labels from phase 13       (instance-preserving)
    conncomp    connected components on our foreground (the naive pipeline)

and then, per lineage, correlates per-image mean shape index q = P/sqrt(A)
against confluence phi, for each source. The headline comparison is how closely
'ours' and 'conncomp' reproduce the expert trajectory, and over what density
range each remains usable.

Outputs
    atlas_percell_<source>.csv    per-cell geometry (area, perimeter, q, ...)
    atlas_trajectories.csv        per-lineage rho(phi, mean q) for each source
    atlas_agreement.csv           per-lineage bias in mean q vs expert, by phi bin
    atlas_comparison.png/pdf      trajectories: expert vs ours vs conncomp

Usage
    python phase17_atlas_from_instances.py \
        --coco   data/raw/livecell/livecell_coco_test.json \
        --images data/raw/livecell_test_images \
        --ours   predictions/instance_final/labels \
        --model  runs/instance/best.pt \
        --out    atlas_instance --min-area 150 --min-hours 8
"""
from __future__ import annotations

import argparse
import logging
import math
import os
import re
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from phase13_watershed_infer import (                    # noqa: E402
    read_image, percentile_norm, predict_maps, connected_components,
    watershed_instances, celltype_of)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("atlas")

TIME_RE = re.compile(r"(\d+)d(\d+)h(\d+)m", re.I)


def parse_hours(file_name):
    m = TIME_RE.search(os.path.basename(file_name or ""))
    if not m:
        return math.nan
    d, h, mi = (int(g) for g in m.groups())
    return d * 24.0 + h + mi / 60.0


def geometry_from_labels(labels, min_area=150, exclude_border=True):
    """Per-cell geometry from an integer label image. Identical code for every
    mask source, so differences are attributable to segmentation alone."""
    from skimage.measure import regionprops

    H, W = labels.shape
    rows = []
    for r in regionprops(labels.astype(np.int32)):
        if r.area < min_area:
            continue
        if exclude_border:
            minr, minc, maxr, maxc = r.bbox
            if minr <= 0 or minc <= 0 or maxr >= H or maxc >= W:
                continue
        per = float(r.perimeter)
        area = float(r.area)
        if area <= 0 or per <= 0:
            continue
        rows.append(dict(cell_area=area, cell_perimeter=per,
                         q=per / math.sqrt(area),
                         eccentricity=float(r.eccentricity),
                         solidity=float(r.solidity),
                         extent=float(r.extent),
                         centroid_y=float(r.centroid[0]),
                         centroid_x=float(r.centroid[1])))
    return rows


def gt_labels(coco, iid, H, W):
    lab = np.zeros((H, W), np.int32)
    for i, ann in enumerate(coco.loadAnns(coco.getAnnIds(imgIds=iid)), start=1):
        m = coco.annToMask(ann)
        lab[m > 0] = i
    return lab


def load_label_png(d, fn):
    stem = os.path.splitext(fn)[0]
    for ext in (".png", ".tif", ".tiff"):
        p = os.path.join(d, stem + ext)
        if os.path.isfile(p):
            from PIL import Image
            return np.array(Image.open(p)).astype(np.int32)
    return None


def partial_spearman(x, y, z):
    """Spearman partial correlation of x,y controlling z. Returns (rho, p)."""
    from scipy import stats
    x, y, z = map(np.asarray, (x, y, z))
    ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
    x, y, z = x[ok], y[ok], z[ok]
    if len(x) < 8:
        return float("nan"), float("nan")
    rx, ry, rz = (stats.rankdata(v) for v in (x, y, z))
    def resid(a, b):
        b1 = np.c_[np.ones_like(b), b]
        coef, *_ = np.linalg.lstsq(b1, a, rcond=None)
        return a - b1 @ coef
    ex, ey = resid(rx, rz), resid(ry, rz)
    r = float(np.corrcoef(ex, ey)[0, 1])
    n, k = len(x), 1
    if abs(r) >= 1.0 or n - k - 2 <= 0:
        return r, float("nan")
    t = r * math.sqrt((n - k - 2) / (1 - r * r))
    p = float(2 * stats.t.sf(abs(t), n - k - 2))
    return r, p


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Atlas from instance-preserved masks")
    ap.add_argument("--coco", required=True)
    ap.add_argument("--images", required=True)
    ap.add_argument("--ours", required=True, help="watershed label dir from phase 13")
    ap.add_argument("--model", default=None, help="checkpoint, for the conncomp source")
    ap.add_argument("--base-channels", type=int, default=32)
    ap.add_argument("--depth", type=int, default=4)
    ap.add_argument("--out", default="atlas_instance")
    ap.add_argument("--min-area", type=int, default=150)
    ap.add_argument("--min-hours", type=float, default=8.0)
    ap.add_argument("--bins", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0)
    # Optional fourth mask source. Cellpose detects better than our extension
    # (Table 1), so running the SAME geometry code on its masks tests whether
    # that detection advantage carries through to the measurement.
    ap.add_argument("--cellpose", action="store_true",
                    help="add Cellpose as a fourth mask source")
    ap.add_argument("--cellpose-model", default="cyto3")
    # Fifth source: our own foreground decoded at a DIFFERENT watershed
    # operating point. The stored masks in --ours are the detection-optimal
    # point; this recomputes instances at the measurement-optimal point so the
    # operating-point choice can be evaluated on the morphometry it produces
    # rather than on the detection score used to select it.
    ap.add_argument("--ours-alt", action="store_true",
                    help="add a second watershed source at --alt-* parameters")
    ap.add_argument("--alt-seed-thr", type=float, default=0.75)
    ap.add_argument("--alt-min-distance", type=int, default=8)
    ap.add_argument("--alt-min-size", type=int, default=50)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    from pycocotools.coco import COCO
    import pandas as pd

    coco = COCO(a.coco)
    on_disk = set(os.listdir(a.images))
    items = []
    for iid in coco.getImgIds():
        info = coco.loadImgs(iid)[0]
        fn = info["file_name"]
        if fn not in on_disk:
            continue
        anns = coco.loadAnns(coco.getAnnIds(imgIds=iid))
        if not anns:
            continue
        phi = sum(float(x.get("area", 0.0)) for x in anns) / float(info["height"] * info["width"])
        hrs = parse_hours(fn)
        if a.min_hours and np.isfinite(hrs) and hrs < a.min_hours:
            continue
        items.append((iid, fn, phi, info["height"], info["width"]))
    if a.limit:
        items = items[:a.limit]
    log.info("%d images after >=%.0fh filter", len(items), a.min_hours)

    # optional conncomp source needs the model
    model = device = amp = None
    if a.model:
        import torch
        from phase11_instance_model import build_instance_model
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        amp = torch.bfloat16 if device.type == "cuda" else torch.float32
        model = build_instance_model(base_channels=a.base_channels, depth=a.depth)
        ck = torch.load(a.model, map_location="cpu", weights_only=False)
        model.load_state_dict(ck.get("model_state_dict", ck))
        model.to(device).eval()

    cp_model = None
    if a.cellpose:
        from cellpose import models as cp_models
        import torch as _t
        cp_model = cp_models.CellposeModel(gpu=_t.cuda.is_available(),
                                           model_type=a.cellpose_model)
        log.info("Cellpose source enabled (requested model '%s')", a.cellpose_model)

    if a.ours_alt and not a.model:
        raise SystemExit("--ours-alt needs --model: it recomputes watershed from the network")
    if a.ours_alt:
        log.info("second watershed source at seed_thr=%.2f min_distance=%d min_size=%d",
                 a.alt_seed_thr, a.alt_min_distance, a.alt_min_size)

    percell = {"expert": [], "ours": [], "conncomp": [], "cellpose": [],
               "oursalt": []}
    perimage = []
    for k, (iid, fn, phi, H, W) in enumerate(items, 1):
        ct = celltype_of(fn)
        srcs = {"expert": gt_labels(coco, iid, H, W)}
        lab = load_label_png(a.ours, fn)
        if lab is not None:
            srcs["ours"] = lab
        if model is not None:
            img = percentile_norm(read_image(os.path.join(a.images, fn)))
            fg, dist_m, bnd_m = predict_maps(model, img, device, amp)
            srcs["conncomp"] = connected_components(fg, min_size=50)
            if a.ours_alt:
                srcs["oursalt"] = watershed_instances(
                    fg, dist_m, bnd_m, seed_thr=a.alt_seed_thr,
                    min_distance=a.alt_min_distance, min_size=a.alt_min_size)
        if cp_model is not None:
            img_cp = percentile_norm(read_image(os.path.join(a.images, fn)))
            try:
                out = cp_model.eval(img_cp, diameter=None)
                srcs["cellpose"] = np.asarray(out[0], dtype=np.int32)
            except Exception as exc:
                log.warning("cellpose failed on %s: %s", fn, exc)

        row = dict(file=fn, cell_type=ct, phi=phi, hours=parse_hours(fn))
        for src, L in srcs.items():
            g = geometry_from_labels(L, min_area=a.min_area)
            for d in g:
                d.update(file=fn, cell_type=ct, phi=phi)
                percell[src].append(d)
            row[f"n_{src}"] = len(g)
            row[f"meanq_{src}"] = float(np.mean([d["q"] for d in g])) if g else np.nan
            row[f"meanarea_{src}"] = float(np.mean([d["cell_area"] for d in g])) if g else np.nan
        perimage.append(row)
        if k % 150 == 0:
            log.info("  %d/%d", k, len(items))

    dfi = pd.DataFrame(perimage)
    dfi.to_csv(os.path.join(a.out, "atlas_per_image.csv"), index=False)
    for src, rows in percell.items():
        if rows:
            pd.DataFrame(rows).to_csv(os.path.join(a.out, f"atlas_percell_{src}.csv"), index=False)

    sources = [s for s in ("expert", "ours", "oursalt", "conncomp", "cellpose")
               if f"meanq_{s}" in dfi.columns]

    # ---- per-lineage trajectories ----
    from scipy import stats
    traj = []
    for ct, g in dfi.groupby("cell_type"):
        rec = dict(cell_type=ct, n_images=len(g))
        for s in sources:
            sub = g.dropna(subset=[f"meanq_{s}", "phi"])
            if len(sub) >= 8:
                rho, p = stats.spearmanr(sub["phi"], sub[f"meanq_{s}"])
                pr, pp = partial_spearman(sub["phi"], sub[f"meanq_{s}"], sub[f"meanarea_{s}"])
            else:
                rho = p = pr = pp = np.nan
            rec[f"rho_{s}"] = round(float(rho), 3)
            rec[f"p_{s}"] = float(p)
            rec[f"partial_{s}"] = round(float(pr), 3)

            # Per-lineage measurement fidelity, so a mask source can be judged
            # on what it does to the morphometry rather than only on detection.
            paired = g.dropna(subset=[f"meanq_{s}", "meanq_expert"])
            rec[f"absbias_{s}"] = (round(float((paired[f"meanq_{s}"]
                                                - paired["meanq_expert"]).abs().mean()), 3)
                                   if len(paired) else np.nan)
            # amplitude: top-tercile minus bottom-tercile mean q, relative to
            # the same span measured from expert masks (Section 2.8).
            amp = np.nan
            if len(paired) >= 9:
                lo_t, hi_t = paired["phi"].quantile([1 / 3, 2 / 3])
                lo = paired[paired["phi"] <= lo_t]
                hi = paired[paired["phi"] >= hi_t]
                if len(lo) and len(hi):
                    span_e = hi["meanq_expert"].mean() - lo["meanq_expert"].mean()
                    span_s = hi[f"meanq_{s}"].mean() - lo[f"meanq_{s}"].mean()
                    if abs(span_e) > 1e-9:
                        amp = span_s / span_e
            rec[f"amp_{s}"] = round(float(amp), 3) if np.isfinite(amp) else np.nan
        traj.append(rec)
    dft = pd.DataFrame(traj).sort_values("rho_expert")
    dft.to_csv(os.path.join(a.out, "atlas_trajectories.csv"), index=False)

    # ---- agreement vs expert by confluence bin ----
    agree = []
    ph = dfi["phi"].to_numpy()
    edges = np.quantile(ph, np.linspace(0, 1, a.bins + 1)); edges[-1] += 1e-6
    for b in range(a.bins):
        lo, hi = edges[b], edges[b + 1]
        sub = dfi[(dfi["phi"] >= lo) & (dfi["phi"] < hi)]
        if sub.empty:
            continue
        rec = dict(bin=b, phi_mid=round(float((lo + hi) / 2), 3), n_images=len(sub))
        for s in sources:
            if s == "expert":
                continue
            d = sub.dropna(subset=[f"meanq_{s}", "meanq_expert"])
            rec[f"bias_{s}"] = round(float((d[f"meanq_{s}"] - d["meanq_expert"]).mean()), 3) if len(d) else np.nan
            rec[f"absbias_{s}"] = round(float((d[f"meanq_{s}"] - d["meanq_expert"]).abs().mean()), 3) if len(d) else np.nan
            rec[f"usable_{s}"] = round(float(d[f"n_{s}"].gt(0).mean()), 3) if len(d) else np.nan
        agree.append(rec)
    dfa = pd.DataFrame(agree)
    dfa.to_csv(os.path.join(a.out, "atlas_agreement.csv"), index=False)

    # ---- figure ----
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator
    style = {"expert": ("#222222", "-", "expert"),
             "ours": ("#2166AC", "-", "ours (instance-preserving)"),
             "conncomp": ("#B2182B", "--", "connected components"),
             "cellpose": ("#1B7837", "-.", "Cellpose"),
             "oursalt": ("#6A51A3", ":", "ours (measurement-optimal)")}
    cts = sorted(dfi["cell_type"].dropna().unique())
    ncol = min(4, max(1, len(cts)))
    nrow = int(math.ceil(len(cts) / ncol))
    # Authored at the placed width: 4 columns x 1.72 in = 6.88 in, which is
    # \textwidth. The previous 3.0 in per column made a 12 in canvas that LaTeX
    # downscaled to 58%, printing the tick labels at 3.7 pt.
    fig, axes = plt.subplots(nrow, ncol, figsize=(1.72 * ncol, 1.58 * nrow),
                             squeeze=False)
    for i, ct in enumerate(cts):
        ax = axes[i // ncol][i % ncol]
        g = dfi[dfi["cell_type"] == ct]
        for s in sources:
            d = g.dropna(subset=[f"meanq_{s}", "phi"])
            if len(d) < 6:
                continue
            try:
                bb = pd.qcut(d["phi"], 5, labels=False, duplicates="drop")
            except Exception:
                continue
            agg = (d.assign(_bin=bb)
                     .groupby("_bin", as_index=False)
                     .agg(phi=("phi", "median"), m=(f"meanq_{s}", "mean")))
            c, ls, lab = style[s]
            ax.plot(agg["phi"], agg["m"], ls, color=c, marker="o", ms=2.6, lw=1.1, label=lab)
        ax.set_title(ct, fontsize=8.0, pad=2.5)
        ax.tick_params(labelsize=7.0, length=2.2, width=0.6, pad=1.5)
        ax.grid(alpha=0.15)
        # At 1.72 in per panel the default locator crowds five or six ticks
        # into the axis and they run together.
        ax.xaxis.set_major_locator(MaxNLocator(nbins=4, prune="both"))
        ax.yaxis.set_major_locator(MaxNLocator(nbins=4))
        if i % ncol == 0:
            ax.set_ylabel("mean $q$", fontsize=7.5)
        if i // ncol == nrow - 1:
            ax.set_xlabel("confluence $\\varphi$", fontsize=7.5)
    for j in range(len(cts), nrow * ncol):
        axes[j // ncol][j % ncol].axis("off")
    h, l = axes[0][0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=3, frameon=False, fontsize=8)
    fig.tight_layout(rect=[0, 0.06, 1, 1])
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(a.out, f"atlas_comparison.{ext}"), dpi=200, bbox_inches="tight")
    plt.close(fig)

    print("\n" + "=" * 84)
    print(" PER-LINEAGE TRAJECTORIES  rho(phi, mean q)   [partial = controlling cell area]")
    cols = ["cell_type", "n_images"] + [c for s in sources for c in (f"rho_{s}", f"partial_{s}")]
    print(dft[cols].to_string(index=False))
    print("-" * 84)
    if not dfa.empty:
        print(" AGREEMENT WITH EXPERT BY CONFLUENCE  (bias in mean q; usable = images with >=1 cell)")
        print(dfa.to_string(index=False))
    print("-" * 84)
    if "rho_ours" in dft and "rho_expert" in dft:
        d = dft.dropna(subset=["rho_ours", "rho_expert"])
        if len(d) >= 3:
            r, p = stats.spearmanr(d["rho_expert"], d["rho_ours"])
            same = int((np.sign(d["rho_expert"]) == np.sign(d["rho_ours"])).sum())
            print(f" ours vs expert across lineages: rho = {r:+.2f} (p = {p:.3g}); "
                  f"direction agrees for {same}/{len(d)} lineages")
        if "rho_conncomp" in dft:
            d2 = dft.dropna(subset=["rho_conncomp", "rho_expert"])
            if len(d2) >= 3:
                r2, p2 = stats.spearmanr(d2["rho_expert"], d2["rho_conncomp"])
                same2 = int((np.sign(d2["rho_expert"]) == np.sign(d2["rho_conncomp"])).sum())
                print(f" conncomp vs expert            : rho = {r2:+.2f} (p = {p2:.3g}); "
                      f"direction agrees for {same2}/{len(d2)} lineages")
    print("=" * 84)
    print(f" csv + figure written to {a.out}/\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
