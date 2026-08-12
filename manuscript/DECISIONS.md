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
