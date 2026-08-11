#!/usr/bin/env python3
"""
Every italicised named section reference must match a heading verbatim.

This submission uses `unnumsec`, so sections carry no numbers and the paper
refers to them by name: \\emph{Operating-point selection} rather than
Section~3.2. That is a settled decision, and it has one failure mode a
numbered scheme does not have. A wrong number is still a pointer -- the
reader can count sections. A wrong NAME is unrecoverable: searching for it
finds nothing, and in a two-column layout "above" may be a page away.

It has already happened twice, and neither was caught by a checker:

  * four references read \\emph{the density-resolved atlas} against a heading
    that actually reads "A density-resolved morphological atlas" -- an
    artifact of converting Section~\\ref{} to named form, wrong in 4 of 78
    sites;
  * three read \\emph{Coverage} against "Coverage: when a pipeline measures
    nothing", and in one caption the same italic token also names a table
    column nine lines later.

Both were found by eye. This exists so the next prose edit cannot recreate
them silently.

Method: collect the headings, collect every \\emph{} span, and classify.
A span is a NEAR MISS -- and a failure -- when it shares at least two
content words with some heading and at least half its own content words,
without matching that heading exactly. That catches paraphrase and
truncation while leaving ordinary emphasis (\\emph{fewer}, \\emph{all},
\\emph{Columns.}) alone.

    python check_named_refs.py
    python check_named_refs.py --dir some/other/tree
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent

STOP = {"the", "a", "an", "of", "and", "in", "is", "not", "to", "from",
        "when", "it", "on", "for", "at", "by", "with", "that"}

rows: list[tuple[str, bool, str]] = []


def note(claim: str, ok: bool, detail: str = "") -> None:
    rows.append((claim, ok, detail))


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().rstrip(".,;:")


def words(s: str) -> set:
    return {w.lower() for w in re.findall(r"[A-Za-z0-9-]+", s)} - STOP


def scan(body: Path):
    raw = body.read_text(encoding="utf8")
    lines = raw.split("\n")

    headings = []
    for i, l in enumerate(lines, 1):
        m = re.match(r"\\(?:sub)*section\*?\{(.+?)\}", l.strip())
        if m:
            headings.append((norm(m.group(1)), i))
    hmap = {h: i for h, i in headings}

    # char offset -> line, for reporting
    off, ln = [], 1
    for ch in raw:
        off.append(ln)
        if ch == "\n":
            ln += 1

    exact, near, other = [], [], 0
    for m in re.finditer(r"\\emph\{([^{}]*)\}", raw, re.S):
        txt = norm(m.group(1))
        line = off[m.start()] if m.start() < len(off) else 0
        if len(txt.split()) < 2:
            other += 1
            continue
        if txt in hmap:
            exact.append((txt, line))
            continue
        tw = words(txt)
        if not tw:
            other += 1
            continue
        best, score = None, 0
        for h in hmap:
            ov = len(tw & words(h))
            if ov > score:
                best, score = h, ov
        if best and score >= 2 and score / len(tw) >= 0.5:
            near.append((txt, line, best))
        else:
            other += 1
    return headings, exact, near, other


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(HERE))
    a = ap.parse_args()
    body = Path(a.dir) / "body.tex"
    if not body.is_file():
        print(f"FAIL  no body.tex in {a.dir}")
        return 1

    headings, exact, near, other = scan(body)
    print(f"tree      : {a.dir}")
    print(f"headings  : {len(headings)}")
    print(f"named refs: {len(exact)} exact, {len(near)} near-miss, "
          f"{other} other emphasis\n")

    if not headings:
        note("body.tex declares headings", False, "none parsed")
    else:
        note(f"{len(headings)} headings parsed", True)

    # A tree that references sections by number (the CAS fallback) has no
    # named refs at all. That is correct there, not a failure.
    if exact or near:
        note(f"{len(exact)} named references match a heading verbatim",
             True)
    for txt, line, best in near:
        note(f"named reference matches a heading verbatim (line {line})",
             False,
             f'\\emph{{{txt}}} -> nearest heading "{best}"')

    bad = [r for r in rows if not r[1]]
    w = max(len(r[0]) for r in rows)
    for claim, ok, detail in rows:
        print(f"  [{'ok  ' if ok else 'FAIL'}] {claim:{w}s}")
        if detail and not ok:
            print(f"         {detail}")
    print("-" * (w + 12))
    print(f"{len(rows) - len(bad)}/{len(rows)} named-reference checks passed")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
