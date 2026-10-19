# Protocol — frozen before implementation

**Frozen:** 2026-10-14, before any analysis code for this study was written.
**Target:** British Journal of Radiology, Research Article (3,000 words, 10 figures, 50 references).
**Supersedes:** the SoftwareX submission SOFTX-D-26-01111, rejected after review on 2026-10-12.

This file exists so that the design cannot be adjusted after the results are seen. Anything
changed below after the first measurement is recorded as an amendment with its date and reason,
never by editing the original line.

---

## 1. The question

Published comparisons of CT-perfusion software — RAPID against Brainomix, RapidAI against
Viz.ai, packages against a delayed infarct core — measure **how much the packages disagree**.
None of them can say **which implementation choice produced the disagreement**, because clinical
data carry no ground truth for perfusion.

> **How much of the disagreement between CT-perfusion implementations is attributable to each
> individual processing choice, and in which direction does each choice move the recovered
> CBV, CBF and TTP?**

On synthetic data with analytically known truth the contributions separate. On real data they can
be shown to persist against an independent reference.

## 2. Relation to prior work

A simulation framework for CT perfusion already exists: *A dynamic simulation framework for CT
perfusion in stroke assessment built from first principles*, Medical Physics 2021,
doi:10.1002/mp.14887. **This study does not claim to be the first synthetic CT-perfusion
reference.** It differs in two stated ways, both verified in that paper's own text on 2026-10-13:

1. That framework is distributed "through incorporation into the **licensed** XCAT phantom", and
   its data are available "from the corresponding author upon reasonable request". It cannot be
   run by a third party without a licence. This implementation is MIT-licensed, installable and
   deterministic.
2. That paper states: "we have **not** included a statistical analysis on the correlation of the
   computer-generated maps with the ground truth; **this is the subject of future work**." The
   measurement below is that future work.

A physical cerebral CTP phantom was published in Physica Medica 2025,
doi:10.1016/j.ejmp.2025.104944; it addresses the same validation need by other means and is not
a competing claim.

## 3. Factors (frozen)

Each factor is varied with all others held at its reference level. Levels are fixed here.

| # | Factor | Levels | Why it is in |
|---|---|---|---|
| F1 | Curve model | gamma-variate fit; fit-free (sampled peak, TTP, trapezoidal AUC) | The two paths `ctp_core` already provides |
| F2 | Spatial smoothing | none; 3 mm; 6 mm | A SoftwareX reviewer asked why smoothing was absent. The dataset's own reference maps use 3 mm, so 3 mm is the comparable level |
| F3 | Arterial input function | automatic detection; operator-placed ROI | The single largest known source of between-operator variation |
| F4 | Noise level | three levels spanning the dose range used in `examples/run_snr_sweep.py` | Separates noise sensitivity from model sensitivity |

**Not varied, and stated as fixed:** reconstruction kernel, slice thickness, temporal sampling,
and the a-LUT colour mapping. The a-LUT is cited by file name and version in the manuscript.

## 4. Outcomes (frozen)

**Primary.** Bias and standard deviation of recovered **CBV, CBF and TTP** against the analytic
truth of the synthetic data, per factor level, over the admitted region.

**Secondary.** Agreement of the same quantities with the reference maps shipped with the
UniToBrain test set (`NLR_CBF`, `NLR_CBV`, `NLR_TTP`), measured as bias and limits of agreement,
per factor level.

**Not an outcome.** Which implementation is "best". Nothing here establishes clinical accuracy,
and the manuscript will say so once, in the Limitations, rather than as a disclaimer repeated
throughout — that repetition was a stated reason for the SoftwareX rejection.

No expected value is written here. The expected values are what the measurement returns.
A closed form is used where one exists (the synthetic generator's analytic CBV and TTP), and
otherwise the quantity is measured before anything is asserted about it.

## 5. Admission rules (frozen)

- **Synthetic:** every voxel of the generated phantom whose true CBV is non-zero.
- **Clinical:** the UniToBrain test set, 15 cases (MOL-001 … MOL-260). A case is excluded only
  for a stated technical failure — missing series, failed registration, or an AIF the automatic
  detector cannot place — and every exclusion is reported with its reason and its case number.
- **The figure case is chosen by rule, not by appearance.** Among admitted cases, the one with
  the **largest left–right hemispheric asymmetry in TTP**. The rule, the number of candidates and
  the exclusions go in the caption. If no admitted case shows a perfusion deficit, that is
  reported and the figure shows what the data contain instead; the paper will not describe a
  deficit that is not there.

## 6. Analysis rules

- Factor effects are reported for every level measured. **No level is dropped after the fact**,
  and no subset of keV, dose or case is selected post hoc.
- A result that contradicts the expectation behind including a factor is reported as measured.
- Every number in the manuscript is produced by executed code into a results file and resolved
  into the text at build time; the test suite fails if text and results disagree.

## 7. Amendments

**2026-10-14 — the statistic for TTP, and the TTP reference point.** Found while checking MOL-001
against the maps shipped with the dataset, before any result was recorded.

1. **Do not summarise TTP with a median.** The fit-free path takes TTP as the argmax over the
   sampled time points, so on this dataset it can take only 18 values spaced 2.81 s apart, while
   the shipped reference maps come from a fit and carry 1213 distinct values in a single slice.
   A median over a quantised map lands on the modal sample on both sides and reports a
   difference of zero where one exists: on slice 9 the median gave +5.62 s and the mean +4.11 s,
   and on two other slices the median gave exactly 0.00. **Means and full distributions are
   reported; the quantisation itself is a result, not a nuisance.**
2. **TTP is not referenced to the same origin in the two implementations.** The shipped maps give
   TTP relative to bolus arrival (left hemisphere median 6.45 s on slice 9); this implementation
   gives it as absolute time from the start of the acquisition (28.10 s). The two differ by a
   near-constant offset of about 23 s. **Agreement is therefore assessed on hemispheric and
   regional differences, not on absolute values**, and the definition used is stated in the
   manuscript. Reporting the absolute difference as an error would be a unit mistake, not a
   finding.

Neither amendment changes a hypothesis or a factor. Both were made before any outcome was
recorded, and both are consequences of looking at the data rather than at a summary number.

**2026-10-16 — a validity rule for the fitted path, and stratification by sampling interval.**
Found on the first full run of the clinical arm, and recorded before the run was repeated.

3. **A fitted peak time outside the sampled window is not a measurement.** `fit_gamma_variate`
   derives `peak_time` analytically from the fitted parameters and never checks it against the
   times that were actually acquired. On MOL-002 it returned values from **−32 s to +919 s** for
   an acquisition spanning 0 to 44 s, and reported `success` for all of them: **about 30 % of
   the fits in that case fall outside the window**. A mean over voxels is then meaningless — it
   gave a hemispheric difference of +17.9 s where the window-restricted mean gives +0.24 s and
   the argmax path gives +0.39 s. **A fit is admitted only if its peak time lies within the
   acquisition window.** The rejected fraction is reported per factor level as an outcome in its
   own right, because it is a property of the implementation and not a nuisance.
4. **Report the window-restricted mean and the median together.** The first clinical run used a
   bare mean and was destroyed by the outliers above; an earlier amendment had to forbid the
   median because it collapses on the quantised path. Neither statistic is safe alone here, so
   both are reported and a disagreement between them is a signal about the distribution rather
   than something to resolve silently.
5. **Stratify the clinical arm by sampling interval.** The UniToBrain test set is not one
   protocol: **9 cases are sampled at 0.50 s (89 points over 44 s) and 6 at 2.81 s (18 points
   over 47.8 s)**. This was not noticed when the set was admitted. It is an advantage rather
   than a problem — the synthetic arm predicts a quantisation floor of `dt/√12`, which is
   0.14 s against 0.81 s for the two groups, so the clinical data can test that prediction
   internally. Case-level results are never pooled across the two intervals.

**2026-10-19 — the hemispheric split, and where the code lives.** The measurement code went
through the Codex × Claude Code cross-check (`.ai-check/`), which found three implementation
defects. One of them changes a number in this protocol's own terms and is recorded here.

6. **The midline is `floor(centroid + 0.5)`, not `round(centroid)`.** Python's `round` sends a
   half to the even integer, so a mask whose column centroid falls exactly between two columns —
   which is every left–right symmetric mask of even width — was split one column off balance for
   half of all widths. The first measurements used `round`. **Every driver was re-run from the
   repository after the correction**, and the pre-correction screen was run again beside the
   corrected one for comparison: the ranking of all 15 cases agrees line for line, so the figure
   case is unchanged (MOL-001, +6.43 s on slice 15); the arterial-area ratios are unchanged
   (median 6.97, range 3.56–10.47); and the clinical arm reproduces to the last digit — all
   **60 records in `f1_f2_clinical.json` are identical** before and after, as are all 15 rows of
   `clinical_vs_reference.json`. The synthetic arm was also re-run and its standard deviation
   at 2.81 s moved from 0.871 s to 0.821 s against the predicted 0.811 s — a different draw of
   the same design, within the ±0.04 s standard error of a standard deviation estimated from 200
   repeats, not a change of result.

---

## 8. Where the code is, and which file holds which number

Every number in the manuscript comes from a file in `paper/results/`, and every one of those
files is written by a driver in `paper/analysis/`. The drivers were in a scratch directory while
the measurements were being designed, which meant they were outside the cross-check and outside
version control; they are in the repository now.

| Driver | Writes | Factor |
|---|---|---|
| `run_screen.py` | `figure_case.json` | the frozen figure-case rule (§5) |
| `run_aif.py` | `aif_factor.json` | F3, automatic detection against the input the dataset used |
| `run_propagation.py` | `aif_propagation.json` | F3, how that error reaches CBV and CBF |
| `run_synthetic.py` | `synthetic_f1_f4.json` | F1 × F4 against analytic truth |
| `run_clinical.py` | `f1_f2_clinical.json` | F1 × F2 on the clinical arm |
| `run_reference.py` | `clinical_vs_reference.json` | F1 against the dataset's own reference maps |

`unitobrain.py` is the only module that knows the dataset's layout; `ctp_measure.py` holds the
measurement logic, tested in `test_ctp_measure.py`. The drivers' screening rules, sampling rule
and design constants are tested in `test_drivers.py`, and `prove_driver_gates.py` injects
fourteen defects and checks that the test which claims to catch each one is the one that fails.
The dataset itself is not redistributed: set `UNITOBRAIN_ROOT` to point at it.
