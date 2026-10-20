"""Prove the driver tests by injection.

    python paper/analysis/prove_driver_gates.py

A check nobody has seen fail is not evidence (AGENTS.md section 7). Each mutation below is a
defect the test module claims to catch. The suite is copied to a temporary directory, the
mutation applied there, and the suite run: the named test must be among those that fail. Other
tests may fail too -- one defect can legitimately trip several checks -- and they are listed.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

SOURCE = pathlib.Path(__file__).resolve().parent

MUTATIONS = [
    (
        "split at the image centre instead of the mask centroid",
        "run_screen.py",
        "    split = hemispheres(mask)",
        "    class _Fixed:\n"
        "        pass\n"
        "    split = _Fixed()\n"
        "    centre = ttp.shape[1] // 2\n"
        "    split.midline = centre\n"
        "    split.left = mask.copy(); split.left[:, centre:] = False\n"
        "    split.right = mask.copy(); split.right[:, :centre] = False",
        "test_the_midline_follows_an_off_centre_head",
    ),
    (
        "drop the per-side minimum and keep only the total",
        "run_screen.py",
        "    if split.left.sum() < MIN_VOXELS or split.right.sum() < MIN_VOXELS:\n"
        "        return None",
        "    pass",
        "test_a_slice_with_too_little_tissue_on_one_side_is_not_compared",
    ),
    (
        "admit background zeros as fast tissue",
        "run_screen.py",
        "TTP_MIN, TTP_MAX = 0.5, 20.0",
        "TTP_MIN, TTP_MAX = -1.0, 20.0",
        "test_background_zeros_are_not_admitted_as_fast_tissue",
    ),
    (
        "admit vessels by removing the upper bound",
        "run_screen.py",
        "TTP_MIN, TTP_MAX = 0.5, 20.0",
        "TTP_MIN, TTP_MAX = 0.5, 1e9",
        "test_vessels_are_excluded_by_the_upper_bound",
    ),
    (
        "cut the clinical sample to a hundred voxels per hemisphere",
        "run_clinical.py",
        "N_PER_HEMISPHERE = 500",
        "N_PER_HEMISPHERE = 100",
        "test_the_frozen_sampling_rule_is_the_one_in_the_protocol",
    ),
    (
        "drop the clinical sampling interval from the synthetic grid",
        "run_synthetic.py",
        "DT_LEVELS = [0.5, 1.0, 2.0, 2.81, 4.0]",
        "DT_LEVELS = [0.5, 1.0, 2.0, 4.0]",
        "test_both_clinical_sampling_intervals_are_on_the_grid",
    ),
    (
        "take ten repeats instead of two hundred",
        "run_synthetic.py",
        "N_REPEATS = 200",
        "N_REPEATS = 10",
        "test_the_repeat_count_resolves_the_floor_it_is_used_to_test",
    ),
    (
        "drop the measured clinical errors from the propagation grid",
        "run_propagation.py",
        "RATIOS = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 6.97, 10.47]",
        "RATIOS = [1.0, 2.0, 3.0]",
        "test_the_measured_clinical_errors_are_on_the_grid",
    ),
    (
        "restate the window in run_reference instead of deriving it, and let it drift",
        "run_reference.py",
        "TTP_MIN, TTP_MAX = run_screen.TTP_MIN, run_screen.TTP_MAX",
        "TTP_MIN, TTP_MAX = 0.5, 30.0",
        "test_the_ttp_windows_are_identical",
    ),
    (
        "admit a hemisphere summarised from a handful of values",
        "run_clinical.py",
        "MIN_ADMITTED = 100",
        "MIN_ADMITTED = 3",
        "test_a_hemisphere_is_not_summarised_from_a_handful_of_values",
    ),
    (
        "take the busiest slice as the first one instead of the one with the most tissue",
        "unitobrain.py",
        "    return int(np.argmax([tissue_mask(volume[:, i]).sum() for i in range(volume.shape[1])]))",
        "    return 0",
        "test_the_busiest_slice_is_the_one_with_the_most_tissue",
    ),
    (
        "admit tissue the bolus never reached",
        "unitobrain.py",
        "BASELINE_MIN, BASELINE_MAX, MIN_PEAK = -10.0, 200.0, 5.0",
        "BASELINE_MIN, BASELINE_MAX, MIN_PEAK = -10.0, 200.0, -1e9",
        "test_the_tissue_mask_needs_a_bolus_to_have_arrived",
    ),
    (
        "admit air and bone as tissue",
        "unitobrain.py",
        "BASELINE_MIN, BASELINE_MAX, MIN_PEAK = -10.0, 200.0, 5.0",
        "BASELINE_MIN, BASELINE_MAX, MIN_PEAK = -1e9, 1e9, 5.0",
        "test_air_and_bone_are_not_admitted",
    ),
    (
        "ignore the environment and return one machine's dataset path",
        "unitobrain.py",
        '    value = os.environ.get(ROOT_VARIABLE, "").strip().strip(\'"\')',
        '    value = os.path.dirname(os.path.abspath(__file__))',
        "test_the_root_comes_from_the_environment",
    ),
    (
        "fall back to a hard-coded default when the environment says nothing",
        "unitobrain.py",
        '    value = os.environ.get(ROOT_VARIABLE, "").strip().strip(\'"\')',
        '    value = os.environ.get(ROOT_VARIABLE) or os.path.dirname(__file__)',
        "test_an_unset_root_is_an_error_that_names_the_variable",
    ),
    (
        "accept a root that is not a directory",
        "unitobrain.py",
        "    if not os.path.isdir(value):\n"
        "        raise RuntimeError(f\"{ROOT_VARIABLE} is set to {value!r}, which is not a "
        "directory\")",
        "    pass",
        "test_a_root_that_is_not_a_directory_is_refused",
    ),
    (
        "write one machine's path back into a driver",
        "run_screen.py",
        "import unitobrain  # noqa: E402",
        "import unitobrain  # noqa: E402\n\n_LOCAL = r\"D:" + chr(92) + "wherever" + chr(92)
        + "UniToBrain\"",
        "test_no_machine_specific_path_is_committed",
    ),
    # The mutations below correspond to the defects the 2026-10-19 cross-check found in the
    # drivers and in the first version of their tests. Each one was a real defect, and each
    # one left every test green at the time it was reported.
    (
        "summarise with a mean where the protocol says median",
        "run_screen.py",
        "    return float(np.median(ttp[split.left]) - np.median(ttp[split.right]))",
        "    return float(ttp[split.left].mean() - ttp[split.right].mean())",
        "test_the_statistic_is_a_median_and_not_a_mean",
    ),
    (
        "let the two screens' total-voxel minimums drift apart",
        "run_reference.py",
        "MIN_TOTAL = 2 * MIN_PER_SIDE",
        "MIN_TOTAL = 4 * MIN_PER_SIDE",
        "test_the_total_minimum_is_identical_too",
    ),
    (
        "take the bolus arrival off the jitter and onto a sampling instant",
        "run_synthetic.py",
        "    return NOMINAL_ARRIVAL + float(rng.uniform(0.0, dt))",
        "    return NOMINAL_ARRIVAL",
        "test_arrival_is_jittered_across_one_whole_sampling_interval",
    ),
    (
        "jitter the arrival over a tenth of the interval instead of all of it",
        "run_synthetic.py",
        "    return NOMINAL_ARRIVAL + float(rng.uniform(0.0, dt))",
        "    return NOMINAL_ARRIVAL + float(rng.uniform(0.0, dt / 10.0))",
        "test_arrival_is_jittered_across_one_whole_sampling_interval",
    ),
    (
        "draw the clinical voxels from an advancing shared generator",
        "run_clinical.py",
        "    rng = np.random.default_rng(seed)\n    picks = {}",
        "    rng = draw_voxels.__dict__.setdefault('rng', np.random.default_rng(seed))\n"
        "    picks = {}",
        "test_the_draw_does_not_depend_on_the_order_it_is_called_in",
    ),
    (
        "draw voxels that are not in the hemisphere they are attributed to",
        "run_clinical.py",
        '        mask = getattr(split, side)',
        '        mask = split.left if side == "right" else getattr(split, side)',
        "test_every_drawn_voxel_lies_inside_its_own_hemisphere",
    ),
    (
        "draw from a hemisphere with fewer voxels than the sample without saying so",
        "run_clinical.py",
        "        if rows.size < n_per_hemisphere:",
        "        if False:",
        "test_a_hemisphere_too_small_to_draw_from_is_refused_by_name",
    ),
    (
        "accept a grid that lies entirely below the implementation's ceilings",
        "run_propagation.py",
        '    key = f"{map_name}_clipped"\n'
        "    return any(not r[key] for r in records) and any(r[key] for r in records)",
        '    key = f"{map_name}_clipped"\n'
        "    return any(not r[key] for r in records)",
        "test_the_run_refuses_a_grid_that_does_not_straddle_the_ceiling",
    ),
    (
        "index the reference maps without checking they are in the volume's order",
        "unitobrain.py",
        "            if abs(found - expected_location) > 1e-6:",
        "            if False:",
        "test_a_mismatched_position_is_refused_rather_than_returned",
    ),
    (
        "read past the end of a reference series",
        "unitobrain.py",
        "        if not 0 <= index < len(self.images):",
        "        if False:",
        "test_an_index_past_the_end_is_refused_and_says_what_was_asked_for",
    ),
    (
        "accept a case whose time vector does not match its acquisitions",
        "unitobrain.py",
        "    if times.size != volume.shape[0] or aif.size != volume.shape[0]:",
        "    if False:",
        "test_a_time_vector_of_the_wrong_length_is_refused",
    ),
    # Round three: the defects the cross-check found in the round-one fixes, and the fixes a
    # reviewer pointed out no test was protecting.
    (
        "treat either map clipping as both maps saturating",
        "run_propagation.py",
        '    key = f"{map_name}_clipped"\n'
        "    return any(not r[key] for r in records) and any(r[key] for r in records)",
        '    return (any(not (r["cbv_clipped"] or r["cbf_clipped"]) for r in records)\n'
        '            and any(r["cbv_clipped"] or r["cbf_clipped"] for r in records))',
        "test_the_two_maps_are_judged_separately",
    ),
    (
        "let a non-finite slice position pass the correspondence check",
        "unitobrain.py",
        "            if not (math.isfinite(found) and math.isfinite(expected_location)):",
        "            if False:",
        "test_a_non_finite_position_cannot_defeat_the_check",
    ),
    (
        "accept a series with an acquisition missing from the middle",
        "unitobrain.py",
        "    if stamps != list(range(stamps[0], stamps[0] + len(stamps))):",
        "    if False:",
        "test_a_gap_in_the_acquisition_numbers_is_refused",
    ),
    (
        "let two files at the same position overwrite one another",
        "unitobrain.py",
        "        if location in by_time[stamp]:",
        "        if False:",
        "test_two_files_at_the_same_position_are_refused",
    ),
    (
        "accept a ragged volume",
        "unitobrain.py",
        "        if sorted(by_time[stamp]) != locations:",
        "        if False:",
        "test_a_ragged_volume_is_refused",
    ),
    (
        "let the screen choose a figure case from a partly extracted set",
        "run_screen.py",
        '    missing = sorted(set(names) - {row["case"] for row in rows})',
        "    missing = []",
        "test_an_empty_reference_folder_aborts_the_whole_screen",
    ),
    (
        "compare the reference result against whatever the clinical file holds",
        "run_reference.py",
        "    if len(cases) != EXPECTED_CASES or len(rows) != EXPECTED_CASES:",
        "    if len(rows) != len(cases):",
        "test_a_subset_from_a_plumbing_run_is_refused",
    ),
    (
        "read a stale clinical file with .get instead of refusing it",
        "run_reference.py",
        '        for field in ("slice_location", "delta_standard_error"):\n'
        '            if field not in raw or field not in gamma:\n'
        "                raise ValueError(\n"
        '                    f"{source} predates this driver: {case} has no {field}. Re-run "\n'
        '                    "run_clinical.py. Skipping a check because the input is old is how a "\n'
        '                    "wrong slice gets compared, or a sampling error gets ignored.")',
        '        raw = dict(raw, slice_location=raw.get("slice_location"),\n'
        '                   delta_standard_error=raw.get("delta_standard_error", 0.0))\n'
        '        gamma = dict(gamma, delta_standard_error=gamma.get("delta_standard_error", 0.0))',
        "test_a_record_without_a_slice_location_is_refused",
    ),
    (
        "drop a case at the stratum boundary from every summary",
        "run_reference.py",
        '          ("dt 2.81 s", lambda dt: dt >= DT_BOUNDARY))',
        '          ("dt 2.81 s", lambda dt: dt > DT_BOUNDARY))',
        "test_every_case_lands_in_exactly_one_stratum",
    ),
    (
        "put a pooled stratum back",
        "run_reference.py",
        '          ("dt 2.81 s", lambda dt: dt >= DT_BOUNDARY))',
        '          ("dt 2.81 s", lambda dt: dt >= DT_BOUNDARY),\n'
        '          ("all cases", lambda dt: True))',
        "test_it_writes_one_stratum_per_sampling_interval_and_no_pooled_row",
    ),
    (
        "rebind stdout so a driver cannot be called from a test",
        "driver_io.py",
        '    buffer = getattr(sys.stdout, "buffer", None)\n    if buffer is not None:',
        "    buffer = sys.stdout.buffer\n    if True:",
        "test_it_chooses_the_largest_asymmetry_and_writes_the_rule_down",
    ),
    # Round four. The pooled-row and boundary injections above were caught only because
    # stratum_of raises, as a reviewer pointed out; this one adds the row where stratum_of
    # cannot see it, so the assertion has to do the work.
    (
        "append a pooled row where stratum_of cannot see it",
        "run_reference.py",
        "    strata.append(summary)",
        "    strata.append(summary)\n"
        "    strata.append({\"stratum\": \"all cases\", \"n\": len(rows),\n"
        "                   \"argmax\": strata[0][\"argmax\"], \"fitted\": strata[0][\"fitted\"]})",
        "test_it_writes_one_stratum_per_sampling_interval_and_no_pooled_row",
    ),
    (
        "take the arterial median over whatever survived",
        "run_aif.py",
        "    if n_directories == n_measured == n_usable == EXPECTED_CASES:",
        "    if True:",
        "test_any_shortfall_is_refused_and_says_which",
    ),
    (
        "accept an area ratio of zero as a measurement",
        "run_aif.py",
        '                     if np.isfinite(r["area_ratio"]) and r["area_ratio"] > 0.0])',
        '                     if np.isfinite(r["area_ratio"])])',
        "test_a_ratio_of_zero_is_not_a_measurement",
    ),
    (
        "admit an infinite voxel as evidence that a bolus arrived",
        "unitobrain.py",
        "    finite = np.isfinite(slab).all(axis=0)",
        "    finite = np.ones(slab.shape[1:], dtype=bool)",
        "test_an_infinite_voxel_is_not_tissue",
    ),
    (
        "drop the shape check between the two input series",
        "run_clinical.py",
        "            if acquisition.volume.shape != filtered.volume.shape:",
        "            if False:",
        "test_a_series_of_a_different_shape_is_refused",
    ),
    (
        "drop the slice-location check between the two input series",
        "run_clinical.py",
        "            if acquisition.slice_locations != filtered.slice_locations:",
        "            if False:",
        "test_a_series_at_different_slice_locations_is_refused",
    ),
    (
        "drop the acquisition-number check between the two input series",
        "run_clinical.py",
        "            if acquisition.acquisitions != filtered.acquisitions:",
        "            if False:",
        "test_a_series_covering_different_acquisitions_is_refused",
    ),
    (
        "take the standard error of one mean as the standard error of the difference",
        "run_clinical.py",
        '    total = 0.0\n    for side in ("left", "right"):',
        '    total = 0.0\n    for side in ("left",):',
        "test_the_standard_error_is_recorded_from_the_measured_spread",
    ),
    (
        "report the raw RMSE without removing our own sampling noise",
        "run_reference.py",
        '            residual = rmse ** 2 - sampling ** 2',
        '            residual = rmse ** 2',
        "test_our_own_sampling_noise_is_separated_from_the_method_error",
    ),
    (
        "let the sampling rule drift off the frozen count",
        "run_clinical.py",
        "N_PER_HEMISPHERE = 500",
        "N_PER_HEMISPHERE = 450",
        "test_the_frozen_sampling_rule_is_the_one_in_the_protocol",
    ),
    (
        "take the slice positions from the first acquisition and drop the rest",
        "unitobrain.py",
        "        if sorted(by_time[stamp]) != locations:",
        "        if len(by_time[stamp]) < len(locations):",
        "test_a_short_first_acquisition_is_refused_too",
    ),
    (
        "rank a case whose reference series is only partly extracted",
        "run_screen.py",
        "        if n_files != expected:",
        "        if False:",
        "test_a_partly_extracted_reference_series_aborts",
    ),
    # Round five.
    (
        "fail open when the expected reference slice count cannot be derived",
        "run_screen.py",
        "        if expected is None:",
        "        if False:",
        "test_an_underivable_slice_count_aborts_rather_than_passing",
    ),
    (
        "let a plumbing run overwrite the published clinical result",
        "run_clinical.py",
        '        output = "f1_f2_clinical.partial.json"',
        "        pass",
        "test_a_plumbing_run_cannot_destroy_the_published_result",
    ),
    (
        "drop the finite-population correction from the standard error",
        "run_clinical.py",
        "        correction = max(0.0, 1.0 - n / population) if population else 1.0",
        "        correction = 1.0",
        "test_the_draw_being_without_replacement_lowers_the_standard_error",
    ),
    (
        "say nothing about why the expected slice count could not be established",
        "run_screen.py",
        '        print(f"{case}: WARNING - no acquisition files under "\n'
        '              f"{case + unitobrain.FILTERED}; the expected slice count cannot be '
        'established")\n'
        "        return None",
        "        return None",
        "test_each_way_of_failing_to_derive_the_count_is_named",
    ),
    # Round six.
    (
        "count the expected slices by division, so a partly extracted folder passes",
        "run_screen.py",
        "    pairs = set()",
        '    return len(files) // max(1, len(open(text, encoding="utf-8")\n'
        "                                   .readline().split())) if os.path.isfile(text) "
        "else None\n    pairs = set()",
        "test_a_partly_extracted_reference_series_aborts",
    ),
    (
        "accept an acquisition folder that does not fill its own grid",
        "run_screen.py",
        "    if len(acquisitions) * len(locations) != len(files):",
        "    if False:",
        "test_each_way_of_failing_to_derive_the_count_is_named",
    ),
    (
        "accept duplicate acquisition files in the screen",
        "run_screen.py",
        "    if len(pairs) != len(files):",
        "    if False:",
        "test_each_way_of_failing_to_derive_the_count_is_named",
    ),
    (
        "really fail open when the expected slice count cannot be established",
        "run_screen.py",
        '            print(f"{case}: EXCLUDED - the expected number of reference slices could '
        'not be "\n                  "derived (see the warning above)")\n            continue',
        "            expected = n_files",
        "test_an_underivable_slice_count_aborts_rather_than_passing",
    ),
    (
        "accept a time vector that is not strictly increasing",
        "unitobrain.py",
        "    if not np.all(np.isfinite(times)) or not np.all(np.diff(times) > 0):",
        "    if False:",
        "test_a_time_vector_that_is_not_increasing_is_refused",
    ),
    (
        "order the reference maps by file name again",
        "unitobrain.py",
        "    found.sort(key=lambda pair: pair[0])",
        "    pass",
        "test_reference_map_sorts_by_position_not_by_file_name",
    ),
    (
        "accept two reference slices at the same position",
        "unitobrain.py",
        "    if len(set(locations)) != len(locations):",
        "    if False:",
        "test_two_reference_slices_at_the_same_position_are_refused",
    ),
    (
        "stop jittering the arrival inside the synthetic driver's own loop",
        "run_synthetic.py",
        "                arrival = arrival_time(rng, dt)",
        "                arrival = NOMINAL_ARRIVAL",
        "test_the_synthetic_arm_jitters_arrival_rather_than_landing_on_the_grid",
    ),
    (
        "skip the straddle abort inside the propagation driver's own main",
        "run_propagation.py",
        "        if not straddles_the_ceiling(records, name):",
        "        if False:",
        "test_the_propagation_arm_refuses_a_grid_that_does_not_straddle",
    ),
    (
        "take the standard error of one mean, where the formula now lives",
        "run_clinical.py",
        '    for side in ("left", "right"):\n        values = per_side[side]',
        '    for side in ("left",):\n        values = per_side[side]',
        "test_both_sides_contribute_to_the_difference",
    ),
]


def ambiguous(expected: str, output: str) -> list[str]:
    """Every qualified test name whose method matches ``expected``, when more than one does."""
    if "." in expected:
        return []
    found = set()
    for line in output.splitlines():
        parts = line.split(" ", 1)
        if len(parts) == 2 and parts[0] == expected and parts[1].startswith("("):
            found.add(parts[1].strip("()").split(" ")[0])
    return sorted(found) if len(found) > 1 else []


def run(folder: pathlib.Path) -> subprocess.CompletedProcess:
    """Run the suite in ``folder``, with the real ctp_core importable.

    The mutated files are the copies in ``folder``; ctp_core comes from the repository and is
    never mutated. Without it the end-to-end tests of the drivers cannot run at all, and the
    mutations aimed at those drivers would be scored as missed.
    """
    environment = dict(os.environ)
    repository = str(pathlib.Path(__file__).resolve().parents[2])
    environment["PYTHONPATH"] = os.pathsep.join(
        [repository] + ([environment["PYTHONPATH"]] if environment.get("PYTHONPATH") else []))
    return subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", ".", "-v"],
        cwd=folder, capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=environment,
    )


def failed_tests(output: str) -> tuple[set[str], set[str]]:
    """The tests that failed on an assertion, and the ones that raised.

    These are kept apart because they are not the same evidence. A FAIL means the test saw the
    defect and said so. An ERROR can mean that too, but it can also mean the mutation broke the
    test for an unrelated reason, which proves nothing about the check. A reviewer found one
    mutation here being scored as caught when it had only made the test raise.
    """
    failures, errors = set(), set()
    for line in output.splitlines():
        for marker, bucket in (("FAIL: ", failures), ("ERROR: ", errors)):
            if not line.startswith(marker):
                continue
            method, _, qualified = line[len(marker):].partition(" ")
            # Both forms are recorded. unittest prints "method (module.Class.method)", and a
            # bare method name is ambiguous: a reviewer found that
            # test_a_non_positive_interval_is_refused exists in QuantisationFloor and in
            # SyntheticDesign, so a failure in the wrong one would have scored as a catch.
            bucket.add(method)
            bucket.add(qualified.strip("()"))
    return failures, errors


def main() -> int:
    with tempfile.TemporaryDirectory() as temp:
        clean = pathlib.Path(temp) / "clean"
        shutil.copytree(SOURCE, clean, ignore=shutil.ignore_patterns("__pycache__"))
        baseline = run(clean)
        if baseline.returncode != 0:
            print("the unmutated suite does not pass, so nothing below means anything")
            print(baseline.stdout[-4000:], baseline.stderr[-4000:])
            return 1
        total = baseline.stderr.count("... ok")
        print(f"baseline: {total} tests pass\n")

        bad = 0
        raised = 0
        for description, filename, before, after, expected in MUTATIONS:
            work = pathlib.Path(temp) / "work"
            if work.exists():
                shutil.rmtree(work)
            shutil.copytree(clean, work, ignore=shutil.ignore_patterns("__pycache__"))
            names = (filename,) if isinstance(filename, str) else filename
            broken = False
            for name in names:
                target = work / name
                text = target.read_text(encoding="utf-8")
                if text.count(before) != 1:
                    print(f"SETUP ERROR  {description}: the text to mutate appears "
                          f"{text.count(before)} times in {name}")
                    broken = True
                    break
                target.write_text(text.replace(before, after), encoding="utf-8")
            if broken:
                bad += 1
                continue

            result = run(work)
            clash = ambiguous(expected, baseline.stderr)
            if clash:
                print(f"SETUP ERROR  {description}: {expected} is ambiguous; it names "
                      f"{', '.join(clash)}. Give the qualified name.")
                bad += 1
                continue
            failures, errors = failed_tests(result.stderr)
            caught = failures | errors
            # Both the bare and the qualified name of every red test are recorded, so the
            # display keeps only the qualified ones and falls back to a bare name that has no
            # qualified form. Otherwise every extra failure is listed twice.
            qualified = {n for n in caught if "." in n}
            methods = {n.rsplit(".", 1)[-1] for n in qualified}
            others = sorted({n for n in qualified if not n.endswith("." + expected)}
                            | {n for n in caught
                               if "." not in n and n != expected and n not in methods})
            extra = f"  (also {', '.join(others)})" if others else ""
            if result.returncode == 0:
                print(f"MISSED       {description}\n             no test failed")
                bad += 1
            elif expected in failures:
                print(f"caught       {description}\n             by {expected}{extra}")
            elif expected in errors:
                # The named test went red because the defect made the code raise where it
                # should have returned -- for instance a bare KeyError where the removed guard
                # used to give a clear ValueError. That is detection, and unittest only files
                # an escaped exception under ERROR rather than FAIL. It is printed separately
                # because an exception can also mean the mutation broke the test for an
                # unrelated reason, and that is worth a look rather than a count.
                raised += 1
                print(f"caught (raised) {description}\n             {expected} went red by "
                      f"raising rather than by a failed assertion{extra}")
            else:
                print(f"WRONG TEST   {description}\n             expected {expected}, "
                      f"got {sorted(caught) or 'a collection error'}")
                if not caught:
                    print(result.stderr[-1500:])
                bad += 1

        caught_total = len(MUTATIONS) - bad
        print(f"\n{caught_total} of {len(MUTATIONS)} injected defects were caught by the test "
              "that claims to catch them")
        print(f"of those, {caught_total - raised} went red on that test's own assertion and "
              f"{raised} went red because the defect made the code raise")
        if raised:
            print("A raised catch shows the test covers the path, not that its assertion "
                  "would have fired. Read those lines before relying on them.")
        return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
