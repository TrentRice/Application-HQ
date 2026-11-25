"""The bullet formula, and the checks every generated bullet must pass.

    [action verb] [what you did] [with what tools or methods], [impact, ideally quantified].
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from .profile import Fact

WEAK_VERBS = {
    "helped", "assisted", "worked", "participated", "responsible", "involved",
    "supported", "handled", "did", "was", "tasked", "contributed", "utilized", "used",
}

STRONG_VERBS = {
    "analyzed", "architected", "automated", "built", "championed", "conducted",
    "consolidated", "created", "delivered", "deployed", "designed", "developed",
    "digitized", "drove", "engineered", "established", "evaluated", "forecasted",
    "identified", "implemented", "improved", "launched", "led", "mapped", "modeled",
    "optimized", "orchestrated", "pioneered", "presented", "produced", "queried",
    "quantified", "redesigned", "reduced", "spearheaded", "standardized",
    "streamlined", "trained", "transformed", "validated",
    # irregular past tenses (don't end in -ed)
    "wrote", "rebuilt", "found", "ran", "made", "won", "grew", "cut", "set", "began",
    "took", "gave", "brought", "taught", "chose", "held", "kept", "oversaw", "undertook",
    "drew", "sought", "upheld", "rewrote", "built", "led", "drove", "showed",
}


class Bullet(BaseModel):
    fact_ids: list[str]
    action: str
    what: str
    how: str
    impact: str

    @property
    def text(self) -> str:
        parts = " ".join(p.strip() for p in (self.action, self.what, self.how) if p.strip())
        impact = self.impact.strip().rstrip(".")
        sentence = f"{parts}, {impact}" if impact else parts
        return sentence.rstrip(".,; ") + "."


_NUMBER = re.compile(r"\d[\d,.]*")


_NUMBER_WORDS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
    "seven": "7", "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12",
}
_WORD = re.compile(r"\b(" + "|".join(_NUMBER_WORDS) + r")\b", re.IGNORECASE)


def _numbers(text: str) -> set[str]:
    """Numbers in the text, with "four" and "4" treated as the same number."""
    digits = {n.replace(",", "").rstrip(".") for n in _NUMBER.findall(text)}
    return digits | {_NUMBER_WORDS[w.lower()] for w in _WORD.findall(text)}


def check(bullet: Bullet, facts: list[Fact]) -> tuple[list[str], list[str]]:
    """Returns (errors, warnings). Errors must be fixed; warnings are shown to you."""
    errors: list[str] = []
    warnings: list[str] = []

    action = bullet.action.strip()
    if not action or " " in action:
        errors.append("action must be a single verb")
    elif action.lower() in WEAK_VERBS:
        errors.append(f"weak action verb '{action}'")
    elif action.lower() not in STRONG_VERBS and not action.lower().endswith("ed"):
        errors.append(f"'{action}' is not a past-tense action verb")

    if not bullet.how.strip():
        errors.append("missing tools or methods")

    allowed = set().union(*(_numbers(f.source_text()) for f in facts)) if facts else set()
    invented = _numbers(bullet.text) - allowed
    if invented:
        errors.append(f"numbers not in your stored facts: {', '.join(sorted(invented))}")

    # A bullet counts as quantified if any stored metric's number appears anywhere in it
    # (the number may sit in the "what", e.g. "consolidating 600 documents").
    metric_numbers = set().union(*(_numbers(" ".join(f.metrics)) for f in facts)) if facts else set()
    used_metric = bool(_numbers(bullet.text) & metric_numbers)
    if not bullet.impact.strip():
        warnings.append("no impact stated")
    if metric_numbers and not used_metric:
        errors.append("a stored metric exists but the bullet doesn't use it")
    elif not metric_numbers and bullet.impact.strip():
        warnings.append("impact not quantified (no metric stored for this work)")

    return errors, warnings


def _how(tools: list[str]) -> str:
    if len(tools) > 1:
        return "using " + ", ".join(tools[:-1]) + " and " + tools[-1]
    return f"using {tools[0]}" if tools else ""


def from_fact(fact: Fact, max_lines: int = 2) -> Bullet:
    """Deterministic bullet built straight from a stored fact (fallback).
    Drops tools one at a time until it fits in max_lines."""
    from .layout import bullet_lines  # local import: layout is optional for checks

    bullet = None
    # keep at least one tool so the bullet still names "with what tools or methods"
    for n in range(min(3, len(fact.tools)), 0 if fact.tools else -1, -1):
        bullet = Bullet(fact_ids=[fact.id], action=fact.action, what=fact.what,
                        how=_how(fact.tools[:n]), impact=fact.impact)
        if bullet_lines(bullet.text) <= max_lines:
            break
    return bullet
