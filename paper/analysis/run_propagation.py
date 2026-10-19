"""How an error in the arterial input reaches CBV and CBF, and where the maps stop showing it.

CBV is a ratio of areas, so an arterial area too small by a factor k inflates it by exactly k.
CBF comes from a deconvolution and has no such obligation, so whether it behaves the same way is
a property of the implementation rather than of the algebra. Both are measured here on a small
synthetic phantom whose values start in the physiological range.

The second question is the one that explains the figure in the rejected manuscript: ctp_core
clips CBV at 20 ml/100 g and CBF at 150 ml/100 g/min, so beyond some error the map is uniform
and the error is no longer visible in it. This locates that point.

    python paper/analysis/run_propagation.py

Writes ``paper/results/aif_propagation.json``.
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

RESULTS = os.path.abspath(os.path.join(HERE, "..", "results"))

SIZE = 24
DT = 2.81
N_TIMES = 18
BASELINE = 40.0
#: Fine steps below 4 locate the point at which the maps saturate; 6.97 is the median error
#: measured on the clinical arm and 10.47 its largest value.
RATIOS = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 6.97, 10.47]
CBV_CLIP, CBF_CLIP = 20.0, 150.0


def build():
    # ctp_core is imported here rather than at the top so that the constants and the phantom
    # builder can be tested in a snapshot that holds only these files.
    from ctp_core.synthetic import generate_synthetic_tac

    artery = generate_synthetic_tac(amplitude=500.0, t0=8.0, alpha=3.0, beta=1.5,
                                    n_time_points=N_TIMES, dt=DT, snr=None,
                                    noise_std=0.0, seed=1)
    # Chosen so the phantom starts in the physiological range -- grey matter is about
    # 4-6 ml/100 g and 50-60 ml/100 g/min -- so that any clipping seen later is caused by the
    # arterial error and not by an unphysical starting point.
    tissue = generate_synthetic_tac(amplitude=20.0, t0=10.0, alpha=3.0, beta=2.5,
                                    n_time_points=N_TIMES, dt=DT, snr=None,
                                    noise_std=0.0, seed=2)
    volume = np.full((N_TIMES, 1, SIZE, SIZE), BASELINE, dtype=np.float32)
    volume[:, 0] += tissue.clean[:, None, None].astype(np.float32)
    metadata = {"n_times": N_TIMES, "rows": SIZE, "cols": SIZE,
                "time_seconds": list(map(float, artery.time))}
    return volume, metadata, artery.clean + BASELINE


def main() -> int:
    from ctp_core.parametric_maps import ParametricMapGenerator

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace", line_buffering=True)
    volume, metadata, true_aif = build()
    generator = ParametricMapGenerator(volume, metadata)
    mask = np.ones((SIZE, SIZE), dtype=bool)

    records, reference = [], None
    print(f"{'arterial area error':>20} {'CBV':>9} {'x':>7} {'CBF':>9} {'x':>7} {'clipped':>9}")
    print("-" * 68)
    for ratio in RATIOS:
        # Keep the shape and shrink the amplitude, so only the area changes.
        scaled = BASELINE + (true_aif - BASELINE) / ratio
        maps = generator.compute(scaled, 0, n_baseline=2, brain_mask=mask)
        cbv = float(np.median(np.asarray(maps.cbv)[mask]))
        cbf = float(np.median(np.asarray(maps.cbf)[mask]))
        if reference is None:
            reference = (cbv, cbf)
        clipped = cbv >= CBV_CLIP * 0.999 or cbf >= CBF_CLIP * 0.999
        print(f"{ratio:20.2f} {cbv:9.2f} {cbv / reference[0]:7.2f} {cbf:9.2f} "
              f"{cbf / reference[1]:7.2f} {'yes' if clipped else '':>9}")
        records.append({"aif_area_ratio": ratio, "cbv": cbv, "cbf": cbf,
                        "cbv_inflation": cbv / reference[0],
                        "cbf_inflation": cbf / reference[1], "clipped": bool(clipped)})

    unclipped = [r for r in records if not r["clipped"]]
    if unclipped:
        worst = max(abs(r["cbv_inflation"] - r["aif_area_ratio"]) / r["aif_area_ratio"]
                    for r in unclipped)
        print(f"\nBelow the clips, CBV inflation departs from the arterial area error by at "
              f"most {worst * 100:.2f}% (up to a ratio of "
              f"{max(r['aif_area_ratio'] for r in unclipped):.1f})")
    clipped = [r for r in records if r["clipped"]]
    if clipped:
        first = min(r["aif_area_ratio"] for r in clipped)
        print(f"The maps reach their ceilings at an arterial area error of {first:.1f}. "
              "Beyond that they are uniform and the error is no longer visible in them.")

    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "aif_propagation.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"cbv_clip": CBV_CLIP, "cbf_clip": CBF_CLIP, "points": records},
                  handle, indent=2)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
