"""The maps behind the clinical figure, computed once and cached.

    python paper/analysis/run_figure_maps.py

Writes ``paper/results/mol001_maps.npz``, which the figure script reads. It takes about an hour:
the fitted map is one gamma fit per admitted voxel, roughly 70,000 of them, and that is the
point. The figure has to show the same computation the measurement reports, not a cheaper
approximation of it, so it uses ``sampled_peak_time`` and ``fitted_peak_time`` from
``ctp_measure`` and the same admission rule from ``unitobrain``.

Which case and which slice, and why they are not the same choice:

* The **case** is chosen by the rule frozen in ``paper/PROTOCOL.md`` section 5 -- the largest
  left-right hemispheric asymmetry in the dataset's own reference maps -- which gives MOL-001.
  That rule also reports where the asymmetry is largest, slice 15, with +6.43 s.
* The **slice** shown is the one the measurement used: the slice with the most admitted tissue,
  which for MOL-001 is slice 7. Showing slice 15 would put a picture next to numbers that
  describe a different slice. Both numbers belong in the caption.
"""

from __future__ import annotations

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

#: The case comes from the frozen rule; it is read from the screen's output rather than typed,
#: so that changing the rule changes the figure.
FIGURE_CASE_FILE = "figure_case.json"


def figure_case() -> tuple[str, int]:
    """The case the frozen rule chose, and the slice where its asymmetry is largest."""
    import json

    path = os.path.join(RESULTS, FIGURE_CASE_FILE)
    with open(path, encoding="utf-8") as handle:
        chosen = json.load(handle)["chosen"]
    return chosen["case"], int(chosen["slice"])


def main() -> int:
    driver_io.use_utf8_stdout()
    case, rule_slice = figure_case()
    print(f"{case}: the frozen rule's largest asymmetry is on slice {rule_slice}")

    acquisition = unitobrain.load(case, filtered=True)
    measured_slice = unitobrain.busiest_slice(acquisition.volume)
    print(f"{case}: the measurement uses slice {measured_slice}, the one with the most "
          "admitted tissue; that is the slice shown")

    slab = acquisition.volume[:, measured_slice]
    mask = unitobrain.tissue_mask(slab)
    split = hemispheres(mask)
    times, window = acquisition.times, acquisition.window
    baseline = slab[:2].mean(axis=0)
    corrected = slab - baseline[None]

    rows, cols = np.nonzero(mask)
    print(f"{rows.size} admitted voxels, dt {acquisition.dt:.2f} s, "
          f"window {window[0]:.1f}-{window[1]:.1f} s")

    from ctp_core.gamma_fit import fit_gamma_variate

    sampled = np.full(mask.shape, np.nan)
    fitted = np.full(mask.shape, np.nan)
    rejected = {"fit_failed": 0, "peak_outside_sampled_window": 0}
    started = clock.time()
    for n, (r, c) in enumerate(zip(rows, cols, strict=True)):
        if n and n % 5000 == 0:
            done = n / rows.size
            print(f"  {n}/{rows.size} ({done * 100:.0f}%), "
                  f"{clock.time() - started:.0f}s elapsed, "
                  f"{(clock.time() - started) / done - (clock.time() - started):.0f}s left",
                  flush=True)
        curve = corrected[:, r, c].astype(np.float64)
        sampled[r, c] = sampled_peak_time(times, curve)
        fit = fit_gamma_variate(times, curve)
        value, reason = fitted_peak_time(fit.peak_time if fit.success else None,
                                         success=bool(fit.success), window=window)
        if value is None:
            rejected[reason] += 1
        else:
            fitted[r, c] = value

    reference = unitobrain.reference_map(case, "NLR_TTP")
    reference_image = reference.at_slice(
        measured_slice, acquisition.slice_locations[measured_slice])

    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "mol001_maps.npz")
    np.savez_compressed(
        path,
        case=case, rule_slice=rule_slice, measured_slice=measured_slice,
        dt=acquisition.dt, window=np.array(window),
        baseline=baseline.astype(np.float32),
        mask=mask, left=split.left, right=split.right, midline=split.midline,
        sampled_ttp=sampled.astype(np.float32),
        fitted_ttp=fitted.astype(np.float32),
        reference_ttp=reference_image.astype(np.float32),
        n_admitted=rows.size,
        n_fit_failed=rejected["fit_failed"],
        n_outside_window=rejected["peak_outside_sampled_window"],
        seconds=clock.time() - started,
    )
    total = sum(rejected.values())
    print(f"\nfitted path: {total} of {rows.size} voxels rejected "
          f"({total / rows.size * 100:.1f}%), of which "
          f"{rejected['peak_outside_sampled_window']} had a peak outside the acquisition")
    print(f"wrote {path} in {clock.time() - started:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
