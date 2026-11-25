"""Page geometry and the one-page fitter.

The resume template uses EXACT line spacing everywhere, so a page's height is
fully determined by how many lines each paragraph wraps to. Wrapping is
measured with real Arial font metrics, which makes the estimate reliable
without needing Word or LibreOffice to render the file.

build_template.py reads these same constants, so the template and the fitter
always agree. If you restyle the template by hand in Word, keep fonts, sizes
and spacing in sync with the values here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

PT_PER_INCH = 72

# ---- Page ---------------------------------------------------------------------
PAGE_WIDTH = 8.5 * PT_PER_INCH
PAGE_HEIGHT = 11 * PT_PER_INCH
MARGIN_TOP = 0.5 * PT_PER_INCH
MARGIN_BOTTOM = 0.5 * PT_PER_INCH
MARGIN_SIDE = 0.75 * PT_PER_INCH
TEXT_WIDTH = PAGE_WIDTH - 2 * MARGIN_SIDE
PAGE_BUDGET = (PAGE_HEIGHT - MARGIN_TOP - MARGIN_BOTTOM) * 0.97  # small safety margin

# ---- Type ---------------------------------------------------------------------
FONT = "Arial"
BODY_SIZE = 10
BODY_LINE = 12.5
NAME_SIZE = 22
NAME_LINE = 26
TITLE_SIZE = 13
TITLE_LINE = 16
HEADING_SIZE = 11
HEADING_LINE = 14
HEADING_BEFORE = 9
HEADING_AFTER = 2
ENTRY_BEFORE = 3  # space above each job / project title line

# ---- Bullets ------------------------------------------------------------------
BULLET_INDENT = 0.3 * PT_PER_INCH  # where bullet text starts
BULLET_HANGING = 0.2 * PT_PER_INCH  # bullet glyph sits this far left of the text
BULLET_TEXT_WIDTH = TEXT_WIDTH - BULLET_INDENT
DATE_GAP = 12  # minimum gap between a left-hand line and its right-aligned date

HEADER_HEIGHT = max(3 * BODY_LINE, NAME_LINE + TITLE_LINE) + 6

_FONT_DIRS = [
    Path("/System/Library/Fonts/Supplemental"),
    Path("/Library/Fonts"),
    Path("C:/Windows/Fonts"),
    Path("/usr/share/fonts/truetype/msttcorefonts"),
]
_FONT_FILES = {False: ["Arial.ttf", "arial.ttf"], True: ["Arial Bold.ttf", "arialbd.ttf"]}


@lru_cache(maxsize=None)
def _font(bold: bool):
    for d in _FONT_DIRS:
        for name in _FONT_FILES[bold]:
            if (d / name).exists():
                return ImageFont.truetype(str(d / name), 1000)
    return None


def text_width(text: str, size: float = BODY_SIZE, bold: bool = False) -> float:
    font = _font(bold)
    if font is None:  # no Arial available: conservative average-width estimate
        return len(text) * size * (0.56 if bold else 0.52)
    return font.getlength(text) * size / 1000


def wrapped_lines(text: str, width: float, size: float = BODY_SIZE, bold: bool = False) -> int:
    lines, current = 1, ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and text_width(candidate, size, bold) > width:
            lines += 1
            current = word
        else:
            current = candidate
    return lines


def bullet_lines(text: str) -> int:
    return wrapped_lines(text, BULLET_TEXT_WIDTH)


def dated_line_lines(left: str, date: str, width: float = TEXT_WIDTH, bold_left: bool = True) -> int:
    """A line with text on the left and a right-aligned date."""
    room = width - text_width(date, bold=True) - DATE_GAP
    return wrapped_lines(left, room, bold=bold_left)


# ---- Whole-page height ----------------------------------------------------------


@dataclass
class Entry:
    """A job or project as it will be printed."""

    title: str
    org: str
    dates: str
    bullets: list[str]


def page_height(education: list[tuple[str, str]], skill_lines: list[str],
                experience: list[Entry], projects: list[Entry]) -> float:
    def heading() -> float:
        return HEADING_BEFORE + HEADING_LINE + HEADING_AFTER

    h = HEADER_HEIGHT

    h += heading()
    for left, date in education:
        # measured as bold: the degree part is bold, so this errs on the safe side
        h += dated_line_lines(left, date, BULLET_TEXT_WIDTH, bold_left=True) * BODY_LINE

    h += heading()
    for line in skill_lines:
        h += bullet_lines(line) * BODY_LINE

    def entries(items: list[Entry]) -> float:
        total = heading()
        for e in items:
            total += ENTRY_BEFORE + dated_line_lines(e.title, e.dates) * BODY_LINE
            if e.org:
                total += BODY_LINE
            total += sum(bullet_lines(b) for b in e.bullets) * BODY_LINE
        return total

    h += entries(experience)
    if projects:
        h += entries(projects)
    return h


def fill_ratio(height: float) -> float:
    return height / PAGE_BUDGET


def fits(height: float) -> bool:
    return height <= PAGE_BUDGET


def lines_left(height: float) -> int:
    return math.floor((PAGE_BUDGET - height) / BODY_LINE)
