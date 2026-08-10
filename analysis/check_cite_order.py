#!/usr/bin/env python3
"""
Confirm the reference list is numbered in order of first citation.

Briefings in Bioinformatics requires references "numbered consecutively in
the order in which they appear". Stock oup-plain.bst sorts alphabetically
instead, which is why this project ships oup-plain-unsrt.bst. That change is
invisible in a build log -- an alphabetically ordered bibliography compiles
with zero errors and zero warnings -- so it is checked here directly.

main.aux records \\citation{} in document order. main.bbl records
\\bibitem{} in the order BibTeX emitted them, which is the order they are
numbered. The two must agree.

    python check_cite_order.py
    python check_cite_order.py --dir some/other/build
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    # --dir exists so the check can be pointed at a scratch build with a
    # deliberately permuted .bbl. A checker that has only ever been run on
    # input it passes has not been shown to detect anything.
    ap.add_argument("--dir", default=str(Path(__file__).parent),
                    help="directory holding main.aux and main.bbl")
    D = Path(ap.parse_args().dir)

    aux = (D / "main.aux").read_text(encoding="latin-1")
    bbl = (D / "main.bbl").read_text(encoding="latin-1")

    order, seen = [], set()
    for grp in re.findall(r"\\citation\{([^}]*)\}", aux):
        for k in (x.strip() for x in grp.split(",")):
            if k and k not in seen:
                seen.add(k)
                order.append(k)

    emitted = re.findall(r"\\bibitem\{([^}]*)\}", bbl)

    print(f"first-citation order : {len(order)} keys")
    print(f"bibliography order   : {len(emitted)} keys")

    if len(order) != len(emitted):
        print("MISMATCH in count -- cited but not emitted:",
              sorted(set(order) - set(emitted)))
        return 1

    bad = [(i + 1, a, b) for i, (a, b) in enumerate(zip(order, emitted))
           if a != b]
    if not bad:
        print("\nOK  every reference is numbered by first appearance.")
        print("    first five:", ", ".join(f"[{i+1}] {k}"
                                           for i, k in enumerate(order[:5])))
        return 0

    print(f"\nOUT OF ORDER at {len(bad)} position(s) -- the bibliography is "
          f"not appearance-ordered:")
    for pos, want, got in bad[:12]:
        print(f"    [{pos:>2}] expected {want:20s} got {got}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
