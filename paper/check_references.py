"""Resolve every DOI in the reference list and compare it with what we claim it is.

    python paper/check_references.py

Each DOI is fetched from Crossref and the returned title, journal, year, volume and pages are
compared with the record in ``references.py``. A DOI that resolves to a *different paper* is the
failure this exists for: writing that list, a DOI assembled from a plausible pattern resolved to
an unrelated article in the same journal and issue, and nothing but a query would have caught
it. On a previous paper in this programme two of twenty-one references pointed at the wrong
work, and one was dead.

Exit status is non-zero if any reference fails to resolve or disagrees. Network failure is
reported as a failure to check rather than as a pass: the whole point is that an unverified
reference is not a verified one.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import references as bib  # noqa: E402

CROSSREF = "https://api.crossref.org/works/"
#: Crossref asks for a contact address in the user agent, and answers faster with one.
AGENT = f"ctp-core-reference-check (mailto:{'yamamoto@lisit.jp'})"


def normalise(text: str) -> str:
    """Compare titles on their words alone: punctuation and case vary between records."""
    return re.sub(r"[^a-z0-9 ]", " ", (text or "").lower())


SKIP = {"a", "an", "the", "of", "in", "for", "and", "on", "to", "with", "by", "from"}


def words(text: str) -> set[str]:
    return {w for w in normalise(text).split() if w and w not in SKIP}


def fetch(doi: str) -> dict:
    request = urllib.request.Request(CROSSREF + doi, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)["message"]


def abbreviates(short: str, full: str) -> bool:
    """Whether ``short`` is a MEDLINE-style abbreviation of ``full``.

    Vancouver requires the abbreviation -- "Magn Reson Med" -- while Crossref returns the full
    title. Comparing them word for word marks every correct reference as wrong, which the first
    version of this checker did for ten of twelve. Three things have to be handled, and each was
    found by a reference that is in fact correct:

    * word stems in order: Magn->Magnetic, Reson->Resonance, Med->Medicine;
    * a leading initialism: "AJNR Am J Neuroradiol" against "American Journal of
      Neuroradiology", where AJNR is the initials of the words that follow;
    * a parenthetical place qualifier, as in "J Med Imaging (Bellingham)", which MEDLINE adds to
      disambiguate and which is not part of the journal's title at all.
    """
    short = re.sub(r"\(.*?\)", " ", short)
    remaining = [w for w in normalise(full).split() if w not in SKIP]
    pieces = [w for w in normalise(short).split() if w not in SKIP]

    # A first token that is an initialism of the whole title is not a stem of its first word.
    # Word initials are not enough: AJNR takes its R from the middle of "NeuroRadiology", so
    # the test is that its letters appear in order in the title and that it starts the title.
    # The remaining pieces must still match the title word by word, which is what keeps this
    # from admitting anything.
    if pieces and len(pieces[0]) > 1 and not remaining[:1] == [pieces[0]]:
        letters = iter("".join(remaining))
        first = pieces[0]
        if remaining and remaining[0].startswith(first[0]) and all(
                any(c == letter for letter in letters) for c in first):
            pieces = pieces[1:]

    for piece in pieces:
        while remaining and not remaining[0].startswith(piece[:4]):
            remaining.pop(0)
        if not remaining:
            return False
        remaining.pop(0)
    return True


def europepmc(doi: str) -> dict | None:
    """The same record from Europe PMC, as a second authority.

    Crossref is authoritative for the DOI but not always complete: it may carry only the online
    year for a paper that appeared in a later print issue, and a journal that numbers articles
    may file the article number nowhere Crossref exposes. Both cases arose in this list, and in
    both the reference was right and Crossref's record was thin. A reference is accepted when
    either source agrees, and the output says which.
    """
    url = ("https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:%22"
           + urllib.parse.quote(doi) + "%22&format=json&resultType=core&pageSize=1")
    try:
        request = urllib.request.Request(url, headers={"User-Agent": AGENT})
        with urllib.request.urlopen(request, timeout=30) as response:
            results = json.load(response).get("resultList", {}).get("result", [])
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None
    return results[0] if results else None


def published_years(live: dict) -> set[int]:
    """Every year the record gives. Crossref's ``issued`` is the earliest, which for a paper
    published online in one year and in an issue the next is not the year Vancouver cites."""
    years = set()
    for field in ("published-print", "published-online", "issued", "published"):
        parts = (live.get(field) or {}).get("date-parts") or []
        for part in parts:
            if part and part[0]:
                years.add(int(part[0]))
    return years


def check(key: str, record: dict) -> tuple[list[str], list[str]]:
    """What disagrees, and what agreed only after a second source was consulted."""
    try:
        live = fetch(record["doi"])
    except urllib.error.HTTPError as exc:
        return [f"the DOI does not resolve: HTTP {exc.code}"], []
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return [f"could not be checked ({exc}); an unchecked reference is not a checked one"], []

    problems, notes = [], []
    live_title = (live.get("title") or [""])[0]
    ours, theirs = words(record["title"]), words(live_title)
    if ours and theirs:
        overlap = len(ours & theirs) / len(ours | theirs)
        if overlap < 0.6:
            problems.append(f"resolves to a different paper: {live_title!r}")
    second = None   # fetched only if Crossref disagrees, to keep the usual case to one request

    years = published_years(live)
    if years and int(record["year"]) not in years:
        second = europepmc(record["doi"]) if second is None else second
        if second and str(second.get("pubYear")) == str(record["year"]):
            notes.append(f"year {record['year']} confirmed by Europe PMC; Crossref has "
                         f"{sorted(years)}")
        else:
            problems.append(f"year {record['year']} against {sorted(years)}")
    live_volume = str(live.get("volume") or "")
    if live_volume and live_volume != str(record["volume"]):
        problems.append(f"volume {record['volume']} against {live_volume}")
    # A journal that numbers articles rather than pages may file the number where Crossref does
    # not expose it, giving a 1-N range instead.
    first_page = record["pages"].split("-")[0]
    candidates = [str(live.get("page") or ""), str(live.get("article-number") or "")]
    if any(candidates) and not any(first_page in c for c in candidates if c):
        second = europepmc(record["doi"]) if second is None else second
        if second and first_page in str(second.get("pageInfo") or ""):
            notes.append(f"pages {record['pages']} confirmed by Europe PMC; Crossref has "
                         f"{[c for c in candidates if c]}")
        else:
            problems.append(f"pages {record['pages']} against {[c for c in candidates if c]}")
    live_journal = (live.get("container-title") or [""])[0]
    if live_journal and not abbreviates(record["journal"], live_journal):
        problems.append(f"journal {record['journal']!r} is not an abbreviation of "
                        f"{live_journal!r}")
    return problems, notes


def main() -> int:
    print(f"{len(bib.REFERENCES)} references with a DOI, plus {len(bib.NON_DOI)} without\n")
    failed = 0
    for key, record in bib.REFERENCES.items():
        problems, notes = check(key, record)
        for note in notes:
            print(f"note {key:22s} {note}")
        if problems:
            failed += 1
            print(f"FAIL {key} ({record['doi']})")
            for problem in problems:
                print(f"     {problem}")
        else:
            print(f"ok   {key:22s} {record['doi']}")
    for key, record in bib.NON_DOI.items():
        print(f"--   {key:22s} no DOI; cited by name and version: {record['title'][:50]}...")

    print()
    if failed:
        print(f"{failed} of {len(bib.REFERENCES)} references did not check out")
        return 1
    print(f"all {len(bib.REFERENCES)} DOIs resolve and agree with the list")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
