"""Prove the reference checker by giving it references that are wrong.

    python paper/prove_reference_check.py

A clean run and a broken checker look identical, and this checker was broken: its first version
marked ten of twelve correct references as wrong, and fixing that meant loosening three
comparisons. Loosening a check is exactly when it must be shown to still bite. Each case below
is a way a reference list goes wrong in practice, and the checker must reject it.

The last case is the one that motivated the whole file. Writing the list, a DOI assembled from a
plausible pattern -- 10.1088/0031-9155/37/7/004 for Madsen 1992, which is really ...37/7/010 --
resolved to an unrelated paper in the same journal and issue. Nothing but a query catches that,
and on an earlier paper in this programme two of twenty-one references pointed at the wrong work.
"""

from __future__ import annotations

import copy
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import check_references as checker  # noqa: E402
import references as bib  # noqa: E402

CASES = [
    ("a DOI that does not exist at all",
     {"doi": "10.9999/not.a.real.doi.12345"}, "resolve"),
    ("the wrong DOI, resolving to another paper in the same journal and issue",
     {"doi": "10.1088/0031-9155/37/7/004"}, "different paper"),
    ("the year of a neighbouring issue",
     {"year": 1991}, "year"),
    ("a transposed volume number",
     {"volume": "73"}, "volume"),
    ("a page range from the article before it",
     {"pages": "1585-1596"}, "pages"),
    ("a journal that is not this journal",
     {"journal": "Radiology"}, "journal"),
]

#: Madsen 1992 is the subject: short, unambiguous, and the reference whose DOI was got wrong.
SUBJECT = "gamma_variate"


def main() -> int:
    original = bib.REFERENCES[SUBJECT]
    problems, notes = checker.check(SUBJECT, original)
    if problems:
        print("the unmutated reference does not check out, so nothing below means anything:")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print(f"baseline: {SUBJECT} checks out"
          + (f" ({len(notes)} note)" if notes else "") + "\n")

    missed = 0
    for description, change, expected in CASES:
        broken = copy.deepcopy(original)
        broken.update(change)
        problems, _ = checker.check(SUBJECT, broken)
        matching = [p for p in problems if expected in p]
        if matching:
            print(f"caught   {description}\n         {matching[0]}")
        else:
            missed += 1
            print(f"MISSED   {description}\n         "
                  f"{problems or 'the checker reported nothing'}")

    print(f"\n{len(CASES) - missed} of {len(CASES)} bad references were rejected")
    return 1 if missed else 0


if __name__ == "__main__":
    raise SystemExit(main())
