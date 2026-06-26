# -*- coding: utf-8 -*-
"""
ctp-core SNR sweep (IORN-001, Table 1 / Figure 2)
=================================================

Monte-Carlo recovery of gamma-variate parameters across SNR levels, using only
the open core and the deterministic synthetic generator. Reproduces Table 1 and
Figure 2 of IORN-001.

Run:
    python examples/run_snr_sweep.py

Outputs (deterministic):
    outputs/snr_sweep_metrics.json   # mean/SD of errors per SNR level
    outputs/snr_sweep.png            # error vs SNR (3 panels)

No GUI, no DICOM, no patient/client data.
"""
from __future__ import annotations

import os
import sys
import json

import numpy as np

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from ctp_core.synthetic import generate_synthetic_tac
from ctp_core.gamma_fit import fit_gamma_variate

OUT_DIR = os.path.join(_REPO_ROOT, "outputs")
SNR_LEVELS = [5, 10, 20, 40, 100]
N_SEEDS = 200

# Ground-truth curve (matches run_synthetic_demo.py)
GT = dict(amplitude=60.0, t0=8.0, alpha=3.0, beta=2.0, n_time_points=40, dt=1.0)
TRUE_PEAK_TIME = GT["t0"] + GT["alpha"] * GT["beta"]   # 14.0
TRUE_PEAK_VALUE = GT["amplitude"]                       # 60.0
TRUE_BAT = GT["t0"]                                     # 8.0


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    rows = []
    for snr in SNR_LEVELS:
        pt, pv_pct, bat, r2, succ = [], [], [], [], 0
        for seed in range(N_SEEDS):
            tac = generate_synthetic_tac(snr=snr, seed=seed, **GT)
            fit = fit_gamma_variate(tac.time, tac.noisy)
            if not fit.success:
                continue
            succ += 1
            pt.append(abs(fit.peak_time - TRUE_PEAK_TIME))
            pv_pct.append(100 * abs(fit.peak_value - TRUE_PEAK_VALUE) / TRUE_PEAK_VALUE)
            bat.append(abs(fit.bat - TRUE_BAT))
            r2.append(fit.r_squared)
        rows.append({
            "snr": snr, "n": succ,
            "peak_time_err_mean": float(np.mean(pt)), "peak_time_err_std": float(np.std(pt)),
            "peak_pct_err_mean": float(np.mean(pv_pct)), "peak_pct_err_std": float(np.std(pv_pct)),
            "bat_err_mean": float(np.mean(bat)), "bat_err_std": float(np.std(bat)),
            "r2_mean": float(np.mean(r2)), "r2_std": float(np.std(r2)),
        })

    json.dump(
        {"config": {**GT, "snr_levels": SNR_LEVELS, "n_seeds_per_snr": N_SEEDS,
                    "true_peak_time": TRUE_PEAK_TIME, "true_peak_value": TRUE_PEAK_VALUE,
                    "true_bat": TRUE_BAT},
         "rows": rows},
        open(os.path.join(OUT_DIR, "snr_sweep_metrics.json"), "w"), indent=2)

    snr = [r["snr"] for r in rows]
    fig, ax = plt.subplots(1, 3, figsize=(12, 3.6))
    ax[0].errorbar(snr, [r["peak_time_err_mean"] for r in rows],
                   yerr=[r["peak_time_err_std"] for r in rows], marker="o", color="tab:red", capsize=3)
    ax[0].set_title("Peak-time (TTP) abs error"); ax[0].set_ylabel("|Δt_peak| (s)")
    ax[1].errorbar(snr, [r["peak_pct_err_mean"] for r in rows],
                   yerr=[r["peak_pct_err_std"] for r in rows], marker="o", color="tab:purple", capsize=3)
    ax[1].set_title("Peak-amplitude relative error"); ax[1].set_ylabel("|Δpeak| (%)")
    ax[2].errorbar(snr, [r["r2_mean"] for r in rows],
                   yerr=[r["r2_std"] for r in rows], marker="o", color="tab:blue", capsize=3)
    ax[2].set_title("Fit quality"); ax[2].set_ylabel("R^2"); ax[2].set_ylim(0.7, 1.01)
    for a in ax:
        a.set_xlabel("SNR"); a.set_xscale("log"); a.grid(True, alpha=0.3)
    fig.suptitle("ctp-core gamma-variate recovery vs SNR (%d Monte-Carlo runs/level)" % N_SEEDS, y=1.03)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "snr_sweep.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)

    print("=== ctp-core SNR sweep (IORN-001) ===")
    for r in rows:
        print(f"SNR {r['snr']:>3} (n={r['n']:>3}): "
              f"dTTP={r['peak_time_err_mean']:.3f}s  dPeak={r['peak_pct_err_mean']:.2f}%  "
              f"dBAT={r['bat_err_mean']:.3f}s  R2={r['r2_mean']:.3f}")
    print("saved outputs/snr_sweep_metrics.json, outputs/snr_sweep.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
