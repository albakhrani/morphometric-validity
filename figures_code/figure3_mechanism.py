#!/usr/bin/env python3
"""
Figure 3 - The instance-decoding mechanism, step by step
========================================================
The distance map and the boundary map ARE the contribution, and the reader
currently never sees one. Naylor et al. (2019) and HoVer-Net (Graham et al.,
2019) -- the two papers the manuscript cites as its antecedents -- both show
this progression. Omitting it invites the criticism the paper is most
exposed to: that this is two convolutions bolted on with nothing shown.

Produces a 6-panel row for ONE representative crowded field:

    phase contrast | predicted foreground | predicted distance map
    predicted boundary | watershed seeds over distance | recovered instances

and, optionally, a second row for a SPARSE field so the reader can see that
the mechanism behaves sensibly at both ends of the density range.

RUN THIS ON YOUR MACHINE -- it needs the trained checkpoint and the images.

Usage (single crowded field, matching the Fig. 3 micrograph):
    python figure3_mechanism.py ^
        --model runs\\instance\\best.pt ^
        --images data\\raw\\livecell_test_images ^
        --coco   data\\raw\\livecell\\livecell_coco_test.json ^
        --image  A172_Phase_C7_1_02d08h00m_3.tif ^
        --out    figures

Two rows (crowded + sparse), recommended:
    ... --image A172_Phase_C7_1_02d08h00m_3.tif ^
        --image2 <a sparse field, phi ~ 0.1> ^
        --out figures

Watershed parameters MUST match the detection-optimal operating point used
everywhere else in the paper. Pass them explicitly so the figure cannot
silently drift from the rest of the results:
    --seed-thr 0.45 --min-distance 6 --min-size 50
(adjust to whatever phase18 selected; the defaults below are placeholders
and the script prints them into the console so they end up in your log).
"""
from __future__ import annotations

import argparse
import os
import sys

import matplotlib
matplotlib.rcParams['pdf.fonttype'] = 42   # TrueType, not Type 3
matplotlib.rcParams['ps.fonttype'] = 42
import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
# Both directories, not just this one. main() imports build_instance_model
# from phase11_instance_model, which lives in the PROJECT ROOT one level up,
# so inserting only _HERE made this script impossible to run as documented --
# it needed a manually supplied PYTHONPATH. Matches figure4_micrographs.py.
for _p in (_HERE, os.path.abspath(os.path.join(_HERE, ".."))):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ---------------------------------------------------------------- utilities
def read_image(path):
    import imageio.v2 as iio
    a = iio.imread(path)
    return a[..., 0] if a.ndim == 3 else a


def percentile_norm(img, lo=1.0, hi=99.0):
    """MUST match the normalization used at training and inference."""
    a = img.astype(np.float32)
    p1, p99 = np.percentile(a, lo), np.percentile(a, hi)
    return np.clip((a - p1) / (p99 - p1 + 1e-6), 0, 1) if p99 > p1 else a * 0


def predict_maps(model, img, device, amp_dtype):
    import torch
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
    dist = torch.sigmoid(out["dist"][0, 0]).float().cpu().numpy()[:h, :w]
    bnd = torch.sigmoid(out["bnd"][0, 0]).float().cpu().numpy()[:h, :w]
    return fg, dist, bnd


def seeds_and_instances(fg, dist, bnd, fg_thr, seed_thr, min_distance,
                        bnd_thr, min_size):
    """Returns (seed coordinates, label image). Mirrors phase13 exactly."""
    from scipy import ndimage as ndi
    from skimage.feature import peak_local_max
    from skimage.measure import label as sklabel
    from skimage.segmentation import watershed

    mask = fg > fg_thr
    coords = peak_local_max(dist, min_distance=min_distance,
                            threshold_abs=seed_thr, labels=mask)
    if coords.shape[0] == 0:
        lab, _ = ndi.label(mask)
        return coords, lab
    markers = np.zeros(dist.shape, dtype=np.int32)
    for i, (r, c) in enumerate(coords, start=1):
        markers[r, c] = i
    lab = watershed(-dist, markers=markers, mask=mask)

    counts = np.bincount(lab.ravel())
    for i, n in enumerate(counts):
        if i != 0 and n < min_size:
            lab[lab == i] = 0
    return coords, sklabel(lab)


def count_breakdown(lab):
    """
    Report the instance count under each filtering rule the manuscript uses,
    so the run can be reconciled with the published number in one pass.

    Section 2.5 excludes, for morphological measurement:
      - objects smaller than 150 px
      - objects touching the image border
    but retains everything for the confluence calculation. A script that
    applies neither will therefore count MORE instances than the paper
    reports. This prints every combination so you can see which matches.
    """
    import numpy as _np

    # Count distinct instance labels. Re-labelling the binary union instead
    # would merge touching instances back together -- the very failure this
    # figure exists to illustrate -- and report a handful of blobs.
    def n_of(m):
        return int(_np.count_nonzero(_np.unique(m)))

    raw = lab.copy()
    sizes = _np.bincount(raw.ravel())

    border_ids = set(_np.unique(_np.concatenate([
        raw[0, :], raw[-1, :], raw[:, 0], raw[:, -1]]))) - {0}

    small150 = {i for i in range(1, len(sizes)) if sizes[i] < 150}
    small50 = {i for i in range(1, len(sizes)) if sizes[i] < 50}

    def drop(ids):
        m = raw.copy()
        if ids:
            m[_np.isin(m, list(ids))] = 0
        return n_of(m)

    rows = [
        ("no filtering (all watershed regions)", n_of(raw)),
        ("minus objects < 50 px",                drop(small50)),
        ("minus objects < 150 px",               drop(small150)),
        ("minus border-touching objects",        drop(border_ids)),
        ("minus < 150 px AND border-touching",   drop(small150 | border_ids)),
        ("minus < 50 px AND border-touching",    drop(small50 | border_ids)),
    ]
    print("\n  ---- instance count under each filtering rule ----")
    for name, n in rows:
        print(f"     {name:<40s} {n:5d}")
    print(f"     (border-touching objects present: {len(border_ids)})")
    return dict(rows)


def colour_labels(lab, seed=0):
    rng = np.random.default_rng(seed)
    n = int(lab.max())
    lut = np.vstack([[0, 0, 0], rng.random((max(n, 1), 3)) * 0.75 + 0.25])
    return lut[lab]


def gt_count(coco_path, fname):
    if not coco_path:
        return None
    from pycocotools.coco import COCO
    coco = COCO(coco_path)
    for iid in coco.getImgIds():
        if coco.loadImgs(iid)[0]["file_name"] == fname:
            return len(coco.getAnnIds(imgIds=iid))
    return None


# ------------------------------------------------------------------- figure
def render_row(axes, img, fg, dist, bnd, coords, lab, tag, n_gt, fg_thr,
               seed_size, row_index, n_rows):
    """
    Colour scheme is chosen for print, not for the screen:

      Every mask-like panel keeps a DARK background so that "cells" reads
      the same way across (b), (c), (d), (e) and (f). An earlier version
      inverted the foreground panel, which made the cell-free gaps look
      like the objects -- the opposite of the intended reading.

      binary foreground  gray     -- white cells on black, matching panel (f)
      distance map       magma    -- dark background makes the per-cell peaks
                                     pop (as in Naylor / HoVer-Net)
      boundary map       cividis  -- dark background, hue distinct from magma
    """
    letters = "abcdef"
    binary = (fg > fg_thr).astype(float)

    panels = [
        (img,    "gray",   None,   f"phase contrast{tag}"),
        (binary, "gray",   (0, 1), f"foreground (thresholded at {fg_thr:g})"),
        (dist,   "magma",  (0, 1), "predicted distance map"),
        # Kept deliberately. The boundary map is a real output of the trained
        # model and a reader is entitled to see it; what they should not
        # conclude is that the decoder uses it, so the title says so.
        (bnd,    "cividis",(0, 1), "predicted boundary map\n(auxiliary; not used in decoding)"),
        (dist,   "magma",  (0, 1), f"watershed seeds  (n = {len(coords)})"),
        (None,   None,     None,   f"recovered instances  (n = {int(lab.max())})"),
    ]

    for k, (ax, (arr, cmap, vlim, title)) in enumerate(zip(axes, panels)):
        if arr is None:
            ax.imshow(np.clip(colour_labels(lab), 0, 1), interpolation="nearest")
        elif vlim is None:
            ax.imshow(arr, cmap=cmap, interpolation="nearest")
        else:
            ax.imshow(arr, cmap=cmap, vmin=vlim[0], vmax=vlim[1],
                      interpolation="nearest")

        # seeds: large enough to actually see, dark-edged so they read
        # against the bright magma peaks underneath
        if "seeds" in title and len(coords):
            # open rings, not filled dots: at a few hundred seeds a filled
            # marker hides the very distance peak it is meant to sit on
            ax.scatter(coords[:, 1], coords[:, 0], s=seed_size,
                       facecolors="none", edgecolors="#00f5d0",
                       linewidths=0.55, zorder=3)

        if n_gt is not None and "recovered" in title:
            over = (int(lab.max()) - n_gt) / n_gt * 100.0
            title += f"\nexpert: {n_gt}   ({over:+.1f}%)"

        # 100 um scale bar, first panel only. LIVECell releases each
        # acquisition as four 704 x 520 crops covering 0.875 x 0.645 mm
        # (Edlund et al. 2021), so one pixel is 1.24 um. The measured
        # descriptors are dimensionless, but a reader cannot judge cell size
        # or the 150 px exclusion without this.
        if k == 0 and row_index == 0:
            import matplotlib.patheffects as _pe
            _ref = arr if arr is not None else lab
            _h, _w = _ref.shape[:2]
            _bar = 100.0 / (0.875e3 / 704.0)
            _x1 = _w * 0.96
            _x0 = _x1 - _bar
            _y = _h * 0.945
            _o = [_pe.withStroke(linewidth=1.8, foreground="black")]
            ax.plot([_x0, _x1], [_y, _y], "-", color="white", lw=2.0,
                    solid_capstyle="butt", zorder=5, path_effects=_o)
            ax.text((_x0 + _x1) / 2.0, _y - _h * 0.022, r"100 $\mu$m",
                    color="white", fontsize=7.0, ha="center", va="bottom",
                    zorder=5, path_effects=_o)

        ax.set_title(title, fontsize=8.0, pad=3)
        ax.set_xticks([]); ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_linewidth(0.5); sp.set_color("#999999")

        # panel letters, continuing across rows: a-f, then g-l
        idx = row_index * 6 + k
        lab_txt = letters[k] if n_rows == 1 else "abcdefghijkl"[idx]
        ax.text(0.022, 0.965, f"({lab_txt})", transform=ax.transAxes,
                fontsize=8.5, fontweight="bold", va="top", ha="left",
                color="white",
                path_effects=[__import__("matplotlib.patheffects",
                              fromlist=["x"]).withStroke(
                                  linewidth=1.8, foreground="black")])


def main():
    ap = argparse.ArgumentParser(description="Figure 3 - decoding mechanism")
    ap.add_argument("--model", required=True)
    ap.add_argument("--images", required=True)
    ap.add_argument("--coco", default=None)
    ap.add_argument("--image", required=True, help="crowded field filename")
    ap.add_argument("--image2", default=None, help="optional sparse field")
    ap.add_argument("--out", default="figures")
    ap.add_argument("--base-channels", type=int, default=32)
    ap.add_argument("--depth", type=int, default=4)
    # operating point -- MUST match the detection-optimal setting
    ap.add_argument("--fg-thr", type=float, default=0.5)
    ap.add_argument("--seed-thr", type=float, default=0.45)
    ap.add_argument("--min-distance", type=int, default=6)
    ap.add_argument("--bnd-thr", type=float, default=0.5)
    ap.add_argument("--min-size", type=int, default=50)
    ap.add_argument("--seed-size", type=float, default=11.0,
                    help="marker area for the seed overlay; raise if the "
                         "seeds are still hard to see at print size")
    ap.add_argument("--expect-instances", type=int, default=None,
                    help="instance count the manuscript reports for this "
                         "field; the script warns loudly if the run differs")
    a = ap.parse_args()

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import torch
    from phase11_instance_model import build_instance_model

    print("=" * 68)
    print(" OPERATING POINT USED FOR THIS FIGURE (must match Section 3.3)")
    print(f"   fg_thr={a.fg_thr}  seed_thr={a.seed_thr} "
          f"min_distance={a.min_distance}  min_size={a.min_size}")
    print("=" * 68)

    os.makedirs(a.out, exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    amp_dtype = torch.bfloat16 if device.type == "cuda" else torch.float32

    model = build_instance_model(base_channels=a.base_channels, depth=a.depth)
    ck = torch.load(a.model, map_location="cpu", weights_only=False)
    model.load_state_dict(ck.get("model_state_dict", ck))
    model.to(device).eval()

    targets = [(a.image, "  (crowded)")]
    if a.image2:
        targets.append((a.image2, "  (sparse)"))

    # 3 x 2 per field, not 1 x 6. A six-panel strip is 7:1, so LaTeX scales it
    # to about half size at \textwidth and every label lands near 3.7 pt --
    # below Elsevier's 6 pt artwork minimum. At 7 inches wide the figure is
    # reproduced at very nearly 1:1, so the type prints at the size set here.
    nrow = len(targets)
    fig, axs = plt.subplots(2 * nrow, 3, figsize=(7.165, 2.098 * 2 * nrow))
    axs = np.atleast_2d(axs)
    # render_row expects the six axes of one field in reading order
    rows = [np.concatenate([axs[2 * r], axs[2 * r + 1]]) for r in range(nrow)]

    for r, (fname, tag) in enumerate(targets):
        img = percentile_norm(read_image(os.path.join(a.images, fname)))
        fg, dist, bnd = predict_maps(model, img, device, amp_dtype)
        coords, lab = seeds_and_instances(fg, dist, bnd, a.fg_thr, a.seed_thr,
                                          a.min_distance, a.bnd_thr, a.min_size)
        n_gt = gt_count(a.coco, fname)
        render_row(rows[r], img, fg, dist, bnd, coords, lab, tag, n_gt,
                   a.fg_thr, a.seed_size, r, nrow)
        n_inst = int(lab.max())
        print(f"  {fname}: seeds={len(coords)}  instances={n_inst}"
              f"  expert={n_gt}")
        if n_gt:
            print(f"      over-count vs expert: {(n_inst-n_gt)/n_gt*100:+.1f}%")
        variants = count_breakdown(lab)
        if r == 0 and a.expect_instances is not None:
            hit = [k for k, v in variants.items() if v == a.expect_instances]
            if hit:
                print(f"\n  >>> the manuscript's {a.expect_instances} is "
                      f"reproduced by: {hit[0]}")
                print("      -> that is the rule the published number used; "
                      "match it here or\n"
                      "         state the rule explicitly in the caption.\n")
            if n_inst != a.expect_instances:
                print("\n  " + "!" * 62)
                print(f"  DRIFT: this run gives {n_inst} instances but the "
                      f"manuscript reports {a.expect_instances}.")
                print("  The watershed parameters here do NOT reproduce the "
                      "published number.")
                print("  Fix the parameters, or correct the manuscript --- "
                      "do not ship both.")
                print("  " + "!" * 62 + "\n")
            else:
                print(f"      MATCHES the manuscript ({a.expect_instances}) "
                      "-- parameters are consistent.\n")

    fig.subplots_adjust(left=0.004, right=0.996, top=0.90, bottom=0.01,
                        wspace=0.045, hspace=0.20)
    for ext in ("pdf", "png"):
        p = os.path.join(a.out, f"Fig3_mechanism.{ext}")
        fig.savefig(p, dpi=400, bbox_inches="tight", facecolor="white")
        print("  wrote", p)
    plt.close(fig)
    return 0


if __name__ == "__main__":
    sys.exit(main())
