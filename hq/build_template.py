"""Builds templates/resume_template.docx: a docxtpl (Jinja) template that loops
over your data, laid out like the November 2026 resume.

    python -m hq.build_template

The template holds styling only. Jobs, projects, bullets and skills come from
data/profile.json plus the generated content, so adding a job never needs a
template or code change. You can restyle the result in Word; keep each {{ }}
and {%p %} tag intact and in its own run, and keep sizes and spacing in sync
with hq/layout.py so the one-page fitter stays accurate.
"""

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt

from . import layout as L
from .paths import RESUME_TEMPLATE


def _fmt(p, *, line=L.BODY_LINE, before=0, after=0, align=None):
    pf = p.paragraph_format
    pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    pf.line_spacing = Pt(line)
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    if align is not None:
        p.alignment = align
    return p


def _run(p, text, *, bold=False, size=L.BODY_SIZE):
    r = p.add_run(text)
    r.bold = bold
    r.font.size = Pt(size)
    r.font.name = L.FONT
    return r


def _right_tab(p, position=L.TEXT_WIDTH):
    p.paragraph_format.tab_stops.add_tab_stop(Pt(position), WD_TAB_ALIGNMENT.RIGHT)


def _control(container, tag):
    """A {%p ... %} paragraph; docxtpl removes it when rendering."""
    p = container.add_paragraph()
    _fmt(p, line=1)
    p.add_run(tag)
    return p


def _bullet(doc):
    p = doc.add_paragraph(style="List Bullet")
    _fmt(p)
    pf = p.paragraph_format
    pf.left_indent = Pt(L.BULLET_INDENT)
    pf.first_line_indent = Pt(-L.BULLET_HANGING)
    # The built-in List Bullet numbering puts a tab stop at 0.25". Without clearing it,
    # the first line's text starts there while wrapped lines start at the left indent,
    # so lines 2+ look indented by an extra space. Clear it and tab to the indent instead.
    pf.tab_stops.add_tab_stop(Pt(18), WD_TAB_ALIGNMENT.CLEAR)  # 18pt = 0.25" (360 twips)
    pf.tab_stops.add_tab_stop(Pt(L.BULLET_INDENT))
    return p


def _heading(doc, text):
    p = doc.add_paragraph()
    _fmt(p, line=L.HEADING_LINE, before=L.HEADING_BEFORE, after=L.HEADING_AFTER)
    _run(p, text, bold=True, size=L.HEADING_SIZE)


def _no_borders(table):
    tbl_pr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "nil")
        borders.append(el)
    tbl_pr.append(borders)
    margins = OxmlElement("w:tblCellMar")
    for side in ("left", "right"):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:w"), "0")
        el.set(qn("w:type"), "dxa")
        margins.append(el)
    tbl_pr.append(margins)


def _align_bullet_numbering(doc) -> None:
    """Make the List Bullet list definition use our indent and tab stop, so the
    first line of a bullet and its wrapped lines start at the same position in
    every renderer (Word, Pages, Google Docs, Quick Look)."""
    numbering = doc.part.numbering_part.element
    style_num = doc.styles["List Bullet"].element.find(f".//{qn('w:numId')}").get(qn("w:val"))
    num = next(n for n in numbering.findall(qn("w:num")) if n.get(qn("w:numId")) == style_num)
    abstract_id = num.find(qn("w:abstractNumId")).get(qn("w:val"))
    abstract = next(a for a in numbering.findall(qn("w:abstractNum"))
                    if a.get(qn("w:abstractNumId")) == abstract_id)
    lvl = next(l for l in abstract.findall(qn("w:lvl")) if l.get(qn("w:ilvl")) == "0")
    twips = lambda pt: str(round(pt * 20))
    ppr = lvl.find(qn("w:pPr"))
    ppr.find(f"{qn('w:tabs')}/{qn('w:tab')}").set(qn("w:pos"), twips(L.BULLET_INDENT))
    ind = ppr.find(qn("w:ind"))
    ind.set(qn("w:left"), twips(L.BULLET_INDENT))
    ind.set(qn("w:hanging"), twips(L.BULLET_HANGING))


def build() -> None:
    doc = Document()

    section = doc.sections[0]
    section.page_width = Pt(L.PAGE_WIDTH)
    section.page_height = Pt(L.PAGE_HEIGHT)
    section.top_margin = Pt(L.MARGIN_TOP)
    section.bottom_margin = Pt(L.MARGIN_BOTTOM)
    section.left_margin = Pt(L.MARGIN_SIDE)
    section.right_margin = Pt(L.MARGIN_SIDE)

    normal = doc.styles["Normal"]
    normal.font.name = L.FONT
    normal.font.size = Pt(L.BODY_SIZE)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), L.FONT)
    _fmt(doc.styles["Normal"])  # style-level defaults

    # ---- Header: contact | name + title | links ---------------------------------
    widths = [L.TEXT_WIDTH * 0.3, L.TEXT_WIDTH * 0.4, L.TEXT_WIDTH * 0.3]
    table = doc.add_table(rows=1, cols=3)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    _no_borders(table)
    left, mid, right = table.rows[0].cells
    for cell, w in zip((left, mid, right), widths):
        cell.width = Pt(w)

    p = left.paragraphs[0]
    _fmt(p)
    _run(p, "{{ h.location }}", bold=True)
    for tag in ("{{ h.phone }}", "{{r h.email_link }}"):
        p = left.add_paragraph()
        _fmt(p)
        _run(p, tag, bold=tag.startswith("{{ h.phone"))

    p = mid.paragraphs[0]
    _fmt(p, line=L.NAME_LINE, align=WD_ALIGN_PARAGRAPH.CENTER)
    _run(p, "{{ h.name }}", bold=True, size=L.NAME_SIZE)
    p = mid.add_paragraph()
    _fmt(p, line=L.TITLE_LINE, align=WD_ALIGN_PARAGRAPH.CENTER)
    _run(p, "{{ h.title }}", bold=True, size=L.TITLE_SIZE)

    first = right.paragraphs[0]
    _fmt(first, line=1)
    first.add_run("{%p for link in h.links %}")
    p = right.add_paragraph()
    _fmt(p, align=WD_ALIGN_PARAGRAPH.RIGHT)
    _run(p, "{{r link }}")
    _control(right, "{%p endfor %}")

    # ---- Education ----------------------------------------------------------------
    _heading(doc, "EDUCATION")
    _control(doc, "{%p for e in education %}")
    p = _bullet(doc)
    _right_tab(p)
    _run(p, "{{ e.degree }}", bold=True)
    _run(p, "{{ e.rest }}")
    _run(p, "\t")
    _run(p, "{{ e.date }}", bold=True)
    _control(doc, "{%p endfor %}")

    # ---- Skills -------------------------------------------------------------------
    _heading(doc, "TECHNICAL SKILLS")
    _control(doc, "{%p for g in skills %}")
    p = _bullet(doc)
    _run(p, "{{ g.name }}:", bold=True)
    _run(p, " {{ g.list }}")
    _control(doc, "{%p endfor %}")

    # ---- Experience and projects ----------------------------------------------------
    def entries(heading, var, with_org):
        if var == "projects":
            _control(doc, "{%p if projects %}")
        _heading(doc, heading)
        _control(doc, f"{{%p for job in {var} %}}")
        p = doc.add_paragraph()
        _fmt(p, before=L.ENTRY_BEFORE)
        _right_tab(p)
        _run(p, "{{ job.title }}", bold=True)
        _run(p, "\t")
        _run(p, "{{ job.dates }}", bold=True)
        if with_org:
            p = doc.add_paragraph()
            _fmt(p)
            _run(p, "{{ job.org }}")
        _control(doc, "{%p for b in job.bullets %}")
        p = _bullet(doc)
        _run(p, "{{ b }}")
        _control(doc, "{%p endfor %}")
        _control(doc, "{%p endfor %}")
        if var == "projects":
            _control(doc, "{%p endif %}")

    entries("WORK EXPERIENCE", "experience", with_org=True)
    entries("PROJECTS", "projects", with_org=False)

    _align_bullet_numbering(doc)

    # python-docx starts documents with an empty paragraph; drop it so it takes no space
    body = doc.element.body
    first_p = body.find(qn("w:p"))
    if first_p is not None and not "".join(first_p.itertext()).strip():
        body.remove(first_p)

    RESUME_TEMPLATE.parent.mkdir(parents=True, exist_ok=True)
    doc.save(RESUME_TEMPLATE)
    print(f"Template written to {RESUME_TEMPLATE}")


if __name__ == "__main__":
    build()
