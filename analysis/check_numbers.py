#!/usr/bin/env python3
"""
Cross-check every number an editor reads against its source on disk.

The abstract, the Key Points and the cover letter are the three things read
first and read together. A number that disagrees between them is worse than
a number that is merely wrong, because it is visible without opening the
paper. This checks all three against each other AND against the tables and
CSVs the values were computed from -- not against one another only, which
would pass a consistent error.

Each claim names the file it is verified against. Where the source is a CSV
the value is recomputed; where it is a table the table row is parsed out of
body.tex.

    python check_numbers.py
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent

DOCS = {
    "abstract": HERE / "main.tex",
    "keypoints": HERE / "keypoints_brief.tex",
    "keypoints-long": HERE / "keypoints.tex",
    "cover letter": HERE / "cover_letter.tex",
}

rows: list[tuple[str, str, str, bool, str]] = []


def note(claim, expect, source, ok, detail=""):
    rows.append((claim, expect, source, ok, detail))


def text(p: Path) -> str:
    s = p.read_text(encoding="utf8")
    s = re.sub(r"^\s*%.*$", "", s, flags=re.M)          # strip comments
    return re.sub(r"\s+", " ", s)


def abstract_of(p: Path) -> str:
    s = text(p)
    m = re.search(r"\\abstract\{", s)
    if m:
        d, j = 0, m.end() - 1
        while j < len(s):
            if s[j] == "{":
                d += 1
            elif s[j] == "}":
                d -= 1
                if d == 0:
                    break
            j += 1
        return s[m.end():j]
    return re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}",
                     s, re.S).group(1)


def main() -> int:
    # --dir points the DOCUMENT reads at a scratch tree so the negative
    # controls can exercise this checker on deliberately broken copies.
    # ROOT is left alone: the CSV the envelope figures are recomputed from
    # is the real one either way, which is what makes a fixture meaningful.
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=None)
    here = Path(ap.parse_args().dir) if ap.parse_args().dir else HERE
    docs_src = {k: here / v.name for k, v in DOCS.items()}

    body = text(here / "body.tex")
    docs = {k: (abstract_of(v) if k == "abstract" else text(v))
            for k, v in docs_src.items()}

    # ---- envelope: recomputed from the CSV, not copied from the paper ----
    csv_p = ROOT / "figures" / "envelope_v2_data.csv"
    with open(csv_p) as f:
        env = list(csv.DictReader(f))
    n_img = sum(int(r["n"]) for r in env)
    iou = [float(r["iou_mean"]) for r in env]
    f1cc = [float(r["f1_cc"]) for r in env]
    src = "figures/envelope_v2_data.csv"
    for label, got, want in (("IoU low", iou[0], "0.832"),
                             ("IoU high", iou[-1], "0.905"),
                             ("CC F1 low", f1cc[0], "0.416"),
                             ("CC F1 high", f1cc[-1], "0.017")):
        note(f"{label} = {want}", want, src,
             f"{got:.3f}" == want, f"recomputed {got:.6f}")
    note(f"confluence sample n = {n_img}", str(n_img), src,
         n_img == 180, f"{len(env)} bins x {env[0]['n']}")

    # ---- Table 6 panel (a): parsed out of body.tex ----
    t6 = {}
    for line in body.split(r"\\"):
        m = re.match(r"\s*(Cellpose|Ours, detection-optimal|"
                     r"Ours, measurement-optimal|Connected components)\s*&"
                     r"\s*([\d.]+)\s*&\s*([\d.]+\\?%|---)", line)
        if m and m.group(1) not in t6:
            t6[m.group(1)] = m.group(2)
    # The measurement-optimal F1 is RECOMPUTED from the frozen-split CSV, not
    # asserted as a literal. It was a literal until now, and the literal was
    # wrong: optimize/test_frozen.csv gives 0.5755 for the min-|bias| row,
    # which is 0.576 at the document's three decimals, while every one of the
    # fifteen sites printed 0.575. The check compared body.tex against a
    # hardcoded copy of body.tex's own error and therefore enforced it --
    # the same false-pass signature as the rest of this project's history.
    #
    # Cellpose's 0.815 and the detection-optimal 0.709 are recomputed too,
    # from the baseline-comparison summary. An earlier revision of this block
    # asserted them as literals on the grounds that "no CSV on disk carries
    # them" -- which was simply false: baselines/baseline_summary.csv has
    # carried all three overall_f1 values the whole time. That would have
    # been the seventh instance of the same false pass, so it is recorded
    # here rather than quietly corrected.
    frozen = ROOT / "optimize" / "test_frozen.csv"
    with open(frozen) as fh:
        rows_f = {r["selected_for"]: r for r in csv.DictReader(fh)}
    meas = float(rows_f["min |bias|"]["test_f1"])
    want_meas = f"{meas:.3f}"
    note(f"F1 Ours, measurement-optimal = {want_meas}", want_meas,
         "recomputed from optimize/test_frozen.csv",
         t6.get("Ours, measurement-optimal") == want_meas,
         f"table says {t6.get('Ours, measurement-optimal')}, "
         f"CSV gives {meas} -> {want_meas}")

    basef = ROOT / "baselines" / "baseline_summary.csv"
    with open(basef) as fh:
        base = {r["method"]: r["overall_f1"] for r in csv.DictReader(fh)}
    for who, key in (("Cellpose", "Cellpose"),
                     ("Ours, detection-optimal", "ours (watershed)")):
        want = f"{float(base[key]):.3f}"
        note(f"F1 {who} = {want}", want,
             "recomputed from baselines/baseline_summary.csv",
             t6.get(who) == want,
             f"table says {t6.get(who)}, CSV gives {base[key]}")

    # ---- values that must appear identically wherever they appear ----
    # The Key Points no longer carry performance statistics: the B17 form
    # was adjudicated at <=160 words with metric values removed, matching
    # the three published exemplars, none of which prints an F1 or a p-value
    # in the box. So the metric rows below are scoped to the abstract and
    # cover letter, which do still carry them. The two rows that remain
    # keypoints-scoped are a coverage fraction and a parameter count, both
    # of which survive in the box by design -- and this map is what would
    # catch it if either silently dropped out.
    SHARED = {
        "0.832": ("IoU floor", ["abstract", "cover letter"]),
        "0.905": ("IoU ceiling", ["abstract", "cover letter"]),
        "0.416": ("CC F1 floor", ["cover letter"]),
        "0.017": ("CC F1 ceiling", ["cover letter"]),
        "0.815": ("Cellpose F1", ["abstract", "cover letter"]),
        "0.709": ("ours F1", ["abstract", "cover letter"]),
        "18.7": ("CC coverage failure %", ["abstract", "keypoints"]),
        "1,419": ("full post-attachment set", ["abstract"]),
        "33": ("head parameter count",
               ["abstract", "keypoints", "cover letter"]),
    }
    for val, (what, where) in SHARED.items():
        miss = [d for d in where
                if val.replace(",", "{,}") not in docs[d]
                and val not in docs[d]]
        note(f"{what} ({val}) appears in {', '.join(where)}", val,
             "cross-document", not miss,
             f"absent from: {', '.join(miss)}" if miss else "")

    # ---- the abstract must not carry a corpus total ----
    # Scope is the three front-matter documents only. body.tex legitimately
    # carries "1.6 million" when it describes the LIVECell corpus itself
    # (body.tex, Introduction), so naming the scope here matters: the label
    # used to read "reader-facing text", which a passing line made look like
    # a whole-manuscript guarantee it never was.
    scope = "abstract, Key Points, cover letter"
    for bad, why in (("1.09 million", "descriptive atlas, not the results"),
                     ("1.6 million", "LIVECell corpus total")):
        present = [d for d, t in docs.items() if bad in t]
        note(f"no '{bad}' in {scope}", "absent", why,
             not present,
             f"found in: {', '.join(present)}" if present else "")

    # ---- precision-pair: one quantity, one precision, everywhere ----
    # The abstract was corrected from 0.83/0.90 and 0.42/0.02 to three
    # decimals so that an editor reading the abstract, Key Points and cover
    # letter side by side does not read one quantity as two measurements
    # (main.tex). The Introduction kept the rounded form for six batches
    # because this check did not look at body.tex. It does now.
    #
    # The rule is scoped, not blanket: a rounded value is only a failure in a
    # sentence that both names the quantity and states it as a range with
    # "from". That leaves the summarizing "remained between 0.83 and 0.90"
    # (body.tex, Results) alone, which is immediately followed by the exact
    # per-bin values, while catching "rises monotonically from 0.83 to 0.90".
    PRECISION = [
        ("foreground IoU", r"intersection-over-union",
         ("0.832", "0.83"), ("0.905", "0.90")),
        ("connected-component detection F1", r"detection F1|matched-instance F1",
         ("0.416", "0.42"), ("0.017", "0.02")),
    ]
    prose = dict(docs)
    prose["body"] = body
    for what, kw, *pairs in PRECISION:
        offenders = []
        for dname, dtext in prose.items():
            for sent in re.split(r"(?<=[.!?])\s+", dtext):
                if not re.search(kw, sent) or " from " not in sent:
                    continue
                for good, rounded in pairs:
                    if re.search(rf"(?<![\d.]){re.escape(rounded)}(?![\d])", sent) \
                            and good not in sent:
                        offenders.append(f"{dname}: '{rounded}' should be {good}")
        note(f"{what} stated at one precision", "3 dp",
             "main.tex precision note; body.tex", not offenders,
             "; ".join(sorted(set(offenders))))

    # ---- Key Points sentence count against the journal's stated rule ----
    kp = (here / "keypoints_brief.tex").read_text(encoding="utf8")
    kp = re.sub(r"^\s*%.*$", "", kp, flags=re.M)
    items = re.split(r"\\item", kp)[1:]
    sents = sum(len([x for x in re.split(r"(?<=[.!?])\s+",
                                         i.split(r"\end{itemize}")[0].strip())
                     if len(x.strip()) > 12]) for i in items)
    note(f"Key Points = {sents} sentences (journal allows 3-5)",
         "3-5", "journal author guidelines", 3 <= sents <= 5,
         f"{len(items)} bullets")

    # ---- report ----
    bad = [r for r in rows if not r[3]]
    w = max(len(r[0]) for r in rows)
    print(f"{'claim':{w}s}  source")
    print("-" * (w + 34))
    for claim, _, source, ok, detail in rows:
        mark = "ok  " if ok else "FAIL"
        print(f"[{mark}] {claim:{w}s}  {source}")
        if detail and not ok:
            print(f"{'':{w + 9}s}{detail}")
    print("-" * (w + 34))
    print(f"{len(rows) - len(bad)}/{len(rows)} checks passed")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
