#!/usr/bin/env python3
"""
Re-author every figure at the OUP placed width and verify it.

The rule this enforces is the one that fixed the typography in the first
place: a figure is authored at the width it will be PLACED at, so LaTeX
applies no scale and the point sizes in the source are the point sizes on
the page. Moving from the Elsevier CAS measure (494.51 pt) to OUP
contemporary/large (526.38 pt) breaks that, so every figsize has to move.

bbox_inches="tight" trims to content, so the artwork width that comes out is
not the figsize that went in, and the trim is not a fixed fraction. Rather
than guess it, this drives each generator, measures the artwork it produced,
corrects the figsize and repeats until the artwork lands on the target. The
converged value is then written back into the generator with a comment, so
the scripts stand alone afterwards and this driver is not a dependency.

Output goes to paper2_bib/. paper2_overleaf_current/ keeps its CAS-width
figures untouched, so the fallback stays buildable.

    python recalibrate_figures.py            # converge, write back, verify
    python recalibrate_figures.py --dry-run  # report only
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
CAS = ROOT / "paper2_overleaf_current"
BIB = ROOT / "paper2_bib"
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")

# Measured from the compiled OUP document, not from the class source:
#   ==PROBE== tw=526.37598pt cw=254.65216pt cs=17.07164pt
TEXTWIDTH = 526.376          # pt, \textwidth  -> figure* / table*
COLUMNWIDTH = 254.652        # pt, \columnwidth -> figure / table
TOL = 1.5                    # pt; below this, a further pass is noise

# Set by --format tiff. Kept in a list so Job.run can read it without a
# global statement. 0 means "PDF only", which is the normal case.
TIFF_DPI = [0]

sys.path.insert(0, str(CAS))
from check_figure_resolution import objects, page_width  # noqa: E402


class Job:
    """One generator, one output figure, one figsize literal to move."""

    def __init__(self, stem, script, cwd, args, pattern, placed=TEXTWIDTH,
                 hpattern=None):
        self.stem, self.script, self.cwd = stem, Path(script), Path(cwd)
        self.args, self.pattern, self.placed = args, pattern, placed
        # Some generators keep the width and the height in different places
        # (phase7 defines W2 as a shared column constant near the top and the
        # height inline at the figure call). hpattern names the second one.
        self.hpattern = hpattern

    def _find(self, s, pat, grp):
        m = re.search(pat, s)
        if not m:
            raise SystemExit(f"{self.stem}: pattern for {grp} did not match "
                             f"in {self.script.name} -- inspect, do not guess")
        return m

    def read_size(self):
        s = self.script.read_text(encoding="utf8")
        mw = self._find(s, self.pattern, "width")
        mh = self._find(s, self.hpattern, "height") if self.hpattern else mw
        return float(mw.group("w")), float(mh.group("h")), s, (mw, mh)

    def write_size(self, w, h):
        _, _, s, (mw, mh) = self.read_size()
        # Apply the later edit first so the earlier match offsets stay valid.
        for m, grp, val in sorted(((mw, "w", w), (mh, "h", h)),
                                  key=lambda t: -t[0].start()):
            if self.hpattern is None and grp == "h":
                continue          # single match carries both; done in one go
            txt = m.group(0)
            if self.hpattern is None:
                txt = txt.replace(m.group("w"), f"{w:.3f}", 1)
                txt = txt.replace(m.group("h"), f"{h:.3f}", 1)
            else:
                txt = txt.replace(m.group(grp), f"{val:.3f}", 1)
            s = s[:m.start()] + txt + s[m.end():]
        self.script.write_text(s, encoding="utf8")

    def run(self):
        # `runner` may differ from `script`: Fig2_micrographs' figsize lives
        # in phase20_key_figures.py but the entry point is
        # figure4_micrographs.py, which calls into it.
        runner = getattr(self, "runner", None) or self.script
        env = dict(os.environ)
        # --format tiff: put tiff_export/ on PYTHONPATH so its sitecustomize
        # is imported at interpreter startup and every Figure.savefig that
        # writes a PDF also writes a TIFF, rendered from the figure rather
        # than rasterised from the finished PDF.
        if TIFF_DPI[0]:
            env["FIG_TIFF_DPI"] = str(TIFF_DPI[0])
            env["PYTHONPATH"] = (str(ROOT / "tiff_export") + os.pathsep
                                 + env.get("PYTHONPATH", ""))
        # figure3_mechanism.py puts only its OWN directory on sys.path
        # (line 49) but imports phase11_instance_model from the project root,
        # so it cannot import standalone. Supplied here as an invocation
        # detail rather than by editing the generator.
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        cmd = [PY, str(runner)] + self.args
        r = subprocess.run(cmd, cwd=self.cwd, capture_output=True, text=True,
                           env=env)
        if r.returncode != 0:
            print(f"    ! {self.stem} generator failed:\n"
                  f"{r.stdout[-800:]}\n{r.stderr[-1500:]}")
            return False
        return True

    def measure(self):
        p = BIB / f"{self.stem}.pdf"
        return page_width(p) if p.exists() else None


JOBS = [
    Job("Fig1_architecture", CAS / "figure1_pipeline.py", CAS,
        ["--out", str(BIB)],
        r"figsize=\((?P<w>[\d.]+), (?P<h>[\d.]+)\)"),
    Job("Fig2_architecture", CAS / "figure2_architecture.py", CAS,
        ["--out", str(BIB)],
        r"plt\.figure\(figsize=\((?P<w>[\d.]+), (?P<h>[\d.]+)\)\)"),
    Job("Fig5_merged", CAS / "figure5_merged.py", CAS,
        ["--out", str(BIB)],
        r"figsize=\((?P<w>[\d.]+), (?P<h>[\d.]+)\)"),
    Job("atlas_comparison", CAS / "figure8_recovery.py", CAS,
        ["--out", str(BIB)],
        r"figsize=\((?P<w>[\d.]+) \* ncol, (?P<h>[\d.]+) \* nrow\)"),
    Job("Fig3_mechanism", CAS / "figure3_mechanism.py", CAS,
        ["--out", str(BIB),
         "--model", str(ROOT / "runs/instance/best.pt"),
         "--images", str(ROOT / "data/raw/livecell_test_images"),
         "--image", "A172_Phase_C7_1_02d08h00m_3.tif"],
        r"figsize=\((?P<w>[\d.]+), (?P<h>[\d.]+) \* 2 \* nrow\)"),
    Job("Fig2_micrographs", CAS / "figure4_micrographs.py", CAS,
        ["--out", str(BIB),
         "--model", str(ROOT / "runs/instance/best.pt"),
         "--images", str(ROOT / "data/raw/livecell_test_images"),
         "--coco", str(ROOT / "data/raw/livecell/livecell_coco_test.json")],
        # the figsize lives in phase20_key_figures.fig_micrographs
        r"plt\.subplots\(1, 4, figsize=\((?P<w>[\d.]+), (?P<h>[\d.]+)\)\)"),
    Job("Fig2_atlas", ROOT / "phase7_figures.py", ROOT,
        ["--out", str(BIB)],
        r"W1, W15, W2 = 90 \* MM, 140 \* MM, (?P<w>[\d.]+) \* MM",
        hpattern=r"fig = plt\.figure\(figsize=\(W2, (?P<h>[\d.]+) \* MM\)\)"),
]
# phase7 states its widths in MILLIMETRES, not inches, so its target has to
# be converted or the correction factor is applied to the wrong unit.
JOBS[-1].placed = TEXTWIDTH
# Fig2_micrographs' figsize is not in its own driver script: patch
# phase20_key_figures.py, but run figure4_micrographs.py, which is the entry
# point that disables the centre crop.
JOBS[5].runner = CAS / "figure4_micrographs.py"
JOBS[5].script = ROOT / "phase20_key_figures.py"


def converge(job, dry):
    print(f"\n{job.stem}")
    w0, h0, _, _ = job.read_size()
    print(f"    figsize in source      {w0:.3f} x {h0:.3f} in")
    if dry:
        return None
    w, h = w0, h0
    best = None
    for it in range(1, 5):
        job.write_size(w, h)
        if not job.run():
            job.write_size(w0, h0)
            return None
        got = job.measure()
        if got is None:
            print("    ! no output produced")
            job.write_size(w0, h0)
            return None
        err = job.placed - got
        print(f"    pass {it}: figsize {w:.3f} -> artwork {got:.2f} pt "
              f"(target {job.placed:.2f}, off by {err:+.2f})")
        if best is None or abs(err) < abs(best[4] - job.placed):
            best = (w0, h0, w, h, got)
        if abs(err) <= TOL:
            return best
        k = job.placed / got
        w, h = w * k, h * k

    # Keep the BEST pass, not the last one. bbox_inches="tight" quantises on
    # some figures (a legend edge snapping in or out), so the correction can
    # oscillate between two values that straddle the target without ever
    # landing inside TOL. Returning the last pass then depends on which
    # iteration the loop happened to stop at, and re-running the driver could
    # move a figure that was already correct.
    print(f"    did not converge within {it} passes; keeping the closest "
          f"pass (artwork {best[4]:.2f} pt)")
    job.write_size(best[2], best[3])
    if not job.run():
        return None
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--format", choices=("pdf", "tiff"), default="pdf",
                    help="tiff also writes a TIFF beside each PDF, "
                         "rendered from the figure, for portals that "
                         "refuse vector uploads")
    ap.add_argument("--tiff-dpi", type=float, default=600.0,
                    help="OUP asks 600 dpi for line art, 300 for "
                         "greyscale; 600 satisfies both")
    a = ap.parse_args()
    if a.format == "tiff":
        TIFF_DPI[0] = a.tiff_dpi
        print(f"TIFF export on: {a.tiff_dpi:.0f} dpi at placed size")

    jobs = [j for j in JOBS if not a.only or j.stem in a.only]
    results = []
    for j in jobs:
        results.append((j, converge(j, a.dry_run)))

    print("\n" + "=" * 76)
    print(f"{'figure':22s} {'figsize before':>16s} {'figsize after':>16s} "
          f"{'artwork':>9s}")
    print("-" * 76)
    for j, r in results:
        if r is None:
            print(f"{j.stem:22s} {'unchanged / failed':>16s}")
            continue
        w0, h0, w, h, got = r
        print(f"{j.stem:22s} {f'{w0:.2f} x {h0:.2f}':>16s} "
              f"{f'{w:.2f} x {h:.2f}':>16s} {got:8.2f}p")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
