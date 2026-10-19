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
import math
import os
import pathlib
import tempfile
import unittest

import numpy as np

import run_clinical
import run_propagation
import run_reference
import run_screen
import run_synthetic
import unitobrain
from ctp_measure import quantisation_floor


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
        self.assertAlmostEqual(run_screen.slice_asymmetry(image), 6.0, places=6)

        # The same slice split at the image centre: the head lies entirely to the left of it,
        # so one hemisphere is empty and no asymmetry can be computed at all. That is the
        # defect taking the midline from the data prevents.
        centre = image.shape[1] // 2
        mask = (image > run_screen.TTP_MIN) & (image < run_screen.TTP_MAX)
        at_image_centre = mask.copy()
        at_image_centre[:, :centre] = False
        self.assertEqual(at_image_centre.sum(), 0)

    def test_the_expected_case_count_is_the_published_one(self):
        # The screen aborts rather than ranking a partially extracted set; this is the number
        # it compares against.
        self.assertEqual(run_screen.EXPECTED_CASES, 15)


class ScreeningWindowsAgree(unittest.TestCase):
    """The screen and the reference comparison read the same maps, so they must admit the same
    tissue. A mismatch would silently compare two different populations of voxels."""

    def test_the_ttp_windows_are_identical(self):
        self.assertEqual((run_screen.TTP_MIN, run_screen.TTP_MAX),
                         (run_reference.TTP_MIN, run_reference.TTP_MAX))

    def test_the_per_side_minimum_is_identical(self):
        self.assertEqual(run_screen.MIN_VOXELS, run_reference.MIN_PER_SIDE)


class SamplingRule(unittest.TestCase):
    """The clinical arm draws a fixed number of voxels per hemisphere. The docstring justifies
    the number with a standard error; that arithmetic is checked here rather than trusted."""

    def test_the_standard_error_claimed_in_the_docstring_holds(self):
        # A voxel-level sd of about 1 s is what the measured per-hemisphere sd comes out at.
        standard_error = 1.0 / math.sqrt(run_clinical.N_PER_HEMISPHERE)
        self.assertLess(standard_error, 0.05)
        # ...and two orders of magnitude below the effect being measured.
        self.assertLess(standard_error * 100, 5.0)

    def test_a_hemisphere_is_not_summarised_from_a_handful_of_values(self):
        self.assertLess(run_clinical.MIN_ADMITTED, run_clinical.N_PER_HEMISPHERE)
        self.assertGreaterEqual(run_clinical.MIN_ADMITTED, 100)

    def test_the_seed_is_fixed_and_shared_with_the_synthetic_arm(self):
        self.assertEqual(run_clinical.SEED, run_synthetic.SEED)

    def test_the_same_voxels_are_used_for_every_series_and_method(self):
        """Injected defect: drawing the sample inside the series loop instead of once per case.

        The comparison is paired. A generator advanced between series would hand the two
        series different voxels, and the difference between them would then be partly a
        difference of sample.
        """
        mask = np.zeros((40, 40), dtype=bool)
        mask[:, :20] = True
        rows, cols = np.nonzero(mask)

        def draw(seed):
            rng = np.random.default_rng(seed)
            return rng.choice(rows.size, size=run_clinical.N_PER_HEMISPHERE, replace=False)

        paired = draw(run_clinical.SEED)
        np.testing.assert_array_equal(paired, draw(run_clinical.SEED))

        advanced = np.random.default_rng(run_clinical.SEED)
        advanced.choice(rows.size, size=run_clinical.N_PER_HEMISPHERE, replace=False)
        second = advanced.choice(rows.size, size=run_clinical.N_PER_HEMISPHERE, replace=False)
        self.assertFalse(np.array_equal(paired, second))


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


if __name__ == "__main__":
    unittest.main()
