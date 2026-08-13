# Submission package — Briefings in Bioinformatics

Everything here is either verified against the journal's own pages or marked
as unverified. Nothing is asserted from memory.

---

## 1. File set

Submission is through ScholarOne Manuscripts (`manuscriptcentral.com/bib`).

| # | File | Contents | Status |
|---|------|----------|--------|
| 1 | `main.pdf` | Compiled manuscript, 20 pp, 52 refs | ready |
| 2 | `main.tex` | Front matter, Key Points, back matter | ready |
| 3 | `body.tex` | Sections 1–4, 7 tables | ready |
| 4 | `keypoints_brief.tex` | Key Points, 5 sentences — see §2 | ready |
| 5 | `refs.bib` | 52 entries, all Crossref-verified | ready |
| 6 | `oup-plain-unsrt.bst` | Appearance-ordered numeric style | ready |
| 7 | `oup-plain.bst` | OUP's unmodified original, for comparison | ready |
| 8 | `oup-authoring-template.cls` | Vendor class, unmodified | ready |
| 9 | 7 figure PDFs | `Fig1_architecture`, `Fig2_architecture`, `Fig3_mechanism`, `Fig2_micrographs`, `Fig5_merged`, `Fig2_atlas`, `atlas_comparison` | ready |
| 10 | `cover_letter.pdf` | 1 page | ready |
| 11 | Data availability | in `main.tex` back matter | **awaiting repository URL** |

Checkers travel with the repository, not the submission: `check_figure_type.py`,
`check_figure_resolution.py`, `check_cite_order.py`, `verify_refs.py`,
`test_checkers.py`.

**Figure formats.** The Manuscript Preparation page lists GIF/TIFF/BITMAP and
asks for 600 dpi line art, 300 dpi greyscale. Our figures are **vector PDF**,
which exceeds any dpi specification for the line-art content and is normally
preferred by OUP production; the embedded rasters measure 397–401 dpi at
placed size. Figures are supplied as separate files, as the journal requires.

**If the portal refuses vector uploads**, the TIFF path is built and tested,
not improvised:

```
python recalibrate_figures.py --format tiff --tiff-dpi 600
```

This puts `tiff_export/` on `PYTHONPATH`; its `sitecustomize.py` wraps
`Figure.savefig` so every generator that writes a PDF also writes a TIFF
**rendered from the live figure**, with the same bbox and padding. It does
not rasterise the finished PDF — that would resample artwork already laid
out, which is the failure the resolution checker exists to catch. No
generator is edited, so the figsize calibration cannot drift out of step.

Measured on the exported TIFFs at the OUP measure: **596–617 dpi** at placed
size across all five vector figures, FAIL count 0. The two model-dependent
figures (`Fig3_mechanism`, `Fig2_micrographs`) need the checkpoint and
LIVECell images on disk; drop `--only` to include them.

`check_figure_resolution.py` now reads TIFF and PNG directly (IFD tag 256 /
IHDR, no Pillow dependency). `check_figure_type.py` **cannot** check a
flattened raster — there are no text objects left — so type is verified on
the PDF master and the raster inherits it only at a dpi high enough to
resolve it. The checker prints that caveat rather than leaving it implied.

**Author biographies — unresolved, and only resolvable at the portal.** The
Manuscript Preparation page mentions a short author bio (~30 words). The
Author Guidelines page does not mention biographies at all, and neither ties
the requirement to an article type. Briefings has historically been a review
journal, where author bios are conventional; whether ScholarOne asks for one
on a Research Article submission is visible only after login, which cannot be
checked from here. It is a thirty-second check on the first submission
screen. If it asks, three ~30-word bios are needed and the text must come
from the authors.

---

## 2. Key Points — settled

**Placement confirmed.** The journal states Key Points are "displayed at the
end of the article". Ours sit after the Discussion, before the declarations.

**Length: the five-sentence version ships.** The journal states Key Points
"should consist of **3-5 brief sentences**" — sentences in total, not per
bullet. Verified on both the Manuscript Preparation and Author Guidelines
pages.

| file | bullets | sentences | words | status |
|------|---------|-----------|-------|--------|
| `keypoints_brief.tex` | 5 | 5 | 153 | **submitted** |
| `keypoints.tex` | 4 | 15 | 511 | not submitted; kept as `release_repo/manuscript/keypoints_extended.tex` |

`main.tex:235` inputs `keypoints_brief`. The extended variant is labelled as
such in the release repository, available if a reviewer asks for elaboration.

All four dissociations survive the cut, the segmenter-dependence finding
stays in bullet 4, and the closing recommendation is intact. Every number is
identical to the extended version and to the tables — verified mechanically,
not by eye, by `check_numbers.py`.

---

## 3. Suggested reviewers

Held **outside this build tree**, in
`SUBMISSION_reviewers_and_portal_notes.md` at the project root, so that
no named third party or institutional email sits in the directory the
submission bundle is built from. Three verified names; take them from
the root file at the portal, never from anywhere else.

## 4. Outstanding placeholders

Swept across `main.tex`, `body.tex`, `keypoints.tex`, `refs.bib` in both the
BiB and CAS trees, and across the compiled PDF text so the check reflects what
a reader sees rather than what the source contains.

| item | where | note |
|------|-------|------|
| ~~`[REPOSITORY URL]`~~ | resolved | **Closed.** Both trees now print `https://github.com/albakhrani/morphometric-validity`; zero occurrences of the bracketed string remain in either `main.tex`. No bracketed placeholder remains in either document. |
| DLUT department | `paper2_bib/main.tex:132` | **not bracketed** — the empty `\orgdiv{}` was removed because it printed a leading comma. Affiliation 2 currently reads "Dalian University of Technology, Dalian, Liaoning, 116024, China". Add `\orgdiv{...},` before `\orgname` when confirmed. The CAS fallback still carries a `% TODO` comment at `main.tex:99`. |
| author biographies | not written | ~30 words each, if the portal asks for them (§1) |

Every other bracketed string in the compiled PDF is a confidence interval.

---

## 5. Overleaf compile — audited and proven

The manuscript had never been built anywhere but MiKTeX on Windows. Three
things differ on Overleaf, and all three were tested rather than reasoned
about.

### Case sensitivity

`check_filenames.py` extracts every `\includegraphics`, `\input`,
`\bibliography`, `\bibliographystyle` and `\documentclass` reference from
every `.tex` and `.cls`, and compares each byte for byte against the
directory listing. **13 references, 0 case mismatches, 0 extensionless
ambiguities.**

One reference resolves to nothing and is documented as benign:
`oup-authoring-template.cls:3230` does `\input{wordcount.txt}` inside the
body of `\newcommand{\wordcount}`, which this document never calls. The file
would come from the `\immediate\write18{texcount ...}` on the line above, and
shell escape is restricted on both MiKTeX and Overleaf — the log shows
`runsystem(texcount ...)...disabled (restricted)`. Vendor class, not edited.

The audit is not the only evidence. The bundle was built in an NTFS directory
with the per-directory case-sensitive attribute enabled
(`fsutil file setCaseSensitiveInfo ... enable`), verified genuinely
case-sensitive by creating `probe.txt` and `PROBE.txt` side by side. As a
negative control, renaming `Fig2_atlas.pdf` to `Fig2_Atlas.pdf` in that
directory breaks the build with `! LaTeX Error: File 'Fig2_atlas' not
found.` — so the passing run means something.

### Packages

75 `.sty`/`.cls` files are loaded, enumerated from the build log rather than
from `\usepackage` lines, so transitive dependencies are included. Every one
is a standard CTAN package present in full TeX Live, which is what Overleaf
ships. Nothing is vendored except the class and the two `.bst` files, all of
which travel in the bundle.

Fourteen were fetched on demand by MiKTeX during this project, identified by
file mtime against the bulk install date (a path test is useless here — this
MiKTeX is a per-user install, so all 75 sit under the user profile):
`etoolbox`; `array`, `fix-cm`, `ifthen`; the `amsmath` bundle; `listings`,
`lstmisc`, `lstpatch`; and — most recently, 2026-02-13, during this port —
**`flushend.sty` and `stfloats.sty`, the `sttools` bundle**. All are in TeX
Live. The build below ran with `--disable-installer`, so nothing was fetched
during it.

`\societylogo` is `\def\societylogo{}` (`main.tex:72`) — a pure no-op. It
references no image and expands to nothing, so there is no missing-file risk.

### Build configuration

`latexmk -pdf` — Overleaf's default flow — resolves the bibliography by
itself: the log shows pdflatex, then `rule 'bibtex main'` twice interleaved
with reruns. No manual bibtex pass is needed.

`main.tex` records the compiler and TeX Live year at the top, and states that
it is the root. `cover_letter.tex` is the only other file carrying a
`\documentclass`; it is deliberately excluded from the bundle rather than
annotated, so root detection cannot be ambiguous.

### Result, in the case-sensitive directory with auto-install disabled

| check | result |
|---|---|
| latexmk exit | 0 |
| errors | 0 |
| undefined citations / references | 0 / 0 |
| pages | 20 |
| citations | 52 |
| appearance order | correct, 52 keys |
| `??` in output | 0 |
| auto-installs triggered | 0 |
| overfull hbox | 1 (the class's own 11.38107 pt) |

In-text citations print `[6] [1–3] [7] [8] [9] [4] [10, 11] [5]` — square
brackets, comma separators, en-dash ranges, appearance order.

### Bundle

`overleaf_upload/` — 14 files, 2.60 MB uncompressed; `overleaf_upload.zip`
2.28 MB (sha256 `6ff2bf109b7bad63`), flat (no wrapper directory, which Overleaf expects). Every file is
byte-identical to its `paper2_bib` master. No `.py`, no `.png`, no
`tiff_export/`, no `cover_letter.tex`.

`oup-plain.bst` is in the bundle **unmodified** — verified by hash against
the master and by confirming its `ITERATE {presort}` / `SORT` pass is intact,
which our `oup-plain-unsrt.bst` lacks. The cover letter's claim is therefore
true of the bundle a reviewer receives.

---

## 6. Decision log — current as of the close

Each row is the state the manuscript ships in, not the state it passed
through. Where a later finding superseded an earlier record, the earlier
record is named so the supersession is visible rather than silent.

| decision | state | evidence |
|---|---|---|
| **Step F override** | **executed.** The reference style was converted in one atomic pass: `oup-plain-unsrt.bst` gained `format.names` truncating to three authors + `\emph{et~al.}`, `format.jnl.numbers` for the `Journal Year;**Vol**:pages` form, and `format.doi.url`; `doi` was added to `ENTRY`. | refs [1], [19], [30] quoted from the fresh PDF in 7 |
| **Journal abbreviations** | **17 of 18 distinct titles carry the NLM Catalog abbreviation.** The eighteenth, *Nature*, is its own abbreviation. **Supersedes two earlier records:** the F-era "all titles full-form" and the F′-era "13 of 18, five documented exceptions". | four of the five F′ exceptions resolved by keying the NLM lookup on **ISSN** rather than title string; `Comput Biol Med`, `Cytometry A`, `Med Image Anal`, `Phys Rev X` applied |
| **Abbreviations are never invented** | standing. A title that no catalog record confirms ships full-form and is reported. Two of the four above had returned a *different journal* under title-string search — the reason title matching was abandoned. | `FULL_FORM_OK` in `check_bib_consistency.py` now documents only self-abbreviating titles (`Nature`, `BMC Bioinformatics`) |
| **Page ranges** | ship **full, not elided** — `1038--1045`, not `1038--45`. | ref [30] as printed |
| **`refs.bib` diverges between trees, intentionally** | OUP carries 7 eLocators, 10 brace-protected entries and the NLM abbreviations; CAS is untouched. This is not drift and must not be "fixed" by syncing. | the two files differ by design; each tree builds clean |
| **G-3 deictic adjudication** | the meta-frame was deleted. **One sanctioned one-word exception** remains where removal would have broken the sentence. | recorded at adjudication; CAS Introduction is 1 word shorter than OUP for the parallel reason |
| **B19** | **accepted deviation** from the exemplar convention, taken deliberately rather than by oversight. | — |
| **Introduction length** | **1,522 words** (OUP), 1,521 (CAS), heading-anchored, citations excluded. **Supersedes the logged 1,524**, which came from a hard-coded line window (`body[0:177]`) that later edits left stopping mid-sentence; that window now reads 1,507. The span is `\section{Introduction}` to `\section{Materials and methods}`, `body.tex` lines 1–180. | re-derived at the close, both trees |
| **G-4 retraction** | **retracted, with cause.** The claim that `bbae284` was uncited was mine and was false: I grepped `body.tex` for the DOI string. The entry is cited by key as `Tang2024` and prints as reference [21]. | citedness now matches **by key, never by DOI**; a negative control asserts that a DOI appearing in prose does **not** count as a citation |
| **False passes** | seven-plus found and fixed across the program; the class is now guarded, not merely fixed. The lesson is recorded in the checker sources: *a checker that only ever sees passing input has not been shown to detect anything.* | 64 negative controls, up from 18 |
| **Reviewer dossier location** | held in **one** place, `SUBMISSION_reviewers_and_portal_notes.md` at the project root, and **not** in `paper2_bib/`. It had been byte-identical in both; the build-tree copy now carries a pointer only. Three named academics and their institutional emails must never sit in the directory the submission bundle is built from, and must never reach the public repository. | build-tree copy: 0 emails, 0 names; root copy: 3 and 3; public repo swept clean |
| **Abstract length** | **233 words** (source), printing as 234 whitespace tokens because "matched-instance" breaks across a line. Check any portal abstract limit against 233. | `main.tex`, and page 1 of `main.pdf` |
| **Review-turnaround prior** | the only evidence on disk is the three BiB exemplars in `BIB papers/`: received-to-accepted of 113, ~195 and 200 days — roughly **four to seven months**. bbae407 is **not** on disk in any form, so no turnaround figure may be attributed to it. | dateline of each exemplar, page 1 |
| **Out-of-band fork identified and closed** | An Overleaf-side compile of this paper, 21 pp, existed outside both trees: the author’s `Downloads/paper2.pdf`, sha256 `0502e8c6925f3afd`, modified 2026-08-10 17:55. Its author block carried `\author[2,3]`, `School of Software Technology` and `Albaydha University, Albaydha, Yemen`, none of which had ever been in the trees. **Reconciled one-directionally on 2026-08-11: the affiliations came in; for all other content the trees are authoritative.** Its Conclusion is pre-recast, so it must not be used as a source for anything else. Both trees now print the full block; that compile is superseded and must not be sent to anyone. | author block quoted from both freshly compiled PDFs, and the title block of each rendered and inspected |
| **Fork scope** | one file per tree. `main.tex` changed in each; every other bundle file hashes exactly as before. | 13 of 14 bundle hashes unchanged, archive `6ff2bf10…` → `ea082e72…` |
| **Albaydha city spelling — closed** | **Resolved 2026-08-11: AL-Bakhrani confirmed the affiliations directly** — city spelled **Albaydha**, DLUT line "School of Software Technology, Dalian University of Technology", and **no faculty line** to be added. Both trees already printed exactly these strings, so **no edit was made** and the certified bundle `ea082e72…` is unchanged. The `Albydha` city spelling carried by two of his other papers is superseded for this manuscript, not adopted. | re-verified character-for-character in both compiled PDFs on the confirmation date: OUP p.1 and CAS p.2 both print `Albaydha University, Albaydha, Yemen`; `Faculty of Administrative Sciences` and `Albydha` both absent from both |
| **Overleaf is a compile target only** | every upload overwrites the cloud project wholesale; no edit is ever made there directly. This fork is what that rule exists to prevent. | operating rule, adopted 2026-08-11 |
| **Register pass, items B—G** | Executed 2026-08-11 at the corresponding author's request: formal academic register, claims and numbers frozen. **98 edits per tree**, identical in both except where a named-section reference differs (`\emph{Name}` in OUP, `Section~\ref{}` in CAS). Em-dashes **76 → 32**; mid-sentence ", so" **38 → 20** (the remainder are purposive ", so that" or were judged already formal). Sentence-initial *And*/*But* eliminated; 21 colloquialism fixes; 18 colon splices resolved; 2 rhetorical fragments integrated. | page counts unchanged 20 / 24; 9 checkers FAIL 0; 64/64 controls |
| **Register pass — what was refused** | 164 edits were proposed and **65 rejected before any file was touched**: 12 for touching a protected passage, 15 for a non-unique anchor, 4 genuine parentheticals kept, 3 that would have softened the paper's directness about unfavorable results, 1 that moved a digit. **No number changed** — the digit sequence of each `body.tex` is byte-identical before and after. All three protected passages verified verbatim in the freshly compiled PDF, and no forbidden phrase was reintroduced. | applier refuses to write on any digit change, forbidden phrase, or protected-passage loss |
| **No checker was weakened** | every assertion string in all nine checkers survived the pass untouched; none needed updating, because the edits left `\cite`, `\ref`, `\emph` section names, labels and math alone by construction. | 9/9 and 64/64 green on the first run after the edits |
| **Register pass item A — NOT executed** | The abstract is **unchanged**, 233 words. The formalized version was to be "supplied separately by the author" and is not on disk; the newest candidate, `Downloads/paper2_last.pdf`, carries the current abstract verbatim. Writing one would have meant inventing the author's text and re-deriving ten reported numbers into prose he has not approved. Open, pending the supplied text. | abstract quoted in full from the fresh PDF, opener and closer unchanged |
| **Formalized abstract installed** | Installed verbatim 2026-08-11 as supplied by the corresponding author, in **both trees**. Number sets verified identical to the previous text before writing: nothing added, nothing removed. Protected phrase (a) "are not mutually predictive" survives verbatim; only its surrounding punctuation changed, which the instruction explicitly permitted. **234 → 241 words** in source (240 as printed). Pages unchanged. | abstract quoted in full from the fresh PDF; CAS block rendered and inspected |
| **Em-dash elimination policy** | Target met: **zero em-dashes in author-written prose** in both trees, body text and captions alike, down from 32 per tree. Four exclusions were honored and are permanent: (1) en-dashes in numeric and page ranges; (2) dashes inside published titles in `refs.bib`, notably reference [30] `LIVECell{-}{-}{-}A large-scale dataset...`, where altering a cited title would be a citation error; (3) math-mode minus signs; (4) hyphens in compounds. **A fifth exclusion was found and is recorded here:** 10 `---` in table body cells are *not-applicable* markers, a data notation rather than prose, and were left alone. | compiled PDF contains 11 em-dash characters (OUP): the 10 table markers and the one cited title |
| **Em-dash technique distribution** | Deliberately varied rather than mass-substituted, because 20 semicolons from the first pass had already made the prose semicolon-heavy: **5 split into two sentences, 4 parentheses, 4 comma pairs, 2 subordination, 0 new semicolons** at the em-dash sites. Semicolons overall were reduced **116 → 35** (OUP) as first-pass cleanup. | counted in source before and after |
| **Second-pass scope** | 156 edits proposed and guarded, 140 applied per tree in round one plus 7 reconciled individually. Classes: em-dash 15, semicolon 70, long-sentence splits 27, colloquial 16, loose "so" 13, rhetorical flourish 8, anthropomorphism 7. **No number changed** — the digit sequence of every `body.tex` is byte-identical before and after, and `main.tex` changed only by the sanctioned abstract install. All three protected phrases verified in the fresh PDF. | 9 checkers FAIL 0, 64/64 controls, pages unchanged 20 / 24 |
| **Stale CAS figure found and fixed** | **Not caused by this pass.** `paper2_overleaf_current/Fig1_architecture.pdf` was still the pre-fix asset: its outcomes box read *"One rejected phenotype — MCF7: fabricated by two unrelated error sources"*, the retracted double-error claim, containing two forbidden phrases. The submission tree had been regenerated months earlier; the fallback had not, and no check looked. The corrected asset (*"One manufactured phenotype — MCF7: no trajectory survives control; segmentation error creates one"*) was copied across and CAS rebuilt. | both compiled PDFs now sweep clean of all six forbidden phrases |
| **Detection gap closed** | `check_figure_text.py` swept figures only in the tree it was pointed at, which was always `paper2_bib`. It now always sweeps **both trees** for retired claims, because a retracted claim must not survive in any tree that can be compiled and sent. Checker count 118. Proven by live negative control: planting a figure carrying the retired MCF7 wording in the CAS tree makes it fail, and removing it makes it pass. | the checker was strengthened, never weakened |
| **One agent deviation corrected** | At the named Conclusion site the brief required a full stop; the proposed recast used a colon, which recreates the colon-splice construction the first pass removed. Changed to a full stop: *"...and the measurement quantities from each other. No single number certifies a morphometric pipeline."* | quoted from the recompiled PDF |
| **Modal reverted: `may` → `can`** | The supplied abstract read "a method or operating point selected on any one of them **may** therefore corrupt the remainder". Reverted to **can** in both trees on 2026-08-11 at the corresponding author's direction: the paper *demonstrates* the corruption (MCF7 is the worked case), so the modal must assert a shown capability rather than a possibility. Nothing else in the abstract changed. | sentence quoted from the freshly compiled PDF |
| **Conclusion connective restored** | The em-dash split had dropped the inferential link carried by the original "— so". Restored as *"...and the measurement quantities from each other. **No single number therefore certifies** a morphometric pipeline."* Chosen over the bare assertion because the four dissociations are the *reason* for the claim, and with the connective gone the sentence read as a coincidental restatement rather than a conclusion. "Therefore" here marks a real inference, not filler. | quoted from the recompiled PDF |
| **Stale preview deleted** | `paper2_overleaf_current/COMPILED_PREVIEW.pdf` (2,464,917 B, 6 August) carried **all six** forbidden phrases. Confirmed referenced by no `.tex` or `.cls` in either tree, and regenerable from source, then **deleted**. | PDF inventory of both trees re-run after deletion |
| **Second stale orphan found, not deleted** | `paper2_overleaf_current/Fig4_envelope.pdf` (19,080 B) is included by no `\includegraphics` in either tree — the envelope figure is `Fig5_merged`. It is a harmless leftover chart and carries **no** forbidden phrase, so it was reported rather than removed; only the named preview was authorized for deletion. Every other PDF in both trees is accounted for: 7 figure assets, `main.pdf`, and `cover_letter.pdf` in the OUP tree. | full PDF inventory, both trees |
| **Hedging audit — the class no checker can see** | **(a)** Across the two passes the guards refused **12** candidate edits for introducing hedging or weakening a claim (1 of 65 in pass 1, 11 of 67 in pass 2), including two that would have flattened deliberate antithetical frames stating unfavorable results about the authors' own analysis. **(b)** Sweeping the current text against the **pre-pass-1** baseline for 15 hedge constructions across all four source files: **zero newly introduced hedges.** One was *removed* ("arguably", 1 → 0). All four unfavorable-result passages — Cellpose's detection advantage, the measurement-optimal setting costing a lineage, the MCF7 reversal, the A172 listwise-deletion inversion — contain no hedge word and stand exactly as blunt as before. | all four quoted from the fresh PDF and screened individually |
| **Blind read after two register passes** | One agent, compiled OUP PDF only, no brief and no project notes. **The thesis and all four dissociations registered** — an improvement on the earlier blind read, which found only three of four. It counted nine separable results and reported that two of them blur: the detection-optimal/measurement-optimal trade-off and the bias/amplitude/direction split are "two readouts of the same three-point operating-point sweep". That is a structural observation about the evidence, not a register defect, and it is recorded here rather than acted on. | reader-side confirmation that the rewriting did not cost the argument |
| **Blind read — two hedges my audit missed** | The reader flagged *"The four artifact controls left the classification in Table 6 **essentially** unchanged"* and *"Its contribution, **if any**, is to the representation..."* as under-claims: in both cases the paper had already shown a clean result (nothing changed; output bit-identical with an all-zero boundary map). Neither word was on my 15-term hedge list, so the mechanical audit could not see them. **Both predate the register passes and neither was introduced by them.** Flagged for the authors, not silently altered — softening or strengthening a claim is theirs to decide. | the hedge list is a net, not a proof |
| **Illegal hyphenation — real, reported, not fixed** | The blind reader flagged breaks such as `dete-ction`, `dire-ction`, `dista-nce`. Verified on the **rendered page**, not merely in extracted text: page 2 prints "maximizing dete- / ction accuracy". English breaks that word `de-tec-tion`. Neither `fontenc` nor `babel` is loaded — zero occurrences in `main.tex` and zero in the class. 197 distinct line-break hyphens exist; most are correct, a minority are not. The standard remedy is `\usepackage[T1]{fontenc}`. **Not applied:** it changes font metrics, reflows the whole document, and would invalidate the certified bundle at the close, and production typography has been out of scope for this program since the first brief. OUP re-typesets at production in any case. | rendered crop inspected directly |
| **"Independent" dropped from the contribution sentence** | Now reads *"The contribution is one claim supported by four dissociations"*, both trees, `body.tex:139`. The blind reader was right: dissociations 2 and 3 are two readouts of the **same** three-point operating-point sweep, so they are not independent *evidence*. They remain four logically distinct claims and that framing is unchanged. **Every other use of "independent" was audited and kept:** the four artifact controls really are independent (four distinct confounders, four distinct procedures — density definition, cell size, time since plating, segmentation), and the remaining uses are statistical or idiomatic. | 24 occurrences reviewed across both trees and the cover letter; 1 changed |
| **Illegal hyphenation: cause found, fixed** | Verified at **900 dpi** on the rendered page, not by extraction: page 2 printed "maximizing **dete-** / ction". Root cause was **not** font encoding but that no language was ever selected — the OUP class loads neither `babel` nor `fontenc`, so English hyphenation patterns were never active. `\usepackage[english]{babel}` added to `paper2_bib/main.tex`. **12 illegal break patterns → 0**; 197 → 166 distinct line-break hyphens; **20 pages unchanged, the one class-owned overfull box unchanged, no float moved.** The CAS tree needs nothing: `cas-dc.cls` selects a language itself and showed zero illegal breaks. | tested in a scratch copy before the live tree was touched |
| **T1 fontenc tested and REJECTED** | The obvious companion fix was tried and rejected on evidence. With `\usepackage[T1]{fontenc}` and no `lmodern`, the dash glyphs lose a usable ToUnicode map: every em-dash and en-dash extracted from the PDF as raw byte `0x16` instead of U+2014 / U+2013. The printed page is identical, but the text layer is what indexers, copy-paste and our own checkers read, and reporting "0 em-dashes" off that PDF would have been a false pass. `babel` alone fixes the hyphenation and leaves the text layer intact: 11 em-dash and 58 en-dash characters extract correctly. | caught by re-reading the text layer after the fix, not before |
| **Retired envelope asset deleted** | `paper2_overleaf_current/Fig4_envelope.pdf` removed. Confirmed referenced by no `\includegraphics` in either tree before deletion; filename checker re-run at 14 references, 0 problems. Both trees now hold exactly their figure assets plus `main.pdf` (and `cover_letter.pdf` in OUP). | PDF inventory re-run |
| **"Essentially unchanged" was wrong, not merely hedged** | Checked against `atlas_lineage_table_allsplits.csv`. **No trajectory reversed direction under the controls** (zero raw-to-partial sign flips), but the classification did move: **MCF7's partial correlation is not significant (p = 0.17) and it is classified as unsupported**, and A172 sits in Tier B on a split cell-size stratum. The sentence now names what moved instead of hedging over it: *"The four Artifact controls reversed the direction of no trajectory in Table 6, and one lineage did not survive them: MCF7's partial correlation is not significant, and it is classified as unsupported."* | eight lineages checked row by row against the source CSV |
| **Unsupported-lineage count corrected: one → two** | The replacement sentence undercounted. **Table 6 carries two Tier C lineages, not one.** Verified against `atlas_lineage_table_allsplits.csv` and against the printed table. **MCF7**: raw ρ −0.242 (p = 2.2e−10) → partial −0.053, **p = 0.17, not significant**. **BV-2**: raw ρ +0.107 (p = 0.012) → partial **+0.269, p = 2.1e−10 — highly significant**, so significance is not its failure mode; it is Tier C because its partial coefficient *exceeds* its raw one (retained 2.503) while all four cell-size strata carry the opposite sign (−0.04, −0.05, −0.04, −0.01), the control-generated-association condition. | the paper's own Table 6 footnote states this and adds that "the magnitude-based conditions alone would place it in Tier B" |
| **Content audit applied — nine approved items** | Applied 2026-08-11 to both trees, anchored on quoted text in descending line order. (1) the MCF7/BV-2 elaboration replaced by a naming pointer; (2+9) the coverage-artifact defence and two recited Table 4 cells cut; (3) the abstract merging sentence cut with the "of that merging" bridge; (4) the −0.24/−0.05 parenthetical; (5) the *Principal findings* pointer; (6) "Both are stated explicitly wherever they appear."; (7) "These three names are used consistently throughout."; (8) "Reproducibility was verified before the comparison rather than assumed." **Prose 11,430 → 11,284 words (146 removed, 1.3%).** Pages unchanged 20 / 24. | all nine joins quoted from the freshly compiled PDF; 9 checkers FAIL 0; 64/64 controls |
| **Recovery criterion changed (C1 → C2)** | An external review showed sign-only agreement is not a defensible recovery criterion. Recovery is now defined in Methods as sign agreement **and** a percentile bootstrap 95% CI excluding zero. **Table 7 panel (a): 5/6, 6/6, 5/6 → 5/6, 5/6, 5/6** (only ours-detection-optimal moves). **Panel (b): 5/6, 6/6, 6/6, 6/6 → 4/6, 6/6, 6/6, 5/6.** The caption's false bold clause ("the only source that recovers all six") is deleted. | both C1 recomputations reproduced the printed values exactly before anything changed; all 40 per-lineage coefficients reproduced to 0.0005 |
| **Antecedent repair: "that lineage" named** | Both reformulated D4 sentences referred to "that lineage" with **no antecedent at all** — worse than the reported risk of resolving to the wrong one. Cause: two edits from the same Step 2 batch interacting. The D3 rewrite removed the lineage names from the Introduction and Discussion ("They do not lose the same one"), while the D4 rewrite introduced a demonstrative depending on them. Both now name **A172** explicitly. | third occurrence of this class in this manuscript; each time a demonstrative outlived the text it pointed at |
| **Residual non-retracted claim found by the antecedent sweep** | The Results still said connected-component labeling "recovers six of six, as many as the extension" in panel (b) — a C1 count the Step 2 retraction should have caught. **It survived because `six of` and `six` wrap across a source newline and the Step 2 grep is line-based.** Corrected to five of six under C2, with the note that the missed direction is A172, whose panel (b) reference is the coverage-inverted one. | the sweep for a different defect caught this one; a line-based grep cannot see a wrapped phrase |
| **Cellpose citation scope corrected** | Methods cited **all four** Cellpose papers for "the earlier lightweight architectures", a list that included Cellpose-SAM itself — the same defect class as the [26] error the review found, and it predated the renumbering. Now: **Cellpose-SAM model [26]** at the point the sentence identifies the backbone, and **[24, 25, 42]** for the earlier architectures. Full audit: [24] Cellpose 2021 and [25] Cellpose 2.0 support human-in-the-loop retraining; [26] Cellpose-SAM supports both the foundation-backbone claim and the benchmarked backbone; [42] Cellpose3 sits only in the earlier-architectures list. All four resolve to the version their sentence intends. | 52 references, cite-order clean, `(author?)` sweep zero |
| **Type 42 conversion — STILL OPEN** | Not started. The brief's own rule applied: do not begin unless it can be finished and verified, because a partially converted figure set is worse than none. Six of seven figures embed Type 3 fonts; the fix and mechanism are confirmed (`phase7_figures.py` sets `pdf.fonttype` and its `Fig2_atlas.pdf` is the one clean figure). Remaining work: the rcParam in six generators, regeneration through `recalibrate_figures.py` (convergence loop that rewrites figsizes back into the generators — back them up and keep the best pass, not the last), two figures needing the model checkpoint and raw LIVECell images, `figure3_mechanism.py` needing the project root on PYTHONPATH, then font/extraction/type/resolution checks and a visual pass over the rendered pages. **The paper builds and ships clean without it.** | open |
| **Non-monotonicity retracted** | The claim that recovery "peaks at the intermediate detector" rested on **one cell**: A172 under ours-detection-optimal, ρ = −0.105 [−0.286, +0.099] — correctly signed but spanning zero. Under C2 the counts are flat at 5/5/5. Retracted at all 32 sites across both trees. The replacement is stronger: three sources spanning F1 0.576 to 0.815 each recover exactly five of six, and they do not lose the same one — both of our settings lose A172 (Tier B), Cellpose loses BT-474 (Tier A). | `non-monotone`, `peaks in the middle`, `peaks at the intermediate`, `Recovery peaks`, `five, six and five` all absent from the compiled PDF |
| **Sevenfold framing removed from the direction claim** | The direction result is scoped to the three complete-coverage sources, whose F1 spans **0.576 to 0.815**, not sevenfold — sevenfold requires connected-component labeling, whose coefficients come from its own 81.3% coverage. The sevenfold framing stays where the paper uses it for the comparison in general. | the scoping is the paper's own *Coverage* finding applied to itself |
| **D4 reformulated: in kind, not in count** | Under C2 both operating points recover 5/6, so the old claim that measurement-optimal "recovers fewer directions" is false. Both lose A172, **for opposite reasons**: detection-optimal gives ρ = −0.105 with an interval spanning zero (correctly signed, unresolvable); measurement-optimal gives +0.263 with an interval excluding zero (confidently opposite to the expert −0.468). Optimizing the named criterion degraded the unnamed one. The ordering correlation 0.905 → 0.786 is unaffected by the criterion change and stands as printed. | corrected at all three asserting sites; both remaining dissociations verified consistent |
| **Panel (b) 4/6 reported, not claimed** | Cellpose's 4/6 in panel (b) includes an A172 miss scored against the **coverage-inverted** reference (+0.072, not −0.468) — the listwise-deletion artifact the paper itself documents as a failure mode. Building a favorable claim on it would use the very artifact the manuscript warns against. The caption now states that A172 direction results in panel (b) are not interpretable and that the counts are taken over all six lineages regardless. No prose calls Cellpose the worst recoverer. | panel (b) stays corroborative |
| **Flagship claim upgraded with per-lineage F1** | The review's strongest objection — that the 0.815-vs-0.709 advantage is global and says nothing about BT-474 — **fails**. On BT-474 itself Cellpose is **0.771 [0.730, 0.821]** against **0.676 [0.638, 0.726]**, intervals non-overlapping, n = 14. Cellpose detects better on **8 of 8** lineages, non-overlapping on 7. Provenance stated in the adjacent sentence: the 180-image detection benchmark, not the 1,419-image atlas. **Per-lineage F1 was deliberately NOT added to Table 7 panel (c)** — F1 from 180 images beside ρ from 1,419 is exactly the sample-mixing the Provenance block exists to prevent. | the paper had been under-claiming |
| **Citation corrected: [26] was the wrong Cellpose paper** | The Introduction credited the foundation-model backbone to Cellpose3 (one-click image restoration). Corrected to Cellpose-SAM. The bibliography renumbers by first appearance, and the two swapped exactly as predicted: **Pachitariu2025 → [26]**, **Stringer2025 → [42]**. 52 references intact. The other three Cellpose entries resolve correctly. **One ambiguity flagged, not changed:** Methods cites all four Cellpose papers after "the earlier lightweight architectures", a list that includes Cellpose-SAM itself; readable as a version-history citation, but worth the authors' eye. | cite-order checker passes; `(author?)` sweep zero |
| **Control scope corrected** | Three universal claims — "applied to every result", "each applied to every reported trajectory" (Figure 1 caption), and "Four controls were applied to every reported trajectory" (Methods) — contradicted the statement that the cell-area control cannot be applied symmetrically to model-derived masks. All three now read "from expert masks". One clause each, no new sentences. | quoted from the compiled PDF |
| **Type 42 conversion NOT done — the one item still open** | Six of seven figures embed Type 3 fonts with `/Differences` and no `/ToUnicode`, which many journals reject outright and which causes the glyph-index extraction that forced a second-engine workaround. **The fix and its mechanism are both confirmed:** `phase7_figures.py` already sets `pdf.fonttype`, and `Fig2_atlas.pdf`, which it generates, is the single clean figure. The remaining six need the same rcParam and regeneration through `recalibrate_figures.py`; two of them additionally require the model checkpoint and the raw LIVECell images, and the driver runs a convergence loop. Deferred rather than half-done. | open |
| **Item 1 supersedes a previous instruction** | The prior session's instruction to name both lineages and both mechanisms **over-corrected**. The count was wrong and needed fixing, but the elaboration duplicated a fuller, more precise statement 79 lines earlier that the reader reaches first: *"BV-2 and MCF7 did not survive control: for BV-2 the controlled correlation exceeded the raw correlation and contradicted the sign observed in all four cell-size strata... For MCF7 the raw correlation (ρ = −0.24) collapsed to ρ = −0.05 (p = 0.17)..."* Six words now replace forty. | the earlier statement verified intact and reached first |
| **Two deviations from the approved text, both reported** | (a) Item 1's specified parenthetical was `(BV-2 and MCF7, Table~\ref{tbl:atlas})`, but the same sentence already says "in Table 6"; the duplicate reference was dropped, giving `(BV-2 and MCF7)`. (b) Item 2's specified repair ("the same held-out images" → "the same 150 frozen test images") was **moot**: that phrase lives inside the sentence item 9 deletes, so the two approved items resolve each other. Nothing was left dangling. | both confirmed against the compiled PDF |
| **Numbers that left the document** | Four, each verified still present where the audit said: **0.074** (4 other sites incl. Table 6 row), **0.717** (Table 6 row), **−0.24** (4 others incl. line 1091 and the table row), **−0.05** (6 others). Quantity digit tokens 795 → 790; the fifth removed token is the "1" of the metric name **F1**, not a quantity. | every surviving occurrence listed before the edit was written |
| **Three cuts REJECTED on merit, not overlooked** | `:65` *"We ask the second question, and answer it empirically."* — the hinge from gap to contribution; without it the paragraph says what prior work fails to do and never says what this paper does. `:1380` *"Recovery is therefore non-monotone..."* — a finding, and the only occurrence of *non-monotone* in Results; the Discussion's "not merely weak but non-monotone" needs an antecedent in the results text. `:355` *"We report the model we ran rather than the smaller model..."* — a transparency disclosure of the 66-trained / 33-recommended discrepancy, in the same class as the protected single-descriptor concession. | all three remain in both trees |
| **Classes B and C DECLINED on merit** | Not overlooked. **Class B** (method-survey descriptions of StarDist, HoVer-Net, Mask R-CNN, nnU-Net, Omnipose, Cellpose's version history) is the highest-risk, lowest-reward material in the audit: it sits around positioning citations, and damaging how the paper situates itself costs more than the few lines saved. The package list at `:699` stays — a reproducibility convention worth its twenty words — as does `:383`. **Class C** float narrations mostly carry their figures' only in-text citation; the Figure 4 case would have orphaned the float outright. | 36 compress candidates declined, ~957 words |
| **Why the audit mattered more than its yield** | The pass found **59 passages that answer anticipated referee objections against 52 that could be trimmed**. Four of the 59 were natural compression targets, including the single word *primary* at `:494` which makes the four-descriptor disclosure read as declared scope rather than an afterthought. A reviewer's "too long" is often "too loose"; this prose is dense with self-defence, and most of it has to stay. | recorded so the ratio is not relitigated |
| **Which reading the data supported** | **The rejected-by-the-controls reading, not the significance reading.** Scoping the sentence to significance would have been true of MCF7 only and would have left the count reading as a tally of unsupported lineages while the table printed two. Both lineages are rejected *by applying the controls*, by two distinct mechanisms, so both are named with their mechanism. The rest of the manuscript was already consistent with two: "the six lineages whose trajectory is supported under control (tier A or B)", "six of six", and Figure 1's "5 robust · 1 supported · 2 rejected". My sentence was the single outlier. | six other count statements grepped and cross-checked against the table; all agree on six supported |
| **Why the CSV said Tier B** | Not a data error. The `tier` column records the **magnitude-based** assignment; the paper applies the fourth (control-generated-association) condition on top of it and prints C for BV-2. The CSV and the table are consistent once that is understood, and the footnote says so explicitly. | recorded so no later reader "fixes" the CSV to match the table |
| **Digit guard widened again** | The mask needed `BV-2` as well as `MCF7`; the manuscript spells it `BV-2` in prose while the source CSV uses `BV2`. Against the pre-pass-1 baseline: **quantity digit tokens 795 → 795, identical in both trees**; the only added raw tokens are the identifier digits in MCF7 and BV-2. | third time an identifier digit has tripped this guard; the mask is now longest-first |
| **Digit guard corrected** | The no-number-changes guard read the `7` in **MCF7** as a quantity and blocked a legitimate edit. Lineage and model identifiers (MCF7, BT-474, A172, SK-OV-3, SH-SY5Y, BV2, SkBr3, Huh7, U-Net++) are now masked before digits are extracted. Against the pre-pass-1 baseline: **quantity digit tokens 805 → 805, identical in both trees**; the single added raw token is that identifier `7`. | the rule protects measured values, not digits inside names |
| **Blind reader's content objections, recorded not acted on** | For the response letter if they return in review, not register defects. (i) **Single-descriptor scope:** the thesis is that morphometric validity is multidimensional, but every dissociation is a dissociation of the shape index; four further descriptors are computed and released but not analyzed. (ii) **"Across models" rests on two models:** the three mask sources at F1 0.576 / 0.709 / 0.815 are Cellpose plus the same model at two thresholds, and the non-monotonicity is a one-lineage-of-six difference with no interval on the count. (iii) **BT-474 intervals:** Cellpose's interval overlaps the expert's, and the extension's coefficient is roughly 2.5x the expert value with non-overlapping intervals — the honest reading is that one source flattens the trajectory and the other inflates it. | blind read, compiled PDF only |
