#!/usr/bin/env python3
"""
Verify the TEXT INSIDE the figures against the manuscript's claims.

Every other check in this project reads .tex. That is a structural blind
spot: a claim baked into a figure asset is invisible to a prose grep, cannot
be found by searching the manuscript, and survives every revision of the
text around it. Two such errors shipped through six batches --

  * Figure 1's outcomes box still read "MCF7: fabricated by two unrelated
    error sources" long after that claim was retired;
  * Figure 6 printed BT474 (B) and A172 (A) because its generator read a
    stale lineage table, contradicting Table 5 and the Discussion sentence
    "BT-474 is a Tier A lineage".

Both were found by eye. This checker exists so the next one is not.

Text is read from the PDF content stream directly, not through Ghostscript.
That is not a preference, it is a correctness requirement: Ghostscript's
txtwrite device emits the kerning chunks of a TJ array in REVERSE order, so
"two unrelated error sources" comes out as "cesor sourrelated ertwo unr" and
a search for "two unrelated" silently finds nothing. The negative control
below was failing for exactly that reason. The content stream holds the
chunks in drawing order -- (two unr) (elated er) (r) (or sour) (ces) -- so
concatenating them reconstructs the string exactly.

The side benefit is that this checker has no external binary dependency,
which matters for a script that ships in the repository.

    python check_figure_text.py
    python check_figure_text.py --dir some/other/folder
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent

sys.path.insert(0, str(HERE))
from check_figure_resolution import objects, content_streams   # noqa: E402

# Claims retired from the manuscript. If one reappears in a figure, the
# figure is asserting something the text no longer says.
FORBIDDEN = [
    ("fabricated by", "the retired MCF7 double-error claim"),
    ("two unrelated", "the retired MCF7 double-error claim"),
    ("opposite direction",
     "superseded phrasing; the paper says 'inverts its direction'"),
    ("reverses sign", "explicitly ruled out wording"),
    ("opposite-signed", "retired MCF7 double-error claim, in paraphrase"),
    ("failure modes", "retired MCF7 double-error claim, in paraphrase"),
]

# The same retired claims must not survive in PROSE either. The MCF7
# double-error claim was retired from the figures and then reappeared in the
# Conclusion as "opposite-signed measurement error under two unrelated
# failure modes" -- a paraphrase that passed every string grep aimed at the
# figures. Only one failure mode survives the n = 672 correction, so the
# prose scope is not optional.
PROSE_SCOPE = ["body.tex"]

# figure stem -> [(number as printed, what it is, how it is verified)]
NUMBERS = {
    "Fig1_architecture": [
        ("4,875", "images in the descriptive atlas", "atlas_images"),
        ("2.22", "backbone parameters, millions", "backbone_m"),
        ("304.6", "Cellpose-SAM parameters, millions", "const"),
        ("137", "parameter ratio", "ratio_params"),
        ("87", "percent of Cellpose F1", "ratio_f1"),
    ],
    "Fig2_architecture": [
        ("33", "parameters in the distance head", "head_inference"),
        ("2.22", "backbone parameters, millions", "backbone_m"),
    ],
    "Fig2_micrographs": [
        ("315", "expert instances in the shown field", "const"),
        ("370", "watershed instances in the shown field", "const"),
        ("117.5", "watershed as percent of expert", "ratio_recover"),
    ],
    "Fig3_mechanism": [
        ("370", "watershed instances in the shown field", "const"),
    ],
    "Fig5_merged": [
        ("0.832", "foreground IoU, sparsest bin", "iou_lo"),
        ("0.905", "foreground IoU, most crowded bin", "iou_hi"),
    ],
}

rows: list[tuple[str, str, bool, str]] = []


def note(fig, claim, ok, detail=""):
    rows.append((fig, claim, ok, detail))


ESC = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f",
       "(": "(", ")": ")", "\\": "\\"}


def unescape(s: str) -> str:
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            nxt = s[i + 1]
            if nxt in ESC:
                out.append(ESC[nxt])
                i += 2
                continue
            if nxt.isdigit():                      # octal escape
                j = i + 1
                while j < len(s) and j < i + 4 and s[j].isdigit():
                    j += 1
                out.append(chr(int(s[i + 1:j], 8) & 0xFF))
                i = j
                continue
            out.append(nxt)
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


STR_TOKEN = re.compile(r"\(((?:[^()\\]|\\.)*)\)|<([0-9A-Fa-f\s]*)>")
# A new text object, or a repositioning inside one, starts a new visual run.
BREAK = re.compile(r"\bBT\b|\bET\b|\bT[dD]\b|\bTm\b|\bT\*\b")


def extract(pdf: Path) -> str:
    """Visible text, one visual run per line, in drawing order."""
    objs = objects(pdf.read_bytes())
    runs: list[str] = []
    for s in content_streams(objs):
        cur: list[str] = []
        pos = 0
        for m in re.finditer(r"BT(.*?)ET", s, re.S):
            block = m.group(1)
            i = 0
            for tok in re.finditer(
                    r"\(((?:[^()\\]|\\.)*)\)|<([0-9A-Fa-f\s]*)>|"
                    r"(\bBT\b|\bET\b|\bT[dD]\b|\bTm\b|\bT\*\b)", block):
                if tok.group(3):
                    if cur:
                        runs.append("".join(cur))
                        cur = []
                elif tok.group(1) is not None:
                    cur.append(unescape(tok.group(1)))
                elif tok.group(2):
                    h = re.sub(r"\s", "", tok.group(2))
                    if len(h) % 2 == 0:
                        cur.append(bytes.fromhex(h).decode("latin-1"))
            if cur:
                runs.append("".join(cur))
                cur = []
    return "\n".join(w for w in (widechar(r) for r in runs) if w.strip())


def widechar(run: str) -> str:
    """Re-decode a run that holds two-byte CIDs.

    Fig2_atlas embeds its fonts with a two-byte encoding, so a literal
    string in its content stream is b'\\x000\\x00.\\x000' -- "0.0" in
    UTF-16BE. Decoding that byte-wise, which is what the rest of this
    extractor does and what every other figure needs, yields NUL-interleaved
    mush: no tier pair matches, no forbidden phrase matches, and every
    assertion against that figure silently passes on garbage.

    That is the same false-pass signature as the rest of this project's
    history, and it hid the fact that the atlas figure -- the one whose
    tier letters this checker exists to police -- was never actually being
    read. A run is re-decoded when it is even-length and every other byte
    is NUL, which is what a two-byte encoding of Latin text looks like and
    what no single-byte run ever looks like.
    """
    if "\x00" not in run or len(run) % 2:
        return run
    raw = run.encode("latin-1", "replace")
    if any(raw[i] != 0 for i in range(0, len(raw), 2)):
        return run
    try:
        return raw.decode("utf-16-be")
    except UnicodeDecodeError:
        return run


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def contains(text: str, phrase: str) -> bool:
    """Substring test on the reconstructed text.

    Checked both against the whole document text -- so a phrase split across
    two visual lines is still caught -- and against each run on its own,
    which is what makes the whole-text form safe from stitching two unrelated
    labels into a false positive.
    """
    p = norm(phrase)
    if any(p in norm(r) for r in text.split("\n")):
        return True
    return p in norm(text)


def expected_numbers() -> dict[str, str]:
    """Recompute each load-bearing figure number from its source on disk."""
    out = {}
    env = ROOT / "figures" / "envelope_v2_data.csv"
    with open(env) as f:
        rowsx = list(csv.DictReader(f))
    out["iou_lo"] = f"{float(rowsx[0]['iou_mean']):.3f}"
    out["iou_hi"] = f"{float(rowsx[-1]['iou_mean']):.3f}"

    per = ROOT / "fig7_expanded" / "time_out" / "time_per_image.csv"
    with open(per) as f:
        n = sum(1 for _ in csv.DictReader(f))
    out["atlas_images"] = f"{n:,}"

    # 0.709 and 0.815 were literals here until the same false-pass sweep that
    # caught them in check_numbers.py. baselines/baseline_summary.csv carries
    # both, so the 87% Figure 1 prints is now derived from disk, not from a
    # pair of numbers typed in twice.
    basef = ROOT / "baselines" / "baseline_summary.csv"
    with open(basef) as f:
        base = {r["method"]: float(r["overall_f1"]) for r in csv.DictReader(f)}
    # Backbone size, recomputed from the checkpoint under the DEFINED
    # quantity: trainable parameters, buffers excluded.
    #
    # This nearly became the eighth false pass, in the opposite direction to
    # the others. A raw sum of the 166 stored tensors gives 2,225,069 ->
    # 2.23 M, and on that basis the printed 2.22 M looked like a truncation
    # of the same class as the 0.575/0.576 defect. It is not. 60 of those
    # tensors are BatchNorm buffers -- running_mean (1,664), running_var
    # (1,664) and num_batches_tracked (20), 3,348 elements over 20 BN layers
    # -- and buffers are not parameters. Excluding them gives 2,221,721 ->
    # 2.22 M, which is exactly what the paper prints. The measurement was
    # wrong, not the manuscript. Two independent routes agree on 2,221,721:
    # this name partition, and sum(p.numel() for p in model.parameters()) on
    # the instantiated model after a strict load.
    ckpt = ROOT / "runs" / "instance" / "best.pt"
    BUFFERS = ("running_mean", "running_var", "num_batches_tracked")
    import torch                                   # local: only this needs it
    sd = torch.load(ckpt, map_location="cpu", weights_only=False)
    sd = sd["model_state_dict"]
    params = {k: v for k, v in sd.items() if not k.endswith(BUFFERS)}
    n_param = sum(v.numel() for v in params.values())
    n_heads = sum(v.numel() for k, v in params.items()
                  if k.startswith(("dist_head", "bnd_head")))
    out["backbone_m"] = f"{n_param / 1e6:.2f}"
    out["heads_total"] = str(n_heads)
    out["head_inference"] = str(
        sum(v.numel() for k, v in params.items() if k.startswith("dist_head")))

    out["ratio_params"] = f"{304.6 / float(out['backbone_m']):.0f}"
    out["ratio_f1"] = f"{base['ours (watershed)'] / base['Cellpose'] * 100:.0f}"
    out["ratio_recover"] = f"{370 / 315 * 100:.1f}"
    return out


def tier_truth() -> dict[str, str]:
    """Tier letters as the manuscript prints them, from the lineage table."""
    p = ROOT / "final_table_all" / "final_lineage_table.csv"
    with open(p) as f:
        t = {r["cell_type"]: r["tier"] for r in csv.DictReader(f)}
    # phase7 is run with --demote BV2, matching Table 5's dagger footnote.
    t["BV2"] = "C"
    # The artwork prints the hyphenated ATCC forms that LIVECell, the tables
    # and the body text all use; the CSV carries the pipeline's sanitized
    # identifiers. Key the table under the printed form, or the lookup below
    # returns None for every hyphenated label and the assertion disappears
    # instead of failing.
    for raw, shown in (("BT474", "BT-474"), ("BV2", "BV-2")):
        if raw in t:
            t[shown] = t.pop(raw)
    return t


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(HERE))
    a = ap.parse_args()
    D = Path(a.dir)

    figs = sorted(p for p in D.glob("*.pdf")
                  if p.name not in {"main.pdf", "cover_letter.pdf",
                                    "COMPILED_PREVIEW.pdf"})
    if not figs:
        print("no figure PDFs found in", D)
        return 1

    exp = expected_numbers()
    texts = {p.stem: extract(p) for p in figs}

    # 1 ---- retired claims must not appear anywhere -------------------
    for stem, txt in sorted(texts.items()):
        for phrase, why in FORBIDDEN:
            hit = contains(txt, phrase)
            note(stem, f"does not contain \"{phrase}\"", not hit,
                 f"FOUND -- {why}" if hit else "")

    # 1a --- and not in the OTHER tree's figures either -----------------
    # This check used to run against whichever tree --dir pointed at, which
    # in practice was always paper2_bib. On 2026-08-11 the CAS fallback was
    # found still shipping the pre-fix Fig1_architecture.pdf, whose outcomes
    # box read "MCF7: fabricated by two unrelated error sources" -- the exact
    # retracted claim this list exists to catch. The submission tree had been
    # regenerated; the fallback had not, and nothing looked. A retired claim
    # must not survive in ANY tree that can be compiled and sent, so the
    # sweep now always covers both.
    for sib in ("paper2_bib", "paper2_overleaf_current"):
        sd = ROOT / sib
        if not sd.is_dir() or sd.resolve() == D.resolve():
            continue
        sibfigs = sorted(p for p in sd.glob("*.pdf")
                         if p.name not in {"main.pdf", "cover_letter.pdf",
                                           "COMPILED_PREVIEW.pdf"})
        for p in sibfigs:
            txt = extract(p)
            for phrase, why in FORBIDDEN:
                hit = contains(txt, phrase)
                note(f"{sib}/{p.stem}", f"does not contain \"{phrase}\"",
                     not hit, f"FOUND -- {why}" if hit else "")

    # 1b --- retired claims must not survive in the prose either --------
    for stem in PROSE_SCOPE:
        src = D / stem
        if not src.is_file():
            continue
        txt = src.read_text(encoding="utf8")
        # Normalize before matching. Collapsing whitespace alone is not
        # enough: the recurring failure in this project is a phrase that
        # wraps, and it wraps three ways -- across a newline ("six of\nsix"),
        # across a paragraph indent, and at a hyphenation point
        # ("manu-\nfactured", "sup- ported"). norm() strips every
        # non-alphanumeric character, so all three rejoin and no forbidden
        # phrase can hide in the line breaks. A line-based grep missed a live
        # retraction site here once; this is the class fix.
        flat = norm(txt)
        for phrase, why in FORBIDDEN:
            hit = norm(phrase) in flat
            note(stem, f'does not contain "{phrase}"', not hit,
                 f"FOUND -- {why}" if hit else "")

    # 2 ---- atlas tier letters against the lineage table ---------------
    # Search each expected lineage by name rather than harvesting whatever
    # matches a generic "word (X)" pattern. Fig2_atlas positions every glyph
    # separately, so its runs are one character long and a free-running
    # pattern cannot span a label; and a greedy pattern over the collapsed
    # text happily swallows the tail of the preceding word ("condensing" +
    # "SK-OV-3"). Anchoring on the known names removes both failure modes,
    # and makes a lineage that is present-but-unrecognised a FAILURE rather
    # than a silent skip -- which is how the unhyphenated labels survived.
    truth = tier_truth()
    for stem, txt in sorted(texts.items()):
        flat = re.sub(r"\s+", "", txt)
        found = {}
        for name in truth:
            m = re.search(re.escape(re.sub(r"\s+", "", name)) + r"\(([ABC])\)",
                          flat)
            if m:
                found[name] = m.group(1)
        if not found:
            continue
        for name, letter in sorted(found.items()):
            want = truth[name]
            note(stem, f"tier {name} = {want}", letter == want,
                 f"figure prints ({letter}), lineage table says ({want})"
                 if letter != want else "")
        missing = sorted(set(truth) - set(found))
        note(stem, f"all {len(truth)} lineages carry a tier letter",
             not missing, f"absent: {', '.join(missing)}" if missing else "")

    # 3 ---- load-bearing numbers --------------------------------------
    for stem, want in NUMBERS.items():
        if stem not in texts:
            note(stem, "figure present", False, "PDF not found")
            continue
        txt = texts[stem]
        for printed, what, how in want:
            ok = contains(txt, printed)
            src = exp.get(how)
            detail = ""
            if src is not None and src.replace(",", "") != printed.replace(",", ""):
                ok = False
                detail = f"source on disk gives {src}, figure prints {printed}"
            elif not ok:
                detail = f"{printed} ({what}) not found in the figure text"
            note(stem, f"prints {printed} -- {what}", ok, detail)

    # ---- report -------------------------------------------------------
    bad = [r for r in rows if not r[2]]
    w = max(len(r[1]) for r in rows)
    cur = None
    for fig, claim, ok, detail in rows:
        if fig != cur:
            print(f"\n{fig}")
            cur = fig
        print(f"  [{'ok  ' if ok else 'FAIL'}] {claim:{w}s}"
              + (f"\n         {detail}" if detail else ""))
    print("\n" + "-" * (w + 12))
    print(f"{len(rows) - len(bad)}/{len(rows)} figure-text checks passed")
    for fig, claim, _, detail in bad:
        print(f"  FAIL {fig}: {claim} -- {detail}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
