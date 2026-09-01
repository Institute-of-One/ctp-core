# -*- coding: utf-8 -*-
"""
Reproducible synthetic CT-perfusion time-attenuation curve generator
===================================================================

Generates synthetic time-attenuation curves (TACs) from a gamma-variate model
**deterministically**, for the validation and reproducibility checks of IORN-001.

Features:
  - Fully reproducible down to the noise, through a fixed random seed.
  - Configurable amplitude (peak concentration), t0 (bolus arrival), alpha and beta.
  - Configurable sampling interval (dt) and number of samples (n_time_points).
  - Noise given either as an SNR or as an absolute standard deviation (noise_std).
  - An optional recirculation component.
  - Returns the time axis, the clean curve, the noisy curve and the true parameters.

Design boundary:
  This module belongs to ctp-core, the open and reproducible part, and depends on no
  graphical interface, no DICOM handling and no patient or client data. Everything it
  produces is synthetic and contains no confidential information.

Usage:
    from ctp_core.synthetic import generate_synthetic_tac
    s = generate_synthetic_tac(amplitude=60, t0=8, alpha=3, beta=2,
                               snr=20, n_time_points=40, dt=1.0, seed=0)
    s.time, s.clean, s.noisy, s.ground_truth
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, Optional

import numpy as np

from .gamma_fit import gamma_variate, gamma_variate_analytic


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class SyntheticTAC:
    """The result of generating a synthetic TAC.

    Attributes:
        time:         time axis (s), shape (n,)
        clean:        the true noiseless enhancement curve, shape (n,)
        noisy:        the noisy observed curve, shape (n,)
        ground_truth: true parameters and analytic indices (dict)
    """
    time: np.ndarray
    clean: np.ndarray
    noisy: np.ndarray
    ground_truth: Dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helper: amplitude (peak height) -> the K coefficient of gamma_variate
# ---------------------------------------------------------------------------

def _amplitude_to_K(amplitude: float, alpha: float, beta: float) -> float:
    """Convert a peak concentration into the K coefficient of gamma_variate.

    The peak value of gamma_variate is K * (alpha*beta)^alpha * exp(-alpha); this solves
    analytically for the K that makes that peak equal to amplitude.
    """
    if alpha <= 0 or beta <= 0:
        return float(amplitude)
    log_denom = alpha * np.log(alpha * beta) - alpha
    denom = float(np.exp(log_denom))
    return float(amplitude / denom) if denom > 0 else float(amplitude)


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def generate_synthetic_tac(
    amplitude: float = 60.0,
    t0: float = 8.0,
    alpha: float = 3.0,
    beta: float = 2.0,
    n_time_points: int = 40,
    dt: float = 1.0,
    snr: Optional[float] = 20.0,
    noise_std: Optional[float] = None,
    recirculation: bool = False,
    recirc_fraction: float = 0.3,
    recirc_delay: float = 12.0,
    recirc_beta_scale: float = 1.6,
    baseline: float = 0.0,
    seed: Optional[int] = 0,
) -> SyntheticTAC:
    """Generate a reproducible synthetic CT-perfusion curve.

    Args:
        amplitude: peak enhancement of the main bolus, for example in HU.
        t0:        bolus arrival time (s).
        alpha,beta: gamma-variate shape parameters.
        n_time_points: number of samples.
        dt:        temporal sampling interval (s).
        snr:       signal-to-noise ratio (= amplitude / noise_std); ignored when
                   noise_std is given.
        noise_std: noise standard deviation given directly (derived from snr if None).
        recirculation: add a recirculation component when True.
        recirc_fraction: recirculation peak as a fraction of the main peak.
        recirc_delay:    recirculation delay from the main t0 (s).
        recirc_beta_scale: factor applied to beta for the recirculation gamma, giving a
                   broader bolus.
        baseline:  constant baseline offset.
        seed:      random seed; None makes the result non-deterministic.

    Returns:
        SyntheticTAC(time, clean, noisy, ground_truth)
    """
    if n_time_points < 4:
        raise ValueError("n_time_points must be at least 4.")
    if dt <= 0:
        raise ValueError("dt must be positive.")

    time = np.arange(n_time_points, dtype=np.float64) * dt

    # Main bolus: solve for K so that amplitude is the peak height.
    K_main = _amplitude_to_K(amplitude, alpha, beta)
    clean = gamma_variate(time, K_main, t0, alpha, beta)

    # Optional recirculation component: a delayed, lower and broader gamma.
    if recirculation:
        amp_r = amplitude * float(recirc_fraction)
        beta_r = beta * float(recirc_beta_scale)
        K_r = _amplitude_to_K(amp_r, alpha, beta_r)
        clean = clean + gamma_variate(time, K_r, t0 + recirc_delay, alpha, beta_r)

    clean = clean + float(baseline)

    # Decide the noise standard deviation.
    if noise_std is None:
        if snr is not None and snr > 0:
            sigma = float(amplitude) / float(snr)
        else:
            sigma = 0.0
    else:
        sigma = float(noise_std)

    # Deterministic noise, from the fixed seed.
    rng = np.random.default_rng(seed)
    if sigma > 0:
        noise = rng.normal(0.0, sigma, size=time.shape)
    else:
        noise = np.zeros_like(time)
    noisy = clean + noise

    # Ground truth and analytic indices.
    analytic = gamma_variate_analytic(K_main, t0, alpha, beta)
    ground_truth = {
        "amplitude": float(amplitude),
        "K": float(K_main),
        "t0": float(t0),
        "alpha": float(alpha),
        "beta": float(beta),
        "baseline": float(baseline),
        "noise_std": float(sigma),
        "snr": (float(amplitude) / sigma) if sigma > 0 else float("inf"),
        "dt": float(dt),
        "n_time_points": int(n_time_points),
        "recirculation": bool(recirculation),
        "seed": seed,
        # Analytic ground truth of the gamma-variate, the reference for validation.
        "true_peak_time": analytic["peak_time"],   # = t0 + alpha*beta
        "true_peak_value": analytic["peak_value"],
        "true_auc": analytic["auc"],
        "true_bat": float(t0),
    }

    return SyntheticTAC(time=time, clean=clean, noisy=noisy,
                        ground_truth=ground_truth)


def ground_truth_table(tac: SyntheticTAC) -> Dict[str, float]:
    """Return the ground-truth dictionary of a SyntheticTAC as a plain, JSON-ready dict."""
    return dict(tac.ground_truth)


__all__ = [
    "SyntheticTAC",
    "generate_synthetic_tac",
    "ground_truth_table",
]
