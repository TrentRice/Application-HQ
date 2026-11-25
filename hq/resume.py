"""Generate a tailored, one-page resume for data/job_description.txt.

    python -m hq.resume

Pipeline:
  1. Rank every stored fact against the job description (vector search).
  2. Claude picks facts and writes each bullet in formula parts
     [action] [what] [how: tools/methods], [impact].
  3. Each bullet is checked (action verb, tools present, no invented numbers,
     stored metrics actually used). Failures go back to Claude (up to twice); anything
     still failing falls back to the stored fact itself.
  4. The lowest-relevance bullets are trimmed until the page fits on one page.
  5. The result is rendered into templates/resume_template.docx.

Writes output/tailored_resume.docx, output/resume.json, output/resume_report.json.
"""

from __future__ import annotations

import json

from docxtpl import DocxTemplate, RichText
from pydantic import BaseModel

from . import layout
from .bullets import Bullet, check, from_fact
from .index import rank
from .llm import generate
from .paths import JOB_DESCRIPTION, OUTPUT, RESUME_DOCX, RESUME_JSON, RESUME_REPORT, RESUME_TEMPLATE
from .profile import Profile, Section, load_profile


# ---- What Claude returns ------------------------------------------------------------


class SectionDraft(BaseModel):
    id: str
    bullets: list[Bullet]


class SkillsDraft(BaseModel):
    name: str
    items: list[str]


class ResumeDraft(BaseModel):
    company: str  # hiring company, read from the job description (used to name the files)
    role: str  # job title, read from the job description
    skills: list[SkillsDraft]
    experience: list[SectionDraft]
    projects: list[SectionDraft]


# ---- Prompt ---------------------------------------------------------------------------


def _facts_block(section: Section, scores: dict[str, float]) -> str:
    header = f'### id="{section.id}" | {section.title} | {section.org} | max {section.max_bullets} bullets'
    if section.stack:
        header += f" | project tools: {section.stack}"
    lines = [header]
    for f in sorted(section.facts, key=lambda f: -scores.get(f.id, 0)):
        entry = {
            "fact_id": f.id,
            "relevance": scores.get(f.id, 0),
            "original": f.source or f"{f.action} {f.what}, {f.impact}",
            "tools": f.tools,
            "metrics": f.metrics,
        }
        if f.group:
            entry["group"] = f.group
        if f.one_liner:
            entry["one_liner"] = True
        lines.append(json.dumps(entry, ensure_ascii=False))
    return "\n".join(lines)


ONE_LINE = 95  # characters that fit on one bullet line at the template's font and width
TWO_LINES = 185


def _prompt(profile: Profile, job: str, scores: dict[str, float], feedback: str = "") -> str:
    experience = "\n\n".join(_facts_block(s, scores) for s in profile.experience)
    projects = "\n\n".join(_facts_block(s, scores) for s in profile.projects)
    skills = "\n".join(f'- "{g.name}" (max {g.max_items}): {", ".join(g.pool)}' for g in profile.skills)
    return f"""You are an expert technical resume writer tailoring a one-page resume to a job.

JOB DESCRIPTION:
{job}

STORED EXPERIENCE FACTS (the ONLY source of truth; higher relevance = closer match to the job):
{experience}

PROJECT POOL:
{projects}

SKILL POOLS:
{skills}

TASK
0. company and role: the hiring organization's name and the job title, as written in the job
   description (e.g. "Washington Nationals", "Junior Analyst, Player Projections"). Use "" if unknown.
1. experience: one entry per job id above, in the same order. Choose up to that job's
   max bullets, picking the facts that best match the job description.
2. projects: choose exactly {profile.projects_to_show} projects from the pool that best match the job.
   One bullet each.
3. skills: for each skill group, choose items ONLY from its pool, most relevant to the job first,
   up to its max. Use the exact group names.

BULLET FORMULA (every bullet, no exceptions). Each bullet is returned in parts:
- action: ONE strong past-tense verb (e.g. Developed, Built, Engineered, Automated, Led).
  Never Helped/Assisted/Worked/Responsible/Utilized. Vary verbs within a job.
- what: what was done, without the verb. Reword toward the job's language where truthful.
- how: the tools or methods, as a phrase starting with a preposition, e.g. "using Python and SQL"
  or "with Power BI". Prefer tools that appear in the job description.
- impact: the result, quantified whenever the fact has a metric, e.g. "saving 650 hours annually".
  Empty string only if the fact has no impact at all.
- fact_ids: the fact_id(s) this bullet is built from (1-2 facts, same job only).
The bullet is assembled as: "<action> <what> <how>, <impact>."

RULES
- Use only information in the facts. Never invent tools, numbers, scope, or outcomes.
- Every number in a bullet must appear in that bullet's facts.
- LENGTH IS A HARD LIMIT. Count the characters of the assembled bullet:
  target {ONE_LINE} characters or fewer (one line); never more than {TWO_LINES} characters (two lines).
  Cut filler words, keep 1-3 tools, and do not restate the same thing twice.
- When choosing between facts of similar relevance, prefer ones with a quantified impact.
- Keep proper names of products and projects (e.g. HR Pathfinder, Interview HQ) instead of generic descriptions.
- Each fact's "original" is the candidate's own bullet. Condense it to fit; never add to it.
- For projects, facts marked one_liner are the candidate's preferred summary bullets; favor them.
- Mirror the job description's keywords where they truthfully describe the work (ATS).
{feedback}"""


# ---- Checking and repair -------------------------------------------------------------


def _review(profile: Profile, draft: ResumeDraft):
    """Returns (problems for Claude, warnings for you), keyed by section id."""
    facts = {f.id: f for _, f in profile.all_facts()}
    section_of = {f.id: s.id for s, f in profile.all_facts()}
    problems: list[str] = []
    for sd in [*draft.experience, *draft.projects]:
        for b in sd.bullets:
            used = [facts[i] for i in b.fact_ids if i in facts and section_of[i] == sd.id]
            if not used:
                problems.append(f'[{sd.id}] "{b.text}": fact_ids must reference facts from this section')
                continue
            errors, _ = check(b, used)
            if layout.bullet_lines(b.text) > 2:
                errors.append(f"{len(b.text)} characters, over the {TWO_LINES} limit; shorten it")
            for e in errors:
                problems.append(f'[{sd.id}] "{b.text}": {e}')
    return problems


def _finalize(profile: Profile, draft: ResumeDraft, scores: dict[str, float]):
    """Apply fallbacks and build the final sections plus per-bullet warnings."""
    facts = {f.id: f for _, f in profile.all_facts()}
    drafts = {sd.id: sd for sd in [*draft.experience, *draft.projects]}
    notes: list[dict] = []

    def build(section: Section, limit: int) -> list[tuple[Bullet, float]]:
        out: list[tuple[Bullet, float]] = []
        sd = drafts.get(section.id)
        own = {f.id for f in section.facts}
        seen: set[str] = set()
        for b in (sd.bullets if sd else [])[:limit]:
            used = [facts[i] for i in b.fact_ids if i in own]
            errors, warnings = check(b, used) if used else (["no valid facts"], [])
            if errors or layout.bullet_lines(b.text) > 2:
                fallback = next((f for f in used if f), None) or max(section.facts, key=lambda f: scores.get(f.id, 0))
                notes.append({"section": section.title, "bullet": from_fact(fallback).text,
                              "note": "used your stored wording (generated bullet failed checks: "
                                      + "; ".join(errors or ["too long"]) + ")"})
                b, used = from_fact(fallback), [fallback]
                _, warnings = check(b, used)
            if any(f.id in seen for f in used):
                continue  # never print the same fact twice
            seen.update(f.id for f in used)
            for w in warnings:
                notes.append({"section": section.title, "bullet": b.text, "note": w})
            out.append((b, max(scores.get(f.id, 0) for f in used)))
        if not out:  # Claude skipped this job entirely
            best = sorted(section.facts, key=lambda f: -scores.get(f.id, 0))[:limit]
            out = [(from_fact(f), scores.get(f.id, 0)) for f in best]
        return out

    experience = [(s, build(s, s.max_bullets)) for s in profile.experience]

    chosen = [sd.id for sd in draft.projects if any(p.id == sd.id for p in profile.projects)]
    if len(chosen) < profile.projects_to_show:  # top up by relevance
        by_score = sorted(profile.projects, key=lambda p: -max(scores.get(f.id, 0) for f in p.facts))
        chosen += [p.id for p in by_score if p.id not in chosen]
    chosen = chosen[: profile.projects_to_show]
    projects = [(s, build(s, s.max_bullets)) for s in profile.projects if s.id in chosen]
    projects.sort(key=lambda sb: chosen.index(sb[0].id))
    return experience, projects, notes


def _skills(profile: Profile, draft: ResumeDraft) -> list[tuple[str, list[str]]]:
    picked = {g.name.lower(): g.items for g in draft.skills}
    out = []
    for group in profile.skills:
        pool = {p.lower(): p for p in group.pool}
        items = [pool[i.lower()] for i in picked.get(group.name.lower(), []) if i.lower() in pool]
        items = list(dict.fromkeys(items)) or group.pool
        items = items[: group.max_items]
        while len(items) > 1 and layout.bullet_lines(f"{group.name}: {', '.join(items)}") > 1:
            items.pop()  # keep every skill group to a single line
        out.append((group.name, items))
    return out


# ---- One page -------------------------------------------------------------------------


def _fit(profile: Profile, skills, experience, projects):
    education = [(f"{e.degree}, {e.school}" + (f", {e.detail}" if e.detail else ""), e.date)
                 for e in profile.education]
    skill_lines = [f"{name}: {', '.join(items)}" for name, items in skills]
    trimmed: list[str] = []

    def height():
        to_entries = lambda rows: [
            layout.Entry(s.title, s.org, s.dates, [b.text for b, _ in bullets]) for s, bullets in rows
        ]
        return layout.page_height(education, skill_lines, to_entries(experience), to_entries(projects))

    while not layout.fits(height()):
        # lowest-relevance bullet among jobs that still have more than one
        candidates = [(score, i, j) for i, (_, bl) in enumerate(experience) if len(bl) > 1
                      for j, (_, score) in enumerate(bl)]
        if candidates:
            _, i, j = min(candidates)
            trimmed.append(experience[i][1].pop(j)[0].text)
        elif len(projects) > 1:
            s, bl = projects.pop()
            trimmed.append(f"Project: {s.title}")
        else:
            break
    return height(), trimmed


# ---- Main -------------------------------------------------------------------------------


def run() -> None:
    profile = load_profile()
    job = JOB_DESCRIPTION.read_text(encoding="utf-8").strip()
    if not job:
        raise SystemExit("data/job_description.txt is empty.")

    print("Ranking stored experience against the job...")
    scores = rank(profile, job)

    print("Writing bullets with Claude...")
    draft = generate(_prompt(profile, job, scores), ResumeDraft)
    for attempt in range(2):  # up to two revision rounds
        problems = _review(profile, draft)
        if not problems:
            break
        print(f"{len(problems)} bullet(s) failed checks, asking for a revision...")
        feedback = "\nYOUR PREVIOUS ATTEMPT HAD THESE PROBLEMS. FIX ALL OF THEM:\n" + "\n".join(
            f"- {p}" for p in problems
        )
        draft = generate(_prompt(profile, job, scores, feedback), ResumeDraft)

    experience, projects, notes = _finalize(profile, draft, scores)
    skills = _skills(profile, draft)
    height, trimmed = _fit(profile, skills, experience, projects)

    if not RESUME_TEMPLATE.exists():
        from .build_template import build

        build()

    tpl = DocxTemplate(RESUME_TEMPLATE)

    def link(text: str, url: str) -> RichText:
        rt = RichText()
        rt.add(text, url_id=tpl.build_url_id(url), color="1155CC", underline=True, bold=True,
               font=layout.FONT, size=layout.BODY_SIZE * 2)
        return rt

    h = profile.header
    context = {
        "h": {
            "name": h.name, "title": h.title, "location": h.location, "phone": h.phone,
            "email_link": link(h.email, f"mailto:{h.email}"),
            "links": [link(l.label, l.url) for l in h.links],
        },
        "education": [
            {"degree": e.degree, "rest": f", {e.school}" + (f", {e.detail}" if e.detail else ""), "date": e.date}
            for e in profile.education
        ],
        "skills": [{"name": name, "list": ", ".join(items)} for name, items in skills],
        "experience": [
            {"title": s.title, "org": s.org, "dates": s.dates, "bullets": [b.text for b, _ in bl]}
            for s, bl in experience
        ],
        "projects": [
            {"title": s.title, "dates": s.dates, "bullets": [b.text for b, _ in bl]} for s, bl in projects
        ],
    }
    tpl.render(context, autoescape=True)
    OUTPUT.mkdir(exist_ok=True)
    tpl.save(RESUME_DOCX)

    plain = {k: v for k, v in context.items() if k != "h"}
    RESUME_JSON.write_text(json.dumps(plain, indent=2, ensure_ascii=False), encoding="utf-8")
    report = {
        "company": draft.company.strip(),
        "role": draft.role.strip(),
        "page_fill": round(layout.fill_ratio(height), 3),
        "lines_free": layout.lines_left(height),
        "trimmed_to_fit": trimmed,
        "notes": notes,
    }
    RESUME_REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Resume created ({report['page_fill']:.0%} of one page, {len(notes)} note(s)).")


if __name__ == "__main__":
    run()
