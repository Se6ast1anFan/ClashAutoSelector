"""Pure selection and scheduling rules, independent from desktop automation."""
from dataclasses import dataclass
import re


@dataclass
class Candidate:
    name: str
    status: str
    rect: tuple[int, int, int, int]
    selected: bool = False
    reliable: bool = True

    @property
    def delay(self):
        match = re.fullmatch(r"([1-9]\d{0,5})\s*(?:ms)?", self.status.strip(), re.I)
        return int(match[1]) if match else None


def choose(candidates):
    valid = [c for c in candidates if c.reliable and c.delay is not None]
    best = min(valid, key=lambda c: (c.delay, not c.selected, c.rect[1], c.rect[0])) if valid else None
    # A lower number that failed verification may be the real winner. Wait for
    # another round instead of confidently selecting a slower verified node.
    if best and any(not c.reliable and c.delay is not None and c.delay < best.delay for c in candidates):
        return None
    return best


def all_timeout(candidates, complete=True):
    return bool(candidates) and complete and all(
        c.reliable and c.status.strip().casefold() == "timeout" for c in candidates
    )


def next_due(start, finish, interval, retry=False):
    if retry:
        return finish
    # Skip elapsed slots rather than executing catch-up rounds.
    return start + (int(max(0, finish - start) // interval) + 1) * interval
