"""
パラメトリックマップ生成モジュール
====================================
AIF とデコンボリューション解析を用いて、
CBF / CBV / MTT / TTP マップを生成する。

理論背景:
---------
CT Perfusionの基本モデル（Meier & Zierler, 1954 の指標希釈理論）:

    C_tissue(t) = CBF * (C_a(t) ⊗ R(t))

ここで:
    C_tissue(t): 組織の造影剤濃度（造影値）
    C_a(t): 動脈入力関数 (AIF)
    R(t): 残留関数 (Residue function)
    ⊗: コンボリューション（畳み込み）

参考文献:
- Ostergaard L, et al. "High resolution measurement of cerebral
  blood flow using intravascular tracer bolus passages. Part I:
  Mathematical approach and statistical analysis."
  Magnetic Resonance in Medicine. 1996;36(5):715-725.
  → SVDデコンボリューション法の原典:
    "The tissue concentration time curve C(t) can be expressed as
     C(t) = CBF · (Ca(t) ⊗ R(t)), where R(t) is the residue
     function describing the fraction of tracer still present in
     the tissue at time t."
    "CBF is determined as the maximum of the deconvolved residue
     function: CBF = max(R(t))"

- Wu O, et al. "Tracer arrival timing-insensitive technique for
  estimating flow in MR perfusion-weighted imaging using singular
  value decomposition with a block-circulant deconvolution matrix."
  Magnetic Resonance in Medicine. 2003;50(1):164-174.
  → block-circulant SVD (oSVD) による遅延非感受性デコンボリューション:
    "By using a block-circulant matrix formulation, the technique
     becomes insensitive to tracer arrival timing differences
     between the AIF and tissue curves."

- Konstas AA, et al. "Theoretic basis and technical implementations
  of CT perfusion in acute ischemic stroke, Part 1: Theoretic basis."
  AJNR American Journal of Neuroradiology. 2009;30(4):662-668.
  → CT Perfusionの理論的基礎を包括的にまとめたレビュー:
    "CBV is proportional to the area under the tissue enhancement
     curve: CBV = (1/ρ) · ∫C_tissue(t)dt / ∫C_a(t)dt"
    "MTT = CBV / CBF (central volume theorem)"

使い方:
    from parametric_maps import ParametricMapGenerator
    generator = ParametricMapGenerator(volume_4d, metadata)
    maps = generator.compute(aif_curve, slice_index=2)
    generator.save_maps(maps, "output_folder")
"""

import numpy as np
from scipy.linalg import svd, circulant


class ParametricMaps:
    """パラメトリックマップの結果を保持するクラス。"""

    def __init__(self):
        self.cbf = None   # Cerebral Blood Flow map (ml/100g/min)
        self.cbv = None   # Cerebral Blood Volume map (ml/100g)
        self.mtt = None   # Mean Transit Time map (s)
        self.ttp = None   # Time to Peak map (s)
        self.tmax = None  # Time to Maximum of residue function (s)
        self.delay = None # Tracer arrival delay map (s)
        self.residue = None  # 残留関数マップ (n_times, rows, cols)
        self.slice_index = None
        self.computation_info = {}


class ParametricMapGenerator:
    """パラメトリックマップ生成エンジン。"""

    # CT値→造影剤濃度の変換係数
    # (Wintermark et al., 2005: 約1 HU ≈ 1 mg/mL for iodinated contrast)
    HU_TO_CONCENTRATION = 1.0

    # 脳組織の密度 (g/mL)
    BRAIN_DENSITY = 1.04

    def __init__(self, volume_4d, metadata):
        self.volume = volume_4d
        self.meta = metadata
        self.n_times = metadata['n_times']
        self.rows = metadata['rows']
        self.cols = metadata['cols']
        self.time_seconds = np.array(metadata['time_seconds'])

        # 時間間隔の算出
        if len(self.time_seconds) > 1:
            self.dt = np.mean(np.diff(self.time_seconds))
        else:
            self.dt = 1.0

    def _build_convolution_matrix(self, aif, method='standard'):
        """AIFからコンボリューション行列を構築する。

        Standard SVD:
            下三角のToeplitz行列
            (Ostergaard 1996: standard truncated SVD)

        Block-circulant SVD (oSVD):
            ブロック循環行列を使用し、遅延に対してロバスト
            (Wu 2003: block-circulant deconvolution)

        Args:
            aif: AIF造影値カーブ (n_times,)
            method: 'standard' or 'circulant'

        Returns:
            A: コンボリューション行列 shape=(N, N) or (2N, 2N)
        """
        n = len(aif)

        if method == 'standard':
            # 標準的な下三角Toeplitz行列
            A = np.zeros((n, n))
            for i in range(n):
                for j in range(i + 1):
                    A[i, j] = aif[i - j]
            A *= self.dt
            return A

        elif method == 'circulant':
            # Block-circulant行列 (Wu 2003)
            # 2N x 2N の循環行列を構成
            D = 2 * n
            c = np.zeros(D)
            c[:n] = aif
            # 循環行列は最初の列から生成
            A = circulant(c) * self.dt
            return A

        else:
            raise ValueError(f"未知のmethod: {method}")

    def _svd_deconvolution(self, tissue_curve, aif, method='circulant',
                            svd_threshold=0.15):
        """SVDデコンボリューションを実行する。

        Ostergaard (1996) の truncated SVD 法:
        1. C_tissue = CBF * dt * A * R  (A: AIFのコンボリューション行列)
        2. R = (1/CBF) * A^(-1) * C_tissue / dt
        3. A の逆行列をSVDで正則化して求める

        Args:
            tissue_curve: 組織の造影値カーブ
            aif: AIF造影値カーブ
            method: 'standard' or 'circulant'
            svd_threshold: 特異値の打ち切り閾値（最大特異値に対する比率）
                          (Ostergaard 1996: "singular values below a threshold
                           fraction of the maximum singular value are set to zero")

        Returns:
            residue: 残留関数 R(t)
            cbf: CBF値
        """
        n = len(aif)

        # コンボリューション行列の構築
        A = self._build_convolution_matrix(aif, method=method)

        if method == 'circulant':
            # 入力ベクトルも2Nに拡張
            tissue_ext = np.zeros(2 * n)
            tissue_ext[:n] = tissue_curve
        else:
            tissue_ext = tissue_curve

        # SVD分解
        U, S, Vt = svd(A, full_matrices=False)

        # 特異値の打ち切り（正則化）
        # (Ostergaard 1996: truncated SVD)
        s_max = S[0]
        threshold = svd_threshold * s_max
        S_inv = np.zeros_like(S)
        for i, s in enumerate(S):
            if s > threshold:
                S_inv[i] = 1.0 / s

        # 残留関数の算出
        # R = V * diag(1/S) * U^T * C_tissue
        residue_full = Vt.T @ np.diag(S_inv) @ U.T @ tissue_ext

        if method == 'circulant':
            residue = residue_full[:n]
        else:
            residue = residue_full

        # CBF = max(R(t))
        # (Ostergaard 1996: "CBF is determined as the maximum of
        #  the deconvolved residue function")
        cbf = np.max(residue)

        return residue, cbf

    def compute(self, aif_curve, slice_index, n_baseline=2,
                method='circulant', svd_threshold=0.15,
                brain_mask=None):
        """パラメトリックマップを計算する。

        Args:
            aif_curve: AIF造影値カーブ (n_times,)（生のCT値）
            slice_index: 対象スライスインデックス
            n_baseline: ベースライン時相数
            method: デコンボリューション手法
            svd_threshold: SVD正則化閾値
            brain_mask: 脳領域マスク（Noneなら自動）

        Returns:
            ParametricMaps
        """
        maps = ParametricMaps()
        maps.slice_index = slice_index

        # 造影値への変換
        slice_data = self.volume[:, slice_index, :, :]
        baseline = np.mean(slice_data[:n_baseline], axis=0)
        tissue_enhancement = slice_data - baseline[np.newaxis, :, :]

        aif_baseline = np.mean(aif_curve[:n_baseline])
        aif_enhancement = aif_curve - aif_baseline

        # AIFが有効な値を持つことを確認
        if np.max(aif_enhancement) <= 0:
            raise ValueError("AIF造影値が無効です（ピーク <= 0）")

        # 脳マスクの自動生成（簡易版）
        if brain_mask is None:
            peak_enh = np.max(tissue_enhancement, axis=0)
            brain_mask = (baseline > -10) & (baseline < 200) & (peak_enh > 5)

        # マップの初期化
        cbf_map = np.zeros((self.rows, self.cols), dtype=np.float32)
        cbv_map = np.zeros((self.rows, self.cols), dtype=np.float32)
        mtt_map = np.zeros((self.rows, self.cols), dtype=np.float32)
        ttp_map = np.zeros((self.rows, self.cols), dtype=np.float32)
        tmax_map = np.zeros((self.rows, self.cols), dtype=np.float32)
        residue_map = np.zeros((self.n_times, self.rows, self.cols),
                                dtype=np.float32)

        # AIF面積（CBV算出用）
        # (Konstas 2009: "CBV = (1/ρ) · ∫C_tissue(t)dt / ∫C_a(t)dt")
        aif_area = np.trapz(aif_enhancement, self.time_seconds)
        if aif_area <= 0:
            aif_area = 1.0  # ゼロ除算防止

        # ピクセルごとのデコンボリューション
        total_pixels = int(brain_mask.sum())
        processed = 0
        print_interval = max(total_pixels // 10, 1)

        print(f"パラメトリックマップ計算中... ({total_pixels} ピクセル)")

        for r in range(self.rows):
            for c in range(self.cols):
                if not brain_mask[r, c]:
                    continue

                tissue_curve = tissue_enhancement[:, r, c]

                # 造影が乏しいピクセルはスキップ
                if np.max(tissue_curve) < 5:
                    continue

                try:
                    # SVDデコンボリューション
                    residue, cbf = self._svd_deconvolution(
                        tissue_curve, aif_enhancement,
                        method=method, svd_threshold=svd_threshold
                    )

                    # CBF (ml/100g/min に変換)
                    # CBF_raw は1/秒単位なので、60を掛けて100gあたりに換算
                    cbf_value = cbf * 60.0 / self.BRAIN_DENSITY * 100.0

                    # CBV (ml/100g)
                    tissue_area = np.trapz(tissue_curve, self.time_seconds)
                    cbv_value = (tissue_area / aif_area) / self.BRAIN_DENSITY * 100.0

                    # MTT (s) = CBV / CBF (中心容積定理)
                    # (Konstas 2009: "MTT = CBV / CBF")
                    if cbf_value > 0:
                        mtt_value = cbv_value / cbf_value * 60.0
                    else:
                        mtt_value = 0.0

                    # TTP
                    ttp_idx = np.argmax(tissue_curve)
                    ttp_value = self.time_seconds[ttp_idx]

                    # Tmax (残留関数のピーク時刻)
                    tmax_idx = np.argmax(residue)
                    tmax_value = self.time_seconds[min(tmax_idx, self.n_times - 1)]

                    # 値のクリッピング（異常値除外）
                    cbf_map[r, c] = np.clip(cbf_value, 0, 150)
                    cbv_map[r, c] = np.clip(cbv_value, 0, 20)
                    mtt_map[r, c] = np.clip(mtt_value, 0, 30)
                    ttp_map[r, c] = ttp_value
                    tmax_map[r, c] = tmax_value
                    residue_map[:, r, c] = residue[:self.n_times]

                except Exception:
                    continue

                processed += 1
                if processed % print_interval == 0:
                    pct = processed / total_pixels * 100
                    print(f"  {pct:.0f}% ({processed}/{total_pixels})")

        print(f"  完了: {processed} ピクセルを処理")

        maps.cbf = cbf_map
        maps.cbv = cbv_map
        maps.mtt = mtt_map
        maps.ttp = ttp_map
        maps.tmax = tmax_map
        maps.residue = residue_map

        maps.computation_info = {
            'method': method,
            'svd_threshold': svd_threshold,
            'n_baseline': n_baseline,
            'dt': self.dt,
            'aif_area': float(aif_area),
            'processed_pixels': processed,
            'total_pixels': total_pixels,
        }

        return maps

    @staticmethod
    def save_maps(maps, output_folder):
        """パラメトリックマップをNumPyファイルとして保存する。"""
        import os
        os.makedirs(output_folder, exist_ok=True)

        np.save(os.path.join(output_folder, 'cbf_map.npy'), maps.cbf)
        np.save(os.path.join(output_folder, 'cbv_map.npy'), maps.cbv)
        np.save(os.path.join(output_folder, 'mtt_map.npy'), maps.mtt)
        np.save(os.path.join(output_folder, 'ttp_map.npy'), maps.ttp)
        np.save(os.path.join(output_folder, 'tmax_map.npy'), maps.tmax)

        print(f"パラメトリックマップを保存しました: {output_folder}")


def plot_parametric_maps(maps, baseline_image=None, save_path=None):
    """パラメトリックマップを可視化する。"""
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 3, figsize=(18, 11))
    fig.suptitle("CT Perfusion Parametric Maps", fontsize=16, fontweight='bold')

    # CBF
    ax = axes[0, 0]
    im = ax.imshow(maps.cbf, cmap='jet', vmin=0, vmax=100)
    plt.colorbar(im, ax=ax, label='ml/100g/min')
    ax.set_title('CBF (Cerebral Blood Flow)')

    # CBV
    ax = axes[0, 1]
    im = ax.imshow(maps.cbv, cmap='jet', vmin=0, vmax=10)
    plt.colorbar(im, ax=ax, label='ml/100g')
    ax.set_title('CBV (Cerebral Blood Volume)')

    # MTT
    ax = axes[0, 2]
    im = ax.imshow(maps.mtt, cmap='jet', vmin=0, vmax=20)
    plt.colorbar(im, ax=ax, label='seconds')
    ax.set_title('MTT (Mean Transit Time)')

    # TTP
    ax = axes[1, 0]
    im = ax.imshow(maps.ttp, cmap='jet')
    plt.colorbar(im, ax=ax, label='seconds')
    ax.set_title('TTP (Time to Peak)')

    # Tmax
    ax = axes[1, 1]
    im = ax.imshow(maps.tmax, cmap='jet')
    plt.colorbar(im, ax=ax, label='seconds')
    ax.set_title('Tmax (Time to Maximum)')

    # ベースライン画像（あれば）
    ax = axes[1, 2]
    if baseline_image is not None:
        ax.imshow(baseline_image, cmap='gray', vmin=0, vmax=100)
        ax.set_title('Baseline Image')
    else:
        ax.axis('off')
        info_text = (
            f"Computation Info:\n"
            f"  Method: {maps.computation_info.get('method', 'N/A')}\n"
            f"  SVD threshold: {maps.computation_info.get('svd_threshold', 'N/A')}\n"
            f"  Processed: {maps.computation_info.get('processed_pixels', 'N/A')} px\n"
            f"  dt: {maps.computation_info.get('dt', 'N/A'):.2f} s"
        )
        ax.text(0.1, 0.5, info_text, transform=ax.transAxes,
               fontsize=11, fontfamily='monospace')
        ax.set_title('Info')

    for ax_row in axes:
        for ax in ax_row:
            ax.tick_params(labelsize=8)

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"パラメトリックマップ画像を保存しました: {save_path}")

    return fig
