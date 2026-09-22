"""Sprint scheduling.

Sprints start every Wednesday and developers pick up new work at the start of a
sprint. A ticket therefore belongs to the **next Wednesday strictly after the
day it is created**: work raised on Tuesday is picked up the following morning,
while work raised on Wednesday has missed that sprint and waits a week.

Expressing it as "strictly after today" rather than as a weekday special case
keeps one rule for all seven days:

===========  ==========  ====================================
Created      Example     Sprint
===========  ==========  ====================================
Monday       29 Sep      1 Oct (that week)
Tuesday      30 Sep      1 Oct (next morning)
Wednesday    1 Oct       8 Oct (the sprint began without it)
Thursday     2 Oct       8 Oct
Sunday       5 Oct       8 Oct
===========  ==========  ====================================
"""

from datetime import date, timedelta

#: Monday is 0 in :meth:`datetime.date.weekday`.
SPRINT_WEEKDAY = 2

#: Deterministic month abbreviations. ``strftime("%b")`` is locale-dependent and
#: would silently produce a different sprint name on a differently configured
#: machine.
MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN",
          "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")


def next_sprint(today: date) -> date:
    """The sprint a ticket created on ``today`` belongs to."""
    ahead = (SPRINT_WEEKDAY - today.weekday()) % 7
    return today + timedelta(days=ahead or 7)


def sprint_name(day: date) -> str:
    """The sprint tag, e.g. ``2 OCT SPRINT``. No leading zero on the day."""
    return "%d %s SPRINT" % (day.day, MONTHS[day.month - 1])


def sprint_for(today: date):
    """``(start date, tag)`` for a ticket created on ``today``."""
    start = next_sprint(today)
    return start, sprint_name(start)


def upcoming(today: date, count: int = 4):
    """The next ``count`` sprints, for showing what a deferral would mean."""
    sprints, cursor = [], today
    for _ in range(max(0, count)):
        start = next_sprint(cursor)
        sprints.append((start, sprint_name(start)))
        cursor = start
    return sprints
