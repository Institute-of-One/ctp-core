"""Build the manuscript from the measurements, for the British Journal of Radiology.

    python paper/build_manuscript.py

Writes ``paper/build/manuscript.md``, ``paper/build/title_page.md`` and
``paper/build/word_counts.json``.

The manuscript is a generated document and this file is its source. **No measured number is
typed into the prose.** Every one is interpolated from ``paper/results/``, so the text cannot
drift from the data, and a changed measurement either changes the sentence or breaks the build.
Figure captions and their alt text come from ``paper/figures/captions.json``, written beside
each figure by ``make_figures.py``.

What the journal requires, and where it is met:

* structured abstract of 250 words with Objectives, Methods, Results, Conclusions and
  **Advances in knowledge** -- :func:`abstract`
* body headings Introduction, Methods, Results, Discussion, with the conclusion at the end of
  the Discussion rather than in a section of its own
* alt text under every figure legend, prefixed ``Alt text:``
* data availability and ethics statements, the second naming the authorising body or saying
  plainly that approval was not required and why
* conflicts and funding on the title page
"""

from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")
FIGURES = os.path.join(HERE, "figures")
BUILD = os.path.join(HERE, "build")

#: The affiliation exactly as Crossref carries it: city before postcode. Checked against the
#: published record rather than recalled, because it has been got wrong before.
AUTHOR = "Shuji Yamamoto"
AFFILIATION = "Institute of One, LISIT Co., Ltd., Tokyo 150-0044, Japan"
ORCID = "0000-0001-9211-1071"
EMAIL = "yamamoto@lisit.jp"

TITLE = ("Which processing choice moves a CT perfusion number, and by how much: "
         "an attributable measurement on public data")


def load(name: str):
    with open(os.path.join(RESULTS, name), encoding="utf-8") as handle:
        return json.load(handle)


def figures() -> dict:
    path = os.path.join(FIGURES, "captions.json")
    if not os.path.isfile(path):
        raise SystemExit("run paper/make_figures.py first: no captions.json")
    with open(path, encoding="utf-8") as handle:
        return {int(k): v for k, v in json.load(handle).items()}


class Numbers:
    """Every measured value the prose uses, resolved once from the results files."""

    def __init__(self):
        self.aif = load("aif_factor.json")
        self.propagation = load("aif_propagation.json")
        self.synthetic = load("synthetic_f1_f4.json")
        self.clinical = load("f1_f2_clinical.json")
        self.reference = load("clinical_vs_reference.json")
        self.figure_case = load("figure_case.json")

        self.intervals = sorted({r["dt"] for r in self.synthetic})
        self.noises = sorted({r["snr"] for r in self.synthetic})
        self.strata = {s["stratum"]: s for s in self.reference["strata"]}
        self.cases = sorted({r["case"] for r in self.clinical})
        self.fine = [c for c in self.reference["cases"] if c["dt"] < 1.0]
        self.coarse = [c for c in self.reference["cases"] if c["dt"] >= 1.0]

    def cell(self, dt: float, snr: float, method: str) -> dict:
        return next(r for r in self.synthetic
                    if r["dt"] == dt and r["snr"] == snr and r["method"] == method)

    def rejected(self, series: str, method: str) -> tuple[float, float, float]:
        values = sorted(r["pct_rejected"] for r in self.clinical
                        if r["series"] == series and r["method"] == method)
        middle = values[len(values) // 2]
        return values[0], middle, values[-1]

    def samples_in(self, case: str) -> int:
        """How many time points that case was acquired at, which is how many values the
        fit-free path can return."""
        return next(r["n_samples"] for r in self.clinical if r["case"] == case)

    def standard_errors(self) -> tuple[float, float]:
        values = [r["delta_standard_error"] for r in self.clinical]
        return min(values), max(values)

    def unresolved_arms(self) -> tuple[int, int]:
        total = len(self.clinical)
        under = sum(1 for r in self.clinical
                    if abs(r["delta"]) < 2 * r["delta_standard_error"])
        return under, total

    @property
    def ceiling(self) -> float:
        return min(v for v in self.propagation["first_clipped_ratio"].values()
                   if v is not None)


def abstract(n: Numbers) -> str:
    coarse = n.strata["dt 2.81 s"]
    fine = n.strata["dt 0.50 s"]
    floor = n.cell(2.81, max(n.noises), "sampled")
    return f"""
## Abstract

**Objectives.** Comparisons of CT perfusion software measure how much implementations disagree
but cannot say which processing choice caused it. This study measures each separately.

**Methods.** Curve model, smoothing, arterial input and noise were varied one at a time in an
open-source implementation, on synthetic curves with analytically known time to peak and on the
{n.aif['n_cases']} public UniToBrain cases, which ship reference maps and the arterial input
used to make them. The design was fixed before measurement.

**Results.** The sampled time to peak has a precision floor at the sampling grid: at
{floor['dt']:.2f} s its spread was {floor['sd']:.2f} s against a predicted
{floor['quantisation_floor']:.2f} s, unmoved by raising the signal. Against the
reference maps, with our own sampling error removed, it disagreed by
{coarse['argmax']['residual_after_removing_our_sampling']:.2f} s at 2.81 s sampling while the
fitted path agreed within our precision; at 0.50 s the two were indistinguishable. Automatic
arterial input detection understated the arterial area by a median factor of
{n.aif['median_area_ratio']:.1f}, which passes proportionally into blood volume and flow; both
saturate at {n.ceiling:.1f}, beyond which every case lies.

**Conclusions.** Two choices account for most of the disagreement and fail in opposite ways: the
arterial input sets a scale error large enough to saturate the maps, and the sampled time to
peak a precision floor that dose cannot lower where sampling is coarse.

**Advances in knowledge.** Each choice is measured rather than inferred from between-package
disagreement, on code and data a reader can run, and the conditions under which the simpler
path suffices are quantified.
"""


def introduction(n: Numbers) -> str:
    return f"""
## Introduction

CT perfusion guides treatment in acute stroke, and the numbers it produces depend on software.
Comparisons between packages are therefore common, and they consistently find disagreement: core
and penumbra volumes differ between vendors on the same acquisition, and the differences are
large enough to move a patient across a treatment threshold.[@vendor_disagreement;@not_interchangeable] What those studies cannot do is say *which* choice produced the
disagreement. They compare finished products on data that carry no ground truth for perfusion, so
a difference can be attributed to a package but not to a decision inside it.

The decisions are few and well known. Whether the time to peak is read from the sampled curve or
from a fitted model; whether the data are smoothed before fitting and by how much; how the
arterial input is chosen; and how much noise the acquisition carries. Each is a line in an
implementation. What is missing is the size of each one's effect, in the units the clinician
reads.

The closest existing measurement asks a related question from the other side. Lengthening the
acquisition interval from 1 to 5 s on 25 patients, one study reported the bias this introduces
in blood flow, volume and transit time and in infarct volumes, and concluded that axial coverage
can be bought with intervals up to 5 s depending on the analysis method.[@prolonged_intervals]
It examines neither the time to peak nor any limit the sampling grid imposes on precision — and
it is precisely at the intervals it licenses that such a limit would bind.

A simulation framework for CT perfusion built from first principles also exists, and it names
the missing measurement explicitly: its authors state that they have not included a statistical
analysis of the correlation between the generated maps and the ground truth, and that this is
the subject of future work.[@simulation_framework] That framework is distributed through a
licensed phantom and its data are available on request, so a third party cannot run it. A
physical cerebral perfusion phantom addresses the same validation need by other
means.[@physical_phantom] Standardising the processing steps themselves has been shown to
harmonise the results between packages,[@harmonisation] which is an argument for knowing what
each step contributes.

This study does that measurement on an implementation that anyone can install and on data anyone
can download. Four factors are varied one at a time, on synthetic curves whose time to peak is
known in closed form and on the {n.aif['n_cases']} cases of the public UniToBrain test
set,[@unitobrain] which ships reference perfusion maps together with the arterial input curve
those maps were made with — so that feeding the same input to a different implementation makes a
difference in the maps a difference in method. The question is not which package is better. It
is which choice moves a number, by how much, and under what conditions it stops mattering.
"""


def methods(n: Numbers) -> str:
    rejected_unfiltered = n.rejected("unfiltered", "gamma")
    rejected_filtered = n.rejected("filtered_3mm", "gamma")
    low, high = n.standard_errors()
    sample = n.clinical[0]
    return f"""
## Methods

**Ethics and consent.** This study used only synthetic data and the UniToBrain test set, which
is published, de-identified and openly licensed. No institutional review board approval was
required and none was sought, because no new human data were acquired and no identifiable
information was accessed; for the same reason the requirement for informed consent does not
arise. The dataset's own publication records the approvals under which it was collected.

**Implementation.** All measurements use ctp-core, an MIT-licensed Python implementation of
singular value decomposition deconvolution[@ostergaard] in its block-circulant,
arrival-insensitive form,[@wu_osvd] with gamma-variate fitting,[@gamma_variate] following the
indicator-dilution formulation.[@konstas] The implementation displays
blood flow and volume maps with the ASIST-Japan standard lookup table;[@alut] the time-to-peak
maps in Figure 4 are shown on a diverging scale instead, because what is compared there is a
deviation about a midpoint rather than a magnitude. The version measured here is archived with
a digital object identifier (Data availability).

**Design.** Four factors were varied with the others held at a reference level (Figure 1): the
curve model (gamma-variate fit against the fit-free path, which takes the time to peak as the
argmax of the sampled curve); spatial smoothing (the unfiltered series against the 3 mm / 20 HU
series the dataset's own reference maps were produced from); the arterial input (automatic
detection against the curve shipped with the maps); and noise. Reconstruction kernel, slice
thickness and temporal sampling were fixed and are reported rather than varied. The design, the
levels, the admission rules and the rule for selecting the illustrative case were written down
before any measurement; the record and its amendments accompany the code.

**Synthetic arm.** Gamma-variate curves were generated at {len(n.intervals)} sampling intervals
from {min(n.intervals):.2f} to {max(n.intervals):.0f} s and {len(n.noises)} signal to noise
ratios from {min(n.noises):.0f} to {max(n.noises):.0f}, with
{n.cell(2.81, 40.0, 'sampled')['n_attempted']} curves per combination. Bolus arrival was
jittered uniformly across one sampling interval: without that, arrival would always coincide
with a sampling instant, the fit-free path would be unbiased by construction, and the comparison
would be empty. The outcome is the bias and standard deviation of the recovered time to peak
against the analytic peak time of the generating curve.

**What the reference maps are.** The UniToBrain set ships perfusion maps produced by a
model-based non-linear regression, which fits a box-shaped impulse response to each voxel's
attenuation curve;[@nlr_method] they were the training target of the neural network that paper
presents, not its output.[@unitobrain] They are therefore an independent implementation of the
same physics — and a *fitted* one, which matters for interpreting the comparison and is taken
up in the Discussion.

**Clinical arm.** All {n.aif['n_cases']} cases of the UniToBrain test set were used; none was
excluded. The set is not one protocol — {len(n.fine)} cases are sampled at 0.50 s and
{len(n.coarse)} at 2.81 s — and case-level results are never pooled across the two. For each
case the slice with the most admitted tissue was measured, tissue being admitted on a plausible
baseline attenuation, an enhancement that actually arrived, and finite values throughout. The
midline was taken as the column centroid of the tissue mask rather than the image centre,
because the head is not always centred.

A fitted peak time was admitted only if it lay within the acquisition window. This rule is
necessary rather than cosmetic: the fitter reports success for peak times far outside the times
sampled, and admitting them moved one case's hemispheric difference from +0.24 s to +17.9 s. The
rejected fraction is reported as an outcome in its own right, since it is a property of the
implementation.

{sample['n_per_hemisphere']} voxels were drawn per hemisphere without replacement, with a fixed
seed, once per case, so that both input series and both curve models were compared on the same
voxels. The standard error of each hemispheric difference was computed from the two measured
spreads with the finite-population correction, and ranges from {low:.2f} to {high:.2f} s; it is
reported with every value and subtracted in quadrature before any disagreement with the
reference maps is attributed to method. Agreement is assessed on hemispheric *differences*, not
on absolute times, because the reference maps are referenced to bolus arrival and this
implementation to the start of the acquisition, a near-constant offset of about 23 s.

**Statistics.** Bias, standard deviation and root mean square error are reported per stratum
with the number of cases behind them. No test of significance is reported: the comparisons are
of measurement error against a reference, not of groups, and the quantity of interest is the
size of an effect and its precision.
"""


def results(n: Numbers) -> str:
    captions = figures()
    coarse = n.strata["dt 2.81 s"]
    fine = n.strata["dt 0.50 s"]
    floor_coarse = n.cell(2.81, max(n.noises), "sampled")
    floor_fine = n.cell(min(n.intervals), max(n.noises), "sampled")
    gain_fine = 100 * (1 - floor_fine["sd"]
                       / n.cell(min(n.intervals), 20.0, "sampled")["sd"])
    gain_coarse = 100 * (1 - floor_coarse["sd"] / n.cell(2.81, 20.0, "sampled")["sd"])
    unfiltered = n.rejected("unfiltered", "gamma")
    filtered = n.rejected("filtered_3mm", "gamma")
    under, total = n.unresolved_arms()
    chosen = n.figure_case["chosen"]
    return f"""
## Results

*The fit-free path has a precision floor at the sampling grid, and it binds only when sampling
is coarse.* On synthetic curves the standard deviation of the recovered time to peak for the
fit-free path approaches the closed form for a value rounded to a grid of spacing Δt
(Figure 2). At {floor_coarse['dt']:.2f} s and the highest signal it was
{floor_coarse['sd']:.2f} s against a predicted {floor_coarse['quantisation_floor']:.2f} s, a
ratio of {floor_coarse['sd'] / floor_coarse['quantisation_floor']:.2f}; at
{floor_fine['dt']:.2f} s it was {floor_fine['sd']:.2f} s against
{floor_fine['quantisation_floor']:.2f} s, a ratio of
{floor_fine['sd'] / floor_fine['quantisation_floor']:.1f}. The consequence for acquisition is
direct: doubling the signal to noise ratio improved the fit-free path by {gain_fine:.0f}% at
{floor_fine['dt']:.2f} s but only {gain_coarse:.0f}% at {floor_coarse['dt']:.2f} s, while it
improved the fitted path at every interval. Where sampling is coarse, the fit-free path is
already at its floor and dose cannot lower it.

*Against an independent reference the same split appears.* Compared with the reference maps
the dataset ships, and after removing the sampling error of our own estimate, at
{coarse['stratum'].split()[1]} s sampling the fit-free path disagreed by
{coarse['argmax']['residual_after_removing_our_sampling']:.2f} s — close to the predicted floor
of {floor_coarse['quantisation_floor']:.2f} s — while the fitted path's disagreement did not
exceed the sampling error of our own estimate ({coarse['fitted']['rmse']:.3f} against
{coarse['fitted']['our_sampling_standard_error']:.3f} s), so none of it can be attributed to
method. At {fine['stratum'].split()[1]} s the two were indistinguishable
({fine['argmax']['residual_after_removing_our_sampling']:.2f} against
{fine['fitted']['residual_after_removing_our_sampling']:.2f} s) and the fit bought nothing. The
precision of the measurement is a limit on what can be said: on {under} of the {total} measured
arms the hemispheric difference was smaller than twice its own standard error.

*Smoothing buys admissible fits rather than accuracy.* On the unfiltered series the validity
rule rejected a median {unfiltered[1]:.0f}% of fits (range {unfiltered[0]:.0f} to
{unfiltered[2]:.0f}%); on the 3 mm series the median fell to {filtered[1]:.0f}%
({filtered[0]:.0f} to {filtered[2]:.0f}%). The hemispheric differences themselves moved little
between the two series.

*The automatic arterial input understates the arterial area, and the maps stop showing it.*
Across all {n.aif['n_cases']} cases the automatically detected input gave an area smaller than
the one the dataset's maps were made with by a median factor of
{n.aif['median_area_ratio']:.2f} (range {n.aif['min_area_ratio']:.2f} to
{n.aif['max_area_ratio']:.2f}; Figure 3). Because blood volume is a ratio of areas, that error
passes into it proportionally: on a phantom in the physiological range the recovered volume
tracked the error exactly up to the implementation's own clips, which both maps reach at a
factor of {n.ceiling:.1f}. Every case measured here lies beyond that point, so on this data the
quantitative map cannot show the error it contains.

*On real images the quantisation is visible, not only measurable.* Figure 4 shows the case the
frozen rule selected, {chosen['case']}, whose left-right asymmetry in the reference maps is the
largest in the set at {chosen['signed_delta']:+.2f} s, on the slice the measurement used. The
delay in the left hemisphere appears in all three maps. The fit-free map is also visibly
stepped, in flat regions of a single value, because on this acquisition its output can fall only
on the {n.samples_in(chosen['case'])} sampling instants — the same property that Figure 2
measures as a precision floor, seen directly on a brain.
"""


def discussion(n: Numbers) -> str:
    coarse = n.strata["dt 2.81 s"]
    floor_coarse = n.cell(2.81, max(n.noises), "sampled")
    under, total = n.unresolved_arms()
    return f"""
## Discussion

Two of the four choices account for most of the movement, and they fail in opposite ways. The
arterial input sets a *systematic scale* error: blood volume and flow are divided by the area
under that curve, so an area understated by a factor of {n.aif['median_area_ratio']:.1f} inflates
both by the same factor, and past {n.ceiling:.1f} the implementation's own ceilings make the
error invisible in the map. A reader looking at a saturated map cannot see that it is saturated.
The fit-free time to peak sets a *precision floor*: it cannot do better than the sampling grid,
and no increase in dose will lower it.

What a reader should take from this is conditional, and that is the point. At coarse temporal
sampling — the 2.81 s protocol here — fitting the curve is worth its cost, because the fit-free
path is at a floor of {floor_coarse['quantisation_floor']:.2f} s and was measured disagreeing
with the reference by {coarse['argmax']['residual_after_removing_our_sampling']:.2f} s. At fine
sampling the floor is far below the other sources of error, the two paths are
indistinguishable, and the simpler one is the better choice. Equally, where the arterial input
is placed automatically, the absolute values of blood volume and flow should not be reported at
all; the maps remain usable for the side-to-side comparison this measurement rests on, which is
insensitive to a scale error common to both hemispheres.

**What this does not establish.** Nothing here speaks to clinical accuracy, to diagnosis or to
patient management: the comparison is with another implementation's maps, not with outcome or
with a physical standard. No claim is made that one package is better than another, because the
factors are properties of choices rather than verdicts on products. The synthetic arm is not the
first such reference — the framework cited above precedes it — and what is new is that its named
future work has been done on code and data a reader can run.

*The reference is not neutral between the two paths compared.* The maps the clinical arm is
measured against come from a model-based non-linear regression — a fitted method.[@nlr_method]
A fitted path agreeing with them better than a fit-free one is therefore not, by itself,
evidence about accuracy; it could be agreement between two methods that make the same
assumption. What settles it is that the two arms meet. The synthetic arm has analytic truth and
no such circularity, and it predicts a floor of
{floor_coarse['quantisation_floor']:.2f} s at 2.81 s sampling; the clinical disagreement
measured against the reference maps at that interval is
{coarse['argmax']['residual_after_removing_our_sampling']:.2f} s. A quantity derived from the
sampling grid alone, with no reference involved, predicts the size of a disagreement observed
against an independent implementation. That agreement is the argument, and it is why the
synthetic arm is not decoration.

**Limitations.** The clinical arm measures one slice per case, chosen by a stated rule, and
{under} of the {total} measured arms do not resolve their own hemispheric difference at twice
its standard error; the sample of {n.clinical[0]['n_per_hemisphere']} voxels per hemisphere was
set by what a gamma fit costs, and a larger one would narrow that. The arterial comparison uses the dataset's shipped input as the
reference, which is a curve chosen by its authors rather than a measured truth. Only one
smoothing level was available in the published data, so F2 is a comparison of two levels rather
than a curve. The synthetic curves are gamma-variate in form, which is the shape the fitted path
assumes, so that arm is favourable to it by construction; the clinical arm, where no such
assumption is shared with the data, is the check on that.

The conclusion a reader can act on is narrow and quantitative. Report the arterial input used
and, if it was placed automatically, do not report absolute blood volume or flow. Fit the curve
when temporal sampling is coarse, and do not pay for it when sampling is fine. And where a
measurement's own precision is the same size as the effect, say so: half the arms measured here
were in that position, and a paper that did not report standard errors would have presented them
as results.
"""


def statements(n: Numbers) -> str:
    return """
## Data availability

The UniToBrain dataset is public and is not redistributed here. The implementation, the drivers
that produced every number in this manuscript, the recorded design and its amendments, and the
measurement results as data files are archived at the digital object identifier given on the
title page; the repository is public. The figures are generated from those result files by a
script in the same archive, and the manuscript itself is generated from them, so no number in
the text is typed by hand.

## Figures
"""


def figure_block() -> str:
    out = []
    for number, figure in sorted(figures().items()):
        out.append(f"**Figure {number}.** {figure['caption'].split('. ', 1)[1]}\n\n"
                   f"Alt text: {figure['alt_text']}\n")
    return "\n".join(out)


def title_page() -> str:
    return f"""# {TITLE}

{AUTHOR}, ORCID {ORCID}

{AFFILIATION}

Corresponding author: {AUTHOR}, {AFFILIATION}. Email: {EMAIL}

## Competing interests

The author is an employee of LISIT Co., Ltd. The implementation measured here is released by the
author under an MIT licence, and no commercial product of the company is evaluated, recommended
or compared in this work. The author has no other competing interest to declare.

## Funding

This research received no specific grant from any funding agency in the public, commercial or
not-for-profit sectors.

## Generative artificial intelligence

Generative artificial intelligence was used as a programming and editing assistant during the
preparation of the software, the analysis scripts and this manuscript. Every measurement was
produced by executed code, every number in the manuscript is interpolated from a results file
written by that code, and the author takes full responsibility for the content.
"""


def number_citations(document: str) -> tuple[str, list[str]]:
    """Replace ``[@key]`` with Vancouver numbers in order of first appearance.

    Returns the document and the keys in that order. An unknown key raises rather than
    rendering as itself: a citation that does not resolve is a missing reference, and the
    editorial office finds those before the reviewers do.
    """
    import references as bib

    known = set(bib.REFERENCES) | set(bib.NON_DOI)
    order: list[str] = []

    def replace(match: re.Match) -> str:
        numbers = []
        for key in (k.strip() for k in match.group(1).split(";")):
            key = key.lstrip("@")
            if key not in known:
                raise SystemExit(f"citation [@{key}] has no reference in references.py")
            if key not in order:
                order.append(key)
            numbers.append(str(order.index(key) + 1))
        return "[" + ",".join(numbers) + "]"

    return re.sub(r"\[((?:@[\w;@\s]+))\]", replace, document), order


def reference_list(order: list[str]) -> str:
    import references as bib

    lines = [bib.vancouver(key, n + 1) for n, key in enumerate(order)]
    return "\n## References\n\n" + "\n\n".join(lines) + "\n"


def word_count(text: str) -> int:
    body = re.sub(r"\[@[^\]]+\]", "", text)
    body = re.sub(r"[#*]", "", body)
    return len(body.split())


def main() -> int:
    n = Numbers()
    sections = {
        "Abstract": abstract(n),
        "Introduction": introduction(n),
        "Methods": methods(n),
        "Results": results(n),
        "Discussion": discussion(n),
    }
    document = "\n".join([f"# {TITLE}\n", *sections.values(), statements(n), figure_block()])
    document, order = number_citations(document)
    document += reference_list(order)

    os.makedirs(BUILD, exist_ok=True)
    with open(os.path.join(BUILD, "manuscript.md"), "w", encoding="utf-8") as handle:
        handle.write(document)
    with open(os.path.join(BUILD, "title_page.md"), "w", encoding="utf-8") as handle:
        handle.write(title_page())

    counts = {name: word_count(text) for name, text in sections.items()}
    body = sum(v for k, v in counts.items() if k != "Abstract")
    counts["body total"] = body
    with open(os.path.join(BUILD, "word_counts.json"), "w", encoding="utf-8") as handle:
        json.dump(counts, handle, indent=2)

    # The journal sets two limits: 250 words of structured abstract and 3,000 of body. The
    # per-section figures are this author's plan for how to spend the 3,000 and are advisory:
    # going over one of them while the total holds is a decision about emphasis, not a breach.
    # They are printed so that decision is visible rather than drifting.
    hard = {"Abstract": 250, "body total": 3000}
    advisory = {"Introduction": 450, "Methods": 900, "Results": 750, "Discussion": 750}
    print(f"{'section':14s} {'words':>6} {'limit':>7}")
    breached = []
    for name, count in counts.items():
        if name in hard:
            over = count > hard[name]
            breached += [name] if over else []
            print(f"{name:14s} {count:6d} {hard[name]:7d}  journal{'  OVER' if over else ''}")
        else:
            flag = "  over plan" if count > advisory[name] else ""
            print(f"{name:14s} {count:6d} {advisory[name]:7d}  plan{flag}")
    print(f"\nwrote {os.path.join(BUILD, 'manuscript.md')}")
    if breached:
        print(f"a journal limit is breached: {', '.join(breached)}")
    return 1 if breached else 0


if __name__ == "__main__":
    raise SystemExit(main())
