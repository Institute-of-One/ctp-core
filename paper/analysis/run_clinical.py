"""Factors F1 (curve model) and F2 (spatial smoothing) on the clinical arm.

    python paper/analysis/run_clinical.py            # all cases, about an hour
    python paper/analysis/run_clinical.py --cases 1  # the first case, to check the plumbing

A full run writes ``paper/results/f1_f2_clinical.json`` after every case, so an interrupted run
leaves the cases it finished rather than nothing. A ``--cases`` run writes
``f1_f2_clinical.partial.json`` instead: it is a plumbing check, and it must not be able to
destroy an hour of measurement.

Why the sampling rule is what it is
-----------------------------------
The first version fitted every tissue voxel in a slice -- about 70,000 gamma fits -- and ran for
3.7 hours on one case without finishing. Scaled to 15 cases and two input series that is roughly
sixty hours, which is not a measurement, it is a wait.

The outcome here is a hemispheric mean, not a map, and a mean does not need every voxel. A fit on
a real tissue curve costs about 150 ms, four times one on a clean synthetic curve, so 2,000
voxels per hemisphere still took 25 minutes per case. 500 per hemisphere is what the measurement
can afford: 15 cases, two input series and two methods in about an hour.

**What that costs in precision, measured rather than assumed.** An earlier version of this
docstring justified 500 with "the standard error of a mean whose voxel-level sd is about 1 s is
roughly 0.05 s, two orders below the effect being measured". A reviewer took that apart and was
right on every count. The voxel-level sd this data actually gives is **3.4 to 12.7 s**, not 1 s.
The reported quantity is a *difference* of two means, so its standard error is larger than one
mean's by sqrt(2). And the effect is not "about 5 s": amendment 3 of the protocol cites an
admitted hemispheric difference of +0.24 s.

Done properly, the standard error of each hemispheric difference is **0.23 to 0.79 s**, and it is
recorded per arm as ``delta_standard_error`` rather than argued for here. It is large enough to
matter: on 31 of the 60 arms the difference is smaller than twice its own standard error, and
``run_reference.py`` subtracts this sampling variance before reporting how much of the
disagreement with the reference maps belongs to the method. Raising the sample until the residual
could be measured would need the whole hemisphere -- which is the 3.7-hour case above -- so the
limit is stated instead of chased. The number and the seed are fixed here and in
``paper/PROTOCOL.md`` so the result is reproducible rather than incidental.

F2 uses the two input series the dataset ships -- the registered volume and the same volume
filtered at 3 mm / 20 HU -- rather than smoothing anything here. The 3 mm level is the one the
dataset's own reference maps were made from.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time as clock

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))

import driver_io  # noqa: E402
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


def standard_error_of_difference(per_side, populations) -> float:
    """Standard error of the left-minus-right difference of means.

    Two corrections, each pointed out by a reviewer after an earlier version got it wrong.

    The quantity reported is a *difference* of two means, so the two variances add; taking one
    mean's standard error understates it by sqrt(2) when the two sides are alike.

    The voxels are drawn without replacement from a hemisphere of finite size, so the variance
    of each mean is ``s^2/n * (1 - n/N)`` rather than ``s^2/n``. With 500 drawn from about
    35,000 the factor is 0.986 and the effect on the standard error is under one percent --
    small, but it is the correction that makes the quantity we subtract from the RMSE against
    the reference maps an estimate of the right thing, and subtracting an inflated variance
    would erase genuine disagreement.

    One approximation remains and is not hidden: on the fitted path the admitted values are
    those whose fit passed the validity rule, which is not a random subset of the drawn
    voxels, so ``n`` is the admitted count and the formula is an approximation there.
    """
    total = 0.0
    for side in ("left", "right"):
        values = per_side[side]
        n, population = values.size, populations[side]
        if n < 2:
            raise ValueError(f"the {side} hemisphere has {n} admitted values")
        correction = max(0.0, 1.0 - n / population) if population else 1.0
        total += float(values.var(ddof=1)) / n * correction
    return float(np.sqrt(total))


def draw_voxels(split, n_per_hemisphere: int = N_PER_HEMISPHERE, seed: int = SEED):
    """The voxels to measure, drawn once per case from a generator seeded per case.

    Returned as ``{"left": (rows, cols), "right": (rows, cols)}``. This is a function, and is
    called once before the series loop, because the comparison between the two input series and
    between the two methods is paired: every arm must see the same voxels. A review pointed out
    that drawing inside the loop from one advancing generator would silently unpair it, and
    that the test which claimed to cover this never touched the driver.
    """
    rng = np.random.default_rng(seed)
    picks = {}
    for side in ("left", "right"):
        mask = getattr(split, side)
        rows, cols = np.nonzero(mask)
        if rows.size < n_per_hemisphere:
            raise ValueError(
                f"the {side} hemisphere has {rows.size} voxels, fewer than the "
                f"{n_per_hemisphere} to be drawn")
        index = rng.choice(rows.size, size=n_per_hemisphere, replace=False)
        picks[side] = (rows[index], cols[index])
    return picks


def main(argv=None) -> int:
    # ctp_core is imported here rather than at the top so that the sampling rule can be tested
    # in a snapshot that holds only these files.
    from ctp_core.gamma_fit import fit_gamma_variate

    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=int, default=0, help="0 = all")
    # argv is a parameter so that main() can be called from a test; parse_args() would
    # otherwise read the test runner's own arguments and exit.
    args = parser.parse_args(argv)
    driver_io.use_utf8_stdout()

    names = unitobrain.cases()
    # A partial run writes somewhere else. The published file takes about an hour to produce,
    # and a reviewer pointed out that the documented plumbing check overwrote it -- the gate
    # added for this only stopped run_reference.py from *consuming* the result.
    output = "f1_f2_clinical.json"
    if args.cases:
        names = names[: args.cases]
        output = "f1_f2_clinical.partial.json"
        say(f"--cases {args.cases}: this is a plumbing check, so it writes {output} and "
            "leaves the published result alone.")
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

        picks = draw_voxels(split)
        # The populations the voxels are drawn from, for the finite-population correction.
        populations = {"left": int(split.left.sum()), "right": int(split.right.sum())}

        for label in ("unfiltered", "filtered_3mm"):
            acquisition = (filtered if label == "filtered_3mm"
                           else unitobrain.load(case, filtered=False))
            # The time axis, the window and the slice index all come from the filtered series
            # and are applied to this one. A review pointed out that nothing checked the two
            # series correspond; they do on all 15 cases here, but a mismatch would have fitted
            # one series' curves at the other's times, or sampled a different physical slice,
            # with no error.
            if acquisition.volume.shape != filtered.volume.shape:
                raise ValueError(
                    f"{case}: the {label} series has shape {acquisition.volume.shape} and the "
                    f"filtered series {filtered.volume.shape}; they cannot be compared")
            if acquisition.slice_locations != filtered.slice_locations:
                raise ValueError(
                    f"{case}: the {label} series and the filtered series are at different "
                    "slice locations, so slice indices do not mean the same thing")
            # Equal shape and equal positions still do not say the two series cover the same
            # acquisitions, which is what makes the shared time axis meaningful. A reviewer
            # pointed that out, so the acquisition numbers are compared as well.
            if acquisition.acquisitions != filtered.acquisitions:
                raise ValueError(
                    f"{case}: the {label} series covers acquisitions "
                    f"{acquisition.acquisitions[0]}-{acquisition.acquisitions[-1]} and the "
                    f"filtered series {filtered.acquisitions[0]}-"
                    f"{filtered.acquisitions[-1]}; they do not share a time axis")
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
                    # The physical position of that slice, so a later comparison against the
                    # reference maps can verify it is looking at the same anatomy instead of
                    # trusting that two series are in the same order.
                    "slice_location": float(filtered.slice_locations[chosen]),
                    "series": label, "method": method,
                    "dt": acquisition.dt, "n_samples": int(times.size),
                    "left_mean": float(per_side["left"].mean()),
                    "right_mean": float(per_side["right"].mean()),
                    "left_median": float(np.median(per_side["left"])),
                    "right_median": float(np.median(per_side["right"])),
                    "left_sd": float(per_side["left"].std(ddof=1)),
                    "right_sd": float(per_side["right"].std(ddof=1)),
                    "delta": float(per_side["left"].mean() - per_side["right"].mean()),
                    # The precision of that difference, from the spread actually measured
                    # rather than from an assumption. A reviewer found the docstring's
                    # justification used an assumed voxel-level sd of 1 s where the measured
                    # values are 3.4 to 12.7 s, and forgot that a difference of two means
                    # carries sqrt(2) times one mean's standard error. A second reviewer then
                    # pointed out that the draw is without replacement from a finite
                    # hemisphere, so the variance of each mean carries the factor
                    # (1 - n/N): see standard_error_of_difference.
                    "delta_standard_error": standard_error_of_difference(
                        per_side, populations),
                    "left_population": populations["left"],
                    "right_population": populations["right"],
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
        with open(os.path.join(RESULTS, output), "w", encoding="utf-8") as handle:
            json.dump(records, handle, indent=2)

    say(f"\nwrote {os.path.join(RESULTS, output)} ({len(records)} records)")
    return 0 if records else 1


if __name__ == "__main__":
    raise SystemExit(main())
