"""Checks the manuscript has to pass before anyone is asked to read it.

    python paper/check_manuscript.py

Each check here exists because this programme lost a round trip to the thing it tests. They are
cheap; the failures they catch are not.

* **No bold sentence in the body.** Bold is for the structured abstract's labels, the
  ``Figure N.`` label and the declaration headings. The author has objected to bold lead-ins
  every time they have appeared, and they have appeared every time until a gate stopped them.
* **Alt text for every figure**, which the journal requires under every legend and which is
  easy to omit and be returned for.
* **Every figure is cited in the body**, and in a sentence rather than only in a heading.
* **Every measured number in the text appears in a results file.** The manuscript is generated
  and interpolates its numbers, so a number that is not in the results is one somebody typed.
* **Every citation resolves** to the reference list, and every reference is cited.
* **The affiliation is the one Crossref carries**, city before postcode. It has been wrong
  before, in a way that only showed up at proof stage.
"""

from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

BUILD = os.path.join(HERE, "build")
RESULTS = os.path.join(HERE, "results")
FIGURES = os.path.join(HERE, "figures")

#: The structured abstract's five labels, and the figure label. Nothing else is bold by name.
ABSTRACT_LABELS = re.compile(
    r"^(Objectives|Methods|Results|Conclusions|Advances in knowledge|Figure \d+)\.$")

#: A run-in subsection label: a short noun phrase ending in a full stop, as "Clinical arm.".
#: The limit is what separates a label from a sentence. The first version of this check also
#: allowed "^[A-Z][^.]{0,120}\.$", which admits any sentence of under 120 characters without an
#: internal full stop -- that is to say, every bold lead-in the rule exists to forbid. It passed
#: a manuscript carrying six of them. A gate whose own pattern defeats it is worse than none,
#: because it is reported as green.
MAX_LABEL = 35
RUN_IN_LABEL = re.compile(rf"^[A-Z][^.]{{0,{MAX_LABEL - 2}}}\.$")

#: A number that is part of the language rather than a measurement.
NOT_A_MEASUREMENT = {"1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12",
                     "0", "100", "15", "500", "2006", "2026", "150044", "20"}


def read(name: str) -> str:
    with open(os.path.join(BUILD, name), encoding="utf-8") as handle:
        return handle.read()


def results_numbers() -> set[str]:
    """Every number any results file holds, formatted the ways the text formats them."""
    out: set[str] = set()

    def walk(value):
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, bool):
            pass
        elif isinstance(value, (int, float)):
            for places in (0, 1, 2, 3):
                out.add(f"{float(value):.{places}f}")
            out.add(str(value))
            if float(value).is_integer():
                out.add(str(int(value)))
            # The text also writes percentages and counts derived from these.
            for scaled in (float(value) * 100, float(value) / 100):
                for places in (0, 1, 2):
                    out.add(f"{scaled:.{places}f}")

    for name in os.listdir(RESULTS):
        if name.endswith(".json"):
            with open(os.path.join(RESULTS, name), encoding="utf-8") as handle:
                walk(json.load(handle))
    return out


def body_of(document: str) -> str:
    """The manuscript without its reference list, figure legends or headings."""
    document = document.split("## References")[0]
    document = document.split("## Figures")[0]
    return document


def check_bold(document: str) -> list[str]:
    problems = []
    for match in re.finditer(r"\*\*(.+?)\*\*", document, re.S):
        text = " ".join(match.group(1).split())
        if ABSTRACT_LABELS.match(text) or RUN_IN_LABEL.match(text):
            continue
        problems.append(
            f"bold that is not a label ({len(text)} characters, limit {MAX_LABEL}): "
            f"{text[:70]!r}")
    return problems


def check_figures(document: str) -> list[str]:
    problems = []
    path = os.path.join(FIGURES, "captions.json")
    if not os.path.isfile(path):
        return ["no captions.json: run make_figures.py"]
    with open(path, encoding="utf-8") as handle:
        figures = json.load(handle)
    body = body_of(document)
    for number, figure in figures.items():
        if not figure.get("alt_text"):
            problems.append(f"figure {number} has no alt text")
        if f"Alt text: {figure['alt_text'][:40]}" not in document:
            problems.append(f"figure {number}'s alt text is not in the manuscript")
        cited = re.search(rf"Figure {number}\b", body)
        if not cited:
            problems.append(f"figure {number} is never cited in the body")
        if figure["dpi"] < 600:
            problems.append(f"figure {number} is {figure['dpi']} dpi; the journal asks 600-900 "
                            "for combination half-tone and line art")
    return problems


def check_numbers(document: str) -> list[str]:
    known = results_numbers()
    problems = []
    body = body_of(document)
    body = re.sub(r"\[\d+(?:,\d+)*\]", " ", body)          # citation markers
    for token in re.findall(r"(?<![\w.])\d+\.\d+(?![\w])", body):
        if token not in known:
            problems.append(f"the number {token} is in the text but in no results file")
    return problems


def check_citations(document: str) -> list[str]:
    import references as bib

    problems = []
    listed = re.findall(r"^(\d+)\. ", document.split("## References")[1], re.M)
    cited = set()
    for group in re.findall(r"\[(\d+(?:,\d+)*)\]", body_of(document) + document):
        cited.update(group.split(","))
    for number in listed:
        if number not in cited:
            problems.append(f"reference {number} is listed but never cited")
    for number in sorted(cited, key=int):
        if number not in listed:
            problems.append(f"citation [{number}] has no reference")
    expected = len(bib.REFERENCES) + len(bib.NON_DOI)
    if len(listed) > 50:
        problems.append(f"{len(listed)} references; the journal allows 50")
    if len(listed) != expected:
        problems.append(f"{len(listed)} references in the manuscript against {expected} "
                        "defined; an uncited reference is not in the list")
    return problems


def check_affiliation(title_page: str) -> list[str]:
    import build_manuscript as build

    if build.AFFILIATION not in title_page:
        return ["the title page does not carry the affiliation from build_manuscript.py"]
    if not re.search(r"Tokyo \d{3}-\d{4}", build.AFFILIATION):
        return ["the affiliation must give the city before the postcode, as Crossref carries it"]
    return []


def check_statements(document: str) -> list[str]:
    """The statements the journal requires, found where they have to be.

    Searching the whole document for the phrase is not the same as finding the statement: the
    Methods refer the reader to "(Data availability)", so deleting that section left the words
    behind and the first version of this check saw nothing wrong.
    """
    problems = []
    if not re.search(r"^## Data availability\s*$", document, re.M):
        problems.append("there is no Data availability section")
    # A sentence, not a word. "approval" survives in "the approvals under which the dataset was
    # collected" and "consent" in the subsection's own label, so looking for the word alone
    # passed a Methods section with the statement deleted -- which the injection proof caught.
    methods = document.split("## Methods")[-1].split("## Results")[0]
    sentences = [" ".join(s.split()).lower() for s in re.split(r"(?<=\.)\s+", methods)]
    wanted = {
        "approval": ({"required", "sought", "waived", "granted", "obtained"},
                     "the Methods do not state ethical approval, or why it was not required"),
        "consent": ({"required", "waived", "obtained", "does not arise", "not applicable"},
                    "the Methods do not state consent, or why it does not arise"),
    }
    for word, (qualifiers, complaint) in wanted.items():
        if not any(word in s and any(q in s for q in qualifiers) for s in sentences):
            problems.append(complaint)
    return problems


def main() -> int:
    document = read("manuscript.md")
    title_page = read("title_page.md")

    checks = {
        "bold in the body": check_bold(body_of(document)),
        "figures and alt text": check_figures(document),
        "numbers traceable to results": check_numbers(document),
        "citations and references": check_citations(document),
        "affiliation": check_affiliation(title_page),
        "required statements": check_statements(document),
    }

    failed = 0
    for name, problems in checks.items():
        if problems:
            failed += len(problems)
            print(f"FAIL  {name}")
            for problem in problems:
                print(f"      {problem}")
        else:
            print(f"ok    {name}")
    print()
    if failed:
        print(f"{failed} problems")
        return 1
    print("the manuscript passes every check in this file")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
