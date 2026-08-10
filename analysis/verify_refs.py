#!/usr/bin/env python3
"""
Check every DOI-bearing entry in refs.bib against Crossref.

The rule this enforces: no citation enters the bibliography unless its
title, first author, year and venue can be confirmed against the registry.
A .bib entry that compiles is not a verified entry -- BibTeX will happily
typeset a reference that does not exist.

Reports one line per entry:
  OK        every checked field agrees
  CHECK     the DOI resolves but a field disagrees; the Crossref value is
            printed so the disagreement can be judged rather than guessed at
  NOT FOUND the DOI does not resolve -- the entry must be dropped
  no doi    nothing to check against (preprints, software, datasets)

Year tolerance is deliberate: Crossref's `issued` is often the online-first
date, so a one-year gap against the print year is normal and not an error.

    python verify_refs.py            # all entries
    python verify_refs.py He2017     # named entries only
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

UA = "refcheck/1.0 (mailto:tzluo@ustc.edu.cn)"
BIB = Path(__file__).parent / "refs.bib"


def norm(s: str) -> str:
    s = re.sub(r"\{|\}|\\[a-zA-Z]+|\$", "", s or "")
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def field(block: str, name: str) -> str:
    m = re.search(name + r"\s*=\s*", block, re.I)
    if not m:
        return ""
    i = m.end()
    if block[i] == "{":
        depth, j = 0, i
        while j < len(block):
            if block[j] == "{":
                depth += 1
            elif block[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        return re.sub(r"\s+", " ", block[i + 1:j]).strip()
    m2 = re.match(r'"([^"]*)"|([^,\n]*)', block[i:])
    return re.sub(r"\s+", " ", (m2.group(1) or m2.group(2) or "")).strip()


def crossref(doi: str):
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)["message"]
    except urllib.error.HTTPError as e:
        return None if e.code == 404 else "ERR"
    except Exception:
        return "ERR"


def main() -> int:
    want = set(sys.argv[1:])
    text = BIB.read_text(encoding="utf8")
    blocks = re.split(r"\n(?=@)", text)
    bad = 0
    for b in blocks:
        m = re.match(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", b)
        if not m:
            continue
        key = m.group(2)
        if want and key not in want:
            continue
        doi = field(b, "doi")
        if not doi:
            print(f"{key:22s} no doi   {field(b, 'title')[:52]}")
            continue
        cr = crossref(doi)
        time.sleep(0.4)
        if cr is None:
            print(f"{key:22s} NOT FOUND  {doi}")
            bad += 1
            continue
        if cr == "ERR":
            print(f"{key:22s} error contacting Crossref for {doi}")
            bad += 1
            continue

        notes = []
        ct = (cr.get("title") or [""])[0]
        if norm(field(b, "title"))[:45] not in norm(ct) and \
           norm(ct)[:45] not in norm(field(b, "title")):
            notes.append(f"title -> {ct[:70]}")

        auth = field(b, "author").split(" and ")[0]
        surname = norm(auth.split(",")[0] if "," in auth else auth.split()[-1])
        first = (cr.get("author") or [{}])[0]
        crname = norm(first.get("family", "") or first.get("name", ""))
        if surname and crname and surname not in crname and crname not in surname:
            notes.append(f"1st author -> {first.get('family', first.get('name'))}")

        try:
            cry = int(cr["issued"]["date-parts"][0][0])
            by = int(re.search(r"\d{4}", field(b, "year")).group())
            if abs(cry - by) > 1:
                notes.append(f"year -> {cry}")
        except Exception:
            pass

        venue = field(b, "journal") or field(b, "booktitle")
        crv = (cr.get("container-title") or [""])[0]
        if venue and crv and norm(venue)[:14] not in norm(crv) and \
                norm(crv)[:14] not in norm(venue):
            notes.append(f"venue -> {crv[:55]}")

        if notes:
            bad += 1
            print(f"{key:22s} CHECK    " + "; ".join(notes))
        else:
            print(f"{key:22s} OK       {ct[:56]}")
    print(f"\nentries needing attention: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    import urllib.parse
    raise SystemExit(main())
