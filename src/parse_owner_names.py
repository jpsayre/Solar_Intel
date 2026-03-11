"""
Utility to parse Regrid owner name strings into structured first/last names.

Handles formats like:
  - "SMITH, JOHN A"           -> [(JOHN, SMITH)]
  - "JOHN A SMITH"            -> [(JOHN, SMITH)]
  - "SMITH JOHN & JANE"       -> [(JOHN, SMITH), (JANE, SMITH)]
  - "MACKENZIE CHRISTOPHER T & BROOKE E" -> [(CHRISTOPHER, MACKENZIE), (BROOKE, MACKENZIE)]
  - "BETIK JULIE RICHARDS & MICHAEL LYNN" -> [(JULIE, BETIK), (MICHAEL, BETIK)]
  - "SMITH JOHN AND JANE"     -> [(JOHN, SMITH), (JANE, SMITH)]
  - "JOHN SMITH & JANE SMITH" -> [(JOHN, SMITH), (JANE, SMITH)]
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ParsedName:
    first_name: str
    last_name: str
    middle_name: str = ""

    def __str__(self):
        parts = [self.first_name]
        if self.middle_name:
            parts.append(self.middle_name)
        parts.append(self.last_name)
        return " ".join(parts)


def _clean(name: str) -> str:
    """Normalize whitespace and casing."""
    name = re.sub(r"\s+", " ", name.strip())
    return name.upper()


def _title(s: str) -> str:
    """Title-case a name string."""
    return s.strip().title()


def parse_owner_name(raw: str) -> list[ParsedName]:
    """
    Parse a Regrid owner name string into a list of ParsedName objects.
    Returns an empty list if the name can't be parsed.
    """
    if not raw or not isinstance(raw, str):
        return []

    raw = _clean(raw)

    # Skip obviously non-personal names (trusts, LLCs, etc.)
    skip_patterns = [
        r"\bLLC\b", r"\bINC\b", r"\bCORP\b", r"\bTRUST\b", r"\bLTD\b",
        r"\bCOMPANY\b", r"\bASSOC\b", r"\bFOUNDATION\b", r"\bESTATE\b",
        r"\bREVOCABLE\b", r"\bIRREVOCABLE\b", r"\bLIVING\b",
        r"\bPARTNERSHIP\b", r"\bVENTURE\b", r"\bHOA\b",
    ]
    for pat in skip_patterns:
        if re.search(pat, raw):
            return []

    # Split on & or AND to find joint owners
    splitter = re.split(r"\s+&\s+|\s+AND\s+", raw)

    # Case 1: "LASTNAME, FIRSTNAME [MIDDLE]"
    if "," in splitter[0]:
        parts = splitter[0].split(",", 1)
        last_name = parts[0].strip()
        first_parts = parts[1].strip().split()
        first_name = first_parts[0] if first_parts else ""
        middle = " ".join(first_parts[1:]) if len(first_parts) > 1 else ""

        results = [ParsedName(
            first_name=_title(first_name),
            last_name=_title(last_name),
            middle_name=_title(middle),
        )]

        # Handle second owner after &: could be just a first name
        for extra in splitter[1:]:
            extra = extra.strip()
            if not extra:
                continue
            extra_parts = extra.split()
            if len(extra_parts) == 1:
                # Just a first name, shares the last name
                results.append(ParsedName(
                    first_name=_title(extra_parts[0]),
                    last_name=_title(last_name),
                ))
            elif "," in extra:
                # Another "LAST, FIRST" format
                ep = extra.split(",", 1)
                ef = ep[1].strip().split()
                results.append(ParsedName(
                    first_name=_title(ef[0]) if ef else "",
                    last_name=_title(ep[0].strip()),
                    middle_name=_title(" ".join(ef[1:])) if len(ef) > 1 else "",
                ))
            else:
                # Multiple words - assume first [middle...] last
                results.append(ParsedName(
                    first_name=_title(extra_parts[0]),
                    last_name=_title(extra_parts[-1]),
                    middle_name=_title(" ".join(extra_parts[1:-1])) if len(extra_parts) > 2 else "",
                ))
        return results

    # Case 2: No comma - "LASTNAME FIRSTNAME [MIDDLE] [& FIRSTNAME2 [MIDDLE2]]"
    # Regrid typically puts last name first when no comma
    # Heuristic: first token is the last name
    primary_parts = splitter[0].strip().split()

    if len(primary_parts) < 2:
        # Single word - can't reliably parse
        return [ParsedName(first_name="", last_name=_title(primary_parts[0]))] if primary_parts else []

    last_name = primary_parts[0]
    first_name = primary_parts[1]
    middle = " ".join(primary_parts[2:]) if len(primary_parts) > 2 else ""

    results = [ParsedName(
        first_name=_title(first_name),
        last_name=_title(last_name),
        middle_name=_title(middle),
    )]

    # Handle additional owners after &
    for extra in splitter[1:]:
        extra = extra.strip()
        if not extra:
            continue
        extra_parts = extra.split()
        if len(extra_parts) == 1:
            # Just a first name, shares the last name
            results.append(ParsedName(
                first_name=_title(extra_parts[0]),
                last_name=_title(last_name),
            ))
        elif len(extra_parts) == 2:
            # Could be "FIRSTNAME MIDDLE" (sharing last name) or "FIRSTNAME LASTNAME"
            # Heuristic: if second word looks like a middle initial or common middle name, share last name
            if len(extra_parts[1]) <= 2 or extra_parts[1].endswith("."):
                results.append(ParsedName(
                    first_name=_title(extra_parts[0]),
                    last_name=_title(last_name),
                    middle_name=_title(extra_parts[1]),
                ))
            else:
                # Assume it's "FIRST LAST"
                results.append(ParsedName(
                    first_name=_title(extra_parts[0]),
                    last_name=_title(extra_parts[1]),
                ))
        else:
            # "FIRST MIDDLE LAST" or "FIRST MIDDLE..." sharing last name
            # If last word matches primary last name, they share it
            if extra_parts[-1].upper() == last_name.upper():
                results.append(ParsedName(
                    first_name=_title(extra_parts[0]),
                    last_name=_title(last_name),
                    middle_name=_title(" ".join(extra_parts[1:-1])),
                ))
            else:
                # Assume sharing last name, rest is first + middle
                results.append(ParsedName(
                    first_name=_title(extra_parts[0]),
                    last_name=_title(last_name),
                    middle_name=_title(" ".join(extra_parts[1:])),
                ))

    return results


if __name__ == "__main__":
    # Test with sample names from the dataset
    test_names = [
        "MACKENZIE CHRISTOPHER T & BROOKE E",
        "BETIK JULIE RICHARDS & MICHAEL LYNN",
        "SMITH, JOHN A",
        "JOHNSON ROBERT",
        "WILLIAMS MARY ANN & JAMES",
        "BROWN, SARAH & BROWN, MICHAEL",
        "",
        "BOULDER COUNTY HOUSING LLC",
        "JONES FAMILY REVOCABLE TRUST",
    ]

    for name in test_names:
        results = parse_owner_name(name)
        parsed = [(r.first_name, r.last_name, r.middle_name) for r in results]
        print(f"{name!r:50s} -> {parsed}")
