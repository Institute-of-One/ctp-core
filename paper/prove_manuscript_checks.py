"""Prove the manuscript checks by breaking the manuscript in the ways they claim to catch.

    python paper/prove_manuscript_checks.py

The checks passed on their first run, which is the least informative outcome there is: a clean
manuscript and a blind checker are indistinguishable from the result alone. One of them *was*
blind. Its pattern for allowed bold ended in an alternation admitting any sentence shorter than
120 characters with no internal full stop -- that is to say, every bold lead-in the rule exists
to forbid -- and it reported a manuscript carrying six of them as passing.

Each case below edits the built manuscript in memory and requires the named check to object.
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import check_manuscript as checker  # noqa: E402

CASES = [
    ("a bold lead-in sentence of the kind the author keeps objecting to",
     "check_bold",
     lambda d: d.replace("## Results\n", "## Results\n\n**The arterial input dominates "
                                        "everything else measured here.** ")),
    ("a bold sentence just under the old pattern's 120-character limit",
     "check_bold",
     lambda d: d.replace("## Discussion\n", "## Discussion\n\n**Two of the four choices "
                                            "account for nearly all of the movement observed "
                                            "in this study.** ")),
    ("a figure that is never cited in the body",
     "check_figures",
     lambda d: d.replace("Figure 4", "Figure IV", 1).replace(
         "(Figure 4)", "").replace("Figure 4 shows", "The last figure shows")),
    ("a number in the text that is in no results file",
     "check_numbers",
     lambda d: d.replace("## Discussion", "## Discussion\n\nThe effect was 7.43 s.", 1)),
    ("a citation with no reference",
     "check_citations",
     lambda d: d.replace("## Discussion", "## Discussion\n\nAs shown elsewhere.[99]", 1)),
    ("a reference that nothing cites",
     "check_citations",
     lambda d: d + "\n13. Someone S. An uncited work. J Irrelevant 2020;1:1. doi:10/x\n"),
    ("a figure whose alt text was dropped",
     "check_figures",
     lambda d: d.replace("Alt text:", "Caption continues:", 1)),
    ("the data availability section removed, with the phrase left elsewhere",
     "check_statements",
     lambda d: d.replace("## Data availability", "## Acknowledgements", 1)),
    ("the ethics statement removed from the Methods",
     "check_statements",
     lambda d: d.replace("No institutional review board approval was", "None was", 1)),
    ("the consent statement removed from the Methods",
     "check_statements",
     lambda d: d.replace("informed consent", "informed agreement", 1)),
]

AFFILIATION_CASES = [
    ("a title page without the affiliation", lambda t: t.replace("Institute of One", "Somewhere")),
]


def main() -> int:
    document = checker.read("manuscript.md")
    title_page = checker.read("title_page.md")

    baseline = {name: getattr(checker, name)(document if name != "check_affiliation"
                                             else title_page)
                for name in ("check_bold", "check_figures", "check_numbers",
                             "check_citations", "check_statements", "check_affiliation")}
    unclean = {k: v for k, v in baseline.items() if v}
    if unclean:
        print("the unmodified manuscript does not pass, so nothing below means anything:")
        for name, problems in unclean.items():
            print(f"  {name}: {problems}")
        return 1
    print("baseline: the manuscript passes every check\n")

    missed = 0
    for description, check_name, break_it in CASES:
        broken = break_it(document)
        if broken == document:
            print(f"SETUP    {description}: the edit changed nothing")
            missed += 1
            continue
        problems = getattr(checker, check_name)(broken)
        if problems:
            print(f"caught   {description}\n         {problems[0][:95]}")
        else:
            missed += 1
            print(f"MISSED   {description}\n         {check_name} reported nothing")

    for description, break_it in AFFILIATION_CASES:
        problems = checker.check_affiliation(break_it(title_page))
        if problems:
            print(f"caught   {description}\n         {problems[0][:95]}")
        else:
            missed += 1
            print(f"MISSED   {description}")

    total = len(CASES) + len(AFFILIATION_CASES)
    print(f"\n{total - missed} of {total} broken manuscripts were rejected")
    return 1 if missed else 0


if __name__ == "__main__":
    raise SystemExit(main())
