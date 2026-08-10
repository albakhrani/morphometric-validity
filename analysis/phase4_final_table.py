#!/usr/bin/env python3
"""
Phase 4 - Final tiered lineage classification (manuscript Table 1)
==================================================================
Consolidates every control into ONE defensible per-lineage table with explicit
evidence tiers. This is the table the paper is written around.

Two refinements over phase3:
  1. MIN-AREA FILTER. Cells below --min-area px are dominated by pixel
     discretisation (a 100 px mask cannot resolve real concavity), which is
     precisely where the size artifact lives. Excluding them is principled and
     stated in Methods. Default 150 px; --min-area 0 disables.
  2. CLASSIFICATION FROM THE AREA-CONTROLLED RESPONSE, not the raw one, so a
     lineage whose apparent response is explained by cell size cannot be
     labelled a responder.

Density axis = AREA FRACTION phi (confluence) from the COCO annotations, which
phase3 showed gives identical classification to cells-per-image (8/8 stable).

EVIDENCE TIERS (all inputs printed so you can audit the call):
  A - robust      : sign of partial rho matches raw, |partial rho| >= 0.25,
                    and >= 3/4 cell-size bands agree in sign
  B - supported   : sign holds under the area control but the effect is modest
                    or size bands are split
  C - not supported: sign flips under the area control (size-driven) or the
                    response is negligible (|partial rho| < 0.10)

DIRECTION (morphology only - no mechanical claim is made):
  condensing : q falls as confluence rises (cells become more regular)
  spreading  : q rises as confluence rises (cells become more irregular)
  inert      : no appreciable response

Outputs (--out):
    final_lineage_table.csv     Table 1 (tier, direction, all statistics)
    final_phi_ranges.csv        confluence range reached by each lineage
    final_table1.png            publication-style summary figure

Usage
    python phase4_final_table.py \
        --csv  phase1_out/atlas_features_percell.csv \
        --coco "D:/paper1_mechanobiology - Copy (2)/data/raw/livecell/livecell_coco_test.json" \
        --out  final_table_out
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:
    from scipy import stats as sps
except Exception:  # pragma: no cover
    print("ERROR: scipy is required.")
    sys.exit(1)

T, IMG, AREA = "cell_type", "image_id", "cell_area"
DEFAULT_MIN_AREA = 150
DEFAULT_MIN_HOURS = 8.0        # exclude the post-plating attachment phase
TIME_RE = re.compile(r"(\d+)d(\d+)h(\d+)m", re.I)
N_BANDS = 4
MIN_IMAGES = 6
MIN_CELLS_BAND = 150

TIER_A_RHO = 0.25
TIER_C_RHO = 0.10

PAL = {"MCF7": "#0B4F6C", "SkBr3": "#1B7FA5", "SK-OV-3": "#4FA3C7", "BT474": "#7FC3DE",
       "Huh7": "#227C70", "A172": "#D98324", "BV2": "#E0A458", "SH-SY5Y": "#B0662B"}

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("phase4")


# --------------------------------------------------------------------------
def partial_spearman(x, y, z):
    """Rank-based partial correlation of x,y controlling z. Returns (rho, p, n)."""
    d = pd.DataFrame({"x": x, "y": y, "z": z}).replace([np.inf, -np.inf], np.nan).dropna()
    n = len(d)
    if n < 6:
        return math.nan, math.nan, n
    rx, ry, rz = (sps.rankdata(d[c].to_numpy()) for c in ("x", "y", "z"))

    def resid(a, b):
        if np.ptp(b) == 0:
            return a - a.mean()
        s, i = np.polyfit(b, a, 1)
        return a - (s * b + i)

    ex, ey = resid(rx, rz), resid(ry, rz)
    if np.std(ex) == 0 or np.std(ey) == 0:
        return math.nan, math.nan, n
    rho = float(np.clip(np.corrcoef(ex, ey)[0, 1], -0.999999, 0.999999))
    dof = n - 3
    if dof <= 0:
        return rho, math.nan, n
    t = rho * math.sqrt(dof / (1 - rho * rho))
    return rho, float(2 * sps.t.sf(abs(t), dof)), n


def spearman(x, y, min_n=MIN_IMAGES):
    d = pd.DataFrame({"x": x, "y": y}).replace([np.inf, -np.inf], np.nan).dropna()
    if len(d) < min_n:
        return math.nan, math.nan, len(d)
    r, p = sps.spearmanr(d["x"], d["y"])
    return float(r), float(p), len(d)


def parse_hours(file_name):
    """'A172_Phase_C7_1_00d04h00m_1.tif' -> 4.0 hours since plating."""
    m = TIME_RE.search(os.path.basename(file_name or ""))
    if not m:
        return math.nan
    d, h, mi = (int(g) for g in m.groups())
    return d * 24.0 + h + mi / 60.0


def phi_from_coco_multi(paths):
    """Merge phi/hours maps across several COCO files.

    The three LIVECell splits use disjoint image-id namespaces (verified: zero
    overlap between train, val and test), so the maps can be merged by id
    without collision. Asserted here rather than assumed.
    """
    phi, hrs = {}, {}
    for p in paths:
        f, h = phi_from_coco(p)
        clash = set(f) & set(phi)
        if clash:
            raise SystemExit(f"image-id collision between COCO files: "
                             f"{len(clash)} ids, e.g. {sorted(clash)[:5]}")
        phi.update(f)
        hrs.update(h)
    log.info("merged %d COCO file(s): %d images with confluence", len(paths), len(phi))
    return phi, hrs


def phi_from_coco(path):
    """Unbiased confluence per image from all COCO annotations, plus hours."""
    if not os.path.isfile(path):
        log.error("COCO json not found: %s", path)
        sys.exit(2)
    try:
        from pycocotools.coco import COCO
        coco = COCO(path)
        px, hrs = {}, {}
        for i in coco.getImgIds():
            info = coco.loadImgs(i)[0]
            px[i] = float(info["height"] * info["width"])
            hrs[i] = parse_hours(info.get("file_name", ""))
        tot = {}
        for ann in coco.loadAnns(coco.getAnnIds()):
            tot[ann["image_id"]] = tot.get(ann["image_id"], 0.0) + float(ann.get("area", 0.0))
    except Exception as exc:
        log.info("pycocotools unavailable (%s); parsing json", exc)
        data = json.load(open(path))
        px = {im["id"]: float(im["height"] * im["width"]) for im in data.get("images", [])}
        hrs = {im["id"]: parse_hours(im.get("file_name", "")) for im in data.get("images", [])}
        tot = {}
        for ann in data.get("annotations", []):
            tot[ann["image_id"]] = tot.get(ann["image_id"], 0.0) + float(ann.get("area", 0.0))
    phi = {i: tot.get(i, 0.0) / a for i, a in px.items() if a > 0}
    return phi, hrs


# --------------------------------------------------------------------------
def analyse(df, phi_map, hours_map, min_area, min_hours):
    n_before = len(df)
    if min_area > 0:
        df = df[df[AREA] >= min_area].copy()
    log.info("Min-area filter %d px: kept %d / %d cells (%.1f%% dropped)",
             min_area, len(df), n_before, 100 * (1 - len(df) / max(n_before, 1)))

    df["phi"] = df[IMG].map(phi_map)
    df["hours"] = df[IMG].map(hours_map)
    df = df.dropna(subset=["phi", "q", AREA])

    if min_hours and min_hours > 0:
        n_img_before = df[IMG].nunique()
        known = df["hours"].notna()
        df = df[(~known) | (df["hours"] >= min_hours)]
        log.info("Min-hours filter %.1f h (attachment phase excluded): kept %d / %d images",
                 min_hours, df[IMG].nunique(), n_img_before)

    img = (df.groupby(IMG)
             .agg(cell_type=(T, "first"), phi=("phi", "first"),
                  mean_q=("q", "mean"), mean_area=(AREA, "mean"), n=("q", "size"))
             .reset_index())

    rows, phi_rows = [], []
    for ct, g in img.groupby("cell_type"):
        if len(g) < MIN_IMAGES:
            continue
        raw, p_raw, n_img = spearman(g["phi"], g["mean_q"])
        par, p_par, _ = partial_spearman(g["phi"], g["mean_q"], g["mean_area"])

        cells = df[df[T] == ct]
        try:
            cells = cells.assign(band=pd.qcut(cells[AREA], N_BANDS, labels=False, duplicates="drop"))
        except Exception:
            cells = cells.assign(band=pd.cut(cells[AREA], N_BANDS, labels=False))
        signs, band_rhos = [], []
        for b, gb in cells.groupby("band", observed=True):
            if len(gb) < MIN_CELLS_BAND:
                continue
            r, _, _ = spearman(gb["phi"], gb["q"], min_n=MIN_CELLS_BAND)
            if np.isfinite(r):
                band_rhos.append(r)
                signs.append(1 if r > 0 else -1)
        n_bands = len(signs)
        agree = max(signs.count(1), signs.count(-1)) if n_bands else 0
        band_frac = agree / n_bands if n_bands else math.nan
        band_major = (1 if signs.count(1) >= signs.count(-1) else -1) if n_bands else 0

        sign_ok = (np.isfinite(raw) and np.isfinite(par) and np.sign(raw) == np.sign(par))
        if not sign_ok or (np.isfinite(par) and abs(par) < TIER_C_RHO):
            tier = "C"
        elif abs(par) >= TIER_A_RHO and np.isfinite(band_frac) and band_frac >= 0.75 \
                and band_major == np.sign(par):
            tier = "A"
        else:
            tier = "B"

        if tier == "C":
            direction = "not supported"
        elif par < 0:
            direction = "condensing"
        elif par > 0:
            direction = "spreading"
        else:
            direction = "inert"

        rows.append(dict(cell_type=ct, n_images=n_img, n_cells=len(cells),
                         raw_rho=raw, raw_p=p_raw, partial_rho=par, partial_p=p_par,
                         retained=(abs(par) / abs(raw)) if raw else math.nan,
                         n_bands=n_bands, bands_agree=f"{agree}/{n_bands}" if n_bands else "-",
                         band_rhos="; ".join(f"{r:+.2f}" for r in band_rhos),
                         tier=tier, direction=direction))
        phi_rows.append(dict(cell_type=ct, phi_min=float(g["phi"].min()),
                             phi_median=float(g["phi"].median()),
                             phi_max=float(g["phi"].max())))

    order = {"A": 0, "B": 1, "C": 2}
    res = pd.DataFrame(rows).sort_values(
        ["tier", "partial_rho"], key=lambda s: s.map(order) if s.name == "tier" else s
    ).reset_index(drop=True)
    return res, pd.DataFrame(phi_rows), df


# --------------------------------------------------------------------------
def report(res, phis, min_area):  # noqa: D401
    print("\n" + "=" * 104)
    print(f" TABLE 1 - MORPHOLOGICAL TRAJECTORIES BY LINEAGE  (min cell area {min_area} px;"
          f" post-attachment only; density = confluence phi)")
    print("=" * 104)
    print(f" {'lineage':9s} {'tier':4s} {'direction':14s} {'raw':>7s} {'partial':>8s} "
          f"{'kept':>6s} {'p(part)':>9s} {'bands':>6s} {'per-band rho':26s} {'imgs':>5s}")
    for _, r in res.iterrows():
        kept = f"{r['retained']*100:4.0f}%" if np.isfinite(r["retained"]) else "   -"
        print(f" {r['cell_type']:9s} {r['tier']:^4s} {r['direction']:14s} "
              f"{r['raw_rho']:+7.2f} {r['partial_rho']:+8.2f} {kept:>6s} "
              f"{r['partial_p']:9.1e} {r['bands_agree']:>6s} {r['band_rhos']:26s} "
              f"{int(r['n_images']):5d}")
    print("=" * 104)
    nA = (res["tier"] == "A").sum(); nB = (res["tier"] == "B").sum(); nC = (res["tier"] == "C").sum()
    print(f" Tier A (robust): {nA}   Tier B (supported): {nB}   Tier C (not supported): {nC}")
    for d in ("condensing", "spreading"):
        sub = res[(res["direction"] == d) & (res["tier"].isin(["A", "B"]))]
        if len(sub):
            print(f"   {d:11s}: {', '.join(sub['cell_type'])}")
    sub = res[res["tier"] == "C"]
    if len(sub):
        print(f"   size-driven / absent: {', '.join(sub['cell_type'])}")

    print("\n" + "-" * 104)
    print(" CONFLUENCE RANGE REACHED (phi = fraction of field covered by cells)")
    print(f" {'lineage':9s} {'min':>7s} {'median':>8s} {'max':>7s}   note")
    for _, r in phis.sort_values("phi_max", ascending=False).iterrows():
        note = "approaches confluence" if r["phi_max"] > 0.75 else \
               "sub-confluent throughout" if r["phi_max"] < 0.5 else "partially confluent"
        print(f" {r['cell_type']:9s} {r['phi_min']:7.3f} {r['phi_median']:8.3f} "
              f"{r['phi_max']:7.3f}   {note}")
    print("\n NOTE: where phi stays well below 1, the cultures are sub-confluent. Jamming theory")
    print(" is defined for confluent tissue, so describe these as crowding-associated")
    print(" MORPHOLOGY, not mechanical state. State this in the limitations.")
    print("=" * 104 + "\n")


def figure(res, out):
    fig, ax = plt.subplots(figsize=(9.0, 5.2), dpi=130)
    res2 = res.sort_values("partial_rho")
    y = np.arange(len(res2))
    hatch = {"A": "", "B": "//", "C": "xx"}
    for i, (_, r) in enumerate(res2.iterrows()):
        ax.barh(i, r["partial_rho"], color=PAL.get(r["cell_type"], "#666"),
                edgecolor="k", hatch=hatch.get(r["tier"], ""), alpha=0.9)
        ax.plot(r["raw_rho"], i, "o", color="grey", ms=6, zorder=3)
    ax.axvline(0, color="k", lw=1.2)
    ax.set_yticks(y); ax.set_yticklabels(
        [f"{r['cell_type']}  [{r['tier']}]" for _, r in res2.iterrows()])
    ax.set_xlabel("shape-index response to confluence (partial rho, cell area controlled)")
    ax.set_title("Crowding-response phenotypes by lineage\n"
                 "bars = area-controlled response; grey dots = uncontrolled; "
                 "hatch: // supported, xx not supported",
                 fontweight="bold", fontsize=11)
    ax.text(0.01, 0.02, "left = condensing (q falls)      right = spreading (q rises)",
            transform=ax.transAxes, fontsize=9, style="italic")
    ax.grid(alpha=0.2, axis="x")
    fig.tight_layout()
    fig.savefig(os.path.join(out, "final_table1.png"), bbox_inches="tight")
    plt.close(fig)
    log.info("Saved %s", os.path.join(out, "final_table1.png"))


def main():
    ap = argparse.ArgumentParser(description="Final tiered lineage table")
    ap.add_argument("--csv", required=True)
    ap.add_argument("--coco", nargs="+", required=True,
                    help="one or more COCO json files; ids must not collide")
    ap.add_argument("--out", default="final_table_out")
    ap.add_argument("--min-hours", type=float, default=DEFAULT_MIN_HOURS,
                    help=f"exclude images before this many hours post-plating "
                         f"(default {DEFAULT_MIN_HOURS}; 0=off)")
    ap.add_argument("--min-area", type=int, default=DEFAULT_MIN_AREA,
                    help=f"exclude cells below this pixel area (default {DEFAULT_MIN_AREA}; 0=off)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    if not os.path.isfile(a.csv):
        log.error("CSV not found: %s", a.csv); return 2
    df = pd.read_csv(a.csv).replace([np.inf, -np.inf], np.nan)
    if "q" not in df.columns and "cell_perimeter" in df.columns:
        df["q"] = np.where(df[AREA] > 0, df["cell_perimeter"] / np.sqrt(df[AREA]), np.nan)
    for c in (T, IMG, AREA, "q"):
        if c not in df.columns:
            log.error("missing column %s", c); return 3

    phi_map, hours_map = phi_from_coco_multi(
        a.coco if isinstance(a.coco, list) else [a.coco])
    res, phis, _ = analyse(df, phi_map, hours_map, a.min_area, a.min_hours)
    if res.empty:
        log.error("no lineages with sufficient data"); return 3

    res.to_csv(os.path.join(a.out, "final_lineage_table.csv"), index=False)
    phis.to_csv(os.path.join(a.out, "final_phi_ranges.csv"), index=False)
    report(res, phis, a.min_area)
    figure(res, a.out)
    print(f" Files written to {a.out}. Send me final_lineage_table.csv + final_table1.png"
          f" and we start drafting.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
