# ASIST-Japan 標準灌流カラーマッピング (a-LUT)

CTP Analyzer / IORN-001 における灌流マップの標準化可視化の実装ドキュメント。
本ドキュメントは IORN-001 の **Methods** セクションへ転載可能な記述を含む。

---

## 1. 背景と目的

灌流画像 (CTP/MRP) のカラースケール (Lookup Table; LUT) は装置・施設ごとに
異なり、同一の量的データであっても表示色が大きく異なる。これは読影者間・
施設間の比較可能性を損ない、再現性のある研究・報告の妨げとなる。

**ASIST-Japan** (Acute Stroke Imaging Standardization Group Japan,
急性期脳卒中画像診断標準化委員会) は「CT/MR 灌流画像実践ガイドライン2006」
において表示方法の標準化を推奨し、標準ルックアップテーブル **a-LUT** を
256 階調の RGB テーブルとして公開している。

IORN-001 は透明性と再現性のある CT 灌流パイプラインを目指しており、
標準化された可視化はその再現性の一部を構成する。本実装は ASIST-Japan の
推奨に明示的に準拠する。

### 出典 / References

- ASIST-Japan: <https://asist.umin.jp/>
- 標準 LUT (CSV): <https://asist.umin.jp/data/alut.csv>
- CT/MR 灌流画像実践ガイドライン2006:
  <https://asist.umin.jp/data/guidelineCtpMrp2006.pdf>

同梱資産 (`assets/`):

| ファイル | 内容 |
|---|---|
| `alut.csv` | a-LUT 本体 (`Index,R,G,B`; 256 行) ― 本実装が読み込む正準ソース |
| `alut.tif` | a-LUT の TIFF 表現 (参照用) |
| `ASIST.lut` | ImageJ 等向け LUT バイナリ (参照用) |
| `alut-horizontal.gif` | ASIST 公開の横方向カラーバー (慣例確認用) |

---

## 2. a-LUT の配色

a-LUT は低値→高値で次のように遷移する 256 階調 RGB テーブルである:

```
黒 → 紫 → 青 → シアン → 緑 → 黄 → 橙 → 赤
index 0 = (0,0,0) 黒      index 255 = (255,0,0) 赤
```

慣例として **高値 = 赤、低値 = 青/黒** で符号化される。急性期脳卒中では
CBF/CBV の低下領域 (虚血コア)、MTT/TTP/Tmax の延長領域が直感的に
識別できる。

---

## 3. 設計方針 (重要)

1. **量的体素値は一切変更しない。** LUT は *可視化のみ* に作用する。
   `apply_a_lut()` は常に新しい RGB 配列を返し、入力スカラー配列を破壊しない
   (ユニットテスト `test_apply_a_lut_does_not_mutate_input` で保証)。
   量的値は別途 `.npy` 等で保持し、PNG には保存しない。
2. **決定論的 (deterministic)。** 固定スカラー値・固定表示窓に対し RGB 出力は
   bit-exact に再現可能 (`test_apply_a_lut_deterministic`,
   `test_scalar_to_index_deterministic`)。乱数を一切使用しない。
3. **LUT 切り替え可能。** `grayscale` / `asist` (標準) / `custom` (研究用任意 CSV)。
4. **マスク外/無効体素** (NaN, Inf, mask=False) は背景色 (既定: 黒) に割り当てる。

---

## 4. 表示窓 (vmin/vmax)

各灌流パラメータの標準表示レンジ。これは **表示窓** であり量的値には影響しない。
急性期脳卒中で慣用される範囲及び ASIST ガイドラインに準拠する。

| map_type | ラベル | 単位 | vmin | vmax |
|---|---|---|---|---|
| `cbf` | Cerebral Blood Flow | mL/100g/min | 0 | 80 |
| `cbv` | Cerebral Blood Volume | mL/100g | 0 | 8 |
| `mtt` | Mean Transit Time | s | 0 | 12 |
| `ttp` | Time To Peak | s | 0 | 25 |
| `tmax`| Time to Max of residue | s | 0 | 14 |

表示窓の解決優先順位: **明示指定 (vmin/vmax) > プリセット (map_type) > データ実測 (min/max)**。

---

## 5. アルゴリズム

スカラーマップ `data` から RGB 画像への変換:

1. 表示窓 `(vmin, vmax)` を解決する (§4)。
2. 正規化: `norm = clip((data - vmin) / (vmax - vmin), 0, 1)`。
   `vmax <= vmin` の異常入力ではゼロ除算せず全 0。
3. インデックス化: `idx = round(norm * 255)` ∈ [0, 255]（最近傍・四捨五入）。
4. 直引き: `rgb = LUT[idx]`。
5. 無効体素 (NaN/Inf/mask=False) を背景色で上書き。

> 中央値の例: `data=40, vmin=0, vmax=80` → `norm=0.5` → `idx=round(127.5)=128`。
> 端点: `data=0 → idx 0`、`data=80 → idx 255`。

---

## 6. API

モジュール: [`a_lut.py`](a_lut.py)

```python
from ctp_core.a_lut import (
    load_a_lut,            # (256,3) uint8 LUT を取得
    apply_a_lut,           # スカラーマップ -> (H,W,3) uint8 RGB
    export_png_with_a_lut, # 生 RGB PNG を書き出し (軸/余白なし)
    export_colorbar,       # 目盛・ラベル付きカラーバー PNG
    make_colorbar_strip,   # カラーバー画像 (H,W,3) を生成
    to_mpl_colormap,       # matplotlib ListedColormap へ変換 (既存 imshow 連携用)
    MAP_PRESETS,           # 表示窓プリセット
)

# 例: CBF マップを ASIST 標準配色で PNG 化 (量的値は不変)
rgb = apply_a_lut(cbf_map, map_type="cbf")                 # ASIST 標準
export_png_with_a_lut(cbf_map, "cbf.png", map_type="cbf")
export_colorbar("cbf_bar.png", map_type="cbf")

# LUT 切り替え
rgb_gray   = apply_a_lut(cbf_map, map_type="cbf", lut="grayscale")
rgb_custom = apply_a_lut(cbf_map, map_type="cbf", lut="custom",
                         custom_lut_path="my_research_lut.csv")

# 既存の matplotlib imshow への組み込み
import matplotlib.pyplot as plt
cmap = to_mpl_colormap("asist")
plt.imshow(cbf_map, cmap=cmap, vmin=0, vmax=80)
```

---

## 7. 検証図 (Validation figures)

生成スクリプト: [`make_a_lut_figures.py`](make_a_lut_figures.py)

```bash
python make_a_lut_figures.py            # 全 5 種別 (cbf/cbv/mtt/ttp/tmax)
python make_a_lut_figures.py cbf cbv    # 指定種別のみ
```

出力先 `output/figures/a_lut/`。各 `map_type` につき以下 5 種:

| 接尾辞 | 内容 |
|---|---|
| `_grayscale.png` | グレースケールマップ |
| `_asist.png`     | ASIST a-LUT マップ |
| `_histogram.png` | 量的値分布 + 表示窓 (vmin/vmax) |
| `_colorbar.png`  | ASIST 慣例カラーバー |
| `_comparison.png`| grayscale ↔ ASIST 並置 + カラーバー |

入力データは `output/maps/<map_type>.npy` があれば実データを、無ければ
決定論的合成ファントム (中央に虚血コア・頭蓋外マスク) を使用する。

---

## 8. ユニットテスト

テスト: [`test_a_lut.py`](test_a_lut.py) （全 29 件）

```bash
python -m pytest test_a_lut.py -v   # pytest 環境
python test_a_lut.py                # pytest 不在でも簡易ランナーで実行可
```

主な検証項目:

- 固定スカラー値に対する決定論的 RGB 出力 (要件 9)
- 量的体素値の不変性 (要件 5)
- LUT 切り替え (grayscale/asist/custom, 要件 4)
- 表示窓の解決順位と境界・異常入力 (ゼロ除算回避・クリップ)
- LUT 端点 (黒/赤)・カラーバー方向・matplotlib 連携

---

## 9. IORN-001 Methods 記述例

> **Perfusion map visualization.**
> Parametric perfusion maps (CBF, CBV, MTT, TTP, and Tmax) were rendered using
> the standardized lookup table (a-LUT) published by the Acute Stroke Imaging
> Standardization Group Japan (ASIST-Japan; CT/MR Perfusion Imaging Practical
> Guideline 2006). The a-LUT is a 256-level RGB table mapping low-to-high values
> from black through blue/cyan/green/yellow to red. Scalar maps were linearly
> windowed to standard display ranges (CBF 0–80 mL/100 g/min, CBV 0–8 mL/100 g,
> MTT 0–12 s, TTP 0–25 s, Tmax 0–14 s), normalized, and indexed into the a-LUT.
> Color mapping affects visualization only; quantitative voxel values were
> preserved unchanged and stored separately. The implementation is deterministic:
> identical scalar values yield bit-exact RGB output, verified by unit tests.
> Grayscale and custom research LUTs are also supported for comparison.

---

## 10. ファイル一覧

| パス | 役割 |
|---|---|
| [`a_lut.py`](a_lut.py) | a-LUT モジュール本体 |
| [`test_a_lut.py`](test_a_lut.py) | ユニットテスト (29 件) |
| [`make_a_lut_figures.py`](make_a_lut_figures.py) | 検証図ジェネレータ |
| `assets/alut.csv` | ASIST 標準 a-LUT (正準ソース) |
| `assets/alut.tif`, `assets/ASIST.lut`, `assets/alut-horizontal.gif` | 参照用資産 |
| `output/figures/a_lut/` | 生成された検証図・スクリーンショット |
