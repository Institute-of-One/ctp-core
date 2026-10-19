"""Factors F1 and F4 on synthetic curves, where the time to peak is known analytically.

This is the measurement the prior simulation framework for CT perfusion named as future work
(Medical Physics 2021, doi:10.1002/mp.14887, which built the simulator and wrote "we have not
included a statistical analysis on the correlation of the computer-generated maps with the
ground truth; this is the subject of future work").

    python paper/analysis/run_synthetic.py

Writes ``paper/results/synthetic_f1_f4.json``.

One design point decides whether the experiment means anything. If the bolus always arrived on a
sampling instant, taking the time to peak as the argmax of the sampled curve would be unbiased
by construction and the quantisation would vanish. A scanner does not know when the bolus will
come, so the arrival is jittered uniformly across one sampling interval. The intervals include
2.81 s and 0.50 s, the two the clinical arm actually uses, so the two arms can be read together.
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

from ctp_measure import fitted_peak_time, quantisation_floor, sampled_peak_time  # noqa: E402

RESULTS = os.path.abspath(os.path.join(HERE, "..", "results"))

DT_LEVELS = [0.5, 1.0, 2.0, 2.81, 4.0]   # 0.50 s and 2.81 s are the clinical arm's intervals
SNR_LEVELS = [5.0, 10.0, 20.0, 40.0]
N_REPEATS = 200
DURATION = 50.0
SEED = 20261016


def main() -> int:
    # ctp_core is imported here rather than at the top so that the design constants can be
    # tested in a snapshot that holds only these files.
    from ctp_core.gamma_fit import fit_gamma_variate
    from ctp_core.synthetic import generate_synthetic_tac

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace", line_buffering=True)
    rng = np.random.default_rng(SEED)
    records = []

    print(f"{'dt':>5} {'floor':>6} {'snr':>5} {'method':>7} {'bias':>8} {'sd':>8} {'RMSE':>8} "
          f"{'rejected':>9}")
    print("-" * 64)
    for dt in DT_LEVELS:
        n_points = int(round(DURATION / dt))
        floor = quantisation_floor(dt)
        for snr in SNR_LEVELS:
            errors: dict[str, list[float]] = {"sampled": [], "fitted": []}
            rejected = 0
            for _ in range(N_REPEATS):
                arrival = 8.0 + float(rng.uniform(0.0, dt))
                tac = generate_synthetic_tac(
                    amplitude=60.0, t0=arrival, alpha=3.0, beta=2.0,
                    n_time_points=n_points, dt=dt, snr=snr,
                    seed=int(rng.integers(1 << 31)),
                )
                truth = float(tac.ground_truth["true_peak_time"])
                window = (float(tac.time[0]), float(tac.time[-1]))
                errors["sampled"].append(sampled_peak_time(tac.time, tac.noisy) - truth)
                fit = fit_gamma_variate(tac.time, tac.noisy)
                value, _reason = fitted_peak_time(
                    fit.peak_time if fit.success else None,
                    success=bool(fit.success), window=window)
                if value is None:
                    rejected += 1
                else:
                    errors["fitted"].append(value - truth)

            for method in ("sampled", "fitted"):
                values = np.array(errors[method])
                if values.size == 0:
                    continue
                record = {
                    "dt": dt, "quantisation_floor": floor, "snr": snr, "method": method,
                    "n": int(values.size), "bias": float(values.mean()),
                    "sd": float(values.std(ddof=1)),
                    "rmse": float(np.sqrt((values ** 2).mean())),
                    "n_rejected": rejected if method == "fitted" else 0,
                    "n_attempted": N_REPEATS, "seed": SEED,
                }
                records.append(record)
                print(f"{dt:5.2f} {floor:6.2f} {snr:5.0f} {method:>7} {record['bias']:8.3f} "
                      f"{record['sd']:8.3f} {record['rmse']:8.3f} "
                      f"{record['n_rejected']:9d}")

    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "synthetic_f1_f4.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(records, handle, indent=2)
    print(f"\nwrote {path} ({len(records)} records, {N_REPEATS} curves per cell)")

    print("\nThe sampled path against its predicted floor, at the highest signal:")
    for dt in DT_LEVELS:
        cell = [r for r in records
                if r["dt"] == dt and r["snr"] == max(SNR_LEVELS) and r["method"] == "sampled"]
        if cell:
            print(f"  dt {dt:4.2f} s: sd {cell[0]['sd']:.3f} s against "
                  f"dt/sqrt(12) = {cell[0]['quantisation_floor']:.3f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
