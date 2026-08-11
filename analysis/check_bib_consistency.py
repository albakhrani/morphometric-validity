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


# ---------------------------------------------------------------- citedness
# Every entry in the .bib must be cited. The compile gate already catches the
# reverse direction -- a \cite to a key that does not exist is a LaTeX
# warning and an empty bracket -- but an entry that sits in refs.bib uncited
# is silent, and a reference list is a claim about what the work rests on.
#
# Matched by KEY, never by DOI string. That is the whole point of this check:
# it replaces a hand-grep of body.tex for the DOI fragment "bbae284", which
# found nothing because DOI fragments do not appear in prose, and produced a
# false "uncited" finding that nearly led to a duplicate \citep on an entry
# already cited as Tang2024 and printed as reference [21].
#
# The class is currently EMPTY -- every entry is cited. This exists so the
# next one is found by a checker rather than by a grep that cannot see keys.
CITE_CMD = re.compile(r"\\(?:cite|citep|citet|citealt|citeauthor|citeyear)"
                      r"\*?(?:\[[^\]]*\])*\{([^}]*)\}")


def cited_keys(tex_dir: Path) -> set:
    keys = set()
    for tex in sorted(tex_dir.glob("*.tex")):
        try:
            s = tex.read_text(encoding="utf8")
        except OSError:
            continue
        s = re.sub(r"(?m)^\s*%.*$", "", s)          # strip comment lines
        for m in CITE_CMD.finditer(s):
            for k in m.group(1).split(","):
                k = k.strip()
                if k:
                    keys.add(k)
    return keys


def check_citedness(bib_entries, tex_dir: Path) -> None:
    declared = {k for _, k, _ in bib_entries}
    used = cited_keys(tex_dir)
    uncited = sorted(declared - used)
    note(f"every refs.bib entry is cited ({len(declared)} entries, "
         f"{len(used)} keys cited)",
         not uncited,
         "uncited: " + ", ".join(uncited) if uncited else "")
    # The reverse direction is the compiler's job, but report it if visible.
    dangling = sorted(k for k in used - declared if not k.startswith("fig:"))
    if dangling:
        note("every \\cite key resolves to a refs.bib entry", False,
             "missing from bib: " + ", ".join(dangling[:6]))


# ------------------------------------------------------ rendered .bbl form
# The .bst was converted to the journal's printed entry style (Step F).
# These check the RENDERED result, not the .bib: a .bst is a stack language
# with no type system, and the only honest test of one is what it emits.
BBL_ENTRY = re.compile(r"\\bibitem\{([^}]*)\}(.*?)(?=\\bibitem\{|\\end\{thebibliography\})",
                       re.S)


def check_rendered(bbl_path, bib_entries, required=False) -> None:
    # Opt-in: a .bib with no compiled .bbl beside it (a fixture, or a tree
    # that has not been built) is not a failure. Pass --bbl to require it.
    if not bbl_path.is_file():
        if required:
            note("rendered bibliography present", False, "no %s" % bbl_path.name)
        return
    txt = bbl_path.read_text(encoding="utf8", errors="replace")
    ents = {k: b for k, b in BBL_ENTRY.findall(txt)}
    note("rendered bibliography parsed (%d entries)" % len(ents), bool(ents))
    if not ents:
        return

    nauth = {}
    for typ, key, f in bib_entries:
        a = f.get("author", "")
        nauth[key] = len(re.split(r"\s+and\s+", a)) if a else 0

    # 1. no entry lists more than three authors
    over = []
    for k, blk in ents.items():
        head = blk.split("\\newblock")[0]
        listed = len([x for x in head.split(",") if x.strip()])
        if "et~al." in head or "et al." in head:
            listed = 3
        if listed > 3:
            over.append("%s (%d)" % (k, listed))
    note("no rendered entry lists more than three authors", not over,
         ", ".join(over[:6]))

    # 2. italic et al. wherever the .bib has more than three
    missing = [k for k, n in nauth.items()
               if n > 3 and k in ents
               and "\\emph{et~al.}" not in ents[k].split("\\newblock")[0]]
    note("italic et al. present wherever the bib has >3 authors",
         not missing, ", ".join(missing[:6]))
    # ...and absent where it has <= 3
    spurious = [k for k, n in nauth.items()
                if 0 < n <= 3 and k in ents and "et~al." in ents[k].split("\\newblock")[0]]
    note("no et al. where the bib has three or fewer authors",
         not spurious, ", ".join(spurious[:6]))

    # 3. bold volume, on every entry that renders a volume
    arts = {k for typ, k, f in bib_entries if typ == "article" and f.get("volume")}
    unbold = [k for k in arts if k in ents and "\\textbf{" not in ents[k]]
    note("volume is bold in every article entry that has one",
         not unbold, ", ".join(unbold[:6]))

    # 4. uniform DOI URL
    withdoi = {k for typ, k, f in bib_entries if typ == "article" and f.get("doi")}
    nourl = [k for k in withdoi
             if k in ents and "\\url{https://doi.org/" not in ents[k]]
    note("every article DOI renders as a full https://doi.org/ URL",
         not nourl, ", ".join(nourl[:6]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bib", default=str(HERE / "refs.bib"))
    ap.add_argument("--bbl", default=None,
                    help="rendered .bbl to check for entry form; "
                         "defaults to main.bbl beside the .bib")
    ap.add_argument("--tex-dir", default=None,
                    help="directory of .tex files to scan for \\cite keys; "
                         "defaults to the .bib's own directory")
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

    # Journal names carry the NLM Catalog abbreviation, with a closed set of
    # documented exceptions. The list is not "titles we did not get to": each
    # was queried against the NLM Catalog and each failed to confirm, and
    # printing an unconfirmed abbreviation is the failure mode this whole
    # exercise exists to avoid. A title that is full-form and NOT on this
    # list is a genuine miss and fails.
    # Both remaining entries ARE their own NLM abbreviation, confirmed by
    # ISSN lookup -- not unresolved cases. Four titles that a title-string
    # query had failed to confirm (and for two of which it returned a
    # DIFFERENT journal) were resolved by keying on the ISSN instead, and
    # are now abbreviated like the rest.
    FULL_FORM_OK = {
        "Nature":             "NLM medlineta is 'Nature'; ISSN 0028-0836",
        "BMC Bioinformatics": "NLM medlineta is 'BMC Bioinformatics'",
        # IS the NLM form (of 'Cytometry. Part A'), but carries no stem the
        # is_abbreviated() heuristic recognises. Listed rather than widening
        # the heuristic, which would start passing real full-form titles.
        "Cytometry A":        "NLM medlineta; ISSN 1552-4922",
    }
    jr = [(k, f["journal"]) for t, k, f in ents if f.get("journal")]
    if jr:
        stray = sorted({j for k, j in jr
                        if not is_abbreviated(j) and j not in FULL_FORM_OK})
        note("journal names are NLM-abbreviated except the documented set",
             not stray,
             "un-abbreviated and undocumented: " + ", ".join(stray[:6]))
        used_exc = sorted({j for k, j in jr if j in FULL_FORM_OK})
        note(f"{len(used_exc)} documented full-form titles, each with a reason",
             True, "")

    check_citedness(ents, Path(a.tex_dir) if a.tex_dir
                    else Path(a.bib).parent)

    check_rendered(Path(a.bbl) if a.bbl
                   else Path(a.bib).parent / "main.bbl", ents,
                   required=bool(a.bbl))

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
