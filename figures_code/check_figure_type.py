#!/usr/bin/env python3
"""
Report the smallest type size actually PRINTED in each figure.

Reads the Tf font-size operators out of the PDF content stream, applies the
current transformation matrix scale, then multiplies by the scale LaTeX will
apply when placing the artwork at \\textwidth (or \\linewidth). This catches
the failure mode that source-level font sizes hide: matplotlib renders
mathtext sub/superscripts at about 0.7x the base size, so a 7 pt label can
put a 4.9 pt subscript on the page.

    python check_figure_type.py            # all figures in this folder
    python check_figure_type.py Fig2_architecture.pdf
"""
from __future__ import annotations

import re
import subprocess
import sys
import zlib
from pathlib import Path

TEXTWIDTH = 494.51   # pt, from the CAS class at this document's settings
LINEWIDTH = 234.88

# figures placed at \linewidth rather than \textwidth
SINGLE_COLUMN: set[str] = {"Fig4_envelope"}

# Not currently included by body.tex; measured for completeness only.
UNUSED: set[str] = {"Fig4_envelope"}

# Known false positives: mathtext draws a radical from a size-variant font, so
# the Tf operand is small even though the glyph prints at full size. Keyed by
# figure stem -> number of sub-6 pt occurrences that are attributable to this.
# Verified by eye on a 200 dpi render before being listed here.
RADICAL_GLYPHS: dict[str, int] = {"Fig2_atlas": 1}   # the sqrt in "q = P/sqrt(A)"

FLOOR_HARD = 6.0     # Elsevier artwork minimum
FLOOR_TARGET = 7.0   # this project's target, with headroom


def raw_streams(path: Path) -> str:
    """Concatenate the decompressed content streams of page 1."""
    data = path.read_bytes()
    out = []
    for m in re.finditer(rb"stream\r?\n", data):
        start = m.end()
        end = data.find(b"endstream", start)
        if end < 0:
            continue
        chunk = data[start:end]
        try:
            out.append(zlib.decompress(chunk).decode("latin-1"))
        except Exception:
            try:
                out.append(chunk.decode("latin-1"))
            except Exception:
                pass
    return "\n".join(out)


def page_width(path: Path) -> float:
    o = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True).stdout
    for line in o.splitlines():
        if line.lower().startswith("page size"):
            return float(line.split()[2])
    raise SystemExit(f"cannot read page size of {path}")


def sizes_in(path: Path) -> list[float]:
    """Every distinct rendered text size, in artwork points."""
    s = raw_streams(path)
    found = []
    # track the text-matrix scale set by Tm, which matplotlib uses for
    # rotated / scaled text; combine with the Tf size operand.
    tm_scale = 1.0
    for tok in re.finditer(
            r"([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+[-\d.]+\s+[-\d.]+\s+Tm"
            r"|/[A-Za-z0-9+\-]+\s+([\d.]+)\s+Tf", s):
        if tok.group(5) is not None:
            found.append(float(tok.group(5)) * tm_scale)
        else:
            a, b = float(tok.group(1)), float(tok.group(2))
            tm_scale = (a * a + b * b) ** 0.5 or 1.0
    return [round(v, 2) for v in found if v > 0.5]


def main() -> int:
    here = Path(__file__).parent
    targets = ([Path(p) for p in sys.argv[1:]] or
               sorted(p for p in here.glob("*.pdf")
                      if p.name not in {"COMPILED_PREVIEW.pdf", "main.pdf"}))
    bad = 0
    print(f"{'figure':26s} {'artwork':>8s} {'scale':>6s} {'min pt':>7s}  verdict")
    print("-" * 74)
    for p in targets:
        try:
            w = page_width(p)
        except SystemExit:
            continue
        placed = LINEWIDTH if p.stem in SINGLE_COLUMN else TEXTWIDTH
        scale = placed / w
        sz = sorted(v * scale for v in sizes_in(p))
        if not sz:
            print(f"{p.stem:26s} {w:8.1f} {scale:6.3f} {'-':>7s}  no text found")
            continue
        # drop the documented radical-glyph false positives before judging
        drop = RADICAL_GLYPHS.get(p.stem, 0)
        judged = sz[drop:] if drop and sz[0] < FLOOR_HARD else sz
        smallest = judged[0]
        if smallest < FLOOR_HARD:
            verdict, bad = "FAIL  below 6 pt", bad + 1
        elif smallest < FLOOR_TARGET:
            verdict = "warn  below 7 pt"
        else:
            verdict = "ok"
        if p.stem in UNUSED:
            verdict += "   (not used by body.tex)"
        if drop:
            verdict += f"   [{drop} radical glyph ignored]"
        print(f"{p.stem:26s} {w:8.1f} {scale:6.3f} {smallest:7.2f}  {verdict}")
        if smallest < FLOOR_TARGET:
            small = sorted({round(v, 2) for v in judged if v < FLOOR_TARGET})
            print(f"{'':26s} {'':8s} {'':6s} {'':7s}  sizes under 7 pt: {small}")
    print("-" * 74)
    print("FAIL count:", bad)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
