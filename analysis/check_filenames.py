#!/usr/bin/env python3
"""
Audit every filename the document references against what is on disk.

Overleaf runs Linux, where filenames are case-sensitive. MiKTeX on Windows is
not, so `Fig2_Atlas` and `Fig2_atlas` are the same file locally and different
files there: a build that is green on Windows fails on the first compile after
upload, with an error that points at the include and not at the typo.

Every reference is compared BYTE FOR BYTE against the directory listing. A
match that differs only in case is reported as a failure even though it builds
locally, because locally is not where it has to build.

Extensionless references are also flagged when more than one file on disk
could satisfy them, since graphics/input resolution order is not identical
across TeX distributions and the ambiguity is silent when it picks wrong.

    python check_filenames.py
    python check_filenames.py --dir overleaf_upload
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# What each command resolves to, and the extensions TeX will try for it.
COMMANDS = {
    "includegraphics": [".pdf", ".png", ".jpg", ".jpeg", ".eps"],
    "input": [".tex", ""],
    "include": [".tex"],
    "bibliography": [".bib"],
    "bibliographystyle": [".bst"],
    "documentclass": [".cls"],
}
SCAN = ("*.tex", "*.cls")

# References that legitimately point at nothing. Each needs a reason, and
# each was checked against the build log rather than assumed.
BENIGN = {
    ("oup-authoring-template.cls", "wordcount.txt"):
        "sits inside the body of \\newcommand{\\wordcount}, which this "
        "document never calls, so the \\input is never expanded. The file "
        "would be produced by the \\immediate\\write18{texcount ...} on the "
        "line above, and shell escape is restricted on both MiKTeX and "
        "Overleaf -- our log shows 'runsystem(texcount ...)...disabled "
        "(restricted)'. Vendor class: not edited.",
}


def refs_in(text: str, path: Path):
    """(command, referenced-name, line number) for every filename reference."""
    out = []
    for cmd, _ in COMMANDS.items():
        pat = re.compile(r"\\" + cmd + r"\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}")
        for m in pat.finditer(text):
            line = text[:m.start()].count("\n") + 1
            for name in m.group(1).split(","):
                name = name.strip()
                if name:
                    out.append((cmd, name, line))
    return out


def strip_comments(s: str) -> str:
    return re.sub(r"(?<!\\)%.*$", "", s, flags=re.M)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(Path(__file__).parent))
    a = ap.parse_args()
    D = Path(a.dir)

    on_disk = [p.name for p in D.iterdir() if p.is_file()]
    lower = {}
    for n in on_disk:
        lower.setdefault(n.lower(), []).append(n)

    print(f"directory : {D}")
    print(f"files     : {len(on_disk)}\n")

    problems = 0
    checked = 0
    for src in sorted(p for pat in SCAN for p in D.glob(pat)):
        text = strip_comments(src.read_text(encoding="utf8", errors="replace"))
        for cmd, name, line in refs_in(text, src):
            exts = COMMANDS[cmd]
            checked += 1
            has_ext = any(name.lower().endswith(e) for e in exts if e)

            # Candidates on disk that could satisfy this reference.
            cands = []
            for e in ([""] if has_ext else exts):
                cands += lower.get((name + e).lower(), [])
            cands = sorted(set(cands))

            if not cands:
                why = BENIGN.get((src.name, name))
                if why:
                    print(f"[known] {src.name}:{line} \\{cmd}{{{name}}} "
                          f"-- {why}")
                elif cmd == "documentclass":
                    # A class may live in the distribution rather than here.
                    print(f"[note]  {src.name}:{line} \\{cmd}{{{name}}} "
                          f"not in this directory (distribution class?)")
                else:
                    print(f"[MISS]  {src.name}:{line} \\{cmd}{{{name}}} "
                          f"-- no file on disk can satisfy this")
                    problems += 1
                continue

            # Exact-case check: the reference must equal a real name byte for
            # byte, once the extension TeX would append is accounted for.
            exact = [c for c in cands
                     if c == name or any(c == name + e for e in exts if e)]
            if not exact:
                print(f"[CASE] {src.name}:{line} \\{cmd}{{{name}}} "
                      f"-- on disk as {', '.join(cands)}. Builds on Windows, "
                      f"FAILS on Overleaf.")
                problems += 1
                continue

            if not has_ext and len(cands) > 1:
                print(f"[AMBIG] {src.name}:{line} \\{cmd}{{{name}}} "
                      f"-- {len(cands)} candidates: {', '.join(cands)}. "
                      f"Resolution order is distribution-dependent.")
                problems += 1

    print(f"\n{checked} filename references checked")
    if problems:
        print(f"{problems} problem(s) -- fix before uploading")
    else:
        print("0 problems: every reference matches a real filename exactly")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
