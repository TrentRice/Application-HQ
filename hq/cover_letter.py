"""Generate a tailored cover letter for data/job_description.txt.

    python -m hq.cover_letter

Uses the same stored facts and vector ranking as the resume, then fills the
{{NAME}} / {{LOCATION}} / {{PHONE}} / {{EMAIL}} placeholders (from your profile header) and
{{INTRO}} / {{BODY}} / {{WHY_COMPANY}} / {{CLOSING}} (written by Claude) in
templates/cover_letter_template.docx.
"""

from __future__ import annotations

import json

from docx import Document
from pydantic import BaseModel

from .index import rank
from .llm import generate
from .paths import COVER_DOCX, COVER_JSON, COVER_TEMPLATE, JOB_DESCRIPTION, OUTPUT
from .profile import load_profile

TOP_FACTS = 15


class CoverLetter(BaseModel):
    intro: str
    body: str
    why_company: str
    closing: str


def _replace_keeping_format(paragraph, key: str, value: str) -> None:
    """Replace a placeholder but keep the template's font, size and color.

    Setting paragraph.text directly deletes every run, and with them the
    formatting, so the text falls back to Word's default font. Instead, put
    the new text in the run that holds the placeholder (or the first run, if
    Word split the placeholder across several runs) and empty the others.
    """
    runs = paragraph.runs
    holder = next((r for r in runs if key in r.text), None)
    if holder is not None:
        holder.text = holder.text.replace(key, value)
        return
    full = paragraph.text.replace(key, value)
    runs[0].text = full
    for r in runs[1:]:
        r.text = ""


def run() -> None:
    profile = load_profile()
    job = JOB_DESCRIPTION.read_text(encoding="utf-8").strip()

    print("Ranking stored experience against the job...")
    scores = rank(profile, job)
    pairs = sorted(profile.all_facts(), key=lambda sf: -scores.get(sf[1].id, 0))[:TOP_FACTS]
    experience = "\n".join(
        f"- {s.title}{' at ' + s.org if s.org else ''}: "
        + (f.source or f"{f.action} {f.what}; tools: {', '.join(f.tools)}; impact: {f.impact} {'; '.join(f.metrics)}")
        for s, f in pairs
    )

    print("Writing cover letter with Claude...")
    letter = generate(
        f"""Write a professional, specific cover letter for {profile.header.name}.

JOB DESCRIPTION:
{job}

RELEVANT EXPERIENCE (use ONLY this; never invent experience, tools or numbers):
{experience}

Return four paragraphs:
- intro: the role being applied for and a one-sentence hook tying the candidate's background to it.
- body: 2-3 concrete accomplishments from the experience that match the job's needs, with their numbers.
- why_company: why this company and role specifically, based only on the job description.
- closing: a short, confident close inviting a conversation.
Do not include a greeting or sign-off; the template already has them. Keep the letter under 350 words.""",
        CoverLetter,
    )

    OUTPUT.mkdir(exist_ok=True)
    COVER_JSON.write_text(json.dumps(letter.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8")

    doc = Document(COVER_TEMPLATE)
    h = profile.header
    replacements = {
        "{{NAME}}": h.name,
        "{{LOCATION}}": h.letter_location or h.location,
        "{{PHONE}}": h.phone,
        "{{EMAIL}}": h.email,
        "{{INTRO}}": letter.intro,
        "{{BODY}}": letter.body,
        "{{WHY_COMPANY}}": letter.why_company,
        "{{CLOSING}}": letter.closing,
    }
    for paragraph in doc.paragraphs:
        for key, value in replacements.items():
            if key in paragraph.text:
                _replace_keeping_format(paragraph, key, value)
    doc.save(COVER_DOCX)
    print("Cover letter created.")


if __name__ == "__main__":
    run()
