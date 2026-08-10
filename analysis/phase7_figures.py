#!/usr/bin/env python3
"""
Phase 7 - Publication figure set
================================
Generates the Results figures for Paper 2 from files already produced by the
analysis pipeline. Nothing is recomputed except light binning, so the figures
cannot drift from the reported statistics.

Figures (each written as PDF for the journal and PNG for drafts):

  Fig 1  Workflow                 conceptual overview of measurement + controls
  Fig 2  Morphological atlas      A trajectories, B effect forest, C confluence range
  Fig 3  Control cascade          A raw->controlled slopegraph, B size strata,
                                  C within-timepoint vs overall      [KEY METHODS FIGURE]
  Fig 4  Operating envelope       A fidelity vs confluence, B scientific recovery

Inputs (auto-detected; a figure is skipped if its inputs are absent)
    final_table_out/final_lineage_table.csv
    final_table_out/final_phi_ranges.csv
    time_out/time_per_image.csv
    time_out/time_control_summary.csv
    control_out/control_size_stratified.csv
    envelope_out/envelope_by_confluence.csv
    envelope_out/envelope_recovery.csv

Style follows Elsevier practice: sans-serif, 7 pt base, column widths of
90 / 140 / 190 mm, 600 dpi raster, and TrueType fonts so text stays editable in
Illustrator or Inkscape.

Usage
    python phase7_figures.py --root . --out figures
    python phase7_figures.py --root . --out figures --demote BV2 MCF7
"""
from __future__ import annotations

import argparse
import logging
import math
import os
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib.lines import Line2D

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("figures")

# ---------------------------------------------------------------- style ----
MM = 1 / 25.4
# W2 is the full-measure width and is no longer an Elsevier column: it is
# whatever figsize makes bbox_inches="tight" emit artwork exactly
# \textwidth wide for the target class, so LaTeX places at scale 1.0. The
# value below is converged for OUP contemporary/large (\textwidth 526.38pt);
# for the Elsevier CAS fallback it was 190. W1 and W15 are untouched -- they
# feed Fig1_workflow and Fig_bias_recovery, neither of which this paper uses.
W1, W15, W2 = 90 * MM, 140 * MM, 224.768 * MM

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
    "font.size": 7,
    "axes.labelsize": 7.5,
    "axes.titlesize": 8,
    "xtick.labelsize": 7.05,
    "ytick.labelsize": 7.05,
    "legend.fontsize": 7.05,
    "axes.linewidth": 0.6,
    "xtick.major.width": 0.6,
    "ytick.major.width": 0.6,
    "xtick.major.size": 2.5,
    "ytick.major.size": 2.5,
    "lines.linewidth": 1.0,
    "savefig.dpi": 600,
    "figure.dpi": 140,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "legend.frameon": False,
})

# Colour encodes the finding: condensing (blues), spreading (reds), null (grey).
C_COND = ["#08306B", "#2171B5", "#6BAED6", "#9ECAE1"]
C_SPRD = ["#67000D", "#CB181D", "#FB6A4A", "#FCAE91"]
C_NULL = "#9E9E9E"
INK = "#222222"

PANEL = dict(fontsize=9, fontweight="bold", va="top", ha="left")


def panel_label(ax, s, x=-0.16, y=1.10):
    ax.text(x, y, s, transform=ax.transAxes, **PANEL)


def savefig(fig, out, name):
    for ext in ("pdf", "png"):
        p = os.path.join(out, f"{name}.{ext}")
        fig.savefig(p, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    log.info("wrote %s.pdf / .png", name)


# ----------------------------------------------------------------- data ----
def find(root, *rel):
    for r in rel:
        p = os.path.join(root, r)
        if os.path.isfile(p):
            return p
    return None


def assert_tiers_consistent(root, loaded_path, table):
    """Refuse to draw tier letters that any other copy on disk contradicts.

    The figure asset is the one place a stale number cannot be caught by
    grepping the manuscript, so the guard belongs here, at the point the
    letters are read, rather than downstream.
    """
    import glob

    want = dict(zip(table["cell_type"], table["tier"]))
    bad = []
    for p in glob.glob(os.path.join(root, "**", "final_lineage_table.csv"),
                       recursive=True):
        if os.path.samefile(p, loaded_path):
            continue
        try:
            other = pd.read_csv(p)
        except Exception:
            continue
        got = dict(zip(other["cell_type"], other["tier"]))
        diff = {k: (want.get(k), got.get(k)) for k in want
                if k in got and want[k] != got[k]}
        if diff:
            bad.append((os.path.relpath(p, root), diff))

    if bad:
        log.error("TIER CONFLICT -- refusing to draw the atlas.")
        log.error("  loaded: %s", os.path.relpath(loaded_path, root))
        for p, diff in bad:
            for ct, (mine, theirs) in sorted(diff.items()):
                log.error("    %-9s loaded=%s  but %s says %s",
                          ct, mine, p, theirs)
        log.error("  Delete or refresh the stale copy, then rerun.")
        raise SystemExit(2)
    log.info("tier letters agree across all %d copies on disk", len(bad) + 1)


def load_all(root):
    d = {}
    spec = {
        # final_table_all/ FIRST, and this order is load-bearing.
        #
        # final_table_out/final_lineage_table.csv is a stale artefact from
        # 2026-07-23 that predates the evidence-tier correction: it still
        # carries BT474=B and A172=A. Because it was listed first, Figure 6
        # printed those letters in panel B while Table 5 and the Discussion
        # printed the corrected A and B -- the figure contradicted the
        # sentence "BT-474 is a Tier A lineage ... not a marginal trajectory
        # being lost" five pages later. Nothing in the build could see it,
        # because the wrong letters lived in a figure asset and not in .tex.
        #
        # assert_tiers_consistent() below now refuses to proceed if any copy
        # on disk disagrees with the one loaded, so re-ordering alone is not
        # what protects this.
        "table":    ("final_table_all/final_lineage_table.csv",
                     "fig7_expanded/final_table_out/final_lineage_table.csv",
                     "final_table_out/final_lineage_table.csv",
                     "final_lineage_table.csv"),
        "phi":      ("final_table_all/final_phi_ranges.csv",
                     "final_table_out/final_phi_ranges.csv",
                     "final_phi_ranges.csv"),
        "per_img":  ("time_out/time_per_image.csv", "time_per_image.csv"),
        "time":     ("time_out/time_control_summary.csv", "time_control_summary.csv"),
        "bands":    ("control_out/control_size_stratified.csv", "control_size_stratified.csv"),
        "env":      ("envelope_out/envelope_by_confluence.csv", "envelope_by_confluence.csv"),
        "recov":    ("envelope_out/envelope_recovery.csv", "envelope_recovery.csv"),
    }
    for key, paths in spec.items():
        p = find(root, *paths)
        if p:
            try:
                d[key] = pd.read_csv(p)
                log.info("loaded %-8s %s (%d rows)", key, os.path.relpath(p, root), len(d[key]))
                if key == "table":
                    assert_tiers_consistent(root, p, d[key])
            except Exception as exc:
                log.warning("could not read %s: %s", p, exc)
        else:
            log.warning("missing %-8s (looked for %s)", key, paths[0])
    return d


def build_palette(table, demote):
    """Assign a colour per lineage from its direction, strongest effect darkest."""
    t = table.copy()
    t["direction"] = t["direction"].astype(str)
    if demote:
        t.loc[t["cell_type"].isin(demote), "direction"] = "not supported"
        t.loc[t["cell_type"].isin(demote), "tier"] = "C"

    pal, order = {}, []
    cond = t[t["direction"] == "condensing"].sort_values("partial_rho")
    sprd = t[t["direction"] == "spreading"].sort_values("partial_rho", ascending=False)
    null = t[~t["cell_type"].isin(list(cond["cell_type"]) + list(sprd["cell_type"]))]
    for i, ct in enumerate(cond["cell_type"]):
        pal[ct] = C_COND[min(i, len(C_COND) - 1)]
    for i, ct in enumerate(sprd["cell_type"]):
        pal[ct] = C_SPRD[min(i, len(C_SPRD) - 1)]
    for ct in null["cell_type"]:
        pal[ct] = C_NULL
    order = list(cond["cell_type"]) + list(null["cell_type"]) + list(sprd["cell_type"])
    return pal, order, t


# ------------------------------------------------------------- figure 1 ----
def fig1_workflow(out):
    fig, ax = plt.subplots(figsize=(W2, 62 * MM))
    ax.set_xlim(0, 100); ax.set_ylim(0, 44); ax.axis("off")

    def box(x, y, w, h, text, fc="#FFFFFF", ec=INK, bold=False, fs=6.8):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.6,rounding_size=1.2",
                                    linewidth=0.7, facecolor=fc, edgecolor=ec))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs,
                fontweight=("bold" if bold else "normal"), color=INK, linespacing=1.35)

    def arrow(x1, y1, x2, y2):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=7,
                                     linewidth=0.7, color="#555555", shrinkA=1, shrinkB=1))

    # row 1: measurement
    box(1, 30, 17, 10, "LIVECell\n8 lineages\n1,564 images", fc="#EEF3F8", bold=True)
    box(22, 30, 17, 10, "Ground-truth\ninstance masks\n400,741 cells", fc="#EEF3F8")
    box(43, 30, 17, 10, "Geometry\narea, perimeter,\ncentroid", fc="#EEF3F8")
    box(64, 30, 17, 10, "Descriptors\nq = P/\u221aA,\nsolidity, extent,\neccentricity", fc="#EEF3F8")
    box(85, 30, 14, 10, "Confluence\n\u03c6 per image", fc="#EEF3F8")
    for x in (18, 39, 60, 81):
        arrow(x, 35, x + 4, 35)

    # row 2: controls
    ax.text(2, 26.4, "artifact controls", ha="left", fontsize=7.2,
            fontweight="bold", color="#B2182B")
    ctrl = [("1  density\ndefinition", 2), ("2  cell size\npartial + strata", 26),
            ("3  time since\nplating", 50), ("4  model vs\nground truth", 74)]
    for text, x in ctrl:
        box(x, 13, 22, 9, text, fc="#FDF0EE", ec="#B2182B")
    for x in (13, 37, 61, 85):
        arrow(x, 29.4, x, 22.6)

    # row 3: outputs
    box(6, 1, 26, 8, "Evidence-tiered\nlineage trajectories", fc="#F2F2F2", bold=True)
    box(37, 1, 26, 8, "Operating envelope\nfor model morphometry", fc="#F2F2F2", bold=True)
    box(68, 1, 26, 8, "Rejected results\n(size- or model-driven)", fc="#F2F2F2", bold=True)
    for x in (19, 50, 81):
        arrow(x, 12.4, x, 9.6)

    savefig(fig, out, "Fig1_workflow")


# ------------------------------------------------------------- figure 2 ----
def fig2_atlas(d, pal, order, table, out, min_hours=8.0):
    per_img, phi = d.get("per_img"), d.get("phi")
    fig = plt.figure(figsize=(W2, 78.077 * MM))
    gs = fig.add_gridspec(1, 3, width_ratios=[1.25, 1.0, 0.85], wspace=0.42)
    axA, axB, axC = (fig.add_subplot(gs[0, i]) for i in range(3))

    # --- A: trajectories -------------------------------------------------
    mono_report, end_labels = [], []
    if per_img is not None and {"phi", "mean_q", "cell_type"} <= set(per_img.columns):
        has_time = "hours" in per_img.columns
        for ct in order:
            g_all = per_img[per_img["cell_type"] == ct].dropna(subset=["phi", "mean_q"])
            if len(g_all) < 12:
                continue
            c = pal.get(ct, C_NULL)
            solid = pal.get(ct, C_NULL) != C_NULL

            def binned(gg, nb=6):
                if len(gg) < nb * 2:
                    return None
                try:
                    gg = gg.assign(b=pd.qcut(gg["phi"], nb, labels=False, duplicates="drop"))
                except Exception:
                    gg = gg.assign(b=pd.cut(gg["phi"], nb, labels=False))
                return (gg.groupby("b").agg(phi=("phi", "median"), m=("mean_q", "mean"),
                                            s=("mean_q", "sem")).reset_index())

            # faint full trajectory, including the excluded attachment phase
            if has_time and min_hours and min_hours > 0:
                full = binned(g_all)
                if full is not None:
                    axA.plot(full["phi"], full["m"], "-", color=c, lw=0.7,
                             alpha=0.30, zorder=1)
                g = g_all[g_all["hours"] >= min_hours]
            else:
                g = g_all

            agg = binned(g)
            if agg is None:
                continue

            # monotonicity of the analysed window
            dm = np.diff(agg["m"].to_numpy())
            if len(dm):
                frac_same = max((dm > 0).mean(), (dm < 0).mean())
                mono_report.append((ct, frac_same, len(dm) + 1))
            axA.plot(agg["phi"], agg["m"], "-o", color=c, ms=2.6, lw=1.3,
                     ls=("-" if solid else "--"), alpha=(1.0 if solid else 0.75), zorder=2)
            axA.fill_between(agg["phi"], agg["m"] - agg["s"], agg["m"] + agg["s"],
                             color=c, alpha=0.16, linewidth=0)
            # direct label at the end of each trajectory - cleaner than a
            # legend, but the endpoints crowd, so collect now and de-collide
            # once all eight are known (see below).
            end_labels.append((float(agg["phi"].iloc[-1]),
                               float(agg["m"].iloc[-1]), ct, c, solid))
        axA.set_xlabel("confluence  $\\varphi$")
        axA.set_ylabel("mean shape index  $q = P/\\sqrt{A}$")
        xmax = axA.get_xlim()[1]
        axA.set_xlim(right=xmax * 1.30)          # room for the labels
        axA.grid(alpha=0.14, linewidth=0.5)
        if has_time and min_hours and min_hours > 0:
            axA.plot([], [], "-", color="#777777", lw=0.7, alpha=0.5,
                     label=f"incl. attachment (< {min_hours:g} h)")
            axA.plot([], [], "-", color="#777777", lw=1.3, label="analysed window")
            # upper left, not lower right: the lower right is where the
            # trajectory labels live and BV2 used to print on top of it.
            axA.legend(loc="upper left", borderpad=0.2, handlelength=1.6,
                       labelspacing=0.25, fontsize=7.05, framealpha=0.85)

        # De-collide the endpoint labels. Several lineages converge to nearly
        # the same mean shape index, so the raw endpoints overlapped (A172 over
        # SK-OV-3, Huh7 over BT474). Push them apart by a minimum gap and draw
        # a hairline leader wherever a label had to move.
        if end_labels:
            ylo, yhi = axA.get_ylim()
            xlo, xhi = axA.get_xlim()
            span = yhi - ylo
            gap = span * 0.058
            end_labels.sort(key=lambda t: t[1])
            ys = [t[1] for t in end_labels]
            for i in range(1, len(ys)):
                if ys[i] - ys[i - 1] < gap:
                    ys[i] = ys[i - 1] + gap
            overflow = ys[-1] - (yhi - span * 0.02)
            if overflow > 0:
                ys = [y - overflow for y in ys]
            dx = (xhi - xlo) * 0.022
            for (x, y0, ct, c, solid), ynew in zip(end_labels, ys):
                axA.annotate(ct, xy=(x, y0), xytext=(x + dx, ynew),
                             textcoords="data", fontsize=7.05, color=c,
                             va="center", ha="left",
                             fontweight=("bold" if solid else "normal"),
                             arrowprops=dict(arrowstyle="-", color=c,
                                             linewidth=0.45, alpha=0.65,
                                             shrinkA=0.5, shrinkB=1.5)
                             if abs(ynew - y0) > span * 0.012 else None)

    if mono_report:
        print("\n  monotonicity of the analysed window (fraction of steps in one direction):")
        for ct, f, nb in sorted(mono_report, key=lambda x: x[1]):
            flag = "  <-- NON-MONOTONIC" if f < 0.8 else ""
            print(f"    {ct:9s} {f*100:5.0f}%  ({nb} bins){flag}")
        print("    Spearman rho assumes monotonicity; report the descending limb")
        print("    separately for any lineage flagged above.")
    panel_label(axA, "A")

    # --- B: effect forest ------------------------------------------------
    t = table.sort_values("partial_rho")
    y = np.arange(len(t))
    for i, (_, r) in enumerate(t.iterrows()):
        c = pal.get(r["cell_type"], C_NULL)
        axB.plot([r["raw_rho"], r["partial_rho"]], [i, i], "-", color=c, lw=0.8, alpha=0.45)
        axB.plot(r["raw_rho"], i, "o", mfc="white", mec=c, ms=3.2, mew=0.8)
        axB.plot(r["partial_rho"], i, "o", color=c, ms=4.6)
    axB.axvline(0, color=INK, lw=0.7)
    axB.set_yticks(y)
    axB.set_yticklabels([f"{r['cell_type']}  ({r['tier']})" for _, r in t.iterrows()])
    axB.set_xlabel("response to confluence  ($\\rho$)")
    axB.set_xlim(-1.0, 1.0)
    axB.grid(alpha=0.14, axis="x", linewidth=0.5)
    axB.text(-0.92, len(t) - 0.35, "condensing", fontsize=7.05, color=C_COND[0], style="italic")
    axB.text(0.92, len(t) - 0.35, "spreading", fontsize=7.05, color=C_SPRD[1],
             style="italic", ha="right")
    axB.legend(handles=[Line2D([], [], marker="o", ls="", mfc="white", mec=INK,
                               ms=3.2, mew=0.8, label="uncontrolled"),
                        Line2D([], [], marker="o", ls="", color=INK, ms=4.6,
                               label="cell-area controlled")],
               loc="lower right", handletextpad=0.3, borderpad=0.2)
    panel_label(axB, "B", x=-0.42)

    # --- C: confluence range ---------------------------------------------
    if phi is not None:
        p = phi.set_index("cell_type").reindex([r["cell_type"] for _, r in t.iterrows()])
        for i, (ct, r) in enumerate(p.iterrows()):
            c = pal.get(ct, C_NULL)
            axC.plot([r["phi_min"], r["phi_max"]], [i, i], "-", color=c, lw=2.4,
                     solid_capstyle="round", alpha=0.85)
            axC.plot(r["phi_median"], i, "|", color="white", ms=5, mew=1.1)
        axC.axvline(1.0, color="#B2182B", lw=0.8, ls="--")
        # Below the lowest bar and left of the line: at the top right this
        # label printed on top of the SkBr3 bar.
        axC.set_ylim(-1.45, len(p) - 0.45)
        axC.text(0.97, -0.85, "$\\varphi=1$\ncell overlap", fontsize=7.05,
                 color="#B2182B", va="center", ha="right", linespacing=1.25)
        axC.set_yticks(range(len(p)))
        axC.set_yticklabels(list(p.index), fontsize=7.05)
        axC.set_xlabel("confluence range  $\\varphi$")
        axC.grid(alpha=0.14, axis="x", linewidth=0.5)
    panel_label(axC, "C", x=-0.38)

    savefig(fig, out, "Fig2_atlas")


# ------------------------------------------------------------- figure 3 ----
def fig3_controls(d, pal, order, table, out):
    time, bands = d.get("time"), d.get("bands")
    fig = plt.figure(figsize=(W2, 64 * MM))
    gs = fig.add_gridspec(1, 3, width_ratios=[1.0, 1.05, 1.0], wspace=0.40)
    axA, axB, axC = (fig.add_subplot(gs[0, i]) for i in range(3))

    # --- A: cascade slopegraph -------------------------------------------
    if time is not None:
        cols = ["raw_rho", "partial_area", "partial_area_time"]
        labels = ["raw", "+ cell area", "+ time"]
        for _, r in time.iterrows():
            ct = r["cell_type"]
            c = pal.get(ct, C_NULL)
            vals = [r[c_] for c_ in cols]
            fail = pal.get(ct, C_NULL) == C_NULL
            axA.plot(range(3), vals, "-o", color=c, ms=3.0, lw=(1.5 if not fail else 0.9),
                     ls=("-" if not fail else ":"), alpha=(1.0 if not fail else 0.8))
            axA.annotate(ct, (2, vals[2]), xytext=(3, 0), textcoords="offset points",
                         fontsize=5.6, color=c, va="center")
        axA.axhline(0, color=INK, lw=0.7)
        axA.set_xticks(range(3)); axA.set_xticklabels(labels)
        axA.set_xlim(-0.25, 2.9)
        axA.set_ylabel("response to confluence  ($\\rho$)")
        axA.set_title("controls applied cumulatively", fontsize=7, pad=4)
        axA.grid(alpha=0.14, axis="y", linewidth=0.5)
    panel_label(axA, "A")

    # --- B: size-band heatmap for q --------------------------------------
    if bands is not None and "feature" in bands.columns:
        sub = bands[bands["feature"] == "q"]
        types = [ct for ct in order if ct in set(sub["cell_type"])]
        nb = int(sub["size_band"].max()) + 1 if len(sub) else 0
        M = np.full((len(types), nb), np.nan)
        for i, ct in enumerate(types):
            for _, r in sub[sub["cell_type"] == ct].iterrows():
                M[i, int(r["size_band"])] = r["rho"]
        im = axB.imshow(M, cmap="RdBu_r", vmin=-0.4, vmax=0.4, aspect="auto")
        axB.set_yticks(range(len(types))); axB.set_yticklabels(types)
        axB.set_xticks(range(nb))
        axB.set_xticklabels([f"Q{b+1}" for b in range(nb)])
        axB.set_xlabel("cell-size quartile  (small \u2192 large)")
        for i in range(len(types)):
            for j in range(nb):
                if np.isfinite(M[i, j]):
                    axB.text(j, i, f"{M[i, j]:+.2f}", ha="center", va="center", fontsize=5.4,
                             color=("white" if abs(M[i, j]) > 0.26 else INK))
        cb = plt.colorbar(im, ax=axB, fraction=0.045, pad=0.03)
        cb.set_label("$\\rho$", fontsize=6.2)
        cb.ax.tick_params(labelsize=5.8)
        axB.set_title("effect within narrow size bands", fontsize=7, pad=4)
        for sp in axB.spines.values():
            sp.set_visible(False)
    panel_label(axB, "B", x=-0.34)

    # --- C: within-timepoint vs overall ----------------------------------
    if time is not None:
        for _, r in time.iterrows():
            ct = r["cell_type"]
            c = pal.get(ct, C_NULL)
            axC.plot(r["raw_rho"], r["within_tp_mean"], "o", color=c, ms=5.2,
                     mec=INK, mew=0.5, zorder=3)
            axC.annotate(ct, (r["raw_rho"], r["within_tp_mean"]), xytext=(4, 3.5),
                         textcoords="offset points", fontsize=5.6, color=c)
        lim = 1.0
        axC.plot([-lim, lim], [-lim, lim], ls="--", color="#999999", lw=0.7, zorder=1)
        axC.axhline(0, color=INK, lw=0.7); axC.axvline(0, color=INK, lw=0.7)
        axC.set_xlim(-lim, lim); axC.set_ylim(-lim, lim)
        axC.set_xlabel("overall  ($\\rho$)")
        axC.set_ylabel("within timepoint  ($\\rho$)")
        axC.set_title("is it crowding, or time in culture?", fontsize=7, pad=4)
        axC.grid(alpha=0.14, linewidth=0.5)
    panel_label(axC, "C", x=-0.26)

    savefig(fig, out, "Fig3_controls")


# ------------------------------------------------------------- figure 4 ----
def fig4_envelope(d, pal, out):
    env, rec = d.get("env"), d.get("recov")
    fig = plt.figure(figsize=(W15, 62 * MM))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.15, 1.0], wspace=0.46)
    axA, axB = fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1])

    # --- A: fidelity vs confluence ---------------------------------------
    if env is not None:
        ax2 = axA.twinx()
        ax2.spines["right"].set_visible(True)
        l1, = axA.plot(env["phi"], env["abs_bias"], "-o", color="#B2182B", ms=3.0,
                       label="|bias| in mean $q$")
        axA.axhline(0.10, ls=":", color="#B2182B", lw=0.8)
        l2, = ax2.plot(env["phi"], env["ratio"], "-s", color="#2166AC", ms=3.0,
                       label="instance recovery")
        ax2.axhline(0.80, ls=":", color="#2166AC", lw=0.8)
        handles = [l1, l2]
        if "iou" in env.columns and np.isfinite(env["iou"]).any():
            l3, = ax2.plot(env["phi"], env["iou"], "-^", color="#1B7837", ms=3.0,
                           lw=0.9, label="foreground IoU")
            handles.append(l3)
        axA.set_xlabel("confluence  $\\varphi$")
        axA.set_ylabel("|bias| in mean shape index", color="#B2182B")
        axA.tick_params(axis="y", colors="#B2182B")
        ax2.set_ylabel("instance recovery", color="#2166AC")
        ax2.tick_params(axis="y", colors="#2166AC")
        ax2.set_ylim(0, 1.0)
        axA.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.20),
                   ncol=3, borderpad=0.2, columnspacing=1.0, handlelength=1.6)
        axA.grid(alpha=0.14, linewidth=0.5)
        axA.set_title("model vs expert morphometry", fontsize=7, pad=4)
    panel_label(axA, "A")

    # --- B: scientific recovery ------------------------------------------
    if rec is not None:
        lim = 1.0
        axB.plot([-lim, lim], [-lim, lim], ls="--", color="#999999", lw=0.7, zorder=1)
        axB.axhline(0, color=INK, lw=0.7); axB.axvline(0, color=INK, lw=0.7)
        for _, r in rec.iterrows():
            ct = r["cell_type"]
            c = pal.get(ct, C_NULL)
            false_pos = (abs(r["gt_rho"]) < 0.12) and (abs(r["pred_rho"]) > 0.30)
            axB.plot(r["gt_rho"], r["pred_rho"], "o", color=c, ms=5.4,
                     mec=("#B2182B" if false_pos else INK),
                     mew=(1.4 if false_pos else 0.5), zorder=3)
            axB.annotate(ct, (r["gt_rho"], r["pred_rho"]), xytext=(4, 3.5),
                         textcoords="offset points", fontsize=5.6, color=c)
            if false_pos:
                axB.annotate("fabricated\ntrajectory", (r["gt_rho"], r["pred_rho"]),
                             xytext=(10, -16), textcoords="offset points", fontsize=5.6,
                             color="#B2182B",
                             arrowprops=dict(arrowstyle="-", lw=0.6, color="#B2182B"))
        axB.set_xlim(-lim, lim); axB.set_ylim(-lim, lim)
        axB.set_xlabel("from expert masks  ($\\rho$)")
        axB.set_ylabel("from model masks  ($\\rho$)")
        axB.set_title("recovery of per-lineage direction", fontsize=7, pad=4)
        axB.grid(alpha=0.14, linewidth=0.5)
    panel_label(axB, "B", x=-0.22)

    # NOT "Fig4_envelope": that name belongs to the IoU/F1 envelope written by
    # phase20_key_figures.py::fig_envelope_v2, which is the figure the
    # manuscript cites. This is a different plot (bias and per-lineage
    # recovery). Writing both under one name is how the wrong graphic reached
    # the manuscript once already.
    savefig(fig, out, "Fig_bias_recovery")


# ------------------------------------------------------------------ main ---
def main():
    ap = argparse.ArgumentParser(description="Publication figure set")
    ap.add_argument("--root", default=".", help="project root containing the *_out folders")
    ap.add_argument("--out", default="figures")
    ap.add_argument("--min-hours", type=float, default=8.0,
                    help="analysed window start, matching phase4 (default 8; 0=off)")
    ap.add_argument("--demote", nargs="*", default=["BV2"],
                    help="lineages to force to 'not supported' (default BV2; "
                         "its partial correlation contradicts all size strata)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    d = load_all(a.root)
    if "table" not in d:
        log.error("final_lineage_table.csv not found - cannot build figures.")
        return 2

    pal, order, table = build_palette(d["table"], set(a.demote or []))
    if a.demote:
        log.info("demoted to 'not supported': %s", ", ".join(a.demote))

    made = []
    for name, fn in (("Fig1", lambda: fig1_workflow(a.out)),
                     ("Fig2", lambda: fig2_atlas(d, pal, order, table, a.out, a.min_hours)),
                     ("Fig3", lambda: fig3_controls(d, pal, order, table, a.out)),
                     ("Fig4", lambda: fig4_envelope(d, pal, a.out))):
        try:
            fn(); made.append(name)
        except Exception as exc:
            log.warning("%s failed: %s", name, exc)

    print("\n" + "=" * 70)
    print(f" wrote {len(made)} figures to {a.out}/  ({', '.join(made)})")
    print(" each as .pdf (vector, for submission) and .png (for drafts)")
    print("\n figure roles")
    print("   Fig 1  workflow, measurement and the four controls")
    print("   Fig 2  the atlas: trajectories, effect sizes, confluence ranges")
    print("   Fig 3  KEY METHODS FIGURE - what survives each control")
    print("   Fig 4  operating envelope and scientific recovery")
    print("=" * 70 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
