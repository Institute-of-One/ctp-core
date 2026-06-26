# -*- coding: utf-8 -*-
"""
ASIST-Japan 標準灌流カラーマッピング モジュール (a-LUT)
=========================================================

ASIST-Japan (Acute Stroke Imaging Standardization Group Japan,
急性期脳卒中画像診断標準化委員会) が公開している標準ルックアップテーブル
(a-LUT) を用いて、CTP / MRP の灌流マップを標準化された配色で可視化する。

背景:
-----
灌流画像のカラースケール (LUT) は装置・施設ごとに異なり、同一データでも
見え方が大きく異なる。ASIST-Japan の「CT/MR 灌流画像実践ガイドライン2006」
では表示方法の標準化が望まれると明記され、標準 LUT (a-LUT) が
256 階調の RGB テーブルとして公開されている。

    出典: ASIST-Japan  https://asist.umin.jp/  (data/alut.csv)
          CT/MR 灌流画像実践ガイドライン2006
          https://asist.umin.jp/data/guidelineCtpMrp2006.pdf

a-LUT の配色 (低値→高値):
    黒 → 紫 → 青 → シアン → 緑 → 黄 → 橙 → 赤
    (index 0 = 黒(0,0,0)、index 255 = 赤(255,0,0))
慣例として高値=赤、低値=青/黒で符号化される。

設計方針:
--------
- 量的体素値 (voxel value) は一切変更しない。LUT は **可視化のみ** に作用する。
  apply_a_lut() は常に新しい RGB 配列を返し、入力スカラー配列を破壊しない。
- 固定スカラー値に対し RGB 出力は決定論的 (deterministic) である。
- grayscale / ASIST 標準 / 任意の研究用 LUT を切り替え可能。

主要 API:
--------
    load_a_lut(name='asist')        -> (256, 3) uint8 の LUT を取得
    apply_a_lut(data, ...)          -> スカラーマップを (H, W, 3) uint8 RGB へ
    export_png_with_a_lut(data, ..) -> RGB PNG を書き出し
    export_colorbar(...)            -> ASIST 慣例のカラーバー PNG を書き出し

使い方:
    from a_lut import apply_a_lut, export_png_with_a_lut, MAP_PRESETS
    rgb = apply_a_lut(cbf_map, map_type='cbf')          # ASIST 標準
    export_png_with_a_lut(cbf_map, 'cbf.png', map_type='cbf')
"""

from __future__ import annotations

import os
import csv
import numpy as np

# ---------------------------------------------------------------------------
# 定数・設定
# ---------------------------------------------------------------------------

#: a-LUT の階調数 (ASIST 標準は 256)
LUT_SIZE = 256

def _resolve_default_alut_csv() -> str:
    """同梱された標準 a-LUT CSV の絶対パスを解決する。

    パッケージ化 (pip install / wheel) されても確実に読めるよう、まず
    importlib.resources でパッケージ同梱リソース (ctp_core/assets/alut.csv)
    を探し、見つからなければ本ファイル基準の相対パスにフォールバックする。
    いずれも量的値には作用せず、配色テーブルの所在を返すのみ。
    """
    # 1) パッケージ同梱リソース (インストール済みでも堅牢)
    try:
        from importlib.resources import files
        res = files("ctp_core").joinpath("assets", "alut.csv")
        if res.is_file():
            return str(res)
    except Exception:
        pass
    # 2) フォールバック: 本モジュールと同階層の assets/alut.csv (ソース配置)
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "assets", "alut.csv"
    )


#: 既定の a-LUT CSV 配置場所 (パッケージ同梱 ctp_core/assets/alut.csv)
_DEFAULT_ALUT_CSV = _resolve_default_alut_csv()

#: マスク外/無効体素 (NaN, mask=False) に割り当てる背景色 RGB
BACKGROUND_RGB = (0, 0, 0)

#: 利用可能な LUT モード
LUT_MODES = ("grayscale", "asist", "custom")


#: 各灌流パラメータの標準表示設定。
#: vmin/vmax は ASIST ガイドライン及び急性期脳卒中で慣用される表示レンジに準拠。
#: これらは「表示窓」であり、量的値そのものには影響しない。
MAP_PRESETS = {
    "cbf": {
        "label": "CBF (Cerebral Blood Flow)",
        "unit": "mL/100g/min",
        "vmin": 0.0,
        "vmax": 80.0,
    },
    "cbv": {
        "label": "CBV (Cerebral Blood Volume)",
        "unit": "mL/100g",
        "vmin": 0.0,
        "vmax": 8.0,
    },
    "mtt": {
        "label": "MTT (Mean Transit Time)",
        "unit": "s",
        "vmin": 0.0,
        "vmax": 12.0,
    },
    "ttp": {
        "label": "TTP (Time To Peak)",
        "unit": "s",
        "vmin": 0.0,
        "vmax": 25.0,
    },
    # Tmax は将来対応 (現状パイプラインでも算出済み)。
    "tmax": {
        "label": "Tmax (Time to Max of residue)",
        "unit": "s",
        "vmin": 0.0,
        "vmax": 14.0,
    },
}


# ---------------------------------------------------------------------------
# LUT 読み込み
# ---------------------------------------------------------------------------

# プロセス内キャッシュ (同一 LUT の再読込を避ける)
_LUT_CACHE: dict = {}


def _load_alut_csv(path: str) -> np.ndarray:
    """ASIST a-LUT CSV (Index,R,G,B; 256 行) を (256, 3) uint8 で読み込む。"""
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"ASIST a-LUT CSV が見つかりません: {path}\n"
            f"https://asist.umin.jp/data/alut.csv から取得し assets/ に配置してください。"
        )

    rows = []
    with open(path, "r", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        # ヘッダ行が数値なら（ヘッダ無し CSV の場合）データとして扱う
        if header is not None and _looks_numeric(header):
            rows.append([int(float(x)) for x in header[1:4]])
        for row in reader:
            if len(row) < 4 or not row[0].strip():
                continue
            rows.append([int(float(row[1])), int(float(row[2])), int(float(row[3]))])

    lut = np.asarray(rows, dtype=np.uint8)
    if lut.shape != (LUT_SIZE, 3):
        raise ValueError(
            f"a-LUT の形状が不正です: {lut.shape} (期待値: ({LUT_SIZE}, 3))"
        )
    return lut


def _looks_numeric(row) -> bool:
    try:
        [float(x) for x in row[:4]]
        return True
    except (ValueError, IndexError):
        return False


def _grayscale_lut() -> np.ndarray:
    """0→255 の線形グレースケール LUT (256, 3)。"""
    ramp = np.arange(LUT_SIZE, dtype=np.uint8)
    return np.stack([ramp, ramp, ramp], axis=1)


def load_a_lut(name: str = "asist", path: str | None = None) -> np.ndarray:
    """LUT を (256, 3) uint8 配列として取得する。

    Args:
        name: 'asist'  -> ASIST-Japan 標準 a-LUT (assets/alut.csv)
              'grayscale' -> 線形グレースケール
              'custom'  -> ``path`` で指定した CSV を読み込む
        path: name='asist'/'custom' のとき CSV パスを上書き指定。
              'asist' で None の場合は既定の assets/alut.csv を使用。

    Returns:
        (256, 3) uint8 の RGB LUT。

    Note:
        量的値には作用しない。本関数は配色テーブルを返すのみ。
    """
    name = name.lower()
    cache_key = (name, path)
    if cache_key in _LUT_CACHE:
        return _LUT_CACHE[cache_key].copy()

    if name == "grayscale":
        lut = _grayscale_lut()
    elif name == "asist":
        lut = _load_alut_csv(path or _DEFAULT_ALUT_CSV)
    elif name == "custom":
        if not path:
            raise ValueError("name='custom' には path (CSV) の指定が必要です。")
        lut = _load_alut_csv(path)
    else:
        raise ValueError(
            f"未知の LUT 名: {name!r} (有効値: {LUT_MODES})"
        )

    _LUT_CACHE[cache_key] = lut
    return lut.copy()


# ---------------------------------------------------------------------------
# LUT 適用 (スカラー -> RGB)
# ---------------------------------------------------------------------------

def scalar_to_index(
    data: np.ndarray, vmin: float, vmax: float
) -> np.ndarray:
    """スカラー値を [vmin, vmax] で正規化し 0..255 の LUT インデックスへ。

    決定論的: 同一 (value, vmin, vmax) は常に同一インデックスを返す。
    vmax<=vmin の異常入力でもゼロ除算せず全 0 を返す。
    """
    data = np.asarray(data, dtype=np.float64)
    span = float(vmax) - float(vmin)
    if span <= 0:
        norm = np.zeros_like(data)
    else:
        norm = (data - float(vmin)) / span
    norm = np.clip(norm, 0.0, 1.0)
    idx = np.round(norm * (LUT_SIZE - 1)).astype(np.int64)
    return np.clip(idx, 0, LUT_SIZE - 1)


def apply_a_lut(
    data: np.ndarray,
    map_type: str | None = None,
    lut: str | np.ndarray = "asist",
    vmin: float | None = None,
    vmax: float | None = None,
    mask: np.ndarray | None = None,
    custom_lut_path: str | None = None,
) -> np.ndarray:
    """スカラーマップに LUT を適用し RGB 画像 (H, W, 3) uint8 を返す。

    **量的体素値は変更されない。** 入力 ``data`` は読み取り専用に扱われ、
    新規 RGB 配列が生成される。

    Args:
        data: 2 次元のスカラーマップ (例: CBF マップ)。
        map_type: 'cbf'/'cbv'/'mtt'/'ttp'/'tmax'。vmin/vmax 未指定時に
                  MAP_PRESETS の標準レンジを使用する。
        lut: LUT モード名 ('asist'/'grayscale'/'custom') または
             (256,3) の LUT 配列を直接指定。
        vmin, vmax: 表示窓の下限/上限。None なら map_type のプリセット、
                    それも無ければ data の有限値の min/max。
        mask: True の体素のみ着色。False/NaN は BACKGROUND_RGB。
        custom_lut_path: lut='custom' のときの CSV パス。

    Returns:
        (H, W, 3) uint8 の RGB 画像。
    """
    data = np.asarray(data, dtype=np.float64)
    if data.ndim != 2:
        raise ValueError(f"data は 2 次元である必要があります: shape={data.shape}")

    # LUT の解決
    if isinstance(lut, np.ndarray):
        table = lut
        if table.shape != (LUT_SIZE, 3):
            raise ValueError(f"LUT 配列形状が不正: {table.shape}")
        table = table.astype(np.uint8)
    else:
        table = load_a_lut(lut, path=custom_lut_path)

    # 表示レンジの解決
    vmin, vmax = resolve_range(data, map_type, vmin, vmax, mask)

    # 有効体素マスク (NaN/Inf を除外し、mask があれば AND)
    valid = np.isfinite(data)
    if mask is not None:
        valid = valid & np.asarray(mask, dtype=bool)

    # 正規化とインデックス化 (NaN は 0 埋めしてからインデックス化)
    safe = np.where(valid, data, vmin)
    idx = scalar_to_index(safe, vmin, vmax)

    rgb = table[idx]  # (H, W, 3)

    # 無効体素を背景色に
    rgb = rgb.copy()
    rgb[~valid] = np.array(BACKGROUND_RGB, dtype=np.uint8)
    return rgb


def resolve_range(data, map_type, vmin, vmax, mask=None):
    """vmin/vmax を確定する。優先順位: 明示指定 > プリセット > データ実測。"""
    preset = MAP_PRESETS.get(map_type.lower()) if map_type else None
    if vmin is None:
        vmin = preset["vmin"] if preset else None
    if vmax is None:
        vmax = preset["vmax"] if preset else None

    if vmin is None or vmax is None:
        finite = np.asarray(data, dtype=np.float64)
        valid = np.isfinite(finite)
        if mask is not None:
            valid = valid & np.asarray(mask, dtype=bool)
        vals = finite[valid]
        if vals.size == 0:
            data_min, data_max = 0.0, 1.0
        else:
            data_min, data_max = float(np.min(vals)), float(np.max(vals))
        if vmin is None:
            vmin = data_min
        if vmax is None:
            vmax = data_max if data_max > vmin else vmin + 1.0
    return float(vmin), float(vmax)


# ---------------------------------------------------------------------------
# matplotlib Colormap への変換 (既存可視化コードとの連携用)
# ---------------------------------------------------------------------------

def to_mpl_colormap(lut: str | np.ndarray = "asist", name: str = "asist"):
    """LUT を matplotlib の ListedColormap に変換する。

    既存の imshow(cmap=...) ベースのコードへ最小変更で組み込めるようにする。
    """
    from matplotlib.colors import ListedColormap

    table = lut if isinstance(lut, np.ndarray) else load_a_lut(lut)
    return ListedColormap(table.astype(np.float64) / 255.0, name=name)


# ---------------------------------------------------------------------------
# PNG 書き出し
# ---------------------------------------------------------------------------

def _save_rgb_png(rgb: np.ndarray, path: str) -> None:
    """(H, W, 3) uint8 RGB を PNG として保存 (PIL があれば優先、無ければ matplotlib)。"""
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    try:
        from PIL import Image
        Image.fromarray(rgb.astype(np.uint8), mode="RGB").save(path)
    except ImportError:
        import matplotlib.image as mpimg
        mpimg.imsave(path, rgb.astype(np.uint8))


def export_png_with_a_lut(
    data: np.ndarray,
    path: str,
    map_type: str | None = None,
    lut: str | np.ndarray = "asist",
    vmin: float | None = None,
    vmax: float | None = None,
    mask: np.ndarray | None = None,
    custom_lut_path: str | None = None,
) -> np.ndarray:
    """スカラーマップに LUT を適用し、生 RGB PNG (軸・余白なし) を書き出す。

    量的値は保存しない (可視化専用)。量的値は別途 .npy 等で保持すること。

    Returns:
        書き出した (H, W, 3) uint8 RGB 配列。
    """
    rgb = apply_a_lut(
        data, map_type=map_type, lut=lut, vmin=vmin, vmax=vmax,
        mask=mask, custom_lut_path=custom_lut_path,
    )
    _save_rgb_png(rgb, path)
    return rgb


# ---------------------------------------------------------------------------
# カラーバー (ASIST 慣例: 横方向グラデーション + 目盛)
# ---------------------------------------------------------------------------

def make_colorbar_strip(
    lut: str | np.ndarray = "asist",
    orientation: str = "horizontal",
    length: int = 256,
    thickness: int = 32,
) -> np.ndarray:
    """LUT の連続カラーバー画像 (H, W, 3) uint8 を生成する。

    ASIST 公開の alut-horizontal.gif に倣い、既定は横方向 (低値=左→高値=右)。
    """
    table = lut if isinstance(lut, np.ndarray) else load_a_lut(lut)
    idx = scalar_to_index(np.linspace(0, 1, length), 0.0, 1.0)
    line = table[idx]  # (length, 3)

    if orientation == "horizontal":
        strip = np.broadcast_to(line[np.newaxis, :, :], (thickness, length, 3))
    elif orientation == "vertical":
        # 縦方向は下=低値, 上=高値
        line = line[::-1]
        strip = np.broadcast_to(line[:, np.newaxis, :], (length, thickness, 3))
    else:
        raise ValueError("orientation は 'horizontal' か 'vertical'")
    return np.ascontiguousarray(strip, dtype=np.uint8)


def export_colorbar(
    path: str,
    map_type: str | None = None,
    lut: str | np.ndarray = "asist",
    vmin: float | None = None,
    vmax: float | None = None,
    orientation: str = "horizontal",
    label: str | None = None,
    unit: str | None = None,
) -> None:
    """目盛・ラベル付きのカラーバー図を PNG 保存する (ASIST 慣例準拠)。"""
    import matplotlib
    matplotlib.use("Agg", force=False)
    import matplotlib.pyplot as plt

    preset = MAP_PRESETS.get(map_type.lower()) if map_type else None
    if vmin is None:
        vmin = preset["vmin"] if preset else 0.0
    if vmax is None:
        vmax = preset["vmax"] if preset else 1.0
    if label is None:
        label = preset["label"] if preset else (map_type or "")
    if unit is None:
        unit = preset["unit"] if preset else ""

    strip = make_colorbar_strip(lut, orientation=orientation)

    if orientation == "horizontal":
        fig, ax = plt.subplots(figsize=(6, 1.4))
        ax.imshow(strip, extent=[vmin, vmax, 0, 1], aspect="auto")
        ax.set_yticks([])
        ax.set_xlabel(f"{label}  [{unit}]" if unit else label)
    else:
        fig, ax = plt.subplots(figsize=(1.8, 6))
        ax.imshow(strip, extent=[0, 1, vmin, vmax], aspect="auto")
        ax.set_xticks([])
        ax.set_ylabel(f"{label}  [{unit}]" if unit else label)

    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
