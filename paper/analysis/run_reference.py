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

import io
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import unitobrain  # noqa: E402
from ctp_measure import hemispheres  # noqa: E402

RESULTS = os.path.abspath(os.path.join(HERE, "..", "results"))

#: Plausible tissue TTP in the reference maps, in seconds. Zero is background; very large values
#: are vessels or the reference's own fit failures, and neither belongs in a hemispheric mean.
TTP_MIN, TTP_MAX = 0.5, 20.0
MIN_TOTAL, MIN_PER_SIDE = 2000, 500


def reference_delta(case: str, slice_index: int):
    """The reference map's own left-right TTP difference on one slice, or ``None``."""
    series = unitobrain.reference_map(case, "NLR_TTP")
    if slice_index >= len(series):
        return None
    image = series[slice_index]
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
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace", line_buffering=True)
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
        reference = reference_delta(case, raw["slice"])
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
                     "gamma_delta": gamma["delta"], "gamma_error": gamma_err})

    if not rows:
        print("no case could be compared against a reference map")
        return 1

    # Never pooled across the two sampling intervals (amendment 5): the quantisation floor
    # differs by a factor of five between them, so a pooled spread would describe neither.
    print()
    strata = []
    for label, keep in (("dt 0.50 s", lambda r: r["dt"] < 1.0),
                        ("dt 2.81 s", lambda r: r["dt"] > 1.0),
                        ("all cases", lambda r: True)):
        sub = [r for r in rows if keep(r)]
        if not sub:
            continue
        summary = {"stratum": label, "n": len(sub)}
        print(f"{label} (n={len(sub)}):")
        for method, key in (("argmax", "raw_error"), ("fitted", "gamma_error")):
            errors = np.array([r[key] for r in sub])
            summary[method] = {
                "bias": float(errors.mean()),
                "sd": float(errors.std(ddof=1)) if errors.size > 1 else None,
                "rmse": float(np.sqrt((errors ** 2).mean())),
            }
            sd = summary[method]["sd"]
            shown = f"{sd:5.2f}" if sd is not None else "  n/a"
            print(f"   {method:7s} bias {errors.mean():+6.2f}  sd {shown}  "
                  f"RMSE {summary[method]['rmse']:5.2f} s")
        strata.append(summary)

    path = os.path.join(RESULTS, "clinical_vs_reference.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"cases": rows, "strata": strata}, handle, indent=2)
    print(f"\nwrote {path} ({len(rows)} cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
