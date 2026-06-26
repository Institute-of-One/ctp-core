"""
AIF (Arterial Input Function) 自動検出モジュール
=================================================
CT Perfusionデータから動脈入力関数を自動検出する。

アルゴリズムの基本方針:
-------
Rempp et al. (1994) やMouridsen et al. (2006) の手法を参考に、
以下の特徴を持つボクセルを動脈候補として抽出する:

1. 高いピーク造影値（上位数%）
2. 早い到達時間（Time to Peak が短い）
3. 急峻な立ち上がり（wash-in slope が大きい）
4. 狭いカーブ幅（Full Width at Half Maximum が小さい）

参考文献:
- Rempp KA, et al. "Quantification of regional cerebral blood flow
  and volume with dynamic susceptibility contrast-enhanced MR imaging."
  Radiology. 1994;193(3):637-641.
  → 造影剤の初回通過（first-pass）のモデリングについて:
    "The arterial input function C_a(t) was measured in pixels
     within the middle cerebral artery..."

- Mouridsen K, et al. "Automatic selection of arterial input function
  using cluster analysis." Magnetic Resonance in Medicine. 2006;55(3):524-531.
  → AIF自動選択にクラスタリングを使う手法:
    "Voxels were initially screened using the following criteria:
     (1) peak concentration above a threshold,
     (2) time to peak (TTP) earlier than the mean,
     (3) first moment of the concentration-time curve below the mean."
  → AIFは "early arrival, high peak, narrow width" を特徴とする

- Fieselmann A, et al. "Automatic determination of the arterial input
  function in dynamic CT." Medical Physics. 2011;38(4):2468-2480.
  → CT Perfusion専用のAIF自動検出。閾値ベースのスクリーニング後に
    形状特徴で候補をランク付け:
    "Candidate voxels were selected based on (1) peak enhancement
     > T_peak, (2) TTP within a temporal window, and (3) FWHM
     below a threshold."

使い方:
    from aif_detection import AIFDetector
    detector = AIFDetector(volume_4d, metadata)
    aif_result = detector.detect(slice_index=2)
    print(aif_result.aif_curve)
"""

import numpy as np
from scipy import ndimage
from scipy.signal import find_peaks


class AIFResult:
    """AIF検出結果を保持するクラス。"""

    def __init__(self):
        self.aif_curve = None          # 平均AIFカーブ (n_times,)
        self.aif_enhancement = None    # 造影値カーブ (n_times,)
        self.aif_mask = None           # AIFボクセルマスク (rows, cols)
        self.candidate_mask = None     # 候補ボクセルマスク
        self.n_aif_voxels = 0
        self.aif_center = None         # AIFクラスタの重心 (row, col)
        self.time_seconds = None
        self.detection_info = {}       # 検出パラメータ情報


class AIFDetector:
    """AIF自動検出エンジン。

    検出アルゴリズム（Fieselmann et al. 2011 を参考にCT用に実装）:

    Phase 1: 候補ボクセルのスクリーニング
        - ピーク造影値が閾値以上
        - TTPが全ボクセル中央値以下（早期到達）
        - ベースラインCT値がある範囲内（骨・空気を除外）

    Phase 2: 形状特徴によるランキング
        - FWHM（半値幅）が小さい
        - Wash-in slope（立ち上がり勾配）が大きい
        - ピーク造影値が高い

    Phase 3: クラスタリング
        - 上位候補から空間的に近いボクセルをクラスタリング
        - 最大クラスタの平均をAIFとする
    """

    def __init__(self, volume_4d, metadata):
        self.volume = volume_4d
        self.meta = metadata
        self.n_times = metadata['n_times']
        self.rows = metadata['rows']
        self.cols = metadata['cols']
        self.time_seconds = np.array(metadata['time_seconds'])

    def _compute_enhancement_map(self, slice_data, n_baseline=2):
        """造影値マップを算出する。

        Args:
            slice_data: shape=(n_times, rows, cols)
            n_baseline: ベースラインに使う時相数

        Returns:
            enhancement: shape=(n_times, rows, cols)
            baseline: shape=(rows, cols)
        """
        baseline = np.mean(slice_data[:n_baseline], axis=0)
        enhancement = slice_data - baseline[np.newaxis, :, :]
        return enhancement, baseline

    def _compute_peak_map(self, enhancement):
        """ピーク造影値マップとTTPマップを算出する。

        Returns:
            peak_map: shape=(rows, cols) 最大造影値
            ttp_map: shape=(rows, cols) ピークまでのインデックス
        """
        peak_map = np.max(enhancement, axis=0)
        ttp_map = np.argmax(enhancement, axis=0)
        return peak_map, ttp_map

    def _compute_fwhm_map(self, enhancement):
        """各ピクセルのFWHM（半値幅）をフレーム数で算出する。

        Returns:
            fwhm_map: shape=(rows, cols) 半値幅（時相数単位）
        """
        peak_vals = np.max(enhancement, axis=0)
        half_max = peak_vals / 2.0

        fwhm_map = np.full((self.rows, self.cols), self.n_times, dtype=np.float32)

        for r in range(self.rows):
            for c in range(self.cols):
                if peak_vals[r, c] <= 0:
                    continue
                curve = enhancement[:, r, c]
                above_half = curve >= half_max[r, c]
                if np.any(above_half):
                    indices = np.where(above_half)[0]
                    fwhm_map[r, c] = indices[-1] - indices[0] + 1

        return fwhm_map

    def _compute_fwhm_map_fast(self, enhancement):
        """FWHMの高速版（ベクトル化）。"""
        peak_vals = np.max(enhancement, axis=0)  # (rows, cols)
        half_max = peak_vals / 2.0  # (rows, cols)

        # 各時相で半値以上かどうか
        above_half = enhancement >= half_max[np.newaxis, :, :]  # (n_times, rows, cols)

        # 最初と最後のTrueインデックスを求める
        # 時相軸に沿って累積和を使う
        first_above = np.argmax(above_half, axis=0).astype(np.float32)
        last_above = (self.n_times - 1 - np.argmax(above_half[::-1], axis=0)).astype(np.float32)

        fwhm_map = last_above - first_above + 1
        fwhm_map[peak_vals <= 0] = self.n_times

        return fwhm_map

    def _compute_washin_slope(self, enhancement, ttp_map):
        """Wash-in slope（立ち上がり勾配）マップを算出する。

        ベースラインからピークまでの最大勾配。

        Returns:
            slope_map: shape=(rows, cols)
        """
        dt = np.diff(self.time_seconds)
        if np.all(dt == 0):
            dt = np.ones(self.n_times - 1)

        slope_map = np.zeros((self.rows, self.cols), dtype=np.float32)

        # 時間微分
        d_enhancement = np.diff(enhancement, axis=0)  # (n_times-1, rows, cols)
        for i in range(len(dt)):
            d_enhancement[i] /= max(dt[i], 0.001)

        # ピークまでの最大勾配
        slope_map = np.max(d_enhancement, axis=0)

        return slope_map

    def detect(self, slice_index=None, n_baseline=2,
               peak_percentile=95, ttp_percentile=40,
               baseline_min=-50, baseline_max=80,
               peak_ct_max=500, skull_erosion_px=5,
               n_top_candidates=200, min_cluster_size=3):
        """AIF自動検出を実行する。

        Args:
            slice_index: 対象スライス（Noneなら全スライスから検出）
            n_baseline: ベースライン時相数
            peak_percentile: ピーク造影値の閾値パーセンタイル
            ttp_percentile: TTP閾値パーセンタイル（これ以下を候補）
            baseline_min/max: ベースラインCT値の許容範囲 (HU)
                              脳実質は20-45HU。80HU以上は骨の可能性大。
            peak_ct_max: ピーク時の絶対CT値の上限 (HU)
                         骨は造影後も1000HU前後のまま。動脈は最大300-500HU。
            skull_erosion_px: 高CT値領域（骨）からの除外距離 (ピクセル)
            n_top_candidates: 形状スコア上位の候補数
            min_cluster_size: 最小クラスタサイズ

        Returns:
            AIFResult
        """
        result = AIFResult()
        result.time_seconds = self.time_seconds

        # 対象スライスデータ
        if slice_index is not None:
            slice_data = self.volume[:, slice_index, :, :]
        else:
            slice_data = np.mean(self.volume, axis=1)

        # Phase 1: 基本特徴量の算出
        print("AIF検出 Phase 1: 特徴量算出...")
        enhancement, baseline = self._compute_enhancement_map(slice_data, n_baseline)
        peak_map, ttp_map = self._compute_peak_map(enhancement)

        # Phase 1: スクリーニング（段階的に緩和）
        print("AIF検出 Phase 1: 候補ボクセルのスクリーニング...")

        # 骨領域マスクの生成（全段階で共通使用）
        peak_ct_map = np.max(slice_data, axis=0)
        bone_mask = baseline > 150

        # 段階的に緩和する閾値セット
        # (baseline_max, peak_ct_max, skull_erosion_px, peak_pctl, ttp_pctl)
        relaxation_levels = [
            (baseline_max, peak_ct_max, skull_erosion_px,
             peak_percentile, ttp_percentile),
            (120, 600, 3, peak_percentile, ttp_percentile),
            (150, 800, 2, 90, 50),
            (200, 1000, 1, 85, 60),
            (300, 1500, 0, 80, 70),
        ]

        candidate_mask = None
        n_candidates = 0
        used_level = 0

        for level_idx, (bl_max, pct_max, ero_px, p_pctl, t_pctl) in enumerate(relaxation_levels):
            # 条件1: ピーク造影値が上位
            if np.any(peak_map > 0):
                peak_threshold = np.percentile(peak_map[peak_map > 0], p_pctl)
            else:
                break
            mask_peak = peak_map >= peak_threshold

            # 条件2: TTPが早い
            valid_ttp = ttp_map[peak_map > 0]
            ttp_threshold = np.percentile(valid_ttp, t_pctl)
            mask_ttp = ttp_map <= ttp_threshold

            # 条件3: ベースラインCT値範囲
            mask_baseline = (baseline >= baseline_min) & (baseline <= bl_max)

            # 条件4: ピーク絶対CT値
            mask_peak_ct = peak_ct_map < pct_max

            # 条件5: 骨近傍除外
            if np.any(bone_mask) and ero_px > 0:
                bone_dilated = ndimage.binary_dilation(
                    bone_mask, iterations=ero_px)
                mask_not_near_bone = ~bone_dilated
            else:
                mask_not_near_bone = np.ones_like(baseline, dtype=bool)

            candidate_mask = (mask_peak & mask_ttp & mask_baseline &
                              mask_peak_ct & mask_not_near_bone)
            n_candidates = int(candidate_mask.sum())
            used_level = level_idx

            if n_candidates >= min_cluster_size:
                if level_idx > 0:
                    print(f"  閾値を段階{level_idx}まで緩和 "
                          f"(baseline_max={bl_max}, peak_ct_max={pct_max}, "
                          f"erosion={ero_px}px)")
                break

        result.candidate_mask = candidate_mask
        print(f"  候補ボクセル数: {n_candidates}")

        if n_candidates == 0:
            print("  [WARNING] AIF候補が見つかりません。")
            return result

        # Phase 2: 形状特徴によるランキング
        # (Fieselmann 2011: "FWHM below a threshold" + ranking by shape)
        print("AIF検出 Phase 2: 形状特徴によるランキング...")

        fwhm_map = self._compute_fwhm_map_fast(enhancement)
        slope_map = self._compute_washin_slope(enhancement, ttp_map)

        # 各候補のスコア算出
        # スコア = 正規化(peak) + 正規化(slope) - 正規化(fwhm) - 正規化(ttp)
        candidate_indices = np.where(candidate_mask)
        n_cand = len(candidate_indices[0])

        peaks = peak_map[candidate_indices]
        ttps = ttp_map[candidate_indices].astype(np.float32)
        fwhms = fwhm_map[candidate_indices]
        slopes = slope_map[candidate_indices]

        def normalize(arr):
            rng = arr.max() - arr.min()
            if rng == 0:
                return np.zeros_like(arr)
            return (arr - arr.min()) / rng

        score = (normalize(peaks) +
                 normalize(slopes) -
                 normalize(fwhms) -
                 normalize(ttps))

        # 上位候補を選択
        n_top = min(n_top_candidates, n_cand)
        top_indices = np.argsort(score)[::-1][:n_top]

        top_mask = np.zeros_like(candidate_mask)
        top_rows = candidate_indices[0][top_indices]
        top_cols = candidate_indices[1][top_indices]
        top_mask[top_rows, top_cols] = True

        # Phase 3: 空間クラスタリング
        # (Mouridsen 2006: cluster analysis approach)
        print("AIF検出 Phase 3: 空間クラスタリング...")

        labeled, n_clusters = ndimage.label(top_mask)
        if n_clusters == 0:
            print("  [WARNING] クラスタが形成されませんでした。")
            return result

        # 最大クラスタを選択
        cluster_sizes = ndimage.sum(top_mask, labeled, range(1, n_clusters + 1))
        best_cluster = np.argmax(cluster_sizes) + 1
        best_size = int(cluster_sizes[best_cluster - 1])

        if best_size < min_cluster_size:
            # クラスタが小さすぎる場合、上位スコアのボクセルを直接使用
            print(f"  最大クラスタが小さい({best_size}ボクセル)。"
                  f"上位{min_cluster_size}ボクセルを使用します。")
            aif_mask = np.zeros_like(candidate_mask)
            for i in range(min(min_cluster_size, n_top)):
                aif_mask[top_rows[i], top_cols[i]] = True
        else:
            aif_mask = (labeled == best_cluster)
            print(f"  最大クラスタ: {best_size} ボクセル")

        result.aif_mask = aif_mask
        result.n_aif_voxels = int(aif_mask.sum())

        # AIFクラスタの重心
        aif_indices = np.where(aif_mask)
        result.aif_center = (
            float(np.mean(aif_indices[0])),
            float(np.mean(aif_indices[1]))
        )

        # AIF カーブの算出（マスク内ボクセルの平均）
        aif_curve = np.zeros(self.n_times)
        for t in range(self.n_times):
            aif_curve[t] = np.mean(slice_data[t][aif_mask])

        result.aif_curve = aif_curve
        aif_baseline = np.mean(aif_curve[:n_baseline])
        result.aif_enhancement = aif_curve - aif_baseline

        # 検出情報の保存
        result.detection_info = {
            'slice_index': slice_index,
            'n_baseline': n_baseline,
            'peak_percentile': peak_percentile,
            'peak_threshold': float(peak_threshold),
            'ttp_percentile': ttp_percentile,
            'ttp_threshold': float(ttp_threshold),
            'n_initial_candidates': n_candidates,
            'n_top_candidates': n_top,
            'n_clusters': n_clusters,
            'best_cluster_size': best_size,
            'aif_center': result.aif_center,
            'aif_peak_enhancement': float(np.max(result.aif_enhancement)),
            'aif_ttp': float(self.time_seconds[np.argmax(result.aif_enhancement)]),
        }

        print(f"\nAIF検出完了:")
        print(f"  AIFボクセル数: {result.n_aif_voxels}")
        print(f"  AIF中心位置: ({result.aif_center[0]:.1f}, {result.aif_center[1]:.1f})")
        print(f"  ピーク造影値: {result.detection_info['aif_peak_enhancement']:.1f} HU")
        print(f"  Time to Peak: {result.detection_info['aif_ttp']:.1f} s")

        return result

    def extract_aif_at(self, row, col, slice_index=None,
                       radius=3, n_baseline=2):
        """指定点 (row, col) 周囲の小円領域から手動 AIF を抽出する。

        自動検出が失敗した場合や、ユーザが任意の動脈位置を指定したい場合に、
        クリック点を中心とする半径 ``radius`` の円内ボクセルの平均を AIF とする。
        自動検出 (``detect``) と同一の戻り値構造 (AIFResult) を返すため、
        既存の描画・フィッティング・出力経路をそのまま利用できる。

        Args:
            row, col: 画像座標 (行, 列)。浮動小数でも可 (四捨五入される)。
            slice_index: 対象スライス。None なら全スライス平均。
            radius: 平均する円の半径 (ピクセル)。
            n_baseline: ベースライン時相数。

        Returns:
            AIFResult (aif_curve / aif_enhancement / aif_mask / aif_center 等)
        """
        result = AIFResult()
        result.time_seconds = self.time_seconds

        if slice_index is not None:
            slice_data = self.volume[:, slice_index, :, :]
        else:
            slice_data = np.mean(self.volume, axis=1)

        rr = int(np.clip(round(row), 0, self.rows - 1))
        cc = int(np.clip(round(col), 0, self.cols - 1))
        r = max(int(radius), 0)

        yy, xx = np.ogrid[:self.rows, :self.cols]
        mask = (yy - rr) ** 2 + (xx - cc) ** 2 <= r ** 2
        if not np.any(mask):
            mask[rr, cc] = True

        result.aif_mask = mask
        result.candidate_mask = mask
        result.n_aif_voxels = int(np.count_nonzero(mask))
        result.aif_center = (float(rr), float(cc))

        aif_curve = np.array(
            [float(np.mean(slice_data[t][mask])) for t in range(self.n_times)]
        )
        result.aif_curve = aif_curve
        aif_baseline = float(np.mean(aif_curve[:n_baseline]))
        result.aif_enhancement = aif_curve - aif_baseline

        result.detection_info = {
            'manual': True,
            'slice_index': slice_index,
            'point': (rr, cc),
            'radius': r,
            'n_baseline': n_baseline,
            'aif_center': result.aif_center,
            'aif_peak_enhancement': float(np.max(result.aif_enhancement)),
            'aif_ttp': float(self.time_seconds[np.argmax(result.aif_enhancement)]),
        }
        print(f"[AIF手動] 中心=({rr},{cc}) 半径={r}px "
              f"ボクセル数={result.n_aif_voxels} "
              f"ピーク造影={result.detection_info['aif_peak_enhancement']:.1f}HU")
        return result


def plot_aif_detection(volume_4d, metadata, aif_result, slice_index,
                       save_path=None):
    """AIF検出結果を可視化する。

    4パネル構成:
    1. 左上: 元画像 + AIF位置
    2. 右上: ピーク造影値マップ + 候補ボクセル
    3. 左下: AIF カーブ
    4. 右下: TTPマップ + AIFクラスタ
    """
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("AIF Auto-Detection Result", fontsize=14, fontweight='bold')

    # ベースライン画像
    baseline_img = np.mean(volume_4d[:2, slice_index, :, :], axis=0)

    # --- 左上: 元画像 + AIF位置 ---
    ax = axes[0, 0]
    ax.imshow(baseline_img, cmap='gray', vmin=0, vmax=100)
    if aif_result.aif_mask is not None:
        # AIFマスクを赤でオーバーレイ
        overlay = np.zeros((*aif_result.aif_mask.shape, 4))
        overlay[aif_result.aif_mask, 0] = 1.0
        overlay[aif_result.aif_mask, 3] = 0.5
        ax.imshow(overlay)

        if aif_result.aif_center:
            ax.plot(aif_result.aif_center[1], aif_result.aif_center[0],
                   'r+', markersize=15, markeredgewidth=2)

    ax.set_title("Baseline Image + AIF Location")

    # --- 右上: ピーク造影値マップ ---
    ax = axes[0, 1]
    enhancement = volume_4d[:, slice_index, :, :] - baseline_img[np.newaxis, :, :]
    peak_map = np.max(enhancement, axis=0)
    im = ax.imshow(peak_map, cmap='hot', vmin=0,
                   vmax=np.percentile(peak_map[peak_map > 0], 99))
    plt.colorbar(im, ax=ax, label='Peak Enhancement (HU)')

    if aif_result.candidate_mask is not None:
        # 候補ボクセルを緑点で
        cand_idx = np.where(aif_result.candidate_mask)
        ax.plot(cand_idx[1], cand_idx[0], 'g.', markersize=1, alpha=0.5)

    ax.set_title("Peak Enhancement Map + Candidates")

    # --- 左下: AIF カーブ ---
    ax = axes[1, 0]
    if aif_result.aif_curve is not None:
        ax.plot(aif_result.time_seconds, aif_result.aif_curve,
               'r-o', linewidth=2, markersize=4, label='AIF')
        ax.plot(aif_result.time_seconds, aif_result.aif_enhancement,
               'b--', linewidth=1, alpha=0.7, label='Enhancement')
        ax.set_xlabel('Time (s)')
        ax.set_ylabel('CT Value (HU)')
        ax.legend()
        ax.grid(True, alpha=0.3)
    ax.set_title("Detected AIF Curve")

    # --- 右下: TTPマップ ---
    ax = axes[1, 1]
    ttp_map = np.argmax(enhancement, axis=0).astype(np.float32)
    ttp_map[peak_map <= 10] = np.nan  # 造影なし領域はマスク
    im = ax.imshow(ttp_map, cmap='jet')
    plt.colorbar(im, ax=ax, label='Time to Peak (phase)')

    if aif_result.aif_mask is not None:
        aif_idx = np.where(aif_result.aif_mask)
        ax.plot(aif_idx[1], aif_idx[0], 'w+', markersize=3)

    ax.set_title("TTP Map + AIF Cluster")

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"AIF検出結果を保存しました: {save_path}")

    return fig
