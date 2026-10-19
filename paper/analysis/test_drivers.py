"""Tests for the drivers that produce the numbers in ``paper/results/``.

The measurement logic itself is tested in ``test_ctp_measure.py``. What is left in the drivers is
a screening rule, a sampling rule and a set of design constants -- and each of those is a place
where a silent change would move a published number without any test going red. Nothing here
touches the dataset, so the suite runs anywhere.

Two tests inject a defect and check that it is caught, because a check nobody has seen fail is
not evidence.
"""

from __future__ import annotations

import contextlib
import io
import json
import math
import os
import pathlib
import sys
import tempfile
import types
import unittest

import numpy as np

import run_aif
import run_clinical
import run_propagation
import run_reference
import run_screen
import run_synthetic
import unitobrain
from ctp_measure import hemispheres, quantisation_floor


def ttp_image(left_value: float, right_value: float, *, width: int = 200, height: int = 200,
              left_edge: int = 0, right_edge: int | None = None) -> np.ndarray:
    """A TTP map with a rectangular head, zero (background) elsewhere."""
    image = np.zeros((height, width), dtype=np.float64)
    right_edge = width if right_edge is None else right_edge
    span = right_edge - left_edge
    middle = left_edge + span // 2
    image[:, left_edge:middle] = left_value
    image[:, middle:right_edge] = right_value
    return image


class ScreeningRule(unittest.TestCase):
    """The figure case is chosen by the rule in PROTOCOL.md, on the dataset's own maps."""

    def test_it_measures_the_asymmetry_it_claims_to(self):
        value = run_screen.slice_asymmetry(ttp_image(10.0, 4.0))
        self.assertAlmostEqual(value, 6.0, places=6)

    def test_the_sign_follows_the_slower_hemisphere(self):
        self.assertLess(run_screen.slice_asymmetry(ttp_image(4.0, 10.0)), 0.0)

    def test_background_zeros_are_not_admitted_as_fast_tissue(self):
        """If zero were admitted, more background on one side would read as a deficit.

        The band has to cover more than half of a hemisphere for a median to move at all --
        which is the reason the rule uses a median, and the reason an earlier version of this
        test could not see the defect it was written for.
        """
        image = ttp_image(6.0, 6.0)
        image[:, :60] = 0.0
        self.assertAlmostEqual(run_screen.slice_asymmetry(image), 0.0, places=6)

    def test_vessels_are_excluded_by_the_upper_bound(self):
        image = ttp_image(6.0, 6.0)
        image[:, :60] = 1e4
        self.assertAlmostEqual(run_screen.slice_asymmetry(image), 0.0, places=6)

    def test_a_slice_with_too_little_tissue_is_not_compared(self):
        small = ttp_image(10.0, 4.0, width=20, height=20)
        self.assertIsNone(run_screen.slice_asymmetry(small))

    def test_a_slice_with_too_little_tissue_on_one_side_is_not_compared(self):
        """The per-side minimum is not implied by the total.

        The midline is the column centroid, which balances the column-weighted mass, not the
        voxel count. A dense block beside a long thin tail is balanced by the centroid and
        still leaves one side with too few voxels to take a median of.
        """
        image = np.zeros((200, 200))
        image[:, :10] = 6.0      # 2,000 voxels in ten columns
        image[:4, 100:] = 9.0    # 400 voxels spread over a hundred
        admitted = (image > run_screen.TTP_MIN) & (image < run_screen.TTP_MAX)
        self.assertGreater(admitted.sum(), 2 * run_screen.MIN_VOXELS)
        self.assertIsNone(run_screen.slice_asymmetry(image))

    def test_the_midline_follows_an_off_centre_head(self):
        """Injected defect: splitting at the image centre instead of the mask centroid."""
        image = ttp_image(10.0, 4.0, width=300, left_edge=20, right_edge=120)
        value = run_screen.slice_asymmetry(image)
        # Spelled out rather than left to assertAlmostEqual: splitting at the image centre
        # empties one hemisphere, which trips the per-side minimum and returns None, and
        # comparing None to a float raises instead of failing. The injection proof then
        # scored this as an error rather than as the check doing its job.
        self.assertIsNotNone(value, "an off-centre head must still be comparable")
        self.assertAlmostEqual(value, 6.0, places=6)

        # The same slice split at the image centre: the head lies entirely to the left of it,
        # so one hemisphere is empty and no asymmetry can be computed at all. That is the
        # defect taking the midline from the data prevents.
        centre = image.shape[1] // 2
        mask = (image > run_screen.TTP_MIN) & (image < run_screen.TTP_MAX)
        at_image_centre = mask.copy()
        at_image_centre[:, :centre] = False
        self.assertEqual(at_image_centre.sum(), 0)

    def test_the_statistic_is_a_median_and_not_a_mean(self):
        """PROTOCOL.md says the median is deliberate; no earlier fixture could tell them apart.

        A review pointed out that every fixture here filled each hemisphere with one value,
        where median and mean coincide. Here a minority of slow voxels -- a vein, in practice
        -- sits inside the admitted window on the left, so a mean would be dragged by it and a
        median would not.
        """
        image = ttp_image(6.0, 6.0)
        image[:40, :100] = 19.0        # a fifth of the left hemisphere, still inside the window
        mask = (image > run_screen.TTP_MIN) & (image < run_screen.TTP_MAX)
        split = hemispheres(mask)
        by_mean = float(image[split.left].mean() - image[split.right].mean())
        self.assertAlmostEqual(run_screen.slice_asymmetry(image), 0.0, places=6)
        self.assertGreater(abs(by_mean), 2.0, "the fixture does not separate the two statistics")

    def test_the_expected_case_count_is_the_published_one(self):
        # The screen aborts rather than ranking a partially extracted set; this is the number
        # it compares against.
        self.assertEqual(run_screen.EXPECTED_CASES, 15)


class ArterialPopulation(unittest.TestCase):
    """run_aif's gate on the population behind the median it reports.

    A reviewer found the gate inline and untested: the 6.97 the manuscript and the propagation
    grid both rest on could have come from a shrunken set with every test green.
    """

    def test_a_complete_population_passes(self):
        n = run_aif.EXPECTED_CASES
        self.assertIsNone(run_aif.population_complaint(n, n, n))

    def test_any_shortfall_is_refused_and_says_which(self):
        n = run_aif.EXPECTED_CASES
        for directories, measured, usable in ((n - 1, n - 1, n - 1), (n, n - 1, n - 1),
                                              (n, n, n - 1)):
            with self.subTest(d=directories, m=measured, u=usable):
                complaint = run_aif.population_complaint(directories, measured, usable)
                self.assertIsNotNone(complaint)
                self.assertIn(str(n), complaint)

    def test_a_ratio_of_zero_is_not_a_measurement(self):
        """Finite was the old test; a shipped area of zero gives 0.0, which is finite."""
        rows = [{"area_ratio": 6.97}, {"area_ratio": 0.0}, {"area_ratio": float("nan")},
                {"area_ratio": float("inf")}, {"area_ratio": -1.0}]
        usable = run_aif.usable_ratios(rows)
        self.assertEqual(usable.tolist(), [6.97])

    def test_the_expected_count_matches_the_other_drivers(self):
        self.assertEqual(run_aif.EXPECTED_CASES, run_screen.EXPECTED_CASES)


class ScreeningWindowsAgree(unittest.TestCase):
    """The screen and the reference comparison read the same maps, so they must admit the same
    tissue. A mismatch would silently compare two different populations of voxels."""

    def test_the_ttp_windows_are_identical(self):
        self.assertEqual((run_screen.TTP_MIN, run_screen.TTP_MAX),
                         (run_reference.TTP_MIN, run_reference.TTP_MAX))

    def test_the_per_side_minimum_is_identical(self):
        self.assertEqual(run_screen.MIN_VOXELS, run_reference.MIN_PER_SIDE)

    def test_the_total_minimum_is_identical_too(self):
        """A review found this one had drifted while a test called the two "identical".

        The screen required 1,000 admitted voxels in total and the reference comparison 2,000,
        so a slice the screen could rank was not necessarily one the comparison could use.
        The thresholds are now derived from the screen's rather than restated.
        """
        self.assertEqual(2 * run_screen.MIN_VOXELS, run_reference.MIN_TOTAL)


class SamplingRule(unittest.TestCase):
    """The clinical arm draws a fixed number of voxels per hemisphere. The docstring justifies
    the number with a standard error; that arithmetic is checked here rather than trusted."""

    def test_the_frozen_sampling_rule_is_the_one_in_the_protocol(self):
        """PROTOCOL.md fixes these two numbers, so they are pinned and not merely bounded.

        A reviewer pointed out that the standard-error test below is satisfied by any count
        above 400, and that the seed test only required the two arms to agree -- so both could
        have drifted away from the frozen values with every test still green.
        """
        self.assertEqual(run_clinical.N_PER_HEMISPHERE, 500)
        self.assertEqual(run_clinical.SEED, 20261016)

    # There used to be a test here called
    # test_the_standard_error_claimed_in_the_docstring_holds. It computed 1/sqrt(500) with an
    # assumed voxel-level spread of 1 s and asserted the result was below 0.05 s. The driver no
    # longer claims that -- the measured spread is 3.4 to 12.7 s -- so the test was endorsing a
    # claim its own subject had withdrawn. A second reviewer caught that it had survived the
    # correction. It is deleted rather than adjusted: the precision claim is now
    # test_the_standard_error_is_recorded_from_the_measured_spread, which reads what the driver
    # measured instead of asserting arithmetic on an assumption.

    def test_a_hemisphere_is_not_summarised_from_a_handful_of_values(self):
        self.assertLess(run_clinical.MIN_ADMITTED, run_clinical.N_PER_HEMISPHERE)
        self.assertGreaterEqual(run_clinical.MIN_ADMITTED, 100)

    def test_the_seed_is_fixed_and_shared_with_the_synthetic_arm(self):
        self.assertEqual(run_clinical.SEED, run_synthetic.SEED)

    @staticmethod
    def split(width: int = 80, height: int = 80):
        mask = np.ones((height, width), dtype=bool)
        return hemispheres(mask)

    def test_the_draw_is_the_drivers_own_and_is_reproducible(self):
        """The earlier version of this test reimplemented the draw and so tested nothing."""
        first = run_clinical.draw_voxels(self.split())
        second = run_clinical.draw_voxels(self.split())
        for side in ("left", "right"):
            np.testing.assert_array_equal(first[side][0], second[side][0])
            np.testing.assert_array_equal(first[side][1], second[side][1])

    def test_the_two_hemispheres_get_different_voxels(self):
        picks = run_clinical.draw_voxels(self.split())
        left = set(zip(*(a.tolist() for a in picks["left"])))
        right = set(zip(*(a.tolist() for a in picks["right"])))
        self.assertEqual(len(left & right), 0)
        self.assertEqual(len(left), run_clinical.N_PER_HEMISPHERE)

    def test_every_drawn_voxel_lies_inside_its_own_hemisphere(self):
        split = self.split()
        picks = run_clinical.draw_voxels(split)
        for side in ("left", "right"):
            mask = getattr(split, side)
            rows, cols = picks[side]
            self.assertTrue(mask[rows, cols].all(), f"a drawn voxel is outside {side}")

    def test_the_draw_does_not_depend_on_the_order_it_is_called_in(self):
        """Injected defect: drawing inside the series loop from one advancing generator.

        The comparison between the two input series, and between the two methods, is paired.
        Because the draw seeds its own generator, calling it again gives the same voxels; a
        draw that shared an advancing generator would not, and the difference between the two
        series would then be partly a difference of sample.
        """
        split = self.split()
        once = run_clinical.draw_voxels(split)
        for _ in range(3):
            again = run_clinical.draw_voxels(split)
            np.testing.assert_array_equal(once["left"][0], again["left"][0])

    def test_a_hemisphere_too_small_to_draw_from_is_refused_by_name(self):
        """NumPy raises here on its own, so the guard's value is what it says.

        Without the guard the message is "Cannot take a larger sample than population", which
        does not tell the reader which case, which hemisphere, or how short it was. The
        injection proof could not see the guard removed until this test read the message.
        """
        mask = np.ones((10, 10), dtype=bool)
        with self.assertRaises(ValueError) as caught:
            run_clinical.draw_voxels(hemispheres(mask))
        message = str(caught.exception)
        self.assertIn("hemisphere", message)
        self.assertIn(str(run_clinical.N_PER_HEMISPHERE), message)


class SyntheticDesign(unittest.TestCase):
    """The synthetic grid has to be able to answer the question the manuscript asks of it."""

    def test_both_clinical_sampling_intervals_are_on_the_grid(self):
        # Otherwise the synthetic and clinical arms cannot be read together.
        for dt in (0.5, 2.81):
            self.assertIn(dt, run_synthetic.DT_LEVELS)

    def test_the_grid_spans_a_factor_of_eight_in_sampling_interval(self):
        self.assertGreaterEqual(max(run_synthetic.DT_LEVELS) / min(run_synthetic.DT_LEVELS), 8.0)

    def test_the_repeat_count_resolves_the_floor_it_is_used_to_test(self):
        # The sd of an sd estimated from n normal draws is about sd/sqrt(2n). At the coarsest
        # interval the floor is 1.15 s, so the estimate must be far tighter than the step
        # between neighbouring floors -- otherwise agreement with dt/sqrt(12) means nothing.
        coarse = quantisation_floor(max(run_synthetic.DT_LEVELS))
        uncertainty = coarse / math.sqrt(2 * run_synthetic.N_REPEATS)
        step = coarse - quantisation_floor(sorted(run_synthetic.DT_LEVELS)[-2])
        self.assertLess(uncertainty, step / 4)

    def test_the_noise_levels_bracket_the_clinical_range(self):
        self.assertLessEqual(min(run_synthetic.SNR_LEVELS), 5.0)
        self.assertGreaterEqual(max(run_synthetic.SNR_LEVELS), 40.0)

    def test_arrival_is_jittered_across_one_whole_sampling_interval(self):
        """Without this the fit-free path is unbiased by construction and the arm is vacuous.

        The jitter had no test at all until a review said so: it was inline in main(), and
        removing it left every test green.
        """
        for dt in run_synthetic.DT_LEVELS:
            rng = np.random.default_rng(run_synthetic.SEED)
            drawn = np.array([run_synthetic.arrival_time(rng, dt) for _ in range(4000)])
            offsets = drawn - run_synthetic.NOMINAL_ARRIVAL
            with self.subTest(dt=dt):
                self.assertTrue((offsets >= 0).all() and (offsets <= dt).all())
                # A uniform draw over one interval: it must reach into both end tenths, and
                # its mean must sit near the middle. A fixed arrival fails all three.
                self.assertLess(offsets.min(), 0.1 * dt)
                self.assertGreater(offsets.max(), 0.9 * dt)
                self.assertAlmostEqual(offsets.mean() / dt, 0.5, delta=0.03)
                # Every draw landing on a sampling instant is the defect; none should.
                self.assertGreater(len(np.unique(offsets)), 3000)

    def test_a_non_positive_interval_is_refused(self):
        rng = np.random.default_rng(0)
        for dt in (0.0, -1.0):
            with self.subTest(dt=dt), self.assertRaises(ValueError):
                run_synthetic.arrival_time(rng, dt)


class PropagationDesign(unittest.TestCase):
    """The propagation experiment has to straddle the point at which the maps saturate, or it
    cannot show where the error stops being visible."""

    def test_the_ratios_start_at_no_error(self):
        self.assertEqual(run_propagation.RATIOS[0], 1.0)

    def test_the_ratios_are_increasing(self):
        self.assertEqual(run_propagation.RATIOS, sorted(run_propagation.RATIOS))

    def test_the_measured_clinical_errors_are_on_the_grid(self):
        # The median and the largest value measured by run_aif.py, so the figure can say what
        # the implementation does at the error the dataset actually provokes.
        for ratio in (6.97, 10.47):
            self.assertIn(ratio, run_propagation.RATIOS)

    def test_the_grid_is_fine_enough_to_locate_the_ceiling(self):
        below = [r for r in run_propagation.RATIOS if r <= 4.0]
        self.assertGreaterEqual(len(below), 6)
        self.assertLessEqual(max(np.diff(below)), 0.5)

    @staticmethod
    def point(ratio, *, cbv=False, cbf=False):
        return {"aif_area_ratio": ratio, "cbv_clipped": cbv, "cbf_clipped": cbf}

    def test_the_run_refuses_a_grid_that_does_not_straddle_the_ceiling(self):
        """Requirement (14), which had no test: a review found the one that looked like it
        was passing only because its mutation removed two particular grid values."""
        below = [self.point(1.0), self.point(2.0)]
        above = [self.point(9.0, cbv=True, cbf=True)]
        for name in run_propagation.MAPS:
            with self.subTest(map=name):
                self.assertFalse(run_propagation.straddles_the_ceiling(below, name))
                self.assertFalse(run_propagation.straddles_the_ceiling(above, name))
                self.assertTrue(run_propagation.straddles_the_ceiling(below + above, name))

    def test_the_two_maps_are_judged_separately(self):
        """A reviewer found that either map clipping was reported as both saturating.

        CBF comes from a deconvolution and CBV from a ratio of areas; nothing obliges them to
        reach their ceilings together, so a claim about where the error becomes invisible has
        to name its map.
        """
        grid = [self.point(1.0), self.point(5.0, cbv=True)]
        self.assertTrue(run_propagation.straddles_the_ceiling(grid, "cbv"))
        self.assertFalse(run_propagation.straddles_the_ceiling(grid, "cbf"))
        self.assertEqual(run_propagation.first_clipped(grid, "cbv"), 5.0)
        self.assertIsNone(run_propagation.first_clipped(grid, "cbf"))

    def test_an_unknown_map_is_refused(self):
        with self.assertRaises(ValueError):
            run_propagation.straddles_the_ceiling([self.point(1.0)], "mtt")

    def test_the_clips_are_the_ones_the_implementation_uses(self):
        source = (pathlib.Path(__file__).resolve().parents[2]
                  / "ctp_core" / "parametric_maps.py")
        if not source.exists():
            self.skipTest("ctp_core is not present in this snapshot")
        text = source.read_text(encoding="utf-8")
        for value, name in ((run_propagation.CBV_CLIP, "cbv_value"),
                            (run_propagation.CBF_CLIP, "cbf_value")):
            # The implementation writes the ceiling as an integer literal, so compare the
            # whole call rather than the formatted number.
            self.assertIn(f"np.clip({name}, 0, {int(value)})", text)
            self.assertEqual(value, int(value))


class DatasetAccess(unittest.TestCase):
    """unitobrain.py is the only place that knows the dataset's layout."""

    @contextlib.contextmanager
    def root_set_to(self, value):
        """Run the block with UNITOBRAIN_ROOT set to ``value``, or unset when it is None."""
        previous = os.environ.get(unitobrain.ROOT_VARIABLE)
        if value is None:
            os.environ.pop(unitobrain.ROOT_VARIABLE, None)
        else:
            os.environ[unitobrain.ROOT_VARIABLE] = value
        try:
            yield
        finally:
            if previous is None:
                os.environ.pop(unitobrain.ROOT_VARIABLE, None)
            else:
                os.environ[unitobrain.ROOT_VARIABLE] = previous

    def test_the_root_comes_from_the_environment(self):
        # The dataset is not redistributed, so a reader must be able to say where theirs is.
        with tempfile.TemporaryDirectory() as folder:
            with self.root_set_to(folder):
                self.assertEqual(unitobrain.root(), folder)

    def test_an_unset_root_is_an_error_that_names_the_variable(self):
        """Injected defect: a hard-coded default.

        A default is one machine's directory layout. On anyone else's computer it is a path
        that does not exist, and the failure then surfaces as a FileNotFoundError about a
        directory the reader has never heard of instead of as the one instruction they need.
        """
        for value in (None, "", "   ", '""'):
            with self.subTest(value=value), self.root_set_to(value):
                with self.assertRaises(RuntimeError) as caught:
                    unitobrain.root()
                self.assertIn(unitobrain.ROOT_VARIABLE, str(caught.exception))

    def test_a_root_that_is_not_a_directory_is_refused(self):
        with self.root_set_to(str(pathlib.Path(__file__).resolve())):
            with self.assertRaises(RuntimeError):
                unitobrain.root()

    def test_no_machine_specific_path_is_committed(self):
        """Every absolute path here would be wrong on the reader's computer.

        The needles are assembled rather than written out, because a literal one would appear
        in this file and the check would then report itself -- which is exactly what the first
        version of it did.
        """
        needles = [letter + ":" + chr(92) for letter in "CDE"]
        needles += ["/" + name + "/" for name in ("home", "Users")]
        for path in sorted(pathlib.Path(__file__).resolve().parent.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            for needle in needles:
                if needle in text:
                    line = next(n for n, row in enumerate(text.splitlines(), 1)
                                if needle in row)
                    self.fail(f"{path.name}:{line} carries the absolute path {needle!r}")

    def test_the_tissue_mask_needs_a_bolus_to_have_arrived(self):
        # A volume that never enhances is not tissue this measurement can use, however
        # plausible its attenuation.
        flat = np.full((18, 8, 8), 40.0, dtype=np.float32)
        self.assertEqual(unitobrain.tissue_mask(flat).sum(), 0)

    def test_the_tissue_mask_admits_an_enhancing_voxel(self):
        slab = np.full((18, 8, 8), 40.0, dtype=np.float32)
        slab[5:, 2, 3] += 30.0
        mask = unitobrain.tissue_mask(slab)
        self.assertTrue(mask[2, 3])
        self.assertEqual(mask.sum(), 1)

    def test_an_infinite_voxel_is_not_tissue(self):
        """A reviewer found that an infinite sample satisfied "a bolus arrived".

        One such voxel in a hemispheric mean destroys it, and it would also have been counted
        by busiest_slice when choosing which slice to measure.
        """
        slab = np.full((18, 4, 4), 40.0, dtype=np.float32)
        slab[5:] += 30.0                 # every voxel is tissue
        slab[9, 1, 1] = np.inf
        slab[9, 2, 2] = -np.inf
        slab[9, 3, 3] = np.nan
        mask = unitobrain.tissue_mask(slab)
        self.assertFalse(mask[1, 1])
        self.assertFalse(mask[2, 2])
        self.assertFalse(mask[3, 3])
        self.assertTrue(mask[0, 0], "an ordinary voxel should still be admitted")

    def test_a_voxel_whose_baseline_is_not_finite_is_not_tissue(self):
        slab = np.full((18, 3, 3), 40.0, dtype=np.float32)
        slab[5:] += 30.0
        slab[0, 1, 1] = np.nan           # in the baseline window
        self.assertFalse(unitobrain.tissue_mask(slab)[1, 1])

    def test_air_and_bone_are_not_admitted(self):
        slab = np.full((18, 4, 4), 40.0, dtype=np.float32)
        slab[:, 0, 0] = -1000.0   # air
        slab[:, 1, 1] = 1200.0    # bone
        slab[5:] += 30.0
        mask = unitobrain.tissue_mask(slab)
        self.assertFalse(mask[0, 0])
        self.assertFalse(mask[1, 1])

    def test_the_busiest_slice_is_the_one_with_the_most_tissue(self):
        volume = np.full((18, 3, 8, 8), 40.0, dtype=np.float32)
        volume[5:, 1, :4, :4] += 30.0   # 16 voxels
        volume[5:, 2, :2, :2] += 30.0   # 4 voxels
        self.assertEqual(unitobrain.busiest_slice(volume), 1)


class LoadingACase(unittest.TestCase):
    """Requirement (7), which a review found had no test at all.

    load() is built on _read_series, which needs DICOM files, so the reader is replaced here
    and only load()'s own checks are exercised. The checks are what matter: each of them is a
    way for a volume of the right shape to be built from the wrong images, which nothing
    downstream could see.
    """

    @contextlib.contextmanager
    def dataset(self, *, n_times=18, n_slices=4, times=None, aif=None, locations=None):
        folder = tempfile.mkdtemp()
        case = "MOL-999"
        times = list(range(n_times)) if times is None else times
        aif = [0.0] * n_times if aif is None else aif
        volume = np.zeros((n_times, n_slices, 4, 4), dtype=np.float32)
        wrote = pathlib.Path(folder) / (case + unitobrain.MAPS + ".txt")
        wrote.write_text(" ".join(map(str, times)) + "\n" + " ".join(map(str, aif)) + "\n",
                         encoding="utf-8")
        original_read, original_root = unitobrain._read_series, unitobrain.root
        unitobrain._read_series = lambda _folder: (
            volume,
            list(range(n_slices)) if locations is None else locations,
            list(range(1, n_times + 1)))
        unitobrain.root = lambda: folder
        try:
            yield case
        finally:
            unitobrain._read_series, unitobrain.root = original_read, original_root

    def test_a_consistent_case_loads(self):
        with self.dataset() as case:
            acquisition = unitobrain.load(case)
            self.assertEqual(acquisition.times.size, 18)
            self.assertEqual(acquisition.volume.shape[0], 18)

    def test_a_time_vector_of_the_wrong_length_is_refused(self):
        with self.dataset(times=list(range(17))) as case:
            with self.assertRaises(ValueError):
                unitobrain.load(case)

    def test_an_arterial_curve_of_the_wrong_length_is_refused(self):
        with self.dataset(aif=[0.0] * 17) as case:
            with self.assertRaises(ValueError):
                unitobrain.load(case)

    def test_the_window_and_interval_come_from_the_time_vector(self):
        with self.dataset(times=[0.0, 2.81, 5.62, 8.43], n_times=4) as case:
            acquisition = unitobrain.load(case)
            self.assertAlmostEqual(acquisition.dt, 2.81, places=6)
            self.assertEqual(acquisition.window, (0.0, 8.43))


class ReadingASeries(unittest.TestCase):
    """_read_series' own refusals. A reviewer found every one of them untested.

    pydicom is replaced by a stub: each "file" is one slice of one acquisition, which is all
    these checks look at. The point is not to test pydicom but to test what happens when the
    files disagree with each other.
    """

    @contextlib.contextmanager
    def files(self, entries):
        """``entries`` is a list of (acquisition number, slice location)."""
        folder = tempfile.mkdtemp()
        names = []
        for n, _ in enumerate(entries):
            name = pathlib.Path(folder) / f"{n:04d}.dcm"
            name.write_bytes(b"")
            names.append(str(name))

        class Slice:
            def __init__(self, stamp, location):
                self.AcquisitionNumber = stamp
                self.SliceLocation = location
                self.RescaleSlope = 1.0
                self.RescaleIntercept = 0.0
                self.pixel_array = np.zeros((2, 2), dtype=np.int16)

        by_name = {name: Slice(*entry) for name, entry in zip(names, entries)}
        stub = types.ModuleType("pydicom")
        stub.dcmread = lambda path, **kwargs: by_name[str(path)]
        previous = sys.modules.get("pydicom")
        sys.modules["pydicom"] = stub
        try:
            yield folder
        finally:
            if previous is None:
                del sys.modules["pydicom"]
            else:
                sys.modules["pydicom"] = previous

    def test_a_well_formed_series_is_read(self):
        with self.files([(1, 0.0), (1, 2.5), (2, 0.0), (2, 2.5)]) as folder:
            volume, locations, acquisitions = unitobrain._read_series(folder)
            self.assertEqual(volume.shape, (2, 2, 2, 2))
            self.assertEqual(locations, [0.0, 2.5])
            self.assertEqual(acquisitions, [1, 2])

    def test_a_ragged_volume_is_refused(self):
        """A later acquisition with a slice missing. Without the guard this raises KeyError."""
        with self.files([(1, 0.0), (1, 2.5), (2, 0.0)]) as folder:
            with self.assertRaises(ValueError) as caught:
                unitobrain._read_series(folder)
            self.assertIn("slices", str(caught.exception))

    def test_a_short_first_acquisition_is_refused_too(self):
        """The silent half of the same defect, which a reviewer pointed out was untested.

        The slice positions are taken from the *first* acquisition. If that one is the short
        one, every other acquisition's extra slices are simply dropped: no KeyError, no missing
        key, a volume of consistent shape built from a subset of the data. Only the guard
        catches this, so only this test can show the guard working.
        """
        with self.files([(1, 0.0), (2, 0.0), (2, 2.5), (3, 0.0), (3, 2.5)]) as folder:
            with self.assertRaises(ValueError) as caught:
                unitobrain._read_series(folder)
            self.assertIn("slices", str(caught.exception))

    def test_two_files_at_the_same_position_are_refused(self):
        # Otherwise one silently overwrites the other and the volume has the right shape.
        with self.files([(1, 0.0), (1, 0.0), (2, 0.0), (2, 2.5)]) as folder:
            with self.assertRaises(ValueError) as caught:
                unitobrain._read_series(folder)
            self.assertIn("two files", str(caught.exception))

    def test_a_gap_in_the_acquisition_numbers_is_refused(self):
        """A shorter but well-formed volume would otherwise be given the full time axis."""
        with self.files([(1, 0.0), (2, 0.0), (4, 0.0)]) as folder:
            with self.assertRaises(ValueError) as caught:
                unitobrain._read_series(folder)
            self.assertIn("missing", str(caught.exception))

    def test_an_empty_folder_is_refused(self):
        with self.files([]) as folder:
            with self.assertRaises(FileNotFoundError):
                unitobrain._read_series(folder)

    def test_acquisition_numbers_need_not_start_at_one(self):
        # Only a gap is a problem; a set numbered from 7 is still contiguous.
        with self.files([(7, 0.0), (8, 0.0), (9, 0.0)]) as folder:
            _volume, _locations, acquisitions = unitobrain._read_series(folder)
            self.assertEqual(acquisitions, [7, 8, 9])


class ReferenceSeriesOrdering(unittest.TestCase):
    """A review found the reference maps were ordered by file name while the volume was
    ordered by slice location, and the volume's slice index was used to index them."""

    def series(self, locations):
        images = [np.full((4, 4), float(z)) for z in locations]
        return unitobrain.ReferenceSeries(case="MOL-999", series="NLR_TTP",
                                          images=images, slice_locations=list(locations))

    def test_a_matching_position_is_returned(self):
        series = self.series([10.0, 20.0, 30.0])
        self.assertEqual(series.at_slice(1, 20.0)[0, 0], 20.0)

    def test_a_mismatched_position_is_refused_rather_than_returned(self):
        series = self.series([30.0, 20.0, 10.0])   # as a reversed file order would give
        with self.assertRaises(ValueError) as caught:
            series.at_slice(0, 10.0)
        self.assertIn("not in the same order", str(caught.exception))

    def test_a_non_finite_position_cannot_defeat_the_check(self):
        """NaN compares false against everything, so it used to pass the comparison."""
        for found, expected in ((float("nan"), 10.0), (10.0, float("nan")),
                                (float("inf"), 10.0)):
            with self.subTest(found=found, expected=expected):
                with self.assertRaises(ValueError) as caught:
                    self.series([found]).at_slice(0, expected)
                self.assertIn("non-finite", str(caught.exception))

    def test_an_index_past_the_end_is_refused_and_says_what_was_asked_for(self):
        # A bare list raises IndexError by itself, so what this fixes is the message: which
        # case, which series, which index, and how many slices there actually are.
        with self.assertRaises(IndexError) as caught:
            self.series([10.0, 20.0]).at_slice(5)
        message = str(caught.exception)
        self.assertIn("MOL-999", message)
        self.assertIn("NLR_TTP", message)
        self.assertIn("5", message)

    def test_the_position_check_is_optional_but_the_index_check_is_not(self):
        # Callers that genuinely have no position to check still cannot read past the end.
        self.assertEqual(self.series([10.0]).at_slice(0)[0, 0], 10.0)


def ctp_core_available() -> bool:
    """Whether the package the drivers fit curves with can be imported.

    The cross-check snapshot holds only this directory, so these end-to-end tests cannot run
    there. They are skipped rather than failed, and the skip is visible in the report: a
    snapshot that cannot exercise the drivers should say so, not look green for the wrong
    reason.
    """
    import importlib.util
    return importlib.util.find_spec("ctp_core") is not None


@unittest.skipUnless(ctp_core_available(),
                     "ctp_core is not importable; run_clinical cannot be exercised")
class ClinicalEndToEnd(unittest.TestCase):
    """run_clinical.main() on a small synthetic case.

    A reviewer pointed out that no test verified the driver draws its voxels once per case and
    measures all four arms -- two input series by two methods -- on that same draw. That is the
    property the pairing rests on, and it is structural: it cannot be seen from the functions
    in isolation. Here the dataset is replaced by two tiny volumes and the draw is watched.
    """

    @contextlib.contextmanager
    def dataset(self, *, cases=("MOL-001",), n_times=18, size=8, per_hemisphere=3,
                unfiltered_shift=0, different_shape=False, moved_slices=False):
        folder = pathlib.Path(tempfile.mkdtemp())
        times = np.arange(n_times) * 2.81

        def acquisition(case, filtered):
            width = size + (2 if different_shape and not filtered else 0)
            volume = np.full((n_times, 2, size, width), 40.0, dtype=np.float32)
            # A bolus in every voxel, arriving a little later on the left than on the right so
            # the difference has a known sign -- and with a *different* spread of arrival times
            # on each side. The spread matters: with a single arrival time per hemisphere both
            # standard deviations are zero, and a test of the standard error cannot tell the
            # difference of two means from one of them. That is how the first version of this
            # fixture let an injected defect through.
            for r in range(size):
                for c in range(width):
                    left = c < width // 2
                    start = 4 + (1 + r % 2 if left else r % 3)
                    volume[start:, :, r, c] += 30.0 if filtered else 28.0
            locations = ([0.0, 7.5] if moved_slices and not filtered else [0.0, 2.5])
            stamps = list(range(1 + (unfiltered_shift if not filtered else 0),
                                1 + n_times + (unfiltered_shift if not filtered else 0)))
            return unitobrain.Acquisition(
                case=case, volume=volume, times=times,
                shipped_aif=np.linspace(0.0, 100.0, n_times),
                slice_locations=locations, acquisitions=stamps)

        calls = []
        original = {name: getattr(unitobrain, name)
                    for name in ("root", "cases", "load")}
        original_draw = run_clinical.draw_voxels
        original_n = run_clinical.N_PER_HEMISPHERE
        original_min = run_clinical.MIN_ADMITTED
        original_results = run_clinical.RESULTS

        def spy(split, n_per_hemisphere=None, seed=None):
            picks = original_draw(split, per_hemisphere, run_clinical.SEED)
            calls.append({side: tuple(zip(*(a.tolist() for a in picks[side])))
                          for side in picks})
            return picks

        unitobrain.root = lambda: str(folder)
        unitobrain.cases = lambda: list(cases)
        unitobrain.load = lambda case, filtered=True: acquisition(case, filtered)
        run_clinical.draw_voxels = spy
        run_clinical.N_PER_HEMISPHERE = per_hemisphere
        run_clinical.MIN_ADMITTED = 1
        run_clinical.RESULTS = str(folder / "results")
        try:
            yield folder, calls
        finally:
            for name, value in original.items():
                setattr(unitobrain, name, value)
            run_clinical.draw_voxels = original_draw
            run_clinical.N_PER_HEMISPHERE = original_n
            run_clinical.MIN_ADMITTED = original_min
            run_clinical.RESULTS = original_results

    def run_main(self, argv=()):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = run_clinical.main(list(argv))
        return code, out.getvalue()

    def test_the_voxels_are_drawn_once_per_case_for_all_four_arms(self):
        with self.dataset(cases=("MOL-001", "MOL-002")) as (folder, calls):
            code, printed = self.run_main()
        self.assertEqual(code, 0, printed)
        # Once per case, not once per series or per method.
        self.assertEqual(len(calls), 2, "the draw was not made exactly once per case")
        written = json.loads((folder / "results" / "f1_f2_clinical.json")
                             .read_text(encoding="utf-8"))
        arms = {(r["case"], r["series"], r["method"]) for r in written}
        self.assertEqual(len(arms), 8, "two cases should give four arms each")

    def test_every_arm_reports_the_same_voxel_count(self):
        with self.dataset(per_hemisphere=3) as (folder, _calls):
            code, printed = self.run_main()
            # Inside the block: the patched sample size is restored on the way out.
            drawn = run_clinical.N_PER_HEMISPHERE
        self.assertEqual(code, 0, printed)
        written = json.loads((folder / "results" / "f1_f2_clinical.json")
                             .read_text(encoding="utf-8"))
        self.assertTrue(written)
        for record in written:
            self.assertEqual(record["n_attempted"], 2 * drawn)
            self.assertEqual(record["n_per_hemisphere"], drawn)
            self.assertEqual(record["seed"], run_clinical.SEED)

    def test_a_series_covering_different_acquisitions_is_refused(self):
        """Equal shapes and equal slice positions do not make a shared time axis."""
        with self.dataset(unfiltered_shift=5):
            with self.assertRaises(ValueError) as caught:
                self.run_main()
        self.assertIn("time axis", str(caught.exception))

    def test_a_plumbing_run_cannot_destroy_the_published_result(self):
        """--cases writes elsewhere. A reviewer found it overwriting an hour of measurement.

        The earlier fix only stopped run_reference from consuming a one-case file; the file
        itself was still gone.
        """
        with self.dataset(cases=("MOL-001", "MOL-002")) as (folder, _calls):
            results = pathlib.Path(run_clinical.RESULTS)
            results.mkdir(parents=True, exist_ok=True)
            published = results / "f1_f2_clinical.json"
            published.write_text('["the published result"]', encoding="utf-8")
            code, printed = self.run_main(["--cases", "1"])
            self.assertEqual(code, 0, printed)
            self.assertEqual(published.read_text(encoding="utf-8"),
                             '["the published result"]')
            partial = results / "f1_f2_clinical.partial.json"
            self.assertTrue(partial.exists(), "the partial run wrote nothing")
            self.assertEqual({r["case"] for r in json.loads(
                partial.read_text(encoding="utf-8"))}, {"MOL-001"})
        self.assertIn("leaves the published result alone", printed)

    def test_a_series_of_a_different_shape_is_refused(self):
        with self.dataset(different_shape=True):
            with self.assertRaises(ValueError) as caught:
                self.run_main()
        self.assertIn("cannot be compared", str(caught.exception))

    def test_a_series_at_different_slice_locations_is_refused(self):
        with self.dataset(moved_slices=True):
            with self.assertRaises(ValueError) as caught:
                self.run_main()
        self.assertIn("slice locations", str(caught.exception))

    def test_the_standard_error_is_recorded_from_the_measured_spread(self):
        """Requirement 11's precision claim, checked against what the driver measured.

        A reviewer pointed out that the old test did arithmetic on an assumed voxel-level sd of
        1 s and never looked at what the driver recorded. The standard error of a difference of
        two means is not one mean's; it must follow from the two recorded spreads.
        """
        with self.dataset(per_hemisphere=40, size=12) as (folder, _calls):
            code, printed = self.run_main()
        self.assertEqual(code, 0, printed)
        written = json.loads((folder / "results" / "f1_f2_clinical.json")
                             .read_text(encoding="utf-8"))
        self.assertTrue(written)
        for record in written:
            left = (record["left_sd"] ** 2 / record["n_left"]
                    * (1 - record["n_left"] / record["left_population"]))
            right = (record["right_sd"] ** 2 / record["n_right"]
                     * (1 - record["n_right"] / record["right_population"]))
            # Both sides must contribute, or this test cannot see one of them being dropped.
            self.assertGreater(left, 0, "the fixture has no spread on the left")
            self.assertGreater(right, 0, "the fixture has no spread on the right")
            self.assertAlmostEqual(record["delta_standard_error"],
                                   math.sqrt(left + right), places=9,
                                   msg=f"{record['case']} {record['series']} "
                                       f"{record['method']}")

    def test_the_draw_being_without_replacement_lowers_the_standard_error(self):
        """The finite-population correction, which a reviewer found missing.

        Drawing 500 of 35,000 voxels without replacement gives a factor of 0.986 -- under one
        percent on the standard error. It matters because this quantity is subtracted from the
        disagreement with the reference maps, and subtracting an inflated variance would erase
        genuine disagreement.
        """
        per_side = {"left": np.array([1.0, 2.0, 3.0, 4.0]),
                    "right": np.array([2.0, 4.0, 6.0, 8.0])}
        # The uncorrected value, written as a closed form rather than approximated with a huge
        # population: var(1,2,3,4) = 5/3 and var(2,4,6,8) = 20/3, each over n = 4.
        uncorrected = math.sqrt((5 / 3) / 4 + (20 / 3) / 4)
        finite = run_clinical.standard_error_of_difference(per_side, {"left": 8, "right": 8})
        self.assertLess(finite, uncorrected)
        # Drawing half of each population halves each variance, so the standard error falls by
        # exactly sqrt(2).
        self.assertAlmostEqual(finite, uncorrected / math.sqrt(2), places=12)

    def test_drawing_the_whole_population_leaves_no_sampling_error(self):
        per_side = {"left": np.array([1.0, 2.0, 3.0]), "right": np.array([4.0, 5.0, 9.0])}
        self.assertEqual(
            run_clinical.standard_error_of_difference(per_side, {"left": 3, "right": 3}), 0.0)

    def test_a_hemisphere_with_too_few_admitted_values_is_refused(self):
        with self.assertRaises(ValueError):
            run_clinical.standard_error_of_difference(
                {"left": np.array([1.0]), "right": np.array([1.0, 2.0])},
                {"left": 10, "right": 10})


class ScreenEndToEnd(unittest.TestCase):
    """run_screen.main(), with the dataset replaced.

    A reviewer pointed out that the suite tested helpers and constants and never ran a driver,
    so the gate that the previous round added -- abort unless every case produced a comparison
    -- was itself untested. That gate is the whole point of the screen, so it is run here.
    """

    @contextlib.contextmanager
    def dataset(self, usable, empty=(), *, results=None, acquisition_files=True,
                short_reference=None, n_times=4, n_slices=2):
        """Plant a dataset on disk.

        ``usable`` maps case name to the asymmetry to plant, ``empty`` cases get no reference
        files. With ``acquisition_files`` the acquisition folder and the time vector are also
        written, which is what lets the screen derive how many reference slices to expect;
        ``short_reference`` names a case whose reference folder is then left one slice short.
        """
        folder = pathlib.Path(tempfile.mkdtemp())
        names = sorted(list(usable) + list(empty))
        for case in names:
            maps = folder / (case + unitobrain.MAPS) / "NLR_TTP"
            maps.mkdir(parents=True)
            if case in usable:
                wanted = n_slices - 1 if case == short_reference else n_slices
                for n in range(max(wanted, 1)):
                    (maps / f"{n:04d}.dcm").write_bytes(b"")
            if acquisition_files:
                series = folder / (case + unitobrain.FILTERED)
                series.mkdir(parents=True)
                for n in range(n_times * n_slices):
                    (series / f"{n:04d}.dcm").write_bytes(b"")
                (folder / (case + unitobrain.MAPS + ".txt")).write_text(
                    " ".join(str(2.81 * i) for i in range(n_times)) + "\n0 0 0 0\n",
                    encoding="utf-8")

        def reference_map(case, series):
            left = 6.0 + usable[case]
            return unitobrain.ReferenceSeries(
                case=case, series=series, images=[ttp_image(left, 6.0)],
                slice_locations=[0.0])

        patched = {"root": lambda: str(folder),
                   "cases": lambda: names,
                   "reference_map": reference_map}
        originals = {name: getattr(unitobrain, name) for name in patched}
        for name, value in patched.items():
            setattr(unitobrain, name, value)
        previous_results = run_screen.RESULTS
        run_screen.RESULTS = str(results or (folder / "results"))
        previous_expected = run_screen.EXPECTED_CASES
        run_screen.EXPECTED_CASES = len(names)
        try:
            yield folder
        finally:
            for name, value in originals.items():
                setattr(unitobrain, name, value)
            run_screen.RESULTS = previous_results
            run_screen.EXPECTED_CASES = previous_expected

    def run_main(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = run_screen.main()
        return code, out.getvalue()

    def test_it_chooses_the_largest_asymmetry_and_writes_the_rule_down(self):
        with self.dataset({"MOL-001": 6.0, "MOL-002": 1.0, "MOL-003": -2.0}) as folder:
            code, printed = self.run_main()
        self.assertEqual(code, 0, printed)
        self.assertIn("MOL-001", printed.splitlines()[-2])
        written = json.loads((folder / "results" / "figure_case.json")
                             .read_text(encoding="utf-8"))
        self.assertEqual(written["chosen"]["case"], "MOL-001")
        self.assertEqual(written["n_cases"], 3)
        self.assertIn("largest absolute left-right", written["rule"])
        self.assertEqual([row["case"] for row in written["ranking"]],
                         ["MOL-001", "MOL-003", "MOL-002"])

    def test_the_largest_asymmetry_wins_whichever_side_it_is_on(self):
        with self.dataset({"MOL-001": 2.0, "MOL-002": -6.0}):
            code, printed = self.run_main()
        self.assertEqual(code, 0, printed)
        self.assertIn("MOL-002", printed)

    def test_an_empty_reference_folder_aborts_the_whole_screen(self):
        """The defect this gate exists for: one usable map among empty folders.

        Before the fix this printed an exclusion, chose MOL-001 and exited 0.
        """
        with self.dataset({"MOL-001": 6.0}, empty=["MOL-002", "MOL-003"]) as folder:
            code, printed = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("ABORT", printed)
        self.assertIn("MOL-002", printed)
        self.assertIn("MOL-003", printed)
        self.assertFalse((folder / "results" / "figure_case.json").exists(),
                         "a figure case was written from a partial set")

    def test_a_partly_extracted_reference_series_aborts(self):
        """A case whose reference folder holds some of its slices, not none of them.

        The previous gate saw a missing case and an empty folder; a reviewer pointed out that
        a folder with half its slices passed both and was ranked on whatever had arrived. The
        expected count comes from the acquisition folder and the time vector, so it needs no
        pixel data -- which is what makes the check affordable here.
        """
        with self.dataset({"MOL-001": 6.0, "MOL-002": 1.0}, acquisition_files=True,
                          short_reference="MOL-002") as folder:
            code, printed = self.run_main()
        self.assertEqual(code, 1, printed)
        self.assertIn("reference slices of", printed)
        self.assertIn("MOL-002", printed)
        self.assertFalse((folder / "results" / "figure_case.json").exists())

    def test_a_complete_reference_series_is_accepted(self):
        """The same check must not reject a case whose extraction is complete."""
        with self.dataset({"MOL-001": 6.0, "MOL-002": 1.0}) as folder:
            code, printed = self.run_main()
        self.assertEqual(code, 0, printed)
        self.assertIn("MOL-001", printed)
        self.assertTrue((folder / "results" / "figure_case.json").exists())

    def test_an_underivable_slice_count_aborts_rather_than_passing(self):
        """The gate must fail closed. A reviewer found it failing open.

        With no acquisition folder the expected slice count cannot be derived -- which is the
        situation in which the data most obviously do not hang together, and the old code
        waved it through.
        """
        with self.dataset({"MOL-001": 6.0, "MOL-002": 1.0},
                          acquisition_files=False) as folder:
            code, printed = self.run_main()
        self.assertEqual(code, 1, printed)
        self.assertIn("could not be derived", printed)
        self.assertFalse((folder / "results" / "figure_case.json").exists())

    def test_each_way_of_failing_to_derive_the_count_is_named(self):
        folder = pathlib.Path(tempfile.mkdtemp())
        original = unitobrain.root
        unitobrain.root = lambda: str(folder)
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertIsNone(run_screen.expected_slices("MOL-001"))
            self.assertIn("no acquisition files", out.getvalue())

            series = folder / ("MOL-001" + unitobrain.FILTERED)
            series.mkdir(parents=True)
            (series / "0000.dcm").write_bytes(b"")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertIsNone(run_screen.expected_slices("MOL-001"))
            self.assertIn("number of acquisitions is unknown", out.getvalue())

            (folder / ("MOL-001" + unitobrain.MAPS + ".txt")).write_text(
                "0 1 2\n0 0 0\n", encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertIsNone(run_screen.expected_slices("MOL-001"))
            self.assertIn("do not divide", out.getvalue())
        finally:
            unitobrain.root = original

    def test_a_missing_case_directory_aborts(self):
        with self.dataset({"MOL-001": 6.0, "MOL-002": 1.0}) as folder:
            run_screen.EXPECTED_CASES = 15        # as the real set is
            code, printed = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("not fully extracted", printed)
        self.assertFalse((folder / "results" / "figure_case.json").exists())


class ReferenceEndToEnd(unittest.TestCase):
    """run_reference.main(), with the clinical file and the reference maps replaced."""

    def clinical_records(self, cases):
        records = []
        for case, dt in cases.items():
            for method, delta in (("raw", 1.0), ("gamma", 2.0)):
                records.append({"case": case, "series": "filtered_3mm", "method": method,
                                "dt": dt, "slice": 0, "slice_location": 0.0, "delta": delta,
                                "delta_standard_error": 0.3})
        return records

    @contextlib.contextmanager
    def inputs(self, cases, *, expected=None, reference=3.0):
        folder = pathlib.Path(tempfile.mkdtemp())
        (folder / "f1_f2_clinical.json").write_text(
            json.dumps(self.clinical_records(cases)), encoding="utf-8")

        def reference_map(case, series):
            return unitobrain.ReferenceSeries(
                case=case, series=series, images=[ttp_image(6.0 + reference, 6.0)],
                slice_locations=[0.0])

        original_map, original_results = unitobrain.reference_map, run_reference.RESULTS
        original_expected = run_reference.EXPECTED_CASES
        unitobrain.reference_map = reference_map
        run_reference.RESULTS = str(folder)
        run_reference.EXPECTED_CASES = len(cases) if expected is None else expected
        try:
            yield folder
        finally:
            unitobrain.reference_map = original_map
            run_reference.RESULTS = original_results
            run_reference.EXPECTED_CASES = original_expected

    def run_main(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = run_reference.main()
        return code, out.getvalue()

    def test_it_writes_one_stratum_per_sampling_interval_and_no_pooled_row(self):
        with self.inputs({"MOL-001": 2.81, "MOL-002": 0.5}) as folder:
            code, printed = self.run_main()
        self.assertEqual(code, 0, printed)
        written = json.loads((folder / "clinical_vs_reference.json").read_text(encoding="utf-8"))
        self.assertEqual([s["stratum"] for s in written["strata"]], ["dt 0.50 s", "dt 2.81 s"])
        self.assertNotIn("all cases", printed)
        self.assertEqual(written["n_cases"], 2)
        self.assertIn("amendment 5", written["pooling"])

    def test_our_own_sampling_noise_is_separated_from_the_method_error(self):
        """A reported RMSE smaller than our own precision is not an error estimate.

        The reference maps average every voxel in the slice; we average 500 per side. On the
        real data the fitted path's RMSE at 2.81 s is 0.32 s against our own sampling error of
        0.33 s -- so nothing of it belongs to the method. A reviewer found this, and the
        correction has to be in the output, not in a footnote.
        """
        # delta 2.0 against a reference of 3.0 gives an error of exactly 1.0, and the fixture's
        # standard error is 0.3, so the residual is sqrt(1 - 0.09) = 0.954.
        with self.inputs({"MOL-001": 2.81, "MOL-002": 0.5}) as folder:
            code, printed = self.run_main()
        self.assertEqual(code, 0, printed)
        written = json.loads((folder / "clinical_vs_reference.json").read_text(encoding="utf-8"))
        for stratum in written["strata"]:
            for method in ("argmax", "fitted"):
                entry = stratum[method]
                self.assertAlmostEqual(entry["our_sampling_standard_error"], 0.3, places=9)
                expected = math.sqrt(entry["rmse"] ** 2 - 0.3 ** 2)
                self.assertAlmostEqual(entry["residual_after_removing_our_sampling"],
                                       expected, places=9)
                self.assertFalse(entry["within_our_own_precision"])

    def test_an_rmse_inside_our_own_precision_is_declared_as_such(self):
        # The reference is set equal to the fitted delta, so the fitted error is 0 and is
        # certainly within the sampling noise.
        with self.inputs({"MOL-001": 2.81, "MOL-002": 0.5}, reference=2.0) as folder:
            code, printed = self.run_main()
        self.assertEqual(code, 0, printed)
        written = json.loads((folder / "clinical_vs_reference.json").read_text(encoding="utf-8"))
        for stratum in written["strata"]:
            self.assertTrue(stratum["fitted"]["within_our_own_precision"])
            self.assertEqual(stratum["fitted"]["residual_after_removing_our_sampling"], 0.0)
        self.assertIn("within our own sampling precision", printed)

    def test_a_subset_from_a_plumbing_run_is_refused(self):
        """run_clinical.py --cases 1 rewrites the clinical file with one case.

        The earlier gate compared the result against that same file, so it passed.
        """
        with self.inputs({"MOL-001": 2.81}, expected=15) as folder:
            code, printed = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("ABORT", printed)
        self.assertIn("run_clinical.py in full", printed)
        self.assertFalse((folder / "clinical_vs_reference.json").exists())

    def test_a_record_without_a_slice_location_is_refused(self):
        with self.inputs({"MOL-001": 2.81}) as folder:
            stale = json.loads((folder / "f1_f2_clinical.json").read_text(encoding="utf-8"))
            for record in stale:
                del record["slice_location"]
            (folder / "f1_f2_clinical.json").write_text(json.dumps(stale), encoding="utf-8")
            with self.assertRaises(ValueError) as caught:
                self.run_main()
        self.assertIn("slice_location", str(caught.exception))

    def test_every_case_lands_in_exactly_one_stratum(self):
        # A reviewer found that dt exactly at the boundary, or NaN, belonged to neither.
        self.assertEqual(run_reference.stratum_of(0.5), "dt 0.50 s")
        self.assertEqual(run_reference.stratum_of(2.81), "dt 2.81 s")
        self.assertEqual(run_reference.stratum_of(run_reference.DT_BOUNDARY), "dt 2.81 s")
        for bad in (float("nan"), float("inf")):
            with self.subTest(dt=bad), self.assertRaises(ValueError):
                run_reference.stratum_of(bad)

    def test_a_case_at_the_boundary_is_still_summarised(self):
        with self.inputs({"MOL-001": run_reference.DT_BOUNDARY, "MOL-002": 0.5}) as folder:
            code, printed = self.run_main()
        self.assertEqual(code, 0, printed)
        written = json.loads((folder / "clinical_vs_reference.json").read_text(encoding="utf-8"))
        self.assertEqual(sum(s["n"] for s in written["strata"]), 2)


if __name__ == "__main__":
    unittest.main()
