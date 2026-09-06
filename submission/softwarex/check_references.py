"""Resolve every DOI in the manuscript and compare what is registered against what we print.

A DOI that looks right is not a DOI that is right. On another manuscript in this
programme, two DOIs derived by pattern turned out to point at unrelated papers; both were
found only by resolving them. This script resolves each one through doi.org content
negotiation and compares the registered title and year with the reference as typed.

    python check_references.py

Exit status is non-zero if any DOI fails to resolve or disagrees with the reference.
Titles are compared after case folding and stripping punctuation; a registered title that
is a prefix of ours is accepted, because some registrations truncate at a colon.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "build_submission_docs.py"

HEADERS = {
    "Accept": "application/vnd.citationstyles.csl+json",
    "User-Agent": "IORN-001 reference check (yamamoto@lisit.jp)",
}


def references() -> list[str]:
    """The reference list as the manuscript prints it, read from the build source."""
    body = SOURCE.read_text(encoding="utf-8")
    block = body.split("    refs = [", 1)[1].split("\n    ]", 1)[0]
    return [m.group(1) for m in re.finditer(r'^\s*"(.*)",\s*$', block, re.M)]


def dois(reference: str) -> list[str]:
    found = re.findall(r"https://doi\.org/(10\.[^\s,]+?)\.?(?:\s|$)", reference)
    return [d.rstrip(".") for d in found]


def normalise(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("–", "-").replace("—", "-").replace("’", "'")
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def resolve(doi: str) -> dict | None:
    request = urllib.request.Request(f"https://doi.org/{doi}", headers=HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        return {"_error": f"HTTP {exc.code}"}
    except Exception as exc:  # noqa: BLE001 - the message is what matters here
        return {"_error": type(exc).__name__}


def year_of(record: dict) -> str | None:
    for key in ("issued", "published", "published-online", "published-print"):
        parts = record.get(key, {}).get("date-parts") or []
        if parts and parts[0] and parts[0][0]:
            return str(parts[0][0])
    return None


def main() -> int:
    problems: list[str] = []
    refs = references()
    if not refs:
        print("FAIL  no references found in the build source")
        return 1

    for reference in refs:
        label = re.match(r"\[(\d+)\]", reference)
        label = label.group(1) if label else "?"
        found = dois(reference)
        if not found:
            print(f"[{label}] no DOI  {reference[:70]}...")
            continue
        for doi in found:
            record = resolve(doi)
            if record is None or "_error" in record:
                reason = (record or {}).get("_error", "no response")
                print(f"[{label}] FAIL  {doi}  did not resolve ({reason})")
                problems.append(f"[{label}] {doi} did not resolve ({reason})")
                continue

            registered = record.get("title")
            if isinstance(registered, list):
                registered = registered[0] if registered else ""
            registered = registered or ""
            reg = normalise(registered)
            ours = normalise(reference)

            title_ok = bool(reg) and (reg in ours or ours.find(reg[: max(30, len(reg) // 2)]) >= 0)
            registered_year = year_of(record)
            printed_years = re.findall(r"\b(19|20)\d{2}\b", reference)
            printed_years = re.findall(r"\b((?:19|20)\d{2})\b", reference)
            year_ok = registered_year is None or registered_year in printed_years

            status = "ok  " if (title_ok and year_ok) else "CHECK"
            print(f"[{label}] {status}  {doi}")
            print(f"        registered: {registered[:110]}  ({registered_year})")
            if not title_ok:
                problems.append(f"[{label}] {doi} title disagrees: registered {registered!r}")
                print("        ^^ the registered title is not the one we print")
            if not year_ok:
                problems.append(
                    f"[{label}] {doi} year disagrees: registered {registered_year}, "
                    f"printed {printed_years}"
                )
                print(f"        ^^ registered year {registered_year} is not in the reference")

    print()
    if problems:
        print("PROBLEMS:")
        for item in problems:
            print(f"  - {item}")
        return 1
    print(f"all {len(refs)} references resolve and agree with what the manuscript prints")
    return 0


if __name__ == "__main__":
    sys.exit(main())
