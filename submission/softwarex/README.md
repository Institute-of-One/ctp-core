# SoftwareX submission package

Target article type: **Original Software Publication**.
Manuscript number: **SOFTX-S-26-01589**.

## Returned before review, 1 September 2026

The editorial office sent the submission back without review:

> Conclusions section is missing. Your current Sections 5 and 6 are also not required as
> per the template.

Both points are fixed, together with three further departures from the template found
while fixing them. The requirements were read off Elsevier's own
`softwarex-osp-template.docx`, not from memory:

| | Was | Now |
|---|---|---|
| Conclusions | absent (mandatory) | **§5 Conclusions** |
| §5 Limitations and future work | a numbered section | folded into §5 Conclusions |
| §6 Reproducibility | a numbered section | run commands moved into §3; DOIs already in the metadata table, the availability statement and ref. [8] |
| Metadata table | rows S1–S7, no documentation link, no support email | rows **C1–C8** as the template prescribes |
| C2 | the Zenodo DOI | the **GitHub** repository — the template says a GitHub repository is mandatory or the paper will not proceed |
| §2 subsections | "Architecture and scope" / "Gamma-variate fitting…" / "Parametric mapping…" | "**Software architecture**" / "**Software functionalities**" |
| Author address | no postal code | `Institute of One, LISIT Co., Ltd., Tokyo 150-0044, Japan` |

Sections 1–5 are 1,491 words against the template's 4,000-word, six-page limit.

## Found in the full pre-resubmission sweep, 1 September 2026

Fixed in the manuscript:

| | Was | Now |
|---|---|---|
| Ref. [11], second DOI | `10.3389/fnins.2023.1048168` — **404**, and the journal was wrong | `Front Neuroinform. 2023;17:852105`, `10.3389/fninf.2023.852105` (verified: PMID 36970658, PMC10034033) |
| Keywords | seven | six, the template maximum (`perfusion imaging` dropped as subsumed by `CT perfusion`) |
| Ref. [8] title | `(v0.1.0)` | `(IORN-001), version v0.1.1` — matches the registered Zenodo title |
| `highlights.txt` | an en dash | ASCII hyphen; all five bullets are ≤85 characters |
| `figure_unitobrain_mol001.json` | did not record the 106.9 HU quoted in §3.4 | records `aif_peak_enhancement_hu` (re-run: 106.9118) |

Verified and correct, needing no change:

- **Every number in sections 1–5.** §3.1 and §3.2 were re-run today and reproduce exactly
  (14.140 s, 57.543 HU, 8.210 s, R² 0.988, RMSE 2.077; 999/1000 fits, 0.518→0.025 s,
  8.08%→0.41%, SNR 20: 0.128 s / 2.03% / 0.513 s / 0.980). §3.4 reproduces byte-for-byte
  against the submitted provenance JSON.
- **All 11 references resolve** and agree with what we print (`check_references.py`).
- **The ethics statement**, verbatim against the source paper: Comitato Etico
  Interaziendale, CEI, id 596.345; 1964 Helsinki declaration; written consent waived for
  retrospective design.
- **The test-suite coverage claim in §4** — all eight named areas map to real tests (34).
- The a-LUT URLs, the UniToBrain version (V1.4) and DOI, the seven-module count, and
  figure numbering by first mention.

## Resolved, 1 September 2026

All five open items are closed. The release the paper cites is now **v0.1.1**,
`10.5281/zenodo.22226447` (concept `10.5281/zenodo.20921268`).

1. **The archived release ran on NumPy 2.** `ctp_core/parametric_maps.py` called
   `np.trapz`, removed in NumPy 2.0, at two sites on the path that produces Fig. 4, and
   `requirements-core.txt` set no upper bound on NumPy — so the archived v0.1.0 raised
   `AttributeError` on a fresh install. Fixed and released.
2. **Continuous integration exists and is green.** `.github/workflows/tests.yml` had been
   written but never committed; GitHub reported zero runs ever. It now runs the suite and
   both examples on Python 3.9 and 3.12, so §4's claim is true.
3. **`parametric_maps.py` now has tests** — `tests/test_parametric_maps.py`, which
   exercise the trapezoidal integral, assert that every masked pixel is really processed
   (the pixel loop swallows exceptions and would otherwise return silent zeros), and scan
   the package for every attribute NumPy 2.0 removed. Run against the v0.1.0 tree they
   fail, naming both call sites.
4. **The package is documented in English** — 723 lines translated across 20 files. No
   code was changed, verified by comparing the abstract syntax tree of every file before
   and after with string constants normalised, and by checking that no string carrying no
   Japanese was lost. `A_LUT.md` also had three dead links and claimed 29 tests where
   there are 5; both corrected.
5. **The abstract is 145 words**, against the template's "ca. 100"; it was 202.

Numerical results are unchanged. §3.1, §3.2 and §3.4 were all re-run and reproduce every
published value exactly.

## Upload files

- `ctp-core_SoftwareX_manuscript.docx` — manuscript, figures embedded.
- `ctp-core_SoftwareX_cover_letter.docx` — cover letter.
- `highlights.txt` — optional submission highlights.
- `figure_unitobrain_mol001.png` — public-data execution figure embedded as Fig. 4.
- `figure_unitobrain_mol001.json` — machine-readable provenance and run summary.
- `make_unitobrain_figure.py` — script used to recreate Fig. 4 after obtaining the dataset separately.
- `response_to_editorial_office.txt` — paste into the Editorial Manager comments box, one line per paragraph, unwrapped.

Do **not** upload anything named `_returned_v1_*`. Those are the version the editorial
office sent back, kept only as the record of what was returned. There is deliberately no
current `..._FINAL.pdf`: Editorial Manager builds the PDF from the DOCX, and a stale PDF
next to a rebuilt DOCX is how the wrong file gets uploaded.

## Supporting public records

- Repository: <https://github.com/Institute-of-One/ctp-core>
- Release: `v0.1.1` (the version the paper cites; v0.1.0 fails on NumPy 2)
- Version DOI: <https://doi.org/10.5281/zenodo.22226447>
- Concept DOI: <https://doi.org/10.5281/zenodo.20921268>
- Preprint: <https://doi.org/10.64898/2026.06.26.26356666>
- Public example dataset: UniToBrain v1.4, <https://doi.org/10.5281/zenodo.5109415>

## Before clicking Submit

1. Confirm the GitHub Actions test workflow passes on the public repository.
2. Confirm the public release contains the same code described in the manuscript.
3. Enter the medRxiv DOI in the submission system as a preprint.
4. Run `check_template_conformance.py` against the generated DOCX and read its outline. Re-download `softwarex-osp-template.docx` first and re-check the constants in that script against it, in case Elsevier has revised the template.
5. Select Shuji Yamamoto as sole author and corresponding author; use ORCID `0000-0001-9211-1071`.
6. Use the declarations in the manuscript for funding, conflicts, data, ethics, and generative-AI assistance.

Prepared 2026-08-24, revised 2026-09-01, from the authoritative public subtree `_publish/ctp-core` and IORN-001 records.
