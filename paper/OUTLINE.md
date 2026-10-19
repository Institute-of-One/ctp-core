# Manuscript outline — British Journal of Radiology, Research Article

**Written:** 2026-10-16, while the clinical re-measurement runs.
**Last checked against the measurements:** 2026-10-19.
**Companion files:** `PROTOCOL.md` (frozen design, six amendments, and §8 — which driver writes
which results file), `analysis/` (the drivers), `results/` (every number).

The word budget is the binding constraint: **3,000 words** of body text, against roughly 10,000
at the journals this programme usually targets. Structure is therefore decided before writing,
not after.

---

## 1. What the journal requires (read from its author guidelines on 2026-10-16)

| Item | Requirement | Consequence here |
|---|---|---|
| Abstract | **Structured, 250 words**: Objectives, Methods, Results, Conclusions, **Advances in knowledge** (1–2 sentences on novelty). No references, no abbreviations | "Advances in knowledge" is a heading this programme has not written before. Keywords 3–10 |
| Body headings | **Introduction, Methods, Results, Discussion** — the journal names them | No Conclusions section; the conclusion sits at the end of Discussion |
| References | Vancouver / AMA, MEDLINE abbreviations, **maximum 50** | Comfortable. 25–35 is the right density for 3,000 words |
| Figures | **≤10**; colour half-tone 300 dpi, **greyscale 600 dpi**, **combination half-tone and line art 600–900 dpi**, monochrome line art 1200 dpi. Formats jpeg/png/tiff/svg/pdf/eps | **Our figures are combination half-tone and line art, so 600–900 dpi, not the 300 dpi used for IORN-005.** Set this in the generator, not by hand |
| Alt text | **Required for every figure**, under the legend, prefixed `Alt text:` | Easy to omit and get returned for. Generate it with the caption so it cannot drift |
| Tables | ≤5 | One table is enough |
| Data availability | **Required** | Zenodo DOI of the release, plus the UniToBrain accession |
| Ethics | Methods **must** state approval, or that approval was not required, naming the authorising body and reference numbers | Public de-identified data and synthetic data: state plainly that no approval was required and why |
| Consent | Written informed consent for human participants | Not applicable; state why rather than omitting |
| Conflicts, funding | On the **title page**, under their own subheadings | Separate title page, as for Medical Physics |

## 2. Word budget

| Section | Words | Contents |
|---|---|---|
| Introduction | 450 | The gap: published comparisons measure disagreement and cannot attribute it. Prior simulation work exists (Med Phys 2021) and named the quantitative analysis as future work |
| Methods | 900 | The two arms; the four factors; the admission and validity rules; the sampling rule; the two sampling protocols in the clinical set; the ethics and consent statements |
| Results | 750 | F3 (AIF) first, F1/F4 (quantisation floor) second, F2 third, clinical example last |
| Discussion | 750 | What a reader should do differently; what is not claimed; limitations |
| **Total** | **2,850** | 150 words of margin against a limit whose breach is a returned manuscript |

## 3. Figures (four; the limit is 10 but the word budget is the real limit)

1. **Design.** The two arms and the four factors, as one diagram. Line art, 1200 dpi.
2. **The quantisation floor.** Recovered-TTP error against sampling interval and SNR, with the
   closed form `dt/√12` drawn as a line, from `results/synthetic_f1_f4.json`. This is the figure
   that carries the decision.
3. **The arterial input.** Measured AIF area ratio across the 15 cases, and the propagation into
   CBV and CBF with the implementation's own ceilings marked, from `results/aif_factor.json` and
   `results/aif_propagation.json`. Every case lies beyond the saturation threshold.
4. **The clinical case** (author's instruction, and `AGENTS.md` §3). MOL-001, chosen by the
   frozen rule, with the maps and the rule in the caption.

## 4. The claim, in one sentence

> Published comparisons of CT-perfusion software measure how much implementations disagree but
> cannot say which choice produced the disagreement; on data whose truth is known, two choices
> account for most of it, and they fail in opposite ways — the arterial input sets a systematic
> scale error large enough to saturate the quantitative maps, while taking the time to peak from
> the sampled curve imposes a precision floor that no increase in dose can lower.

## 5. What this paper does not claim

- Not the first synthetic CT-perfusion reference. The Medical Physics 2021 framework precedes it
  and is cited as such; what is new is that the analysis it named as future work has been done,
  with an implementation a reader can run.
- Nothing about clinical accuracy, diagnosis or patient management.
- No statement that one package is better than another. The factors are properties of choices,
  not verdicts on products.

## 6. Open before writing

- ~~The clinical re-measurement with the validity rule.~~ **Done, 2026-10-19**, from the
  drivers now in `paper/analysis/`. 15 cases, 60 records, no exclusions.
- ~~Whether the quantisation floor is visible between the two sampling protocols.~~ **Yes, and
  it is the sharpest result in the paper.** Against the dataset's own reference maps the fit-free
  path gives RMSE 0.96 s at 2.81 s sampling and 0.52 s at 0.50 s, while the fitted path gives
  0.32 s and 0.46 s. At the coarse interval the fit-free error sits at the predicted floor of
  0.81 s and the fitted path goes **below** it — which is only possible because a fitted peak is
  not confined to the sampling grid. At the fine interval the floor is 0.14 s, both paths are
  far above it, and they are indistinguishable: there the floor is not the limiting term, so the
  fit buys nothing. The honest statement is therefore conditional, and it tells a reader which
  path to use at which sampling interval rather than which is better.
- Reference list: assembled and every DOI resolved before a word of the Discussion is written.

## 7. Where the numbers come from

`PROTOCOL.md` §8 maps each driver to the results file it writes. Figure generators must read
those files; no number is typed into the manuscript. The dataset's location comes from
`UNITOBRAIN_ROOT` — there is no default path in the repository.
