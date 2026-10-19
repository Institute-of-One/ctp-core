"""Factor F3: what the automatic arterial input detector picks, against the one the dataset used.

CBV and CBF are divided by the area under the arterial input, so an input whose area is too
small inflates both by the same factor. This measures that factor on every case in the test set.

    python paper/analysis/run_aif.py

Writes ``paper/results/aif_factor.json``. The detected curves are saved with the summary: an
earlier run reported only the ratio, and when a correction to the area calculation had to be
checked the curves were gone and the ratio could not be recomputed.
"""

from __future__ import annotations

import io
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))

import unitobrain  # noqa: E402
from ctp_core.aif_detection import AIFDetector  # noqa: E402
from ctp_measure import curve_area  # noqa: E402

RESULTS = os.path.abspath(os.path.join(HERE, "..", "results"))


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace", line_buffering=True)
    names = unitobrain.cases()
    print(f"{len(names)} cases under {unitobrain.root()}\n")

    rows = []
    print(f"{'case':9s} {'auto peak':>10s} {'ship peak':>10s} {'auto area':>10s} "
          f"{'ship area':>10s} {'area ratio':>11s} {'voxels':>7s}")
    print("-" * 74)
    for name in names:
        acquisition = unitobrain.load(name)
        detector = AIFDetector(acquisition.volume, acquisition.metadata())
        result = detector.detect()
        auto = np.asarray(result.aif_enhancement, dtype=float)
        if auto.size != acquisition.times.size:
            print(f"{name}: detected curve has {auto.size} points, expected "
                  f"{acquisition.times.size} — excluded")
            continue
        auto_area = curve_area(acquisition.times, auto)
        ship_area = curve_area(acquisition.times, acquisition.shipped_aif)
        ratio = ship_area / auto_area if auto_area > 0 else float("nan")
        print(f"{name:9s} {auto.max():10.1f} {acquisition.shipped_aif.max():10.1f} "
              f"{auto_area:10.1f} {ship_area:10.1f} {ratio:11.2f} {result.n_aif_voxels:7d}")
        rows.append({
            "case": name,
            "dt": acquisition.dt,
            "auto_peak": float(auto.max()),
            "shipped_peak": float(acquisition.shipped_aif.max()),
            "auto_area": auto_area,
            "shipped_area": ship_area,
            "area_ratio": float(ratio),
            "n_aif_voxels": int(result.n_aif_voxels),
            "aif_centre": [float(x) for x in (result.aif_center or (float("nan"),) * 2)],
            "times": [float(t) for t in acquisition.times],
            "auto_curve": [float(v) for v in auto],
            "shipped_curve": [float(v) for v in acquisition.shipped_aif],
        })

    if not rows:
        print("no cases measured")
        return 1
    ratios = np.array([r["area_ratio"] for r in rows if np.isfinite(r["area_ratio"])])
    print(f"\narterial area ratio (shipped / automatic) over {ratios.size} cases: "
          f"median {np.median(ratios):.2f}, range {ratios.min():.2f} to {ratios.max():.2f}")
    print("CBV and CBF are divided by this area, so they are inflated by the same factor.")

    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "aif_factor.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"cases": rows,
                   "median_area_ratio": float(np.median(ratios)),
                   "min_area_ratio": float(ratios.min()),
                   "max_area_ratio": float(ratios.max())},
                  handle, indent=2)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
