"""
Perfusion CT Preprocessing
===========================
TDC / volume に対するベースライン補正と時間方向平滑化。

Phase 1 の実装目的は以下:
- raw / smoothed / baseline / corrected を**別管理**で保持する
- どの方法で処理したかをログ可能な形で残す
- 後段 (gamma fit, deconvolution) がこの出力を前提にできる

ブラックボックス化回避のため、各段階の中間結果は辞書で明示的に返す。

対応する処理:
- baseline: 'early_mean' | 'minimum' | 'user_phase'
- smoothing: 'none' | 'moving_average' | 'savgol'
"""

from dataclasses import dataclass, field
import numpy as np


@dataclass
class PreprocessConfig:
    """TDC前処理の設定。ログ出力しやすいようにdataclassにする。"""

    # ベースライン推定
    baseline_method: str = 'early_mean'   # 'early_mean' | 'minimum' | 'user_phase'
    baseline_n_phases: int = 2            # early_mean 時の先頭サンプル数
    baseline_phase: int = 0               # user_phase 時の参照phase番号

    # 時間方向平滑化
    smoothing_method: str = 'none'        # 'none' | 'moving_average' | 'savgol'
    smoothing_window: int = 3             # 奇数推奨。savgolでは3以上。
    smoothing_polyorder: int = 2          # savgol多項式次数

    def describe(self) -> str:
        """ログ用の1行要約。"""
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
    """1次元TDC曲線のベースライン値を推定する。

    Args:
        curve: 時間方向の1次元配列
        config: 設定
    Returns:
        float: ベースライン値
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
    """1次元TDC曲線を時間方向に平滑化する。

    強すぎる平滑化を避けるため、窓幅は最大でも curve 長の半分程度までとする。
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
        # 長さ調整
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
    """1次元TDC曲線を前処理し、各段階の中間結果を辞書で返す。

    Returns:
        dict:
            'raw':         元曲線
            'smoothed':    平滑化後
            'baseline':    baseline値 (float)
            'corrected':   smoothed - baseline
            'config_description': 設定の文字列要約
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
    """shape (n_times, ...) の配列を時間軸で平滑化する。

    メモリ効率のため、savgol以外は1次元と同じ窓で vectorized 実装にする。
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
        # 累積和でO(n)
        cumsum = np.cumsum(padded, axis=0)
        smoothed = (cumsum[w:] - cumsum[:-w]) / w
        # 長さ調整 (padding方式により±1する場合あり)
        if smoothed.shape[0] > n_t:
            smoothed = smoothed[:n_t]
        elif smoothed.shape[0] < n_t:
            # エッジ複製
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
    """スライス全体 shape=(n_times, rows, cols) をボクセル単位で前処理する。

    Returns:
        dict:
            'smoothed':     平滑化後 (n_times, rows, cols)
            'baseline_map': ベースライン値マップ (rows, cols)
            'corrected':    smoothed - baseline_map[None]
            'config_description': 設定の文字列要約
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
