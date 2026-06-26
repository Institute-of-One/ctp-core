# -*- coding: utf-8 -*-
"""
合成 CTP 時間–濃度曲線ジェネレータ (再現可能)
=============================================

IORN-001 の検証・再現性確認のために、gamma-variate モデルに基づく
合成 time–attenuation curve (TAC) を **決定論的** に生成する。

特徴:
  - 固定乱数シード (seed) によりノイズまで完全再現可能。
  - amplitude(ピーク濃度) / t0(bolus arrival) / alpha / beta を指定可能。
  - 時間サンプリング間隔 (dt) とサンプル数 (n_time_points) を指定可能。
  - ノイズは SNR もしくは絶対標準偏差 (noise_std) で指定可能。
  - 任意で再循環 (recirculation) 成分を付加可能。
  - 出力: 時間軸 / クリーン曲線 / ノイズ付き曲線 / 真値パラメータ。

設計境界:
  本モジュールは ctp-core (open/reproducible) に属し、GUI・DICOM・患者/顧客
  データに一切依存しない。生成データは合成のみで機密情報を含まない。

使い方:
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
# データ構造
# ---------------------------------------------------------------------------

@dataclass
class SyntheticTAC:
    """合成 TAC の生成結果。

    Attributes:
        time:         時間軸 (s), shape (n,)
        clean:        ノイズ無しの真の曲線 (enhancement), shape (n,)
        noisy:        ノイズ付き観測曲線, shape (n,)
        ground_truth: 真値パラメータと解析的指標 (dict)
    """
    time: np.ndarray
    clean: np.ndarray
    noisy: np.ndarray
    ground_truth: Dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# ヘルパ: amplitude(ピーク高) -> gamma_variate の K 係数
# ---------------------------------------------------------------------------

def _amplitude_to_K(amplitude: float, alpha: float, beta: float) -> float:
    """ピーク濃度 amplitude を gamma_variate の K 係数へ変換する。

    gamma_variate のピーク値 = K * (alpha*beta)^alpha * exp(-alpha)。
    これを amplitude に一致させる K を解析的に求める。
    """
    if alpha <= 0 or beta <= 0:
        return float(amplitude)
    log_denom = alpha * np.log(alpha * beta) - alpha
    denom = float(np.exp(log_denom))
    return float(amplitude / denom) if denom > 0 else float(amplitude)


# ---------------------------------------------------------------------------
# 生成
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
    """再現可能な合成 CTP 曲線を生成する。

    Args:
        amplitude: 主ボーラスのピーク enhancement 値 (例: HU)。
        t0:        bolus arrival time (s)。
        alpha,beta: gamma-variate 形状パラメータ。
        n_time_points: サンプル数。
        dt:        時間サンプリング間隔 (s)。
        snr:       信号対雑音比 (= amplitude / noise_std)。noise_std 指定時は無視。
        noise_std: ノイズ標準偏差を直接指定 (None なら snr から導出)。
        recirculation: True で再循環成分を付加。
        recirc_fraction: 再循環ピークの主ピークに対する比率。
        recirc_delay:    主 t0 からの再循環遅延 (s)。
        recirc_beta_scale: 再循環ガンマの beta 倍率 (broader bolus)。
        baseline:  一定ベースラインオフセット。
        seed:      乱数シード (None で非決定論)。

    Returns:
        SyntheticTAC(time, clean, noisy, ground_truth)
    """
    if n_time_points < 4:
        raise ValueError("n_time_points は 4 以上が必要です。")
    if dt <= 0:
        raise ValueError("dt は正である必要があります。")

    time = np.arange(n_time_points, dtype=np.float64) * dt

    # 主ボーラス (amplitude をピーク高として K を逆算)
    K_main = _amplitude_to_K(amplitude, alpha, beta)
    clean = gamma_variate(time, K_main, t0, alpha, beta)

    # 再循環成分 (任意): 遅延した、低く幅広いガンマ
    if recirculation:
        amp_r = amplitude * float(recirc_fraction)
        beta_r = beta * float(recirc_beta_scale)
        K_r = _amplitude_to_K(amp_r, alpha, beta_r)
        clean = clean + gamma_variate(time, K_r, t0 + recirc_delay, alpha, beta_r)

    clean = clean + float(baseline)

    # ノイズ標準偏差の決定
    if noise_std is None:
        if snr is not None and snr > 0:
            sigma = float(amplitude) / float(snr)
        else:
            sigma = 0.0
    else:
        sigma = float(noise_std)

    # 決定論的ノイズ (固定シード)
    rng = np.random.default_rng(seed)
    if sigma > 0:
        noise = rng.normal(0.0, sigma, size=time.shape)
    else:
        noise = np.zeros_like(time)
    noisy = clean + noise

    # 真値・解析指標
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
        # gamma-variate の解析的真値 (検証時の基準)
        "true_peak_time": analytic["peak_time"],   # = t0 + alpha*beta
        "true_peak_value": analytic["peak_value"],
        "true_auc": analytic["auc"],
        "true_bat": float(t0),
    }

    return SyntheticTAC(time=time, clean=clean, noisy=noisy,
                        ground_truth=ground_truth)


def ground_truth_table(tac: SyntheticTAC) -> Dict[str, float]:
    """SyntheticTAC の真値辞書を返す (JSON 化しやすいプレーン dict)。"""
    return dict(tac.ground_truth)


__all__ = [
    "SyntheticTAC",
    "generate_synthetic_tac",
    "ground_truth_table",
]
