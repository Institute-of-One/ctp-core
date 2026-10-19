"""Factors F1 (curve model) and F2 (spatial smoothing) on the clinical arm.

    python paper/analysis/run_clinical.py            # all cases
    python paper/analysis/run_clinical.py --cases 1  # the first case, to check the plumbing

Writes ``paper/results/f1_f2_clinical.json`` after every case, so an interrupted run leaves the
cases it finished rather than nothing.

Why the sampling rule is what it is
-----------------------------------
The first version fitted every tissue voxel in a slice -- about 70,000 gamma fits -- and ran for
3.7 hours on one case without finishing. Scaled to 15 cases and two input series that is roughly
sixty hours, which is not a measurement, it is a wait.

The outcome here is a hemispheric mean, not a map, and a mean does not need every voxel. A fit on
a real tissue curve costs about 150 ms, four times one on a clean synthetic curve, so 2,000
voxels per hemisphere still took 25 minutes per case. At 500 per hemisphere the standard error of
a mean whose voxel-level sd is about 1 s is roughly 0.05 s, two orders below the effect being
measured (a hemispheric difference of about 5 s). The number and the seed are fixed here and in
``paper/PROTOCOL.md`` so the result is reproducible rather than incidental.

F2 uses the two input series the dataset ships -- the registered volume and the same volume
filtered at 3 mm / 20 HU -- rather than smoothing anything here. The 3 mm level is the one the
dataset's own reference maps were made from.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time as clock

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))

import unitobrain  # noqa: E402
from ctp_measure import fitted_peak_time, hemispheres, sampled_peak_time  # noqa: E402

RESULTS = os.path.abspath(os.path.join(HERE, "..", "results"))

N_PER_HEMISPHERE = 500
SEED = 20261016
#: A hemisphere with fewer admitted values than this is not summarised: a mean of a handful of
#: voxels is not the quantity the manuscript reports.
MIN_ADMITTED = 100


def say(*parts: object) -> None:
    print(*parts, flush=True)


def main() -> int:
    # ctp_core is imported here rather than at the top so that the sampling rule can be tested
    # in a snapshot that holds only these files.
    from ctp_core.gamma_fit import fit_gamma_variate

    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=int, default=0, help="0 = all")
    args = parser.parse_args()
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace", line_buffering=True)

    names = unitobrain.cases()
    if args.cases:
        names = names[: args.cases]
    say(f"{len(names)} cases under {unitobrain.root()}")
    say(f"{N_PER_HEMISPHERE} voxels per hemisphere, seed {SEED}\n")

    records = []
    for case in names:
        started = clock.time()
        filtered = unitobrain.load(case, filtered=True)
        times, window = filtered.times, filtered.window
        chosen = unitobrain.busiest_slice(filtered.volume)
        split = hemispheres(unitobrain.tissue_mask(filtered.volume[:, chosen]))
        say(f"=== {case}: slice {chosen}, midline col {split.midline}, "
            f"L {split.left.sum()} R {split.right.sum()} tissue voxels, "
            f"{times.size} samples, dt {filtered.dt:.2f}s, "
            f"window {window[0]:.1f}-{window[1]:.1f}s")
        if split.left.sum() < N_PER_HEMISPHERE or split.right.sum() < N_PER_HEMISPHERE:
            say(f"    EXCLUDED - fewer than {N_PER_HEMISPHERE} voxels in a hemisphere")
            continue

        # Drawn once per case from a fresh generator, so the same voxels are used for both
        # series and both methods and the comparison is paired.
        rng = np.random.default_rng(SEED)
        picks = {}
        for side, side_mask in (("left", split.left), ("right", split.right)):
            rows, cols = np.nonzero(side_mask)
            index = rng.choice(rows.size, size=N_PER_HEMISPHERE, replace=False)
            picks[side] = (rows[index], cols[index])

        for label in ("unfiltered", "filtered_3mm"):
            acquisition = (filtered if label == "filtered_3mm"
                           else unitobrain.load(case, filtered=False))
            slab = acquisition.volume[:, chosen]
            corrected = slab - slab[:2].mean(axis=0)[None]
            t0 = clock.time()
            for method in ("raw", "gamma"):
                per_side, rejected = {}, {"fit_failed": 0, "peak_outside_sampled_window": 0}
                for side in ("left", "right"):
                    rows, cols = picks[side]
                    values = []
                    tick = clock.time()
                    for n, (r, c) in enumerate(zip(rows, cols, strict=True)):
                        if method == "gamma" and n and n % 250 == 0:
                            say(f"      {label} {side} {n}/{len(rows)} "
                                f"({clock.time() - tick:.0f}s)")
                        curve = corrected[:, r, c].astype(np.float64)
                        if method == "raw":
                            values.append(sampled_peak_time(times, curve))
                            continue
                        fit = fit_gamma_variate(times, curve)
                        value, reason = fitted_peak_time(
                            fit.peak_time if fit.success else None,
                            success=bool(fit.success), window=window)
                        if value is None:
                            rejected[reason] += 1
                        else:
                            values.append(value)
                    per_side[side] = np.array(values)
                if min(per_side["left"].size, per_side["right"].size) < MIN_ADMITTED:
                    say(f"    {label:13s} {method:5s}: fewer than {MIN_ADMITTED} admitted "
                        "values in a hemisphere - not summarised")
                    continue
                attempted = 2 * N_PER_HEMISPHERE
                record = {
                    "case": case, "slice": chosen, "midline": int(split.midline),
                    "series": label, "method": method,
                    "dt": acquisition.dt, "n_samples": int(times.size),
                    "left_mean": float(per_side["left"].mean()),
                    "right_mean": float(per_side["right"].mean()),
                    "left_median": float(np.median(per_side["left"])),
                    "right_median": float(np.median(per_side["right"])),
                    "left_sd": float(per_side["left"].std(ddof=1)),
                    "right_sd": float(per_side["right"].std(ddof=1)),
                    "delta": float(per_side["left"].mean() - per_side["right"].mean()),
                    "delta_median": float(np.median(per_side["left"])
                                          - np.median(per_side["right"])),
                    # On the sampled path this cannot exceed the number of acquisitions, which
                    # is the point of the comparison: a median over 18 possible values collapses.
                    "distinct_values": int(np.unique(np.round(
                        np.concatenate([per_side["left"], per_side["right"]]), 3)).size),
                    "n_left": int(per_side["left"].size),
                    "n_right": int(per_side["right"].size),
                    "n_attempted": attempted,
                    "n_fit_failures": rejected["fit_failed"],
                    "n_outside_window": rejected["peak_outside_sampled_window"],
                    "pct_rejected": round(100.0 * sum(rejected.values()) / attempted, 2),
                    "window": list(window),
                    "n_per_hemisphere": N_PER_HEMISPHERE, "seed": SEED,
                }
                records.append(record)
                say(f"    {label:13s} {method:5s}: L {record['left_mean']:6.2f}  "
                    f"R {record['right_mean']:6.2f}  L-R {record['delta']:+6.2f} s  "
                    f"(median {record['delta_median']:+6.2f})  "
                    f"distinct {record['distinct_values']:5d}  "
                    f"rejected {record['pct_rejected']:5.1f}%  {clock.time() - t0:5.0f}s")
        say(f"    case took {clock.time() - started:.0f}s")

        os.makedirs(RESULTS, exist_ok=True)
        with open(os.path.join(RESULTS, "f1_f2_clinical.json"), "w", encoding="utf-8") as handle:
            json.dump(records, handle, indent=2)

    say(f"\nwrote {os.path.join(RESULTS, 'f1_f2_clinical.json')} ({len(records)} records)")
    return 0 if records else 1


if __name__ == "__main__":
    raise SystemExit(main())
