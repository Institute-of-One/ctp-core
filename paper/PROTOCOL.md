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

**2026-10-19 (second entry of the day) — what the cross-check found in the drivers.** The
expanded snapshot went through Codex × Claude Code, and both reviewers returned fail with
overlapping findings. Seven were defects in the drivers and five were tests that asserted less
than they claimed. One of them changes what this protocol says is reported.

7. **No pooled stratum.** `run_reference.py` wrote an `all cases` row combining both sampling
   intervals — directly under a comment citing amendment 5, which forbids exactly that. The
   numbers had been quoted. **There is no pooled row now**, and the results file records
   `"pooling": "none"`. The per-interval results were unchanged by this amendment; amendment 11
   below then showed that the raw RMSEs quoted here contain our own sampling noise, and is where
   the numbers to use are given.

   The other six were not visible in any result, and two of them could have been. The figure
   case was chosen by a gate that counted **case directories** rather than cases that produced
   a comparison, so fourteen empty reference folders and one usable map would have passed it.
   `run_clinical.py` took the time axis, the acquisition window and the slice index from the
   filtered series and applied them to the unfiltered one without checking the two correspond,
   and the reference maps were ordered by **file name** while the volumes were ordered by
   **slice location**, with the volume's index used to read the reference. All three were
   checked against the data before anything was changed: on all 15 cases the two orders agree,
   the two series agree in shape and slice locations, and the chosen slice is at the same
   physical position in both. **The published numbers are unaffected** — the data happened to
   satisfy what the code never checked, which is luck and not a result. Every one of them is
   now checked, and the slice position is carried in `f1_f2_clinical.json` as `slice_location`
   so the comparison verifies it rather than assuming it.

   Every driver was re-run after the fixes. `synthetic_f1_f4.json` and `figure_case.json` are
   byte-identical; `aif_factor.json` and `aif_propagation.json` differ only by the new
   counts they now record; all 60 clinical records and all 15 reference rows are unchanged.

**2026-10-19 (third entry) — the cross-check on the fixes.** The corrected snapshot went back
through, and both reviewers returned fail again with seven further findings, all of them real.
Two change what this protocol can claim.

8. **Saturation is reported per map, not for "the maps".** `CBV` is a ratio of areas and `CBF`
   comes from a deconvolution; nothing obliges them to reach their ceilings together, and the
   driver had been treating either one clipping as both saturating. On this phantom they do
   coincide — **CBV reaches 20 ml/100 g and CBF 150 ml/100 g/min at the same arterial error of
   3.5**, with CBV at 19.35 and CBF at 147.40 just below it at 3.0 — so the measured claim is
   unchanged. It is now stated per map, because the agreement is a property of this phantom and
   not of the algebra.
9. **The reference comparison gates on the published 15, not on what the clinical file holds.**
   The documented plumbing check `run_clinical.py --cases 1` rewrites `f1_f2_clinical.json` with
   one case, and the completeness gate compared the result against that same file — so a stale
   plumbing run would have silently produced, and published, a one-case result. The gate is now
   against 15. In the same place, the two strata were selected with `dt < 1.0` and `dt > 1.0`,
   which assigns no stratum to a case at exactly 1.0 s or at NaN: it would have been counted and
   then dropped from every summary. Every compared case now lands in exactly one stratum, and a
   non-finite interval is refused.

   The other five were not visible in a result. A series with an acquisition missing from the
   middle would have been stacked into a shorter but well-formed volume and handed the full time
   axis, so acquisition numbers must now be contiguous and are compared between the two series —
   equal shapes and equal slice locations do not establish temporal correspondence. A non-finite
   slice position passed the new position check, because NaN compares false against everything.
   The `ctp_measure` docstring claimed the drivers hold no arithmetic of their own, which is
   false and is corrected. And every driver rebound `sys.stdout`, which raises when stdout has
   no underlying buffer, so **no driver's entry point could be called from a test** — which is
   why none of the previous round's gates was covered end to end. `run_screen.main` and
   `run_reference.main` are now exercised against a replaced dataset; `run_clinical.main` and
   `run_aif.main` read DICOM and are still not, which is stated rather than papered over.

**2026-10-19 (fourth entry) — the precision of the clinical measurement, which was overstated.**
The fourth cross-check round found three defects and, more importantly, took apart the
justification for the sampling rule. It was wrong in three ways at once and the reviewer was
right on all of them.

10. **The sampling rule's precision was asserted, not measured, and it was overstated by an
    order of magnitude.** The driver's docstring justified 500 voxels per hemisphere with "the
    standard error of a mean whose voxel-level sd is about 1 s is roughly 0.05 s, two orders
    below the effect being measured". The voxel-level standard deviation this data actually
    gives is **3.4 to 12.7 s**. The reported quantity is a *difference* of two means, so its
    standard error is larger than one mean's by √2. And the effect is not "about 5 s" — this
    protocol's own amendment 3 cites an admitted hemispheric difference of +0.24 s.

    Measured properly, the standard error of each hemispheric difference is **0.23 to 0.79 s**.
    It is now computed from the two recorded spreads and stored per arm as
    `delta_standard_error`. On **31 of the 60 arms the difference is smaller than twice its own
    standard error**, so those arms do not resolve the quantity they report. Raising the sample
    until they did would need the whole hemisphere, which is the 3.7-hour-per-case measurement
    that was abandoned at the start; the limit is therefore stated rather than chased.

11. **Part of the agreement with the reference maps was our own sampling noise, and one
    headline number was entirely that.** The reference maps average every voxel in the slice;
    we average 500 per side. `run_reference.py` now subtracts our sampling variance in
    quadrature and reports what is left:

    | sampling interval | method | RMSE vs reference | our sampling | method error |
    |---|---|---|---|---|
    | 0.50 s (n=9) | argmax | 0.52 s | 0.37 s | 0.37 s |
    | 0.50 s (n=9) | fitted | 0.46 s | 0.34 s | 0.32 s |
    | 2.81 s (n=6) | argmax | 0.96 s | 0.48 s | **0.83 s** |
    | 2.81 s (n=6) | fitted | 0.32 s | 0.33 s | **0 — within our own precision** |

    (These are the values in `clinical_vs_reference.json` after amendment 12 below; the
    finite-population correction moved them by under one percent.)

    **The claim this replaces was "at 2.81 s the argmax path is three times worse than the
    fitted path".** That ratio compared a number that is mostly method error against one that
    is entirely sampling noise. What the data support is stronger and differently shaped: at
    2.81 s the fitted path agrees with the reference *to within the precision of our own
    measurement*, while the argmax path disagrees by 0.83 s, which our measurement resolves. At
    0.50 s the two are 0.37 s and 0.32 s — indistinguishable, and the fit buys nothing. The
    conclusion a reader acts on is unchanged in direction and must be stated this way.

The three code defects: `tissue_mask` admitted an infinite sample as evidence that a bolus had
arrived, so one such voxel could have entered a hemispheric mean or decided which slice to
measure; `run_aif`'s population gate accepted an area ratio of zero as finite and therefore
usable, though a ratio of zero means one of the two curves is absent; and the screen's
completeness gate saw a missing case and an empty reference folder but not a folder holding
*some* of its slices — the expected count is now derived from the acquisition folder and the
time vector, which needs no pixel data.

**2026-10-19 (fifth entry) — the sampling variance, corrected properly.** Four findings, and
one of them is the statistics rather than the plumbing.

12. **The draw is without replacement, so the variance of each mean carries `(1 − n/N)`.** The
    standard error introduced by amendment 10 omitted the finite-population correction. With 500
    voxels drawn from a hemisphere of about 35,000 the factor is **0.986** — under one percent on
    the standard error — so **no published number changes**. It is corrected anyway, because the
    quantity is subtracted from the disagreement with the reference maps, and subtracting an
    inflated variance erases genuine disagreement. The populations are now recorded per arm as
    `left_population` and `right_population`. One approximation remains and is stated in the
    function rather than buried: on the fitted path the admitted values are those whose fit
    passed the validity rule, which is not a random subset of the drawn voxels, so `n` is the
    admitted count there.

The other three were process, not measurement. The screen's new completeness check **failed
open** — when the expected slice count could not be derived it was skipped, although that is
itself the partial-extraction situation the check was added for; not knowing is now an exclusion,
and each way of failing says which it was. A test still asserted the precision claim amendment 10
withdrew, so it was deleted rather than adjusted, and the injection that used it as its oracle
now names the test that pins the frozen count. And the documented plumbing check
`run_clinical.py --cases 1` **still overwrote the published 15-case result** — the earlier fix had
only stopped `run_reference.py` from consuming a one-case file, not stopped the file being
destroyed; a partial run now writes `f1_f2_clinical.partial.json`.

One limitation is recorded rather than fixed: a partly extracted acquisition folder whose file
count happens to divide by the number of time points still yields a wrong expected slice count.
Catching that would mean reading DICOM headers in the screen, which is what deriving the count
from file names was chosen to avoid.

**2026-10-20 (sixth and last round) — the first clean validation, and seven more findings.**
This was the round where the framework finally reported `inputs_unchanged: true`; the two before
it were refused because the manifest was being edited while they ran. The verdict is still FAIL,
for the one reason that will not change here: the framework executes tests under `python -I`,
which cannot see NumPy. Nothing in this round changed a measured value — the figure case, the
ranking, and every result file are byte-identical afterwards.

13. **The expected number of reference slices is read, not inferred.** The completeness gate had
    been dividing the acquisition folder's file count by the number of time points, which gives
    a plausible wrong answer for a partly extracted folder whose count happens to divide evenly.
    It now reads the DICOM headers — one per file, no pixel data, about three seconds a case —
    and takes the count as the number of **distinct slice locations**, requiring the
    (acquisition, location) pairs to be distinct and to fill the grid. That also catches a
    partly extracted *acquisition* folder, which the division could not. The screen now takes
    88 seconds instead of 40.

14. **The shipped time vector must be strictly increasing.** Its length was checked and its
    order was not. Out of order it would have given a meaningless or negative sampling interval
    and a window that is not the acquisition, with nothing downstream noticing.

The other five were coverage, and the pattern in them is worth keeping: *a fix is not covered by
a test of the function it lives in.* The reference maps' sort by slice location — the actual fix
for the file-name ordering defect — had no test, only its consumer did. Three tests of the
standard-error formula sat inside a class that is skipped wherever `ctp_core` is absent, although
they are pure functions that need nothing from it. Nothing called `run_synthetic.main` or
`run_propagation.main`, so a `main` that stopped jittering the bolus arrival or skipped the
saturation abort would have changed the published results with every test green. One injection
was mislabelled and proved nothing about the defect it named. And a class docstring still
claimed to check a precision claim that amendment 10 withdrew.

**This is where the cross-check stops for this module.** Six rounds, 31 defects, and the measured
values have not moved since the third. What the later rounds found is still real, but it has
shifted from the numbers to the robustness of code paths this dataset does not exercise, and the
next thing the paper needs is figures and text rather than another round.

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
| `run_figure_maps.py` | `mol001_maps.npz` | the maps behind the clinical figure |

`unitobrain.py` is the only module that knows the dataset's layout, `ctp_measure.py` holds the
measurement logic, tested in `test_ctp_measure.py`, and `driver_io.py` holds the one line of
console setup the drivers share. The drivers' screening rules, sampling rule
and design constants are tested in `test_drivers.py`, and `prove_driver_gates.py` applies a known
defect to a copy of the directory and requires the test named for it to go red — distinguishing a
failed assertion from an escaped exception, and refusing a mutation whose expected test name is
ambiguous. Run both; the counts are not written down here, because a count in prose goes stale
the moment the thing it describes changes, and one in this repository already did.

The dataset itself is not redistributed and there is no default path: set `UNITOBRAIN_ROOT`.
CI runs the measurement suite and the injection proof on every push, because a suite that only
ever runs on one laptop is not a gate.
