"""
Gamma Variate Fitting for TDC / AIF
====================================
ボーラス注入後のcontrast passage を表現する gamma variate 関数による
フィッティングと、それに基づく時相指標（TTP / Peak / AUC / BAT）の計算。

定義式 (本実装で採用):
    y(t) = K * (t - t0)^alpha * exp(-(t - t0) / beta)   for t > t0
    y(t) = 0                                            otherwise

解析的性質:
    ピーク時刻:   t_peak = t0 + alpha * beta
    ピーク値:     y_peak = K * (alpha*beta)^alpha * exp(-alpha)
    AUC (0→∞):    K * beta^(alpha+1) * Gamma(alpha+1)

設計方針:
    - raw_indices (フィットなし)   : 高速・シンプル・参照値として使う
    - fit_gamma_variate (curve単位) : ROI詳細解析に使用
    - compute_indices_map           : voxel-wise にマップ化。method を切替可能
    - 失敗時は silent failure にせず GammaFitResult.success=False + error_message を必ず残す
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import numpy as np


# --------------------------------------------------------------------
# Gamma variate basis
# --------------------------------------------------------------------

def gamma_variate(t: np.ndarray, K: float, t0: float,
                  alpha: float, beta: float) -> np.ndarray:
    """Gamma variate function.

    y(t) = K * (t - t0)^alpha * exp(-(t - t0) / beta) for t > t0, else 0.
    """
    t = np.asarray(t, dtype=np.float64)
    out = np.zeros_like(t, dtype=np.float64)
    if alpha <= 0 or beta <= 0 or not np.isfinite(K):
        return out

    mask = t > t0
    if not np.any(mask):
        return out
    tau = t[mask] - t0
    # ログスペースで計算して数値安定化
    with np.errstate(invalid='ignore', divide='ignore', over='ignore'):
        log_y = alpha * np.log(tau) - tau / beta
        vals = K * np.exp(log_y)
    vals = np.where(np.isfinite(vals), vals, 0.0)
    out[mask] = vals
    return out


def gamma_variate_analytic(K: float, t0: float,
                            alpha: float, beta: float) -> Dict[str, float]:
    """パラメータから解析的な指標を返す。"""
    if alpha <= 0 or beta <= 0:
        return {'peak_time': np.nan, 'peak_value': np.nan, 'auc': np.nan}
    peak_time = t0 + alpha * beta
    # ピーク値は log 経由で安定計算
    log_peak = alpha * np.log(alpha * beta) - alpha
    peak_value = float(K * np.exp(log_peak))

    # AUC: Gamma(alpha+1) を scipy.special から
    try:
        from scipy.special import gamma as gamma_fn
        auc = float(K * (beta ** (alpha + 1)) * gamma_fn(alpha + 1))
    except ImportError:
        # scipy がない場合は数値積分
        auc = np.nan

    return {
        'peak_time': float(peak_time),
        'peak_value': peak_value,
        'auc': auc,
    }


# --------------------------------------------------------------------
# Initial guess
# --------------------------------------------------------------------

def initial_guess(time: np.ndarray, curve: np.ndarray,
                  bat_threshold_ratio: float = 0.1) -> Dict[str, float]:
    """フィット初期値を推定する。

    Args:
        time: 時間軸 (秒)
        curve: 既にベースライン補正された enhancement 曲線
        bat_threshold_ratio: ピーク値に対する BAT 判定しきい値の比率
    """
    time = np.asarray(time, dtype=np.float64)
    curve = np.asarray(curve, dtype=np.float64)

    # ピーク位置
    if np.all(~np.isfinite(curve)) or np.nanmax(curve) <= 0:
        return {
            'K': 1.0, 't0': float(time[0]) if len(time) > 0 else 0.0,
            'alpha': 2.0, 'beta': 1.0,
        }

    peak_idx = int(np.nanargmax(curve))
    peak_time = float(time[peak_idx])
    peak_value = float(curve[peak_idx])

    # BAT: ピークまでで閾値を初めて超えるサンプル
    threshold = bat_threshold_ratio * peak_value
    rising = np.where(curve[:peak_idx + 1] > threshold)[0]
    dt = float(time[1] - time[0]) if len(time) >= 2 else 1.0
    if len(rising) > 0:
        t0 = float(time[rising[0]]) - dt  # 1サンプル手前に置く
    else:
        t0 = float(time[0]) - dt

    # alpha = 2 (典型的ボーラス), beta から peak_time 整合
    alpha = 2.0
    beta = max((peak_time - t0) / alpha, dt * 0.5)
    # K は ピーク値一致から逆算: peak_value = K * (alpha*beta)^alpha * exp(-alpha)
    denom = ((alpha * beta) ** alpha) * np.exp(-alpha)
    K = peak_value / denom if denom > 0 else peak_value
    return {'K': float(K), 't0': float(t0), 'alpha': alpha, 'beta': float(beta)}


# --------------------------------------------------------------------
# Fit result container
# --------------------------------------------------------------------

@dataclass
class GammaFitResult:
    """gamma variate フィットの結果。失敗時も必ず返すこと（silent failure 禁止）。"""

    success: bool
    # Parameters
    K: float = np.nan
    t0: float = np.nan
    alpha: float = np.nan
    beta: float = np.nan

    # Derived indices (フィットから解析的に計算)
    peak_value: float = np.nan   # Peak enhancement
    peak_time: float = np.nan    # TTP
    auc: float = np.nan          # AUC
    bat: float = np.nan          # Bolus Arrival Time = t0

    # Fit quality
    rmse: float = np.nan
    r_squared: float = np.nan

    # 失敗時の原因
    error_message: str = ""

    # 可視化用フィット曲線（時系列サンプリング済み）
    fitted_curve: Optional[np.ndarray] = None

    # デバッグ用: 使った初期値
    initial_params: Dict[str, float] = field(default_factory=dict)

    def summary_line(self) -> str:
        if not self.success:
            return f"[FAIL] {self.error_message}"
        return (f"Peak={self.peak_value:.1f} TTP={self.peak_time:.1f}s "
                f"BAT={self.bat:.1f}s AUC={self.auc:.1f} "
                f"R^2={self.r_squared:.3f}")


# --------------------------------------------------------------------
# Single curve fitting
# --------------------------------------------------------------------

def fit_gamma_variate(time: np.ndarray, curve: np.ndarray,
                      bounds: Optional[tuple] = None,
                      min_r_squared: float = -np.inf,
                      min_peak_value: float = 0.0) -> GammaFitResult:
    """単一の曲線にgamma variateをフィットする。

    Args:
        time: shape (n_times,)
        curve: shape (n_times,) ※ ベースライン補正済みを推奨
        bounds: ((K_lo,t0_lo,alpha_lo,beta_lo), (K_hi,t0_hi,alpha_hi,beta_hi))
        min_r_squared: これ未満なら failure 扱い
        min_peak_value: これ未満の Peak は failure 扱い（ノイズ棄却）

    Returns:
        GammaFitResult
    """
    time = np.asarray(time, dtype=np.float64)
    curve = np.asarray(curve, dtype=np.float64)

    result = GammaFitResult(success=False)

    # 入力チェック
    if time.shape != curve.shape:
        result.error_message = f"shape mismatch time={time.shape} curve={curve.shape}"
        return result
    if len(curve) < 4:
        result.error_message = f"too few samples: {len(curve)}"
        return result
    if np.all(~np.isfinite(curve)):
        result.error_message = "all-NaN curve"
        return result
    if np.nanmax(curve) <= min_peak_value:
        result.error_message = f"peak <= {min_peak_value} (no bolus)"
        return result

    try:
        from scipy.optimize import curve_fit
    except ImportError:
        result.error_message = "scipy not available"
        return result

    # 初期値
    p0 = initial_guess(time, curve)
    p0_arr = [p0['K'], p0['t0'], p0['alpha'], p0['beta']]
    result.initial_params = p0

    # バウンド
    if bounds is None:
        time_range = float(time[-1] - time[0]) if len(time) >= 2 else 1.0
        peak_max = float(np.nanmax(curve))
        K_hi = max(peak_max * 1e6, 1e6)
        lo = [1e-6, float(time[0]) - time_range, 0.3, 1e-3]
        hi = [K_hi, float(time[-1]), 20.0, time_range * 4]
        bounds = (lo, hi)

    # フィット実行
    try:
        popt, _pcov = curve_fit(
            gamma_variate, time, curve,
            p0=p0_arr, bounds=bounds, maxfev=5000
        )
    except Exception as e:
        result.error_message = f"curve_fit failed: {type(e).__name__}: {e}"
        return result

    K, t0, alpha, beta = [float(x) for x in popt]

    if not (np.isfinite(K) and np.isfinite(t0)
            and np.isfinite(alpha) and np.isfinite(beta)):
        result.error_message = "non-finite parameters"
        return result

    fitted = gamma_variate(time, K, t0, alpha, beta)

    # 品質メトリクス
    residuals = curve - fitted
    ss_res = float(np.sum(residuals ** 2))
    ss_tot = float(np.sum((curve - np.mean(curve)) ** 2))
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    rmse = float(np.sqrt(np.mean(residuals ** 2)))

    if r_squared < min_r_squared:
        result.error_message = f"R^2={r_squared:.3f} below {min_r_squared}"
        result.r_squared = r_squared
        result.rmse = rmse
        result.fitted_curve = fitted
        result.K = K
        result.t0 = t0
        result.alpha = alpha
        result.beta = beta
        return result

    analytic = gamma_variate_analytic(K, t0, alpha, beta)

    result.success = True
    result.K = K
    result.t0 = t0
    result.alpha = alpha
    result.beta = beta
    result.peak_value = analytic['peak_value']
    result.peak_time = analytic['peak_time']
    result.auc = analytic['auc']
    result.bat = t0
    result.rmse = rmse
    result.r_squared = r_squared
    result.fitted_curve = fitted
    return result


# --------------------------------------------------------------------
# Raw (no-fit) indices
# --------------------------------------------------------------------

def compute_raw_indices(time: np.ndarray, enhancement_curve: np.ndarray,
                         bat_threshold_ratio: float = 0.1) -> Dict[str, float]:
    """フィットせずに enhancement 曲線から指標を計算する。

    信頼できない場合でも NaN を返すのみで例外は投げない。

    Returns:
        dict: 'ttp', 'peak', 'auc', 'bat'
    """
    time = np.asarray(time, dtype=np.float64)
    curve = np.asarray(enhancement_curve, dtype=np.float64)

    if len(curve) == 0 or np.all(~np.isfinite(curve)):
        return {'ttp': np.nan, 'peak': np.nan, 'auc': np.nan, 'bat': np.nan}

    peak_idx = int(np.nanargmax(curve))
    peak_value = float(curve[peak_idx])
    ttp = float(time[peak_idx])

    positive = np.where(np.isfinite(curve), np.maximum(curve, 0), 0.0)
    auc = float(np.trapezoid(positive, time))

    if peak_value > 0:
        threshold = bat_threshold_ratio * peak_value
        rising_idx = np.where(curve[:peak_idx + 1] > threshold)[0]
        bat = float(time[rising_idx[0]]) if len(rising_idx) > 0 else float(time[0])
    else:
        bat = np.nan

    return {'ttp': ttp, 'peak': peak_value, 'auc': auc, 'bat': bat}


# --------------------------------------------------------------------
# Voxel-wise map (raw / gamma)
# --------------------------------------------------------------------

def compute_indices_map(corrected_slice: np.ndarray, time: np.ndarray,
                         brain_mask: Optional[np.ndarray] = None,
                         method: str = 'raw',
                         progress_callback=None) -> Dict[str, Any]:
    """スライス内の全ボクセル (mask内) に対して TTP/Peak/AUC/BAT マップを計算する。

    Args:
        corrected_slice: shape (n_times, rows, cols)  ベースライン補正後
        time: 時間軸
        brain_mask: (rows, cols) bool. None なら全ボクセル
        method: 'raw' | 'gamma'
        progress_callback: optional callable(frac) 0.0→1.0

    Returns:
        dict:
            'ttp', 'peak', 'auc', 'bat': (rows, cols) マップ
            'failure_mask':               (rows, cols) bool / None
            'success_rate':               float (gammaのみ。rawでは None)
            'method':                     str
            'n_processed':                int
            'n_failed':                   int
    """
    if corrected_slice.ndim != 3:
        raise ValueError(f"expected (n_t,rows,cols), got {corrected_slice.shape}")
    n_t, rows, cols = corrected_slice.shape
    time = np.asarray(time, dtype=np.float64)

    if method == 'raw':
        return _compute_indices_map_raw(corrected_slice, time, brain_mask)
    elif method == 'gamma':
        return _compute_indices_map_gamma(
            corrected_slice, time, brain_mask, progress_callback
        )
    else:
        raise ValueError(f"Unknown method: {method}")


def _compute_indices_map_raw(corrected_slice: np.ndarray, time: np.ndarray,
                              brain_mask: Optional[np.ndarray]) -> Dict[str, Any]:
    n_t, rows, cols = corrected_slice.shape

    peak_idx = np.argmax(corrected_slice, axis=0)      # (rows, cols)
    peak_value = np.max(corrected_slice, axis=0)       # (rows, cols)
    ttp = time[peak_idx]
    positive = np.maximum(corrected_slice, 0)
    auc = np.trapezoid(positive, time, axis=0)

    # BAT (10% threshold) - vectorized 化
    threshold = 0.1 * peak_value                        # (rows, cols)
    # 各voxelで threshold を超える最初の time を取得
    above = corrected_slice > threshold[np.newaxis, :, :]  # (n_t, rows, cols)
    # 最初のTrue のindex。見つからない場合は-1で埋める
    any_above = np.any(above, axis=0)
    first_idx = np.argmax(above, axis=0)               # (rows, cols)
    bat = np.where(any_above, time[first_idx], np.nan)

    # 有効ボクセル: peak > 0
    valid = peak_value > 0
    ttp = np.where(valid, ttp, np.nan)
    auc_out = np.where(valid, auc, np.nan)
    peak_out = np.where(valid, peak_value, np.nan)
    bat = np.where(valid, bat, np.nan)

    if brain_mask is not None:
        ttp = np.where(brain_mask, ttp, np.nan)
        auc_out = np.where(brain_mask, auc_out, np.nan)
        peak_out = np.where(brain_mask, peak_out, np.nan)
        bat = np.where(brain_mask, bat, np.nan)

    n_valid = int(np.count_nonzero(np.isfinite(ttp)))
    n_total = rows * cols if brain_mask is None else int(brain_mask.sum())

    return {
        'ttp': ttp.astype(np.float32),
        'peak': peak_out.astype(np.float32),
        'auc': auc_out.astype(np.float32),
        'bat': bat.astype(np.float32),
        'failure_mask': None,
        'success_rate': None,
        'method': 'raw',
        'n_processed': n_total,
        'n_failed': max(0, n_total - n_valid),
    }


def _compute_indices_map_gamma(corrected_slice: np.ndarray, time: np.ndarray,
                                brain_mask: Optional[np.ndarray],
                                progress_callback=None) -> Dict[str, Any]:
    n_t, rows, cols = corrected_slice.shape

    ttp = np.full((rows, cols), np.nan, dtype=np.float32)
    peak_v = np.full((rows, cols), np.nan, dtype=np.float32)
    auc = np.full((rows, cols), np.nan, dtype=np.float32)
    bat = np.full((rows, cols), np.nan, dtype=np.float32)
    failure_mask = np.zeros((rows, cols), dtype=bool)

    # 処理対象リスト
    if brain_mask is None:
        target_rc = [(r, c) for r in range(rows) for c in range(cols)]
    else:
        ys, xs = np.where(brain_mask)
        target_rc = list(zip(ys.tolist(), xs.tolist()))

    n_target = len(target_rc)
    n_done = 0
    n_failed = 0
    next_progress = 0.05

    for r, c in target_rc:
        curve = corrected_slice[:, r, c]
        if np.nanmax(curve) <= 0 or not np.any(np.isfinite(curve)):
            failure_mask[r, c] = True
            n_failed += 1
        else:
            res = fit_gamma_variate(time, curve)
            if not res.success:
                failure_mask[r, c] = True
                n_failed += 1
            else:
                ttp[r, c] = res.peak_time
                peak_v[r, c] = res.peak_value
                auc[r, c] = res.auc
                bat[r, c] = res.bat

        n_done += 1
        if progress_callback is not None and n_target > 0:
            frac = n_done / n_target
            if frac >= next_progress:
                progress_callback(frac)
                next_progress += 0.05

    # brain_mask 外は NaN のまま
    if brain_mask is not None:
        for arr in (ttp, peak_v, auc, bat):
            arr[~brain_mask] = np.nan
        failure_mask[~brain_mask] = False  # 対象外は failure ではない

    success_rate = (1.0 - n_failed / n_target) if n_target > 0 else 0.0

    return {
        'ttp': ttp,
        'peak': peak_v,
        'auc': auc,
        'bat': bat,
        'failure_mask': failure_mask,
        'success_rate': float(success_rate),
        'method': 'gamma',
        'n_processed': n_target,
        'n_failed': n_failed,
    }
