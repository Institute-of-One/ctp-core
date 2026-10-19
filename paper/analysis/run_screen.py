"""Choose the case for the clinical figure, by a rule fixed before the screen was run.

The rule is in ``paper/PROTOCOL.md``: among admitted cases, take the one with the largest
left-right hemispheric asymmetry in TTP.

    python paper/analysis/run_screen.py

Writes ``paper/results/figure_case.json``.

The screen reads the reference maps the dataset ships (``NLR_TTP``), not maps produced by
ctp-core. Choosing the figure case with our own implementation would let the choice flatter the
method. The median is used rather than the mean because a large vessel in one hemisphere would
drag a mean.
"""

from __future__ import annotations

import glob
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

#: Plausible tissue TTP in seconds. Zero is background; very large values are vessels or the
#: reference's own fit failures, and neither belongs in a hemispheric median.
TTP_MIN, TTP_MAX = 0.5, 20.0
#: A slice needs this many admitted voxels on each side to be compared at all.
MIN_VOXELS = 500
#: The published test set. Asserted because the first run of this screen was started while the
#: archive was still being extracted and silently ranked eight cases instead of fifteen.
EXPECTED_CASES = 15


def slice_asymmetry(ttp: np.ndarray) -> float | None:
    mask = (ttp > TTP_MIN) & (ttp < TTP_MAX)
    if mask.sum() < 2 * MIN_VOXELS:
        return None
    split = hemispheres(mask)
    if split.left.sum() < MIN_VOXELS or split.right.sum() < MIN_VOXELS:
        return None
    return float(np.median(ttp[split.left]) - np.median(ttp[split.right]))


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace", line_buffering=True)
    names = unitobrain.cases()
    rows = []
    for case in names:
        folder = os.path.join(unitobrain.root(), case + unitobrain.MAPS, "NLR_TTP")
        if not os.path.isdir(folder):
            print(f"{case}: EXCLUDED - no NLR_TTP folder")
            continue
        # An empty folder and a folder of unusable slices are different failures, and the first
        # run of this screen conflated them: it ran during extraction, so six cases had folders
        # with no files in them yet and were reported as having too little tissue.
        n_files = len(glob.glob(os.path.join(folder, "*.dcm")))
        if n_files == 0:
            print(f"{case}: EXCLUDED - NLR_TTP folder is empty (extraction incomplete?)")
            continue
        series = unitobrain.reference_map(case, "NLR_TTP")
        per_slice = []
        for index, ttp in enumerate(series):
            value = slice_asymmetry(ttp)
            if value is not None:
                per_slice.append((value, index))
        if not per_slice:
            print(f"{case}: EXCLUDED - {n_files} slices present, none with enough tissue "
                  "on both sides")
            continue
        worst, worst_slice = max(per_slice, key=lambda pair: abs(pair[0]))
        rows.append({
            "case": case, "signed_delta": worst, "abs_delta": abs(worst),
            "slice": int(worst_slice),
            "median_abs_delta": float(np.median([abs(v) for v, _ in per_slice])),
            "n_slices_compared": len(per_slice), "n_slices_present": n_files,
        })

    rows.sort(key=lambda row: row["abs_delta"], reverse=True)
    print(f"\n{'case':10s} {'max|L-R| TTP':>13s} {'signed':>8s} {'slice':>6s} "
          f"{'median|L-R|':>12s} {'slices':>7s}")
    print("-" * 62)
    for row in rows:
        print(f"{row['case']:10s} {row['abs_delta']:13.2f} {row['signed_delta']:8.2f} "
              f"{row['slice']:6d} {row['median_abs_delta']:12.2f} "
              f"{row['n_slices_compared']:7d}")
    print(f"\n{len(rows)} cases admitted of {len(names)}")

    if len(names) != EXPECTED_CASES:
        print(f"\nABORT: found {len(names)} cases, expected {EXPECTED_CASES}. The test set is "
              "not fully extracted; the ranking above would be drawn from partial data.")
        return 1
    if not rows:
        print("\nABORT: no case was admitted, so no figure case can be chosen.")
        return 1

    chosen = rows[0]
    print(f"\nBy the frozen rule the figure case is {chosen['case']} (largest left-right TTP "
          f"asymmetry, {chosen['signed_delta']:+.2f} s on slice {chosen['slice']}).")
    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "figure_case.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"rule": "largest absolute left-right hemispheric median TTP difference in "
                           "the dataset's own NLR_TTP maps, among admitted cases",
                   "ttp_window": [TTP_MIN, TTP_MAX], "min_voxels_per_side": MIN_VOXELS,
                   "n_cases": len(names), "chosen": chosen, "ranking": rows},
                  handle, indent=2)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
