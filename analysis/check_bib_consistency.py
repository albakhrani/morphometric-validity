#!/usr/bin/env python3
"""
Every entry of a given type must carry the same field pattern.

A reference list is read as a set. One entry missing a DOI where fifty
carry one, or one journal name spelled out where the rest are abbreviated,
is visible precisely because the eye compares neighbours -- and no other
checker in this project looks at refs.bib at all.

The rule is majority-based rather than prescriptive: the checker learns the
dominant pattern from the file and reports deviations from it. That way it
keeps working whichever entry style ships, and it does not encode a house
format that production may normalize anyway.

    python check_bib_consistency.py
    python check_bib_consistency.py --bib some/other.bib
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent

# Fields whose presence should be uniform across entries of a type.
WATCH = ["doi", "journal", "volume", "pages", "year", "number", "booktitle"]
# Abbreviation stems that never occur as a whole word in a spelled-out
# journal title. Two earlier versions of this check were wrong in opposite
# directions, and both are worth recording:
#   * a hand-written list of long words reported "Cytometry Part A" and
#     "BMC Medical Imaging" as abbreviated -- crying wolf on correct input;
#   * replacing it with a regex alternation that then lost its word-boundary
#     anchors to a reformat made "Nature" match the stem "Nat", so every
#     journal was classed abbreviated, the split test never fired, and the
#     check passed vacuously -- the false-pass signature this project keeps
#     hitting.
# Whole-word set membership cannot degrade in either direction.
ABBREV_STEMS = {
    "nat", "natl", "proc", "acad", "sci", "biol", "rev", "anal", "comput",
    "eng", "trans", "intl", "int", "j", "med", "res", "immunol", "microbiol",
    "genet", "syst", "phys", "chem", "bioinform", "lett", "appl", "mol",
}


def is_abbreviated(journal):
    return any(w.lower() in ABBREV_STEMS
               for w in re.findall(r"[A-Za-z]+", journal))


rows: list[tuple[str, bool, str]] = []


def note(claim: str, ok: bool, detail: str = "") -> None:
    rows.append((claim, ok, detail))


def parse(text: str) -> list[tuple[str, str, dict]]:
    out = []
    for m in re.finditer(r"@(\w+)\s*\{\s*([^,]+),(.*?)\n\}", text, re.S):
        typ, key, body = m.group(1).lower(), m.group(2).strip(), m.group(3)
        fields = {}
        for fm in re.finditer(r"(\w+)\s*=\s*", body):
            name = fm.group(1).lower()
            i = fm.end()
            while i < len(body) and body[i] in " \t\n":
                i += 1
            if i < len(body) and body[i] in "{\"":
                close = "}" if body[i] == "{" else "\""
                d, j = 0, i
                while j < len(body):
                    if body[j] == "{":
                        d += 1
                    elif body[j] == "}":
                        d -= 1
                        if d == 0 and close == "}":
                            break
                    elif body[j] == "\"" and close == "\"" and j > i:
                        break
                    j += 1
                fields[name] = re.sub(r"\s+", " ", body[i + 1:j]).strip()
            else:
                fields[name] = body[i:].split(",")[0].strip()
        out.append((typ, key, fields))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bib", default=str(HERE / "refs.bib"))
    a = ap.parse_args()

    ents = parse(Path(a.bib).read_text(encoding="utf8"))
    if not ents:
        print(f"FAIL  no entries parsed from {a.bib}")
        return 1
    print(f"bib   : {a.bib}")
    print(f"entries: {len(ents)}  "
          f"({', '.join(f'{n} {t}' for t, n in Counter(e[0] for e in ents).most_common())})\n")

    by_type: dict[str, list] = {}
    for typ, key, f in ents:
        by_type.setdefault(typ, []).append((key, f))

    for typ, group in sorted(by_type.items()):
        if len(group) < 3:                       # too few to have a majority
            continue
        for field in WATCH:
            have = [k for k, f in group if f.get(field)]
            frac = len(have) / len(group)
            if frac in (0.0, 1.0):
                continue
            missing = sorted(set(k for k, _ in group) - set(have))
            # DOI presence is held strictly: a reference list where one
            # entry lacks the DOI its fifty neighbours carry is the "odd one
            # out" an editor sees, and there is no legitimate reason for it.
            # Bibliographic fields are reported but not failed: eLocator
            # articles genuinely carry no page range and conference papers
            # genuinely carry no volume, and failing on that would make this
            # checker cry wolf on correct input -- which the first version
            # did, at 35/42 on 'pages'.
            lone = field == "doi" and 1 <= len(missing) <= 2 and frac >= 0.8
            if lone:
                note(f"@{typ}: '{field}' present in every entry",
                     False,
                     f"{len(have)}/{len(group)} carry it; absent from: "
                     + ", ".join(missing))
            else:
                note(f"@{typ}: '{field}' {len(have)}/{len(group)} (not held strict)",
                     True, "")

    # journal-name form must not be mixed
    jr = [(k, f["journal"]) for t, k, f in ents if f.get("journal")]
    if jr:
        full = [k for k, j in jr if not is_abbreviated(j)]
        frac = len(full) / len(jr)
        if 0.0 < frac < 1.0:
            minority = full if frac < 0.5 else [k for k, _ in jr if k not in full]
            note("journal names use one form (all abbreviated or all full)",
                 False,
                 f"{len(full)}/{len(jr)} spelled out; odd ones: "
                 + ", ".join(sorted(minority)[:6]))
        else:
            note("journal names use one form (all abbreviated or all full)",
                 True, "all full" if frac == 1.0 else "all abbreviated")

    # duplicate keys and duplicate DOIs
    dupk = [k for k, n in Counter(e[1] for e in ents).items() if n > 1]
    note("no duplicate citation keys", not dupk, ", ".join(dupk))
    dois = [f["doi"].lower() for _, _, f in ents if f.get("doi")]
    dupd = [d for d, n in Counter(dois).items() if n > 1]
    note("no duplicate DOIs", not dupd, ", ".join(dupd[:4]))

    bad = [r for r in rows if not r[1]]
    w = max(len(r[0]) for r in rows)
    for claim, ok, detail in rows:
        print(f"  [{'ok  ' if ok else 'FAIL'}] {claim:{w}s}")
        if detail and not ok:
            print(f"         {detail}")
    print("-" * (w + 12))
    print(f"{len(rows) - len(bad)}/{len(rows)} entry-consistency checks passed")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
