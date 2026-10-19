"""Each method's hemispheric TTP difference against the reference maps the dataset ships.

This is the shape the literature actually publishes: a package is validated against a reference,
not described. The dataset's own NLR maps are that reference, and they were produced from the
same acquisitions with the arterial input and time vector that ship beside them, so what is left
is a difference of method.

    python paper/analysis/run_reference.py

Reads ``paper/results/f1_f2_clinical.json`` and writes ``paper/results/clinical_vs_reference.json``.

Absolute TTP is not comparable between the two: the reference is referenced to bolus arrival and
ctp-core to the start of the acquisition, a near-constant offset of about 23 s (amendment 2 in
``paper/PROTOCOL.md``). The hemispheric difference is comparable, because the offset cancels.
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import driver_io  # noqa: E402
import run_screen  # noqa: E402
import unitobrain  # noqa: E402
from ctp_measure import hemispheres  # noqa: E402

RESULTS = os.path.abspath(os.path.join(HERE, "..", "results"))

#: The screen and this comparison read the same maps, so they must admit the same tissue. These
#: are imported from run_screen rather than restated: a review found that a restated copy had
#: drifted to a total-voxel minimum of 2,000 against the screen's 1,000, so a slice the screen
#: ranked could be unusable here, while a test asserted the two were "identical".
TTP_MIN, TTP_MAX = run_screen.TTP_MIN, run_screen.TTP_MAX
MIN_PER_SIDE = run_screen.MIN_VOXELS
MIN_TOTAL = 2 * MIN_PER_SIDE
#: The published test set, as in the other drivers.
EXPECTED_CASES = run_screen.EXPECTED_CASES
#: The two sampling protocols are 0.50 s and 2.81 s; this separates them. Every compared case
#: must land in exactly one stratum -- a reviewer pointed out that the earlier predicates
#: (dt < 1.0 and dt > 1.0) silently dropped a case at exactly 1.0 s or at NaN from both.
DT_BOUNDARY = 1.0
STRATA = (("dt 0.50 s", lambda dt: dt < DT_BOUNDARY),
          ("dt 2.81 s", lambda dt: dt >= DT_BOUNDARY))


def stratum_of(dt: float) -> str:
    """Which stratum a sampling interval belongs to. Every finite dt belongs to exactly one."""
    if not np.isfinite(dt):
        raise ValueError(f"a sampling interval of {dt} belongs to no stratum")
    matching = [name for name, keep in STRATA if keep(dt)]
    if len(matching) != 1:
        raise ValueError(f"dt {dt} matches {len(matching)} strata, not one")
    return matching[0]


def reference_delta(case: str, slice_index: int, expected_location: float | None = None):
    """The reference map's own left-right TTP difference on one slice, or ``None``."""
    series = unitobrain.reference_map(case, "NLR_TTP")
    if slice_index >= len(series):
        return None
    # Raises if the reference slice is not at the volume slice's physical position.
    image = series.at_slice(slice_index, expected_location)
    mask = (image > TTP_MIN) & (image < TTP_MAX)
    if mask.sum() < MIN_TOTAL:
        return None
    split = hemispheres(mask)
    if split.left.sum() < MIN_PER_SIDE or split.right.sum() < MIN_PER_SIDE:
        return None
    return {
        "mean": float(image[split.left].mean() - image[split.right].mean()),
        "median": float(np.median(image[split.left]) - np.median(image[split.right])),
        "midline": int(split.midline),
        "n_left": int(split.left.sum()), "n_right": int(split.right.sum()),
    }


def main() -> int:
    driver_io.use_utf8_stdout()
    source = os.path.join(RESULTS, "f1_f2_clinical.json")
    with open(source, encoding="utf-8") as handle:
        records = json.load(handle)
    index = {(r["case"], r["series"], r["method"]): r for r in records}
    cases = sorted({r["case"] for r in records})

    rows = []
    print(f"{'case':9s} {'dt':>5s} | {'reference':>10s} | {'argmax':>7s} {'err':>7s} | "
          f"{'fitted':>7s} {'err':>7s}")
    print("-" * 70)
    for case in cases:
        try:
            raw = index[(case, "filtered_3mm", "raw")]
            gamma = index[(case, "filtered_3mm", "gamma")]
        except KeyError:
            print(f"{case:9s} not measured on both paths - skipped")
            continue
        for field in ("slice_location", "delta_standard_error"):
            if field not in raw or field not in gamma:
                raise ValueError(
                    f"{source} predates this driver: {case} has no {field}. Re-run "
                    "run_clinical.py. Skipping a check because the input is old is how a "
                    "wrong slice gets compared, or a sampling error gets ignored.")
        reference = reference_delta(case, raw["slice"], raw["slice_location"])
        if reference is None:
            print(f"{case:9s} reference slice unusable")
            continue
        raw_err = raw["delta"] - reference["mean"]
        gamma_err = gamma["delta"] - reference["mean"]
        print(f"{case:9s} {raw['dt']:5.2f} | {reference['mean']:10.2f} | "
              f"{raw['delta']:7.2f} {raw_err:+7.2f} | {gamma['delta']:7.2f} {gamma_err:+7.2f}")
        rows.append({"case": case, "dt": raw["dt"], "slice": raw["slice"],
                     "reference_delta": reference["mean"],
                     "reference_delta_median": reference["median"],
                     "reference_midline": reference["midline"],
                     "raw_delta": raw["delta"], "raw_error": raw_err,
                     "argmax_standard_error": raw["delta_standard_error"],
                     "gamma_delta": gamma["delta"], "gamma_error": gamma_err,
                     "fitted_standard_error": gamma["delta_standard_error"]})

    if not rows:
        print("no case could be compared against a reference map")
        return 1

    # Never pooled across the two sampling intervals (amendment 5): the quantisation floor
    # differs by a factor of five between them, so a pooled spread would describe neither.
    # An earlier version wrote an "all cases" stratum anyway, directly under this comment, and
    # a review caught it. There is deliberately no such row now -- a pooled number that exists
    # in the results file is a pooled number that ends up quoted.
    print()
    strata = []
    assigned = {row["case"]: stratum_of(row["dt"]) for row in rows}
    for label, _keep in STRATA:
        sub = [r for r in rows if assigned[r["case"]] == label]
        if not sub:
            continue
        summary = {"stratum": label, "n": len(sub)}
        print(f"{label} (n={len(sub)}):")
        for method, key in (("argmax", "raw_error"), ("fitted", "gamma_error")):
            errors = np.array([r[key] for r in sub])
            rmse = float(np.sqrt((errors ** 2).mean()))
            # Our own hemispheric difference is a sample of 500 voxels per side; the reference
            # map's is every voxel in the slice. So part of this RMSE is our sampling noise and
            # not the method's error. A reviewer pointed out that without removing it, a
            # reported RMSE can be smaller than the precision of the thing reporting it -- as
            # the fitted path's is. Variances add, so the sampling part is subtracted in
            # quadrature; a residual of zero means agreement within our own precision, which
            # is a statement about the measurement and not a claim of exactness.
            sampling = float(np.sqrt(np.mean(
                np.array([r[f"{method}_standard_error"] for r in sub]) ** 2)))
            residual = rmse ** 2 - sampling ** 2
            summary[method] = {
                "bias": float(errors.mean()),
                "sd": float(errors.std(ddof=1)) if errors.size > 1 else None,
                "rmse": rmse,
                "our_sampling_standard_error": sampling,
                "residual_after_removing_our_sampling": (float(np.sqrt(residual))
                                                         if residual > 0 else 0.0),
                "within_our_own_precision": residual <= 0,
            }
            sd = summary[method]["sd"]
            shown = f"{sd:5.2f}" if sd is not None else "  n/a"
            note = ("  <- within our own sampling precision"
                    if summary[method]["within_our_own_precision"] else "")
            print(f"   {method:7s} bias {errors.mean():+6.2f}  sd {shown}  RMSE {rmse:5.2f} s"
                  f"  | our sampling {sampling:5.3f} s, method error "
                  f"{summary[method]['residual_after_removing_our_sampling']:5.2f} s{note}")
        strata.append(summary)

    # Against the published 15, not against whatever the clinical file happens to hold. A
    # reviewer pointed out that the documented plumbing check, run_clinical.py --cases 1,
    # rewrites that file with one case, and the earlier gate compared the result against
    # itself -- so a stale plumbing run would silently have replaced the 15-case result.
    if len(cases) != EXPECTED_CASES or len(rows) != EXPECTED_CASES:
        compared = {row["case"] for row in rows}
        print(f"\nABORT: {len(cases)} cases in {os.path.basename(source)} and {len(rows)} "
              f"compared against a reference map; both must be {EXPECTED_CASES}. "
              f"Not compared: {', '.join(sorted(set(cases) - compared)) or 'none'}. "
              "If f1_f2_clinical.json came from a --cases run, re-run run_clinical.py in full; "
              "a stratum summarising whatever happened to be present is not a result.")
        return 1
    if sum(s["n"] for s in strata) != len(rows):
        print(f"\nABORT: the strata hold {sum(s['n'] for s in strata)} cases of {len(rows)}; "
              "every compared case must appear in exactly one.")
        return 1

    path = os.path.join(RESULTS, "clinical_vs_reference.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"n_cases": len(rows), "pooling": "none: amendment 5 forbids pooling the two "
                                                    "sampling intervals",
                   "cases": rows, "strata": strata}, handle, indent=2)
    print(f"\nwrote {path} ({len(rows)} cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
