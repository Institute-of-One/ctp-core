"""The manuscript's figures, drawn from the files in ``paper/results/``.

    python paper/make_figures.py            # all of them
    python paper/make_figures.py --only 2   # one, while working on it

Writes ``paper/figures/figure_N_*.png`` and ``paper/figures/captions.json``.

Three rules this file exists to keep.

**No number is typed here.** Every value in a figure or a caption is read from a results file,
so a figure cannot disagree with the text. Where a caption needs a number it is formatted from
the same value the figure plots.

**The caption and its alt text are written together.** The British Journal of Radiology requires
alt text under every legend, prefixed ``Alt text:``. Generating it beside the caption is the only
arrangement in which the two cannot drift apart -- and a figure whose caption changed while its
alt text did not is a returned manuscript.

**The resolution is set here, not by hand.** BJR asks for 600-900 dpi for combination half-tone
and line art, and 1200 for pure line art; these are combinations except Figure 1. IORN-005 was
prepared at 300 and that was wrong for this journal.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "analysis"))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, Rectangle  # noqa: E402

RESULTS = os.path.join(HERE, "results")
FIGURES = os.path.join(HERE, "figures")

#: BJR's requirement for the article type: 600-900 dpi for combination half-tone and line art,
#: 1200 for monochrome line art.
DPI_COMBINATION = 600
DPI_LINE_ART = 1200

#: One typeface and one size throughout, so the figures look like one paper.
plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 7,
    "axes.labelsize": 7,
    "axes.titlesize": 7.5,
    "legend.fontsize": 6.5,
    "xtick.labelsize": 6.5,
    "ytick.labelsize": 6.5,
    "axes.linewidth": 0.6,
    "xtick.major.width": 0.6,
    "ytick.major.width": 0.6,
    "lines.linewidth": 1.0,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.02,
})

#: Single-column and double-column widths in inches, from the journal's layout.
ONE_COLUMN, TWO_COLUMN = 3.35, 6.9


def load(name: str):
    with open(os.path.join(RESULTS, name), encoding="utf-8") as handle:
        return json.load(handle)


def save(figure, number: int, slug: str, *, dpi: int, caption: str, alt: str) -> dict:
    os.makedirs(FIGURES, exist_ok=True)
    name = f"figure_{number}_{slug}.png"
    path = os.path.join(FIGURES, name)
    figure.savefig(path, dpi=dpi)
    plt.close(figure)
    size = os.path.getsize(path)
    print(f"  wrote {name} at {dpi} dpi, {size / 1024:.0f} KB")
    return {"number": number, "file": name, "dpi": dpi,
            "caption": " ".join(caption.split()),
            "alt_text": " ".join(alt.split())}


# --------------------------------------------------------------------------------------------
# Figure 1: the design. Line art, no data.
# --------------------------------------------------------------------------------------------

def figure_design() -> dict:
    figure, axes = plt.subplots(figsize=(TWO_COLUMN, 2.5))
    axes.set_axis_off()
    # A margin, or the outer boxes are clipped by the canvas edge.
    axes.set_xlim(-1.5, 101.5)
    axes.set_ylim(-1, 45)

    def box(x, y, w, h, text, *, bold=False, fill="white"):
        axes.add_patch(Rectangle((x, y), w, h, facecolor=fill, edgecolor="black",
                                 linewidth=0.7))
        axes.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=6.6,
                  fontweight="bold" if bold else "normal", linespacing=1.35)

    def arrow(x1, y1, x2, y2):
        axes.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>",
                                       mutation_scale=7, linewidth=0.7, color="black",
                                       shrinkA=0, shrinkB=0))

    box(0, 30, 22, 11, "Synthetic curves\nanalytic truth", bold=True, fill="0.94")
    box(0, 4, 22, 11, "UniToBrain\n15 public cases", bold=True, fill="0.94")

    box(30, 24, 26, 17,
        "F1  curve model\nfitted vs fit-free\n\nF4  noise\nSNR 5 to 40")
    box(30, 1, 26, 17,
        "F1  curve model\nF2  smoothing\nnone vs 3 mm\n\nF3  arterial input\nautomatic vs shipped")

    box(64, 30, 36, 11,
        "bias and spread against\nthe analytic peak time", fill="0.98")
    box(64, 16, 36, 11,
        "hemispheric difference against\nthe dataset's reference maps", fill="0.98")
    box(64, 2, 36, 11,
        "arterial area ratio, and\nwhere the maps saturate", fill="0.98")

    arrow(22, 35.5, 30, 33)
    arrow(22, 9.5, 30, 9.5)
    arrow(56, 32.5, 64, 35.5)
    arrow(56, 12, 64, 21.5)
    arrow(56, 7, 64, 7.5)

    axes.text(50, 42.6, "Two arms, four factors, three outcomes",
              ha="center", va="bottom", fontsize=7.5)

    caption = """
        Figure 1. The design. Each factor is varied with the others held at a reference level,
        on synthetic curves whose peak time is known analytically and on fifteen public
        clinical acquisitions. The synthetic arm gives bias and spread against truth; the
        clinical arm gives agreement with the reference maps the dataset ships, and the size
        of the error the automatic arterial input introduces. Levels and admission rules were
        fixed before any measurement and are recorded with their amendments in the protocol
        accompanying the code.
    """
    alt = """
        A flow diagram in three columns. On the left, two inputs: synthetic curves with
        analytic truth, and the UniToBrain set of fifteen public cases. In the middle, the
        factors applied to each: curve model and noise level for the synthetic arm; curve
        model, spatial smoothing and arterial input for the clinical arm. On the right, three
        outcomes: bias and spread against the analytic peak time, hemispheric difference
        against the dataset's reference maps, and the arterial area ratio with the point at
        which the maps saturate. Arrows run from inputs through factors to outcomes.
    """
    return save(figure, 1, "design", dpi=DPI_LINE_ART, caption=caption, alt=alt)


# --------------------------------------------------------------------------------------------
# Figure 2: the quantisation floor. This is the figure that carries the decision.
# --------------------------------------------------------------------------------------------

def figure_floor() -> dict:
    """The quantisation floor, and the condition under which it binds.

    The first version of this figure carried a caption saying the fit-free spread "meets the
    floor and does not go below it" and that raising the signal "does not move it". Looking at
    the drawn figure showed that is only true at coarse sampling. At 0.50 s the fit-free spread
    is nearly three times the floor and doubling the signal improves it by a third; at 2.81 s
    it sits on the floor and doubling the signal buys three percent. That conditional statement
    is the result, and it is what the third panel now measures directly.
    """
    records = load("synthetic_f1_f4.json")
    intervals = sorted({r["dt"] for r in records})
    noises = sorted({r["snr"] for r in records})

    def cell(dt, snr, method):
        return next(r for r in records
                    if r["dt"] == dt and r["snr"] == snr and r["method"] == method)

    figure, (left, right, gain) = plt.subplots(1, 3, figsize=(TWO_COLUMN, 2.4),
                                               layout="constrained")

    grid = np.linspace(min(intervals) * 0.9, max(intervals) * 1.05, 200)
    greys = np.linspace(0.75, 0.0, len(noises))

    for axis, method, marker, title in (
            (left, "sampled", "o", "Fit-free path"),
            (right, "fitted", "s", "Fitted path")):
        axis.plot(grid, grid / np.sqrt(12), color="black", linewidth=1.2, zorder=1,
                  label=r"$\Delta t/\sqrt{12}$")
        for shade, snr in zip(greys, noises):
            axis.plot(intervals, [cell(dt, snr, method)["sd"] for dt in intervals],
                      marker=marker, markersize=3, linewidth=0.9, color=str(shade), zorder=2,
                      label=f"SNR {snr:.0f}")
        axis.set_xlabel("sampling interval (s)")
        axis.set_title(title)
        axis.legend(frameon=False, loc="upper left", handlelength=1.6)
    left.set_ylabel("standard deviation of the recovered\ntime to peak (s)")

    top = max(r["sd"] for r in records) * 1.08
    for axis in (left, right):
        axis.set_ylim(0, top)
        axis.set_xlim(grid[0], grid[-1])
        axis.spines[["top", "right"]].set_visible(False)
        for clinical in (0.5, 2.81):
            axis.axvline(clinical, color="0.8", linewidth=0.6, linestyle=(0, (1, 2)),
                         zorder=0)

    # What doubling the signal buys each path: the decision the figure exists for.
    improvement = {}
    for method, marker, shade, label in (("sampled", "o", "0.0", "fit-free"),
                                         ("fitted", "s", "0.55", "fitted")):
        values = [100 * (1 - cell(dt, 40.0, method)["sd"] / cell(dt, 20.0, method)["sd"])
                  for dt in intervals]
        improvement[method] = values
        gain.plot(intervals, values, marker=marker, markersize=3, linewidth=0.9,
                  color=shade, label=label)
    gain.axhline(0, color="0.7", linewidth=0.6)
    gain.set_xlabel("sampling interval (s)")
    gain.set_ylabel("improvement from doubling\nthe signal (%)")
    gain.set_title("What dose buys")
    gain.set_xlim(grid[0], grid[-1])
    gain.set_ylim(-8, 62)
    gain.spines[["top", "right"]].set_visible(False)
    gain.legend(frameon=False, loc="center right", handlelength=1.6)
    for clinical in (0.5, 2.81):
        gain.axvline(clinical, color="0.8", linewidth=0.6, linestyle=(0, (1, 2)), zorder=0)

    fine, coarse = min(intervals), max(intervals)
    fine_ratio = cell(fine, 40.0, "sampled")["sd"] / cell(fine, 40.0, "sampled")[
        "quantisation_floor"]
    clinical_coarse = cell(2.81, 40.0, "sampled")
    coarse_ratio = clinical_coarse["sd"] / clinical_coarse["quantisation_floor"]
    gain_fine = improvement["sampled"][intervals.index(fine)]
    gain_coarse = improvement["sampled"][intervals.index(2.81)]
    gain_coarsest = improvement["sampled"][intervals.index(coarse)]

    caption = f"""
        Figure 2. Taking the time to peak from the sampled curve imposes a precision floor at
        the sampling grid, and that floor binds only where the sampling is coarse -- which is
        where more dose cannot help. Left: the standard deviation of the recovered time to peak
        for the fit-free path against the sampling interval at four noise levels, with the
        closed form for a value rounded to a grid of spacing {chr(916)}t drawn as a solid line.
        At {fine:.2f} s the spread at the highest signal is {fine_ratio:.1f} times that floor,
        so the path is noise-limited and not grid-limited; at
        {clinical_coarse['dt']:.2f} s it is {coarse_ratio:.2f} times the floor, which is to say
        on it. Centre: the fitted path on the same axes, which is not confined to the grid and
        falls below the line. Right: the consequence for acquisition. Doubling the signal to
        noise ratio improves the fit-free path by {gain_fine:.0f}% at {fine:.2f} s,
        {gain_coarse:.0f}% at {clinical_coarse['dt']:.2f} s and
        {gain_coarsest:+.0f}% at {coarse:.0f} s, while it continues to help the fitted path at
        every interval. Dotted verticals mark the two sampling intervals present in the
        clinical set. {clinical_coarse['n_attempted']} curves per point; bolus arrival jittered
        uniformly across one sampling interval, without which the fit-free path would be
        unbiased by construction and the comparison empty.
    """
    alt = f"""
        Three charts. Left, for the fit-free path, the standard deviation of the recovered time
        to peak against sampling interval from {fine:.1f} to {coarse:.0f} seconds, with one
        curve per noise level and a straight reference line of slope one over the square root
        of twelve. At the shortest interval the curves sit well above that line and are spread
        apart by noise; by about two seconds they have converged onto it. Centre, the same axes
        for the fitted path, whose curves fall below the reference line. Right, the percentage
        improvement from doubling the signal to noise ratio against sampling interval: for the
        fit-free path it falls from about {gain_fine:.0f} per cent at the shortest interval to
        nothing at the longest, while for the fitted path it stays high throughout.
    """
    return save(figure, 2, "quantisation_floor", dpi=DPI_COMBINATION,
                caption=caption, alt=alt)


# --------------------------------------------------------------------------------------------
# Figure 3: the arterial input, and where the maps stop showing its error.
# --------------------------------------------------------------------------------------------

def figure_arterial() -> dict:
    factor = load("aif_factor.json")
    propagation = load("aif_propagation.json")
    cases = sorted(factor["cases"], key=lambda c: c["area_ratio"])

    figure, (left, middle, right) = plt.subplots(
        1, 3, figsize=(TWO_COLUMN, 2.6), layout="constrained",
        gridspec_kw={"width_ratios": [1.15, 1, 1]})

    # One case's two curves, to show what the ratio is a ratio of.
    worst = max(factor["cases"], key=lambda c: c["area_ratio"])
    left.plot(worst["times"], worst["shipped_curve"], color="black", linewidth=1.1,
              label="shipped with the maps")
    left.plot(worst["times"], worst["auto_curve"], color="0.55", linewidth=1.1,
              linestyle=(0, (4, 2)), label="automatic detection")
    left.fill_between(worst["times"], 0, worst["auto_curve"], color="0.9", zorder=0)
    left.set_xlabel("time from the start of\nthe acquisition (s)")
    left.set_ylabel("enhancement (HU)")
    left.set_title(f"Arterial input, {worst['case']}")
    # Headroom so the legend does not sit on the peak it is describing.
    left.set_ylim(top=max(worst["shipped_curve"]) * 1.28)
    left.legend(frameon=False, loc="upper left", handlelength=1.4, fontsize=5.8,
                borderpad=0.1)

    positions = np.arange(len(cases))
    middle.barh(positions, [c["area_ratio"] for c in cases], color="0.75",
                edgecolor="black", linewidth=0.5, height=0.72)
    middle.axvline(factor["median_area_ratio"], color="black", linewidth=1.0,
                   label=f"median {factor['median_area_ratio']:.2f}")
    middle.set_yticks(positions)
    middle.set_yticklabels([c["case"] for c in cases], fontsize=5.0)
    middle.tick_params(axis="y", length=2, pad=1)
    middle.set_xlabel("arterial area understated\nby a factor of")
    middle.set_title(f"Every case, n={factor['n_cases']}")
    middle.legend(frameon=False, loc="lower right", handlelength=1.4, fontsize=5.8,
                  borderpad=0.1)

    # Both maps as a multiple of their unaffected value, so the two live on one scale and
    # exact proportionality is the identity line rather than something to be taken on trust.
    # An earlier version plotted CBF in its own units and labelled it as divided by 7.5,
    # which it was not -- a figure whose legend did not describe what it drew.
    points = propagation["points"]
    ratios = [p["aif_area_ratio"] for p in points]
    first = min(v for v in propagation["first_clipped_ratio"].values() if v is not None)
    right.axvspan(first, max(ratios) * 1.04, color="0.92", zorder=0)
    right.plot(ratios, ratios, color="0.6", linewidth=0.8, linestyle=(0, (3, 2)), zorder=1,
               label="exact proportionality")
    right.plot(ratios, [p["cbv_inflation"] for p in points], marker="o", markersize=3,
               color="black", zorder=3, label="CBV")
    right.plot(ratios, [p["cbf_inflation"] for p in points], marker="s", markersize=3,
               color="0.45", linestyle=(0, (1, 1.5)), zorder=2, label="CBF")
    right.text(first + 0.2, max(ratios) * 0.92,
               f"both maps at their\nceiling from {first:.1f}x", fontsize=5.8, va="top")
    right.set_xlabel("arterial area understated\nby a factor of")
    right.set_ylabel("recovered value, as a multiple\nof its value at no error")
    right.set_title("Where the error becomes invisible")
    right.set_xlim(0.8, max(ratios) * 1.04)
    right.legend(frameon=False, loc="upper left", handlelength=1.4, fontsize=5.8,
                 borderpad=0.1)

    for axis in (left, middle, right):
        axis.spines[["top", "right"]].set_visible(False)

    caption = f"""
        Figure 3. The automatic arterial input understates the arterial area, and the
        quantitative maps stop showing the error well before the measured size of it. Left: for
        the case with the largest error, the curve the dataset's own maps were made with and
        the curve the automatic detector returns, on the same axes; cerebral blood volume and
        flow are divided by the area under this curve. Middle: the ratio of the two areas for
        every case, median {factor['median_area_ratio']:.2f} and range
        {factor['min_area_ratio']:.2f} to {factor['max_area_ratio']:.2f}. Right: the same error
        applied to a phantom whose values start in the physiological range, with each map drawn
        as a multiple of its value at no error. Below the ceilings both follow the broken line
        of exact proportionality; from a factor of {first:.1f} they sit at the implementation's
        own clips of {propagation['cbv_clip']:.0f} ml/100 g and
        {propagation['cbf_clip']:.0f} ml/100 g/min and are uniform, which is the shaded region.
        Every case measured here lies inside it, so on this data the map cannot show the error
        that is in it.
    """
    alt = f"""
        Three panels. Left, two arterial enhancement curves against time for one case: the
        curve shipped with the dataset's maps peaks far higher than the curve the automatic
        detector returns, and the area under the automatic curve is shaded. Middle, a
        horizontal bar chart of {factor['n_cases']} cases showing by what factor each
        understates the arterial area, from {factor['min_area_ratio']:.1f} to
        {factor['max_area_ratio']:.1f}, with a vertical line at the median of
        {factor['median_area_ratio']:.1f}. Right, recovered blood volume and flow against that
        factor, each as a multiple of its value at no error: both lie on the line of exact
        proportionality and then flatten at the implementation's ceilings from a factor of
        {first:.1f} onwards, with that region shaded; every measured case falls inside it.
    """
    return save(figure, 3, "arterial_input", dpi=DPI_COMBINATION, caption=caption, alt=alt)


# --------------------------------------------------------------------------------------------
# Figure 4: the result on real images, for the case the frozen rule chose.
# --------------------------------------------------------------------------------------------

def figure_clinical() -> dict:
    """The clinical figure, on the slice the measurement used.

    Two choices here are worth stating because they are the ones that could mislead.

    The slice shown is the one the *measurement* used -- the slice with the most admitted
    tissue -- not the slice where the frozen rule found the largest asymmetry. The rule selects
    the case; showing a different slice from the one the numbers describe would put a picture
    next to figures that are not about it. Both are in the caption.

    All three maps are shown as a deviation from their own median over the displayed tissue,
    on one window. They cannot share an absolute window: the reference maps are referenced to
    bolus arrival and this implementation to the start of the acquisition, a near-constant
    offset of about 23 s, which is a difference of convention and not a finding. Removing each
    map's own median is exactly the quantity the paper measures -- a hemispheric difference --
    and leaves the offset where it belongs.
    """
    import numpy as np

    data = np.load(os.path.join(RESULTS, "mol001_maps.npz"))
    case = str(data["case"])
    measured_slice, rule_slice = int(data["measured_slice"]), int(data["rule_slice"])
    mask, left, right = data["mask"], data["left"], data["right"]
    midline = int(data["midline"])

    rows, cols = np.nonzero(mask)
    pad = 6
    box = (slice(max(rows.min() - pad, 0), rows.max() + pad),
           slice(max(cols.min() - pad, 0), cols.max() + pad))

    # Every panel is drawn over the voxels all three admit. Each method's own admission differs
    # -- ours keeps a rim of scalp and skull that the reference's masking removes, and the
    # fitted path drops the voxels whose peak fell outside the acquisition -- and a figure in
    # which the three cover different tissue invites a reader to compare the masks instead of
    # the methods. The Results use each method's own admission; this is stated in the caption,
    # and it is why the numbers printed here are not identical to those.
    admitted = {
        "Reference maps (NLR)": ((data["reference_ttp"] > 0.5) & (data["reference_ttp"] < 20.0)
                                 & mask),
        "Fitted": np.isfinite(data["fitted_ttp"]) & mask,
        "Fit-free (argmax)": np.isfinite(data["sampled_ttp"]) & mask,
    }
    common = admitted["Reference maps (NLR)"] & admitted["Fitted"] & admitted["Fit-free (argmax)"]
    panels = [("Reference maps (NLR)", data["reference_ttp"], common),
              ("Fitted", data["fitted_ttp"], common),
              ("Fit-free (argmax)", data["sampled_ttp"], common)]

    window = 6.0
    figure, axes = plt.subplots(1, 4, figsize=(TWO_COLUMN, 2.0), layout="constrained")

    baseline = data["baseline"]
    axes[0].imshow(baseline[box], cmap="gray", vmin=0, vmax=80)
    axes[0].axvline(midline - box[1].start, color="white", linewidth=0.7,
                    linestyle=(0, (3, 2)))
    axes[0].set_title(f"{case}, slice {measured_slice}", fontsize=6.6)
    axes[0].text(0.03, 0.03, "baseline attenuation\nand the midline used",
                 transform=axes[0].transAxes, fontsize=5.4, color="white", va="bottom")

    deltas = {}
    for axis, (name, image, valid) in zip(axes[1:], panels):
        middle = float(np.median(image[valid]))
        shown = np.where(valid, image - middle, np.nan)
        handle = axis.imshow(shown[box], cmap="RdBu_r", vmin=-window, vmax=window)
        deltas[name] = float(image[valid & left].mean() - image[valid & right].mean())
        axis.set_title(name, fontsize=6.6)
        axis.text(0.03, 0.03, f"L-R {deltas[name]:+.2f} s", transform=axis.transAxes,
                  fontsize=5.8, va="bottom",
                  bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.75,
                        "pad": 1.0})

    for axis in axes:
        axis.set_xticks([])
        axis.set_yticks([])
        for spine in axis.spines.values():
            spine.set_visible(False)

    bar = figure.colorbar(handle, ax=axes, fraction=0.025, pad=0.01)
    bar.set_label("time to peak, relative to the slice median (s)", fontsize=5.8)
    bar.ax.tick_params(labelsize=5.4)

    clinical = load("f1_f2_clinical.json")
    sampled = {r["method"]: r for r in clinical
               if r["case"] == case and r["series"] == "filtered_3mm"}
    reference = next(c for c in load("clinical_vs_reference.json")["cases"]
                     if c["case"] == case)
    rejected = 100 * (int(data["n_fit_failed"]) + int(data["n_outside_window"])) \
        / int(data["n_admitted"])

    caption = f"""
        Figure 4. The two curve models on real images, for the case the frozen rule selected.
        The rule — the largest left-right hemispheric asymmetry in the reference maps — chose
        {case}, where that asymmetry is largest on slice {rule_slice} at
        {load('figure_case.json')['chosen']['signed_delta']:+.2f} s; the slice shown is slice
        {measured_slice}, the one the measurement used, being the slice with the most admitted
        tissue. Left: baseline attenuation with the midline taken from the tissue mask. Right,
        on one window: the reference maps the dataset ships, the fitted path and the fit-free
        path, each as a deviation from its own median over the {int(mask.sum()):,} admitted
        voxels, because the reference is referenced to bolus arrival and this implementation to
        the start of the acquisition. The delay on the left side is visible in all three. Over
        the whole slice the hemispheric differences are
        {deltas['Reference maps (NLR)']:+.2f}, {deltas['Fitted']:+.2f} and
        {deltas['Fit-free (argmax)']:+.2f} s; the Results quote, over each method's own
        admitted voxels and
        {reference['reference_delta']:+.2f}, {sampled['gamma']['delta']:+.2f} ±
        {sampled['gamma']['delta_standard_error']:.2f} and {sampled['raw']['delta']:+.2f} ±
        {sampled['raw']['delta_standard_error']:.2f} s, from the
        {sampled['gamma']['n_per_hemisphere']}-voxel sample per hemisphere that the fit's cost
        allows — the difference between the two being an illustration of the sampling precision
        the Methods report. {rejected:.1f}% of fits were rejected on this slice, almost all for
        a peak outside the acquisition.
    """
    alt = f"""
        Four panels of the same brain slice. The first is a greyscale baseline CT image with a
        dashed vertical line marking the midline. The other three are time-to-peak maps shown
        as a deviation from each map's own median on a shared blue-to-red scale from minus six
        to plus six seconds: the dataset's reference maps, this implementation's fitted path,
        and its fit-free path. All three show the same region of delay on the left side of the
        image, redder than the opposite hemisphere, and each panel is labelled with its
        left-minus-right difference in seconds.
    """
    return save(figure, 4, "clinical_case", dpi=DPI_COMBINATION, caption=caption, alt=alt)


FIGURES_BY_NUMBER = {1: figure_design, 2: figure_floor, 3: figure_arterial,
                     4: figure_clinical}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", type=int, action="append",
                        help="draw just this figure; may be repeated")
    args = parser.parse_args(argv)

    wanted = sorted(args.only) if args.only else sorted(FIGURES_BY_NUMBER)
    unknown = [n for n in wanted if n not in FIGURES_BY_NUMBER]
    if unknown:
        print(f"no such figure: {unknown}")
        return 1

    # Figure 4 needs the clinical maps, which are computed by a separate driver because they
    # take an hour. Its absence is reported rather than passed over.
    if 4 in wanted and not os.path.isfile(os.path.join(RESULTS, "mol001_maps.npz")):
        print("figure 4 needs paper/results/mol001_maps.npz; run "
              "paper/analysis/run_figure_maps.py first")
        return 1

    captions = {}
    existing = os.path.join(FIGURES, "captions.json")
    if os.path.isfile(existing):
        with open(existing, encoding="utf-8") as handle:
            captions = {int(k): v for k, v in json.load(handle).items()}

    for number in wanted:
        print(f"figure {number}:")
        captions[number] = FIGURES_BY_NUMBER[number]()

    os.makedirs(FIGURES, exist_ok=True)
    with open(os.path.join(FIGURES, "captions.json"), "w", encoding="utf-8") as handle:
        json.dump({str(k): captions[k] for k in sorted(captions)}, handle, indent=2,
                  ensure_ascii=False)
    print(f"\nwrote {os.path.join(FIGURES, 'captions.json')} "
          f"({len(captions)} figures with captions and alt text)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
