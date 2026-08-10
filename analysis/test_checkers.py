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
  journal = {{Journal of Testing}},
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

    # One journal abbreviated where five are spelled out.
    (d / "mixed.bib").write_text(
        GOOD_BIB.replace("{Journal of Testing}", "{J Test}", 1), encoding="utf8")
    out = run("check_bib_consistency.py", "--bib", str(d / "mixed.bib"))
    check("a mixed abbreviated/full journal name is caught",
          "[FAIL] journal names use one form" in out)

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
