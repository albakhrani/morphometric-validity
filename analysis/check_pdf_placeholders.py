#!/usr/bin/env python3
"""
Sweep the COMPILED PDF for strings that mean the build silently failed.

Every other checker in this project reads sources. That leaves one blind
spot, and it shipped: `\\citet` against a numeric .bst emits the literal
string "(author?)" into the typeset page. oup-plain-unsrt.bst writes a bare
\\bibitem{key} with no author-year label, so natbib has nothing to put in a
textual citation and prints "(author?)[15]" instead of "Hirling et al.
[15]". It compiles with zero errors and zero warnings, `main.bbl` is
perfectly well formed, and every source-level check passes. Six of them
reached the submission PDF and were found by a reader, not by the suite.

That is the fourth false pass in this project with the same signature: a
check that confirms the inputs are well formed and never looks at the
output. The others were check_figure_resolution.py reporting raster art as
vector, check_cite_order.py comparing .aux to .bbl without seeing the page,
and check_numbers.py asserting "reader-facing text" while reading three
front-matter files. So this checker reads the rendered page and nothing
else.

Text is reconstructed from the PDF content stream via check_figure_text.py's
extractor -- no external binary, and it survives the kerning-chunk splitting
that makes a naive search miss "(author?)" when natbib and the following
bracket land in different TJ elements.

KNOWN carries placeholders that are deliberately unresolved at this stage;
they are reported and do not fail the run. Everything else fails.

    python check_pdf_placeholders.py
    python check_pdf_placeholders.py --pdf some/other.pdf
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from check_figure_text import extract

HERE = Path(__file__).parent

# (needle, why it means the build failed)
FATAL = [
    ("(author?)",
     "natbib textual citation against a numeric .bst -- use "
     "'Surname et al.~\\citep{key}', not \\citet{key}"),
    ("(year?)",
     "natbib year form against a .bbl carrying no year label"),
    ("??",
     "unresolved \\ref -- LaTeX printed the undefined-reference marker"),
    # "?]" not "[?]": natbib prints [?] for an unresolved key, but the
    # opening bracket is drawn from a separate font run and does not survive
    # content-stream extraction -- a control compiled with an undefined
    # citation extracts as "raised by?] in", with the "[" simply absent.
    # The closing half is what is reliably there.
    ("?]",
     "unresolved \\cite -- the key is absent from the .bbl"),
    ("Undefined control sequence",
     "an error message reached the page"),
    ("TODO", "drafting marker"),
    ("FIXME", "drafting marker"),
    ("XXXX", "drafting marker"),
]

# Deliberately unresolved at this stage: reported, never fatal.
KNOWN = {
    "[REPOSITORY URL]":
        "assigned at submission; Data availability, main.tex",
}


def runs_and_text(pdf: Path) -> tuple[list[str], str]:
    raw = extract(pdf)
    runs = [r for r in raw.split("\n") if r.strip()]
    return runs, re.sub(r"\s+", " ", raw.replace("\n", " "))


def squash(s: str) -> str:
    """Collapse whitespace only. Punctuation is load-bearing here:
    '(author?)' and '[?]' are the whole point."""
    return re.sub(r"\s+", "", s)


def find(runs: list[str], whole: str, needle: str) -> bool:
    n = squash(needle)
    if n in squash(whole):
        return True
    return any(n in squash(r) for r in runs)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", default=str(HERE / "main.pdf"))
    a = ap.parse_args()

    pdf = Path(a.pdf)
    if not pdf.is_file():
        print(f"FAIL  no such PDF: {pdf}")
        return 1

    runs, whole = runs_and_text(pdf)
    print(f"pdf   : {pdf}")
    print(f"text  : {len(runs)} runs, {len(whole)} chars\n")

    bad = []
    for needle, why in FATAL:
        hit = find(runs, whole, needle)
        if hit:
            bad.append((needle, why))
        print(f"  [{'FAIL' if hit else 'ok  '}] absent: {needle!r:34s} {why}")

    for needle, why in KNOWN.items():
        hit = find(runs, whole, needle)
        mark = "known" if hit else "gone "
        print(f"  [{mark}] {needle!r:42s} {why}")

    print("-" * 78)
    if bad:
        for needle, why in bad:
            print(f"FAIL  {needle!r} is on the page -- {why}")
        print(f"{len(bad)} placeholder/failure string(s) reached the PDF")
        return 1
    print(f"0 failures: none of the {len(FATAL)} failure strings reached the PDF")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
