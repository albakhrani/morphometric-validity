#!/usr/bin/env python3
"""
Negative controls for the three submission checkers.

A checker that has only ever been run on input it passes has not been shown
to detect anything. Two of these three were wrong on their first version,
both with the same signature -- they reported success on input they had
failed to parse:

  * check_figure_resolution.py reported all seven figures "fully vector"
    when four of them carried raster XObjects, because matplotlib writes
    /XObject as an indirect reference and only the inline form was handled.
  * check_cite_order.py compares .aux against .bbl, which is necessary but
    not sufficient: it cannot see what the PDF actually prints.

So each checker is exercised in BOTH directions here: input it must pass,
and input it must fail, with the failure value asserted rather than merely
the fact of failure. Fixtures are generated at run time, so this file has no
binary dependencies and nothing to keep in sync.

    python test_checkers.py

Exit status is 0 only if every control behaves as specified.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
PY = sys.executable
OUP_TEXTWIDTH = 526.376          # pt, the measure the figures are authored at
DPI_FLOOR = 300.0
TYPE_FLOOR = 6.0

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f"\n         {detail}" if detail else ""))


def run(script: str, *args: str) -> str:
    p = subprocess.run([PY, str(HERE / script), *args],
                       capture_output=True, text=True)
    return p.stdout + p.stderr


def mpl():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


# ---------------------------------------------------------------- fixtures
def fig_low_dpi(path: Path, save_dpi: int = 150) -> float:
    """A figure whose embedded raster is too coarse to print, by a known
    amount.

    What decides the stored pixel count is savefig's dpi, not the size of
    the source array: matplotlib resamples each imshow to the axes size in
    DEVICE pixels. Saving a small array at high dpi therefore produces a
    LARGE raster, which is how the first version of this fixture ended up
    asserting 16 dpi against a figure stored at 600.

    The figure is authored at exactly \\textwidth and saved without a tight
    bbox, so artwork width == placed width, the include scale is 1.0, and
    the effective dpi at placed size is exactly save_dpi. That makes the
    expected value predictable rather than approximated.
    """
    import numpy as np
    plt = mpl()
    w_in = OUP_TEXTWIDTH / 72.0
    fig, ax = plt.subplots(figsize=(w_in, w_in / 2))
    ax.imshow(np.random.default_rng(0).random((400, 400)), cmap="gray")
    ax.set_axis_off()
    fig.subplots_adjust(0, 0, 1, 1)
    fig.savefig(path, dpi=save_dpi)     # no tight bbox: artwork == textwidth
    plt.close(fig)
    return float(save_dpi)


def fig_tiny_type(path: Path, pt: float = 4.0) -> None:
    plt = mpl()
    w_in = OUP_TEXTWIDTH / 72.0
    fig, ax = plt.subplots(figsize=(w_in, w_in / 3))
    ax.text(0.5, 0.5, "deliberately tiny label", fontsize=pt, ha="center")
    ax.set_axis_off()
    fig.savefig(path, dpi=600)
    plt.close(fig)


def fig_mathtext(path: Path, base: float = 7.0) -> None:
    """Base size above the floor, subscript below it.

    This is the original miss: source font sizes were verified and the
    figure passed, but mathtext renders sub/superscripts at about 0.7x, so
    a 7 pt label printed a 4.9 pt subscript.
    """
    plt = mpl()
    w_in = OUP_TEXTWIDTH / 72.0
    fig, ax = plt.subplots(figsize=(w_in, w_in / 3))
    ax.text(0.5, 0.5, r"$q_{\mathrm{cell}} = P/\sqrt{A}$",
            fontsize=base, ha="center")
    ax.set_axis_off()
    fig.savefig(path, dpi=600)
    plt.close(fig)


def fig_good(path: Path) -> None:
    plt = mpl()
    w_in = OUP_TEXTWIDTH / 72.0
    fig, ax = plt.subplots(figsize=(w_in, w_in / 3))
    ax.plot([0, 1], [0, 1])
    ax.set_xlabel("clearly legible label", fontsize=9)
    ax.tick_params(labelsize=9)
    fig.savefig(path, dpi=600, bbox_inches="tight")
    plt.close(fig)


def break_xobject(src: Path, dst: Path) -> bool:
    """Reproduce the historical parser bug in a fixture.

    Renames the /XObject resource key so the image XObjects are still in the
    file but can no longer be reached from the page. Byte length is
    unchanged, so no offsets move. The checker must report ERROR, not
    "fully vector" -- that silent-success path is the exact defect this
    guard exists to prevent.
    """
    data = src.read_bytes()
    if b"/XObject" not in data:
        return False
    dst.write_bytes(data.replace(b"/XObject", b"/XObjecZ", 1))
    return True


# ------------------------------------------------------------------- tests
def test_resolution(tmp: Path) -> None:
    print("\ncheck_figure_resolution.py")
    low = tmp / "neg_lowdpi.pdf"
    expect = fig_low_dpi(low)
    out = run("check_figure_resolution.py", "--venue", "oup", str(low))
    m = re.search(r"neg_lowdpi\s+[\d.]+\s+[\d.]+\s+\S+\s+[\d.]+\"\s+(\d+)",
                  out)
    got = float(m.group(1)) if m else -1
    check("low-dpi raster is reported FAIL",
          "FAIL  below 300 dpi" in out and "FAIL count: 1" in out,
          out.strip().splitlines()[-1] if not m else "")
    check(f"reported dpi matches an independent calculation "
          f"({got:.0f} vs {expect:.0f})",
          m is not None and abs(got - expect) / expect < 0.05)

    good = tmp / "pos_vector.pdf"
    fig_good(good)
    out = run("check_figure_resolution.py", "--venue", "oup", str(good))
    check("a vector figure still passes (not a checker that always fails)",
          "FAIL count: 0" in out)

    broken = tmp / "neg_unreachable.pdf"
    if break_xobject(low, broken):
        out = run("check_figure_resolution.py", "--venue", "oup",
                  str(broken))
        check("guard fires: images present but unreachable -> ERROR",
              "ERROR" in out and "parser bug" in out and
              "fully vector" not in out,
              "reported 'fully vector' -- the false-pass path is open"
              if "fully vector" in out else "")
    else:
        check("guard fires: images present but unreachable -> ERROR",
              False, "fixture could not be built")


def test_type(tmp: Path) -> None:
    print("\ncheck_figure_type.py")
    tiny = tmp / "neg_4pt.pdf"
    fig_tiny_type(tiny, 4.0)
    out = run("check_figure_type.py", "--venue", "oup", str(tiny))
    m = re.search(r"neg_4pt\s+[\d.]+\s+[\d.]+\s+([\d.]+)", out)
    got = float(m.group(1)) if m else -1
    check("4 pt type is reported FAIL",
          "FAIL" in out and "FAIL count: 1" in out)
    check(f"reported size is the 4 pt that was drawn (got {got})",
          m is not None and abs(got - 4.0) < 0.6)

    mt = tmp / "neg_mathtext.pdf"
    fig_mathtext(mt, 7.0)
    out = run("check_figure_type.py", "--venue", "oup", str(mt))
    m = re.search(r"neg_mathtext\s+[\d.]+\s+[\d.]+\s+([\d.]+)", out)
    got = float(m.group(1)) if m else -1
    check("mathtext subscript below the floor is caught "
          f"(base 7 pt drew {got} pt)",
          m is not None and got < TYPE_FLOOR,
          "this is the original miss: source sizes were checked, "
          "rendered sizes were not" if got >= TYPE_FLOOR else "")

    good = tmp / "pos_type.pdf"
    fig_good(good)
    out = run("check_figure_type.py", "--venue", "oup", str(good))
    check("legible type still passes", "FAIL count: 0" in out)


BBL = """\\begin{thebibliography}{10}

\\bibitem{Alpha}
A.~One.
\\newblock First.

\\bibitem{Beta}
B.~Two.
\\newblock Second.

\\bibitem{Gamma}
C.~Three.
\\newblock Third.

\\end{thebibliography}
"""
AUX = ("\\citation{Alpha}\n\\citation{Beta}\n\\citation{Gamma}\n"
       "\\bibdata{refs}\n")


def test_cite_order(tmp: Path) -> None:
    print("\ncheck_cite_order.py")
    d = tmp / "citeorder"
    d.mkdir()
    (d / "main.aux").write_text(AUX, encoding="latin-1")
    (d / "main.bbl").write_text(BBL, encoding="latin-1")
    out = run("check_cite_order.py", "--dir", str(d))
    check("matching order is reported OK",
          "OK  every reference is numbered by first appearance" in out)

    # Permute two entries: Gamma is emitted where Beta should be.
    permuted = (BBL.replace("\\bibitem{Beta}", "\\bibitem{TMP}")
                   .replace("\\bibitem{Gamma}", "\\bibitem{Beta}")
                   .replace("\\bibitem{TMP}", "\\bibitem{Gamma}"))
    (d / "main.bbl").write_text(permuted, encoding="latin-1")
    out = run("check_cite_order.py", "--dir", str(d))
    check("permuted bibliography is reported OUT OF ORDER",
          "OUT OF ORDER" in out)
    check("both offending positions are named, with expected vs got",
          "expected Beta" in out and "expected Gamma" in out,
          out.strip().splitlines()[-1] if "OUT OF ORDER" in out else "")

    # A cited key missing from the .bbl must not read as success either.
    (d / "main.aux").write_text(AUX + "\\citation{Delta}\n", encoding="latin-1")
    (d / "main.bbl").write_text(BBL, encoding="latin-1")
    out = run("check_cite_order.py", "--dir", str(d))
    check("a cited-but-unemitted key is reported, not ignored",
          "MISMATCH in count" in out and "Delta" in out)


def fig_with_text(path: Path, lines: list[str]) -> None:
    plt = mpl()
    fig, ax = plt.subplots(figsize=(6, 3))
    for i, t in enumerate(lines):
        ax.text(0.05, 0.9 - 0.15 * i, t, fontsize=9)
    ax.set_axis_off()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def test_figure_text(tmp: Path) -> None:
    print("\ncheck_figure_text.py")
    d = tmp / "figtext"
    d.mkdir()

    # A figure asserting the retired MCF7 claim, exactly as Figure 1 did.
    fig_with_text(d / "Fig1_architecture.pdf",
                  ["One rejected phenotype",
                   "MCF7: fabricated by",
                   "two unrelated error sources"])
    # An atlas printing the PRE-SWAP tier letters, exactly as Figure 6 did,
    # in the hyphenated forms the artwork now uses.
    fig_with_text(d / "Fig2_atlas.pdf",
                  ["BT-474 (B)", "A172 (A)", "SkBr3 (A)", "MCF7 (C)",
                   "BV-2 (C)", "Huh7 (A)", "SH-SY5Y (A)", "SK-OV-3 (A)"])

    out = run("check_figure_text.py", "--dir", str(d))
    check("retired phrase 'fabricated by' is caught",
          'FAIL Fig1_architecture: does not contain "fabricated by"' in out)
    check("retired phrase 'two unrelated' is caught",
          'FAIL Fig1_architecture: does not contain "two unrelated"' in out)
    check("pre-swap tier BT-474 (B) is caught",
          "FAIL Fig2_atlas: tier BT-474 = A" in out,
          "the Figure 6 error class must not pass" if
          "FAIL Fig2_atlas: tier BT-474 = A" not in out else "")
    check("pre-swap tier A172 (A) is caught",
          "FAIL Fig2_atlas: tier A172 = B" in out)
    check("correct tier letters in the same figure still pass",
          "[ok  ] tier SkBr3 = A" in out and "[ok  ] tier MCF7 = C" in out)

    # An unhyphenated label must now FAIL rather than be skipped. This is the
    # control for the silent-skip that let BT474 survive: truth.get() used to
    # return None for an unrecognised name and the assertion simply vanished.
    d2 = tmp / "figtext_unhyphenated"
    d2.mkdir()
    fig_with_text(d2 / "Fig2_atlas.pdf",
                  ["BT474 (A)", "BV2 (C)", "A172 (B)", "SkBr3 (A)",
                   "MCF7 (C)", "Huh7 (A)", "SH-SY5Y (A)", "SK-OV-3 (A)"])
    out = run("check_figure_text.py", "--dir", str(d2))
    check("an unhyphenated lineage label is caught, not skipped",
          "FAIL Fig2_atlas: all 8 lineages carry a tier letter" in out
          and "BT-474" in out and "BV-2" in out,
          [l for l in out.splitlines() if "lineages carry" in l][:1])

    # A two-byte-encoded figure must be readable at all. Fig2_atlas embeds
    # its fonts that way, and byte-wise decoding turned every assertion
    # against it into a pass on NUL-interleaved mush.
    from check_figure_text import widechar
    check("two-byte (UTF-16BE) runs are decoded, not read as mush",
          widechar("\x00B\x00T\x00-\x004\x007\x004") == "BT-474")
    check("single-byte runs are left alone by the wide-char path",
          widechar("BT-474") == "BT-474")

    # Positive control: the real figures must pass, so the checker is not
    # simply failing everything put in front of it.
    out = run("check_figure_text.py")
    check("the real figure set passes unchanged",
          "figure-text checks passed" in out and "FAIL" not in out,
          [l for l in out.splitlines() if "FAIL" in l][:1])


CITET_DOC = r"""\documentclass{article}
\usepackage[square,comma,numbers,sort&compress]{natbib}
\begin{document}
The concern was raised by \citet{Alpha} in earlier work.
\begin{thebibliography}{1}
\bibitem{Alpha} A. Author. A title. Journal, 2020.
\end{thebibliography}
\end{document}
"""

UNDEF_DOC = CITET_DOC.replace(r"\citet{Alpha}", r"\citep{Missing}")


def latex(d: Path, stem: str, body: str, passes: int = 2) -> Path:
    """Compile a scratch document. Two passes: natbib needs the .aux to
    exist before it can render a citation at all, and the first pass emits
    the undefined-citation marker instead."""
    (d / f"{stem}.tex").write_text(body, encoding="utf8")
    for _ in range(passes):
        subprocess.run(["pdflatex", "-interaction=nonstopmode", f"{stem}.tex"],
                       cwd=d, capture_output=True, text=True)
    return d / f"{stem}.pdf"


def test_named_refs(tmp: Path) -> None:
    """Named section references must match a heading verbatim.

    Two paraphrases already shipped under the unnumbered-section scheme --
    \\emph{the density-resolved atlas} against "A density-resolved
    morphological atlas", and \\emph{Coverage} against "Coverage: when a
    pipeline measures nothing". Both were found by eye. On its first run
    this checker caught a third that no eye had: the CAS tree carried a
    reference to the OUP heading name, which does not exist in that tree.
    """
    print("\ncheck_named_refs.py")
    d = tmp / "namedrefs"
    d.mkdir()
    HEAD = ("\\subsection{A density-resolved morphological atlas}\n"
            "\\subsection{Coverage: when a pipeline measures nothing}\n")

    (d / "body.tex").write_text(
        HEAD + "Text citing \\emph{A density-resolved morphological atlas} "
               "and \\emph{Coverage: when a pipeline measures nothing}.\n",
        encoding="utf8")
    out = run("check_named_refs.py", "--dir", str(d))
    check("verbatim named references pass",
          "named-reference checks passed" in out and "[FAIL]" not in out,
          [l for l in out.splitlines() if "[FAIL]" in l][:1])

    # The exact paraphrase that shipped, four times.
    (d / "body.tex").write_text(
        HEAD + "Text citing \\emph{the density-resolved atlas}.\n",
        encoding="utf8")
    out = run("check_named_refs.py", "--dir", str(d))
    check("a paraphrased heading reference is caught",
          "[FAIL]" in out and "density-resolved atlas" in out,
          [l for l in out.splitlines() if "FAIL" in l][:1])

    # The truncation that shipped, three times.
    (d / "body.tex").write_text(
        HEAD + "Text citing \\emph{Coverage: when a pipeline} only.\n",
        encoding="utf8")
    out = run("check_named_refs.py", "--dir", str(d))
    check("a truncated heading reference is caught", "[FAIL]" in out)

    # Ordinary emphasis must not be mistaken for a broken reference.
    (d / "body.tex").write_text(
        HEAD + "Recovers \\emph{fewer} lineage directions, and \\emph{all} "
               "of them.\n", encoding="utf8")
    out = run("check_named_refs.py", "--dir", str(d))
    # ---- normalization: a forbidden phrase must not hide in a line break ----
    # The recurring failure in this project is a string match defeated by
    # wrapping: "manu-\nfactured", "sup- ported", "six of\nsix". The last of
    # those hid a live retraction site from a line-based sweep. The prose
    # scope now strips every non-alphanumeric character before matching, so
    # all three rejoin. These three controls are what make that claim real:
    # without them the normalizer has only ever seen text that was already
    # contiguous.
    d2 = Path(tempfile.mkdtemp())
    for fig in HERE.glob("*.pdf"):
        if fig.name not in ("main.pdf", "cover_letter.pdf"):
            shutil.copy2(fig, d2 / fig.name)

    (d2 / "body.tex").write_text(
        "The masks were compared.\nMCF7 was fabricated by\ntwo unrelated "
        "error sources.\n", encoding="utf8")
    out = run("check_figure_text.py", "--dir", str(d2))
    check("a forbidden phrase split across a NEWLINE is caught",
          "fabricated by" in out and "FAIL" in out,
          [l for l in out.splitlines() if "FAIL" in l][:1])

    (d2 / "body.tex").write_text(
        "The masks were compared. MCF7 was fabri-\ncated by two unre-\n"
        "lated error sources.\n", encoding="utf8")
    out = run("check_figure_text.py", "--dir", str(d2))
    check("a forbidden phrase broken at a HYPHENATION point is caught",
          "fabricated by" in out and "FAIL" in out,
          [l for l in out.splitlines() if "FAIL" in l][:1])

    (d2 / "body.tex").write_text(
        "The masks were compared and nothing retired appears here.\n",
        encoding="utf8")
    out = run("check_figure_text.py", "--dir", str(d2))
    check("clean prose is not flagged by the normalizer",
          "FAIL" not in out)

    check("ordinary emphasis is not flagged as a broken reference",
          "[FAIL]" not in out)

    for tree, label in ((HERE, "OUP"),
                        (HERE.parent / "paper2_overleaf_current", "CAS")):
        out = run("check_named_refs.py", "--dir", str(tree))
        check(f"the real {label} tree passes",
              "named-reference checks passed" in out and "[FAIL]" not in out,
              [l for l in out.splitlines() if "[FAIL]" in l][:1])


def test_forbidden_prose_scope(tmp: Path) -> None:
    """Retired claims must not survive in PROSE, not only in figures.

    The MCF7 double-error claim was retired from the artwork and then
    reappeared in the Conclusion as "opposite-signed measurement error under
    two unrelated failure modes" -- a paraphrase every figure-scoped grep
    passed. This control puts it back and requires a FAIL.
    """
    print("\ncheck_figure_text.py -- prose scope")
    d = tmp / "prose"
    d.mkdir()
    shutil.copy(HERE / "Fig5_merged.pdf", d / "Fig5_merged.pdf")

    (d / "body.tex").write_text(
        "Some prose. For one lineage, opposite-signed measurement error "
        "under two unrelated failure modes was observed.\n", encoding="utf8")
    out = run("check_figure_text.py", "--dir", str(d))
    check("a retired claim paraphrased into prose is caught",
          'FAIL body.tex: does not contain "opposite-signed"' in out
          and 'FAIL body.tex: does not contain "two unrelated"' in out,
          [l for l in out.splitlines() if "body.tex" in l and "FAIL" in l][:2])

    (d / "body.tex").write_text(
        "Some prose with nothing retired in it at all.\n", encoding="utf8")
    out = run("check_figure_text.py", "--dir", str(d))
    check("clean prose passes the same scope",
          "FAIL body.tex" not in out)

    check("the real body.tex carries none of the retired claims",
          "FAIL body.tex" not in run("check_figure_text.py"))


def test_backbone_param_definition(tmp: Path) -> None:
    """The backbone count must be trainable parameters, buffers excluded.

    Guards a near-miss in the opposite direction to this project's usual
    failure: summing the checkpoint file gives 2,225,069 -> 2.23 M and makes
    the correct printed 2.22 M look like a truncation. The 3,348 BatchNorm
    buffer elements are the whole difference.
    """
    print("\ncheck_figure_text.py -- parameter definition")
    from check_figure_text import expected_numbers, ROOT
    import torch

    e = expected_numbers()
    check("backbone recomputed from the checkpoint reads 2.22",
          e["backbone_m"] == "2.22", f'got {e["backbone_m"]}')
    check("added heads total 66, inference head 33",
          e["heads_total"] == "66" and e["head_inference"] == "33",
          f'{e["heads_total"]} / {e["head_inference"]}')

    sd = torch.load(ROOT / "runs" / "instance" / "best.pt",
                    map_location="cpu", weights_only=False)["model_state_dict"]
    BUFFERS = ("running_mean", "running_var", "num_batches_tracked")
    raw = sum(v.numel() for v in sd.values())
    par = sum(v.numel() for k, v in sd.items() if not k.endswith(BUFFERS))
    check("buffers are actually present and material (else this guards nothing)",
          raw - par == 3348, f"buffer elements {raw - par}")
    check("summing the FILE would give the wrong figure -- 2.23, not 2.22",
          f"{raw / 1e6:.2f}" == "2.23" and f"{par / 1e6:.2f}" == "2.22",
          f"file {raw / 1e6:.4f} vs parameters {par / 1e6:.4f}")
    check("137x ratio is stable under the parameter-only definition",
          f"{304.6 / (par / 1e6):.0f}" == "137")


def test_pdf_placeholders(tmp: Path) -> None:
    print("\ncheck_pdf_placeholders.py")
    d = tmp / "pdfsweep"
    d.mkdir()

    # The exact defect that shipped: \citet against a numeric bibliography.
    pdf = latex(d, "citet", CITET_DOC, passes=2)
    if not pdf.is_file():
        check("scratch pdflatex build available", False,
              "pdflatex did not produce a PDF; control skipped")
        return
    out = run("check_pdf_placeholders.py", "--pdf", str(pdf))
    check("a \\citet under the numeric style is caught",
          "FAIL" in out and "(author?)" in out)
    check("the fix is named in the failure, not just the symptom",
          "\\citep" in out)

    # One pass only: the citation is still undefined, so natbib prints [?].
    pdf2 = latex(d, "undef", UNDEF_DOC, passes=1)
    out = run("check_pdf_placeholders.py", "--pdf", str(pdf2))
    check("an unresolved citation key is caught",
          "FAIL" in out and "?]" in out)

    # The submission PDF must pass, and must still report the one
    # deliberately unresolved placeholder rather than failing on it.
    out = run("check_pdf_placeholders.py")
    check("the real main.pdf passes the sweep",
          "0 failures" in out,
          [l for l in out.splitlines() if "FAIL" in l][:1])
    # The repository URL is now inserted, so the sweep must report the
    # placeholder as gone. Kept as a control rather than deleted: if a future
    # edit reintroduces the bracketed placeholder, this flips back to [known]
    # and the assertion fails, which is the signal we want.
    check("[REPOSITORY URL] is resolved -- sweep reports it gone",
          "[gone ]" in out and "REPOSITORY URL" in out,
          [l for l in out.splitlines() if "REPOSITORY URL" in l][:1])


def test_numbers_precision(tmp: Path) -> None:
    print("\ncheck_numbers.py")
    d = tmp / "precision"
    d.mkdir()
    for f in ("main.tex", "keypoints_brief.tex", "keypoints.tex",
              "cover_letter.tex", "body.tex"):
        shutil.copy(HERE / f, d / f)

    out = run("check_numbers.py", "--dir", str(d))
    check("the real document passes the precision-pair check",
          "checks passed" in out and "[FAIL]" not in out,
          [l for l in out.splitlines() if "[FAIL]" in l][:1])

    # Put the Introduction back the way it was for six batches: the headline
    # dissociation rounded to two decimals while the abstract carries three.
    b = (d / "body.tex").read_text(encoding="utf8")
    rounded = (b.replace("from 0.832 to 0.905", "from 0.83 to 0.90")
                .replace("0.416 in sparse fields to 0.017",
                         "0.42 in sparse fields to 0.02"))
    check("precision fixture differs from the real body",
          rounded != b)
    (d / "body.tex").write_text(rounded, encoding="utf8")
    out = run("check_numbers.py", "--dir", str(d))
    check("a rounded headline value in body.tex is caught",
          "[FAIL] foreground IoU stated at one precision" in out)
    check("the offending value and its correct form are both named",
          "'0.83' should be 0.832" in out)

    # The measurement-optimal F1 must be recomputed from the frozen-split
    # CSV, not asserted. A body printing the old 0.575 must FAIL -- that
    # literal was enforced by this checker for six batches.
    b2 = (d / "body.tex").read_text(encoding="utf8").replace("0.576", "0.575")
    (d / "body.tex").write_text(b2, encoding="utf8")
    out = run("check_numbers.py", "--dir", str(d))
    check("a body printing the superseded 0.575 is caught",
          "[FAIL] F1 Ours, measurement-optimal = 0.576" in out
          and "CSV gives 0.5755" in out,
          [l for l in out.splitlines() if "measurement-optimal" in l][:1])
    # restore for the sentence-level control below
    (d / "body.tex").write_text(b2.replace("0.575", "0.576"), encoding="utf8")

    # The summarizing "remained between 0.83 and 0.90" must NOT trip it:
    # it names no range with "from" and is resolved by the exact per-bin
    # values in the next sentence.
    # b is the unmodified body; the phrase is wrapped across a source line,
    # so compare on collapsed whitespace, not the literal string.
    flat = re.sub(r"\s+", " ", b)
    check("the summarizing two-decimal sentence is not a false positive",
          "remained between 0.83 and 0.90" in flat
          and "[FAIL] foreground IoU" not in run("check_numbers.py",
                                                 "--dir", str(HERE)))


GOOD_BIB = "".join(f"""@article{{K{i},
  author  = {{Alpha, A. and Beta, B.}},
  title   = {{A title {i}}},
  journal = {{J Test}},
  volume  = {{{i}}},
  pages   = {{1--9}},
  year    = {{2020}},
  doi     = {{10.1000/test.{i}}}
}}

""" for i in range(1, 7))


def test_bib_consistency(tmp: Path) -> None:
    print("\ncheck_bib_consistency.py")
    d = tmp / "bib"
    d.mkdir()

    # A .tex that cites every fixture key: the citedness check reads the
    # bib's own directory, so a fixture with no citing source would fail on
    # citedness rather than on the property under test.
    (d / "body.tex").write_text(
        "Text citing " + " ".join("\\citep{K%d}" % i for i in range(1, 7))
        + ".\n", encoding="utf8")

    (d / "refs.bib").write_text(GOOD_BIB, encoding="utf8")
    out = run("check_bib_consistency.py", "--bib", str(d / "refs.bib"))
    check("a uniform reference list passes",
          "entry-consistency checks passed" in out and "[FAIL]" not in out,
          [l for l in out.splitlines() if "[FAIL]" in l][:1])

    # One entry loses its DOI: a lone outlier against five neighbours.
    (d / "nodoi.bib").write_text(
        GOOD_BIB.replace("  doi     = {10.1000/test.3}\n", "", 1), encoding="utf8")
    out = run("check_bib_consistency.py", "--bib", str(d / "nodoi.bib"))
    check("a lone entry missing its DOI is caught",
          "[FAIL]" in out and "K3" in out,
          [l for l in out.splitlines() if "[FAIL]" in l][:1])

    # An un-abbreviated title that is NOT on the documented exception list.
    # The rule is no longer "all one form": five titles are full-form on
    # purpose because the NLM Catalog would not confirm them. A sixth,
    # undocumented, is a genuine miss.
    (d / "mixed.bib").write_text(
        GOOD_BIB.replace("{J Test}", "{Journal of Undocumented Testing}", 1),
        encoding="utf8")
    out = run("check_bib_consistency.py", "--bib", str(d / "mixed.bib"),
              "--tex-dir", str(d))
    check("an un-abbreviated, undocumented journal title is caught",
          "[FAIL] journal names are NLM-abbreviated" in out
          and "Undocumented" in out,
          [l for l in out.splitlines() if "[FAIL]" in l][:1])

    # A documented exception must NOT fail.
    (d / "excepted.bib").write_text(
        GOOD_BIB.replace("{J Test}", "{Nature}", 1),
        encoding="utf8")
    out = run("check_bib_consistency.py", "--bib", str(d / "excepted.bib"),
              "--tex-dir", str(d))
    check("a documented self-abbreviating title does not fail",
          "[FAIL] journal names are NLM-abbreviated" not in out)

    # The stem test must not classify a spelled-out title as abbreviated,
    # and must not miss a real abbreviation. Both directions, because this
    # check has been wrong in each of them.
    from check_bib_consistency import is_abbreviated
    check("spelled-out journal titles are not mistaken for abbreviations",
          not any(is_abbreviated(j) for j in
                  ("Nature Methods", "BMC Medical Imaging", "Cytometry Part A",
                   "Medical Image Analysis")))
    check("real abbreviations are still detected",
          all(is_abbreviated(j) for j in
              ("Nat Methods", "Proc Natl Acad Sci", "Nat Rev Cancer")))

    # A duplicated key must not pass.
    (d / "dup.bib").write_text(GOOD_BIB + GOOD_BIB.split("\n\n")[0] + "\n",
                               encoding="utf8")
    out = run("check_bib_consistency.py", "--bib", str(d / "dup.bib"))
    check("a duplicate citation key is caught",
          "[FAIL] no duplicate citation keys" in out)

    # ---- citedness: an entry nobody cites must FAIL -------------------
    # Closes the class that produced a false "uncited" finding: a hand-grep
    # of prose for the DOI fragment bbae284 could not see that the entry is
    # cited by key as Tang2024. Matched by key here, never by DOI.
    (d / "cited.bib").write_text(
        GOOD_BIB + """@article{Orphan,
  author  = {Nobody, N.},
  title   = {An entry no sentence cites},
  journal = {J Test},
  volume  = {9},
  pages   = {1--2},
  year    = {2020},
  doi     = {10.1000/test.orphan}
}
""", encoding="utf8")
    (d / "body.tex").write_text(
        "Text citing " + " ".join(f"\\citep{{K{i}}}" for i in range(1, 7))
        + ".\n", encoding="utf8")
    out = run("check_bib_consistency.py", "--bib", str(d / "cited.bib"),
              "--tex-dir", str(d))
    check("an uncited refs.bib entry is caught",
          "[FAIL] every refs.bib entry is cited" in out and "Orphan" in out,
          [l for l in out.splitlines() if "cited" in l][:1])

    # And the same fixture passes once something cites it.
    (d / "body.tex").write_text(
        "Text citing " + " ".join(f"\\citep{{K{i}}}" for i in range(1, 7))
        + " and \\citep{Orphan}.\n", encoding="utf8")
    out = run("check_bib_consistency.py", "--bib", str(d / "cited.bib"),
              "--tex-dir", str(d))
    check("the same entry passes once cited",
          "[FAIL] every refs.bib entry is cited" not in out)

    # A key cited by DOI-like text must NOT count as cited.
    (d / "body.tex").write_text(
        "Text citing " + " ".join(f"\\citep{{K{i}}}" for i in range(1, 7))
        + " and the DOI 10.1000/test.orphan in prose.\n", encoding="utf8")
    out = run("check_bib_consistency.py", "--bib", str(d / "cited.bib"),
              "--tex-dir", str(d))
    check("a DOI mentioned in prose does not count as a citation",
          "[FAIL] every refs.bib entry is cited" in out)

    # Both real trees are covered by the same framework.
    for tree, label in ((HERE, "OUP"),
                        (HERE.parent / "paper2_overleaf_current", "CAS")):
        out = run("check_bib_consistency.py", "--bib", str(tree / "refs.bib"),
                  "--tex-dir", str(tree))
        check(f"every entry in the real {label} bib is cited",
              "[FAIL] every refs.bib entry is cited" not in out,
              [l for l in out.splitlines() if "cited" in l][:1])

    # ---- rendered entry form (Step F) --------------------------------
    # A .bst is a stack language with no type system; the only honest test
    # of one is what it emits. These fixtures are hand-written .bbl files,
    # so they exercise the checker without a BibTeX run.
    dF = tmp / "bblform"
    dF.mkdir()
    FOURBIB = """@article{Four,
  author  = {Alpha, A. and Beta, B. and Gamma, C. and Delta, D.},
  title   = {Four authors},
  journal = {J Test},
  volume  = {4},
  pages   = {1--9},
  year    = {2020},
  doi     = {10.1000/test.four}
}
"""
    (dF / "four.bib").write_text(FOURBIB, encoding="utf8")
    (dF / "four.tex").write_text("\\citep{Four}\n", encoding="utf8")

    good = ("\\begin{thebibliography}{1}\n\\bibitem{Four}\n"
            "Alpha A, Beta B, Gamma C \\emph{et~al.}\n"
            "\\newblock Four authors.\n"
            "\\newblock {\\em J Test} 2020;\\textbf{4}:1--9.\n"
            "\\newblock \\url{https://doi.org/10.1000/test.four}.\n"
            "\\end{thebibliography}\n")
    (dF / "good.bbl").write_text(good, encoding="utf8")
    out = run("check_bib_consistency.py", "--bib", str(dF / "four.bib"),
              "--tex-dir", str(dF), "--bbl", str(dF / "good.bbl"))
    check("a correctly truncated four-author entry passes",
          "[FAIL]" not in out,
          [l for l in out.splitlines() if "[FAIL]" in l][:1])

    # (a) all four authors listed -- the truncation failure
    (dF / "fourlisted.bbl").write_text(
        good.replace("Alpha A, Beta B, Gamma C \\emph{et~al.}",
                     "Alpha A, Beta B, Gamma C, Delta D"), encoding="utf8")
    out = run("check_bib_consistency.py", "--bib", str(dF / "four.bib"),
              "--tex-dir", str(dF), "--bbl", str(dF / "fourlisted.bbl"))
    check("a rendered entry listing four authors is caught",
          "[FAIL] no rendered entry lists more than three authors" in out
          and "[FAIL] italic et al. present wherever" in out,
          [l for l in out.splitlines() if "[FAIL]" in l][:2])

    # (b) volume not bold
    (dF / "unbold.bbl").write_text(
        good.replace("\\textbf{4}", "4"), encoding="utf8")
    out = run("check_bib_consistency.py", "--bib", str(dF / "four.bib"),
              "--tex-dir", str(dF), "--bbl", str(dF / "unbold.bbl"))
    check("an unbolded volume is caught",
          "[FAIL] volume is bold in every article entry" in out)

    # (c) DOI not rendered as a URL
    (dF / "nourl.bbl").write_text(
        good.replace("\\url{https://doi.org/10.1000/test.four}",
                     "doi:10.1000/test.four"), encoding="utf8")
    out = run("check_bib_consistency.py", "--bib", str(dF / "four.bib"),
              "--tex-dir", str(dF), "--bbl", str(dF / "nourl.bbl"))
    check("a DOI not rendered as a full URL is caught",
          "[FAIL] every article DOI renders as a full" in out)

    # (d) the real rendered bibliography
    out = run("check_bib_consistency.py")
    check("the real rendered bibliography passes every entry-form check",
          "[FAIL]" not in out,
          [l for l in out.splitlines() if "[FAIL]" in l][:2])

    # Positive control on the real file.
    out = run("check_bib_consistency.py")
    check("the real refs.bib passes",
          "entry-consistency checks passed" in out and "[FAIL]" not in out,
          [l for l in out.splitlines() if "[FAIL]" in l][:1])


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="checker_negctl_"))
    try:
        test_resolution(tmp)
        test_type(tmp)
        test_cite_order(tmp)
        test_figure_text(tmp)
        test_pdf_placeholders(tmp)
        test_numbers_precision(tmp)
        test_bib_consistency(tmp)
        test_backbone_param_definition(tmp)
        test_forbidden_prose_scope(tmp)
        test_named_refs(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    bad = [n for n, ok, _ in results if not ok]
    print("\n" + "-" * 66)
    print(f"{len(results) - len(bad)}/{len(results)} controls behaved as "
          f"specified")
    for n in bad:
        print(f"  NOT DETECTED: {n}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
