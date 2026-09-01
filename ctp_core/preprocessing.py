"""
Perfusion CT Preprocessing
===========================
Baseline correction and temporal smoothing for time-density curves and volumes.

The Phase 1 implementation exists to:
- keep raw, smoothed, baseline and corrected data **separately**, not in place
- leave a record of which method was applied, in a form that can be logged
- give the later stages (gamma fitting, deconvolution) a defined input

To keep the processing from becoming a black box, the intermediate result of each
stage is returned explicitly in a dictionary.

Supported processing:
- baseline: 'early_mean' | 'minimum' | 'user_phase'
- smoothing: 'none' | 'moving_average' | 'savgol'
"""

from dataclasses import dataclass, field
import numpy as np


@dataclass
class PreprocessConfig:
    """Settings for time-density-curve preprocessing.

    A dataclass, so that the configuration is easy to write to a log.
    """

    # Baseline estimation
    baseline_method: str = 'early_mean'   # 'early_mean' | 'minimum' | 'user_phase'
    baseline_n_phases: int = 2            # leading samples used by early_mean
    baseline_phase: int = 0               # phase index referenced by user_phase

    # Temporal smoothing
    smoothing_method: str = 'none'        # 'none' | 'moving_average' | 'savgol'
    smoothing_window: int = 3             # odd is preferred; savgol needs at least 3
    smoothing_polyorder: int = 2          # polynomial order for savgol

    def describe(self) -> str:
        """A one-line summary for the log."""
        parts = [f"baseline={self.baseline_method}"]
        if self.baseline_method == 'early_mean':
            parts.append(f"n={self.baseline_n_phases}")
        elif self.baseline_method == 'user_phase':
            parts.append(f"phase={self.baseline_phase}")

        parts.append(f"smooth={self.smoothing_method}")
        if self.smoothing_method == 'moving_average':
            parts.append(f"win={self.smoothing_window}")
        elif self.smoothing_method == 'savgol':
            parts.append(f"win={self.smoothing_window},poly={self.smoothing_polyorder}")

        return " / ".join(parts)


# --------------------------------------------------------------------
# 1D curve level
# --------------------------------------------------------------------

def estimate_baseline(curve: np.ndarray, config: PreprocessConfig) -> float:
    """Estimate the baseline value of a one-dimensional time-density curve.

    Args:
        curve: a one-dimensional array along time
        config: the settings
    Returns:
        float: the baseline value
    """
    curve = np.asarray(curve, dtype=np.float64)
    n = len(curve)
    if n == 0:
        return 0.0

    method = config.baseline_method
    if method == 'early_mean':
        n_b = max(1, min(config.baseline_n_phases, n))
        return float(np.mean(curve[:n_b]))
    elif method == 'minimum':
        return float(np.min(curve))
    elif method == 'user_phase':
        p = max(0, min(config.baseline_phase, n - 1))
        return float(curve[p])
    else:
        raise ValueError(f"Unknown baseline method: {method}")


def smooth_curve(curve: np.ndarray, config: PreprocessConfig) -> np.ndarray:
    """Smooth a one-dimensional time-density curve along time.

    The window is capped at about half the length of the curve, so that the result
    is not over-smoothed.
    """
    curve = np.asarray(curve, dtype=np.float64)
    n = len(curve)
    if n == 0:
        return curve.copy()

    method = config.smoothing_method
    if method == 'none':
        return curve.copy()

    if method == 'moving_average':
        w = max(1, int(config.smoothing_window))
        w = min(w, n)
        if w <= 1:
            return curve.copy()
        pad = w // 2
        padded = np.pad(curve, pad, mode='edge')
        kernel = np.ones(w) / w
        smoothed = np.convolve(padded, kernel, mode='valid')
        # Adjust the length.
        if len(smoothed) > n:
            smoothed = smoothed[:n]
        elif len(smoothed) < n:
            smoothed = np.pad(smoothed, (0, n - len(smoothed)), mode='edge')
        return smoothed.astype(np.float64)

    if method == 'savgol':
        try:
            from scipy.signal import savgol_filter
        except ImportError as e:
            raise RuntimeError("scipy is required for savgol smoothing") from e
        w = int(config.smoothing_window)
        if w < 3:
            w = 3
        if w % 2 == 0:
            w += 1
        w = min(w, n if n % 2 == 1 else n - 1)
        if w < 3:
            return curve.copy()
        poly = min(int(config.smoothing_polyorder), w - 1)
        poly = max(poly, 1)
        return savgol_filter(curve, w, poly).astype(np.float64)

    raise ValueError(f"Unknown smoothing method: {method}")


def preprocess_curve(curve: np.ndarray, config: PreprocessConfig) -> dict:
    """Preprocess a one-dimensional time-density curve, returning every stage.

    Returns:
        dict:
            'raw':         the original curve
            'smoothed':    after smoothing
            'baseline':    the baseline value (float)
            'corrected':   smoothed - baseline
            'config_description': a text summary of the settings
    """
    raw = np.asarray(curve, dtype=np.float64).copy()
    smoothed = smooth_curve(raw, config)
    baseline = estimate_baseline(smoothed, config)
    corrected = smoothed - baseline
    return {
        'raw': raw,
        'smoothed': smoothed,
        'baseline': baseline,
        'corrected': corrected,
        'config_description': config.describe(),
    }


# --------------------------------------------------------------------
# Slice level (voxel-wise)
# --------------------------------------------------------------------

def _smooth_volume_time(vol_time_first: np.ndarray, config: PreprocessConfig) -> np.ndarray:
    """Smooth an array of shape (n_times, ...) along the time axis.

    For memory efficiency every method except savgol is vectorized, using the same
    window as the one-dimensional case.
    """
    method = config.smoothing_method
    n_t = vol_time_first.shape[0]

    if method == 'none':
        return vol_time_first.astype(np.float64, copy=True)

    if method == 'moving_average':
        w = max(1, int(config.smoothing_window))
        w = min(w, n_t)
        if w <= 1:
            return vol_time_first.astype(np.float64, copy=True)
        pad = w // 2
        padded = np.pad(vol_time_first.astype(np.float64),
                        ((pad, pad),) + ((0, 0),) * (vol_time_first.ndim - 1),
                        mode='edge')
        # A cumulative sum makes this O(n).
        cumsum = np.cumsum(padded, axis=0)
        smoothed = (cumsum[w:] - cumsum[:-w]) / w
        # Adjust the length; padding can leave it one sample out.
        if smoothed.shape[0] > n_t:
            smoothed = smoothed[:n_t]
        elif smoothed.shape[0] < n_t:
            # Replicate the edge.
            deficit = n_t - smoothed.shape[0]
            tail = np.broadcast_to(smoothed[-1:], (deficit,) + smoothed.shape[1:])
            smoothed = np.concatenate([smoothed, tail], axis=0)
        return smoothed

    if method == 'savgol':
        try:
            from scipy.signal import savgol_filter
        except ImportError as e:
            raise RuntimeError("scipy is required for savgol smoothing") from e
        w = int(config.smoothing_window)
        if w < 3:
            w = 3
        if w % 2 == 0:
            w += 1
        w = min(w, n_t if n_t % 2 == 1 else n_t - 1)
        if w < 3:
            return vol_time_first.astype(np.float64, copy=True)
        poly = min(int(config.smoothing_polyorder), w - 1)
        poly = max(poly, 1)
        return savgol_filter(vol_time_first.astype(np.float64), w, poly, axis=0)

    raise ValueError(f"Unknown smoothing method: {method}")


def preprocess_slice(slice_data: np.ndarray, config: PreprocessConfig) -> dict:
    """Preprocess a whole slice of shape (n_times, rows, cols), voxel by voxel.

    Returns:
        dict:
            'smoothed':     after smoothing (n_times, rows, cols)
            'baseline_map': map of baseline values (rows, cols)
            'corrected':    smoothed - baseline_map[None]
            'config_description': a text summary of the settings
    """
    if slice_data.ndim != 3:
        raise ValueError(f"Expected (n_times, rows, cols), got {slice_data.shape}")

    smoothed = _smooth_volume_time(slice_data, config)
    n_t = smoothed.shape[0]

    method = config.baseline_method
    if method == 'early_mean':
        n_b = max(1, min(config.baseline_n_phases, n_t))
        baseline_map = np.mean(smoothed[:n_b], axis=0)
    elif method == 'minimum':
        baseline_map = np.min(smoothed, axis=0)
    elif method == 'user_phase':
        p = max(0, min(config.baseline_phase, n_t - 1))
        baseline_map = smoothed[p].copy()
    else:
        raise ValueError(f"Unknown baseline method: {method}")

    corrected = smoothed - baseline_map[np.newaxis, :, :]

    return {
        'smoothed': smoothed,
        'baseline_map': baseline_map.astype(np.float64),
        'corrected': corrected.astype(np.float64),
        'config_description': config.describe(),
    }
