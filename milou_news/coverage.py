"""Cross-routine coverage, so the same event is never reported twice.

When one routine watches a system directly and that system also emails a
notification, the user is told the same thing twice. The fix is not to silence
the notification channel blindly — that would also hide alerts the direct
routine never saw. Instead a routine publishes what it *demonstrably* reported,
and another routine suppresses only mail it can match against that evidence.

Anything from a covered source that cannot be matched is not silently dropped:
it is surfaced as a coverage gap, because an unmatched notification usually
means the direct routine is missing a project, a permission, or a window.
"""

import re
from dataclasses import dataclass
from typing import FrozenSet, Sequence, Tuple

#: Identifiers long enough to be a real record reference rather than a date or
#: a version number appearing in a subject line.
_IDENT = re.compile(r"\b(\d{4,})\b")
_WORD = re.compile(r"[a-z0-9]+")


def normalize(text: str) -> str:
    return " ".join(_WORD.findall((text or "").lower()))


def identifiers(*parts: str) -> FrozenSet[str]:
    """Every record-shaped identifier appearing in the given text."""
    found = set()
    for part in parts:
        found.update(_IDENT.findall(part or ""))
    return frozenset(found)


@dataclass(frozen=True)
class Coverage:
    """What one routine has already reported, and how its notifications arrive.

    ``keys`` are record identifiers; ``titles`` are normalized record titles,
    used when a notification names an item without quoting its id. ``domains``
    are the sender domains whose mail this routine's coverage applies to.
    """

    routine: str
    keys: FrozenSet[str] = frozenset()
    titles: Tuple[str, ...] = ()
    domains: Tuple[str, ...] = ()

    def owns_sender(self, address: str) -> bool:
        address = (address or "").lower()
        return any(address.endswith("@" + domain) or address.endswith("." + domain)
                   for domain in self.domains)

    def matches(self, *parts: str) -> bool:
        """True when this text clearly refers to a record already reported."""
        if self.keys and identifiers(*parts) & self.keys:
            return True
        haystack = normalize(" ".join(part or "" for part in parts))
        return any(title and title in haystack for title in self.titles)


def find_owner(coverages: Sequence[Coverage], address: str):
    """The coverage responsible for a sender, if any."""
    for coverage in coverages or ():
        if coverage.owns_sender(address):
            return coverage
    return None
