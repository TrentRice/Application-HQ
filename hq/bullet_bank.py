"""Sync your Word bullet bank (data/*.docx) into data/profile.json.

    python -m hq.bullet_bank           # sync if the document changed
    python -m hq.bullet_bank --force   # re-read the document even if unchanged

The bullet bank is the source of truth for experience and projects. Each sync:
  1. Reads the document's structure: jobs ("Company – Title" headings with a
     dates line), project headings with a "dates · tools" line, sub-headings,
     and bullets.
  2. Gives every bullet an ID from a fingerprint of its text. Bullets already in
     profile.json are reused as-is; only new or edited bullets go to Claude.
  3. Has Claude split new bullets into formula parts
     (action / what / tools / impact / metrics). Every number in the parts must
     appear in the original bullet; failures are retried once, then stored
     using your exact wording.
  4. Rewrites the experience and projects sections of profile.json. Header,
     education, skills and section_settings are left untouched.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from docx import Document
from pydantic import BaseModel

from .bullets import _numbers
from .paths import DATA, PROFILE

BATCH_SIZE = 20
DEFAULT_MAX_BULLETS = {"job": 2, "project": 1}

_MONTH = (r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|"
          r"Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?")
_POINT = rf"(?:{_MONTH}\s+\d{{4}}|(?:Spring|Summer|Fall|Autumn|Winter)\s+\d{{4}})"
_DATES = re.compile(rf"({_POINT})(?:\s*[–—-]\s*({_POINT}|Present|Current))?", re.IGNORECASE)


# ---- 1. Reading the document ------------------------------------------------------------


@dataclass
class RawBullet:
    text: str
    group: str
    one_liner: bool


@dataclass
class RawSection:
    kind: str  # "job" | "project"
    id: str
    title: str
    org: str = ""
    dates: str = ""
    stack: str = ""
    bullets: list[RawBullet] = field(default_factory=list)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48]


def _strip_parens(text: str) -> str:
    """'Associate Data Analyst (HR)' -> 'Associate Data Analyst'."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", text).strip()


def _dates_and_rest(text: str) -> tuple[str, str]:
    m = _DATES.search(text)
    if not m:
        return "", text
    dates = m.group(1) + (f" – {m.group(2)}" if m.group(2) else "")
    rest = text[m.end():].strip(" ·|-–\t")
    return dates, rest


def find_bank(profile_data: dict) -> Path:
    name = profile_data.get("bullet_bank") or ""
    if name:
        path = DATA / name
        if not path.exists():
            raise SystemExit(f"Bullet bank {path} not found (set in profile.json 'bullet_bank').")
        return path
    docs = [p for p in DATA.glob("*.docx") if not p.name.startswith("~$")]  # ~$ = Word lock file
    if len(docs) != 1:
        raise SystemExit(
            f"Expected exactly one .docx bullet bank in data/, found {len(docs)}. "
            "Set 'bullet_bank' in profile.json to the file name."
        )
    return docs[0]


def _is_bullet(p) -> bool:
    """A list item, whether numbered directly or through its style (e.g. Word's "List Bullet")."""
    if p._p.pPr is not None and p._p.pPr.numPr is not None:
        return True
    style = p.style
    while style is not None:
        ppr = style.element.pPr
        if ppr is not None and ppr.numPr is not None:
            return True
        style = style.base_style
    return False


def parse(path: Path) -> list[RawSection]:
    doc = Document(path)
    sections: list[RawSection] = []
    mode = "job"
    current: RawSection | None = None
    group = ""
    one_liner = False
    awaiting_meta = False  # the line after a heading holds dates (and tools)

    def start(kind: str, title: str, org: str = "") -> RawSection:
        nonlocal group, one_liner, awaiting_meta
        sec = RawSection(kind=kind, id=_slug(org or title), title=title, org=org)
        sections.append(sec)
        group, one_liner, awaiting_meta = "", False, True
        return sec

    for p in doc.paragraphs:
        text = " ".join(p.text.split())
        if not text:
            continue
        style = p.style.name.lower()
        is_bullet = _is_bullet(p)
        is_bold = any(r.bold for r in p.runs if r.text.strip())

        if is_bullet:
            if current is not None:
                current.bullets.append(RawBullet(text, group, one_liner))
            awaiting_meta = False
            continue

        if style.startswith("heading 1"):
            continue
        if style.startswith("heading 2"):
            if " – " in text or " - " in text:  # "Company – Title" = a job
                org, title = re.split(r"\s+[–-]\s+", text, maxsplit=1)
                mode = "job"
                current = start("job", _strip_parens(title), org.strip())
            else:  # "Jobs", "Boston University Projects", "Personal Projects"
                mode = "project" if "project" in text.lower() else "job"
                current = None
            continue
        if style.startswith("heading 3"):
            if mode == "project":
                current = start("project", _strip_parens(text))
            else:
                group, one_liner = text, False
            continue
        if style.startswith("heading 4"):
            group, one_liner = text, False
            continue

        # Normal paragraphs
        if awaiting_meta and current is not None:
            dates, rest = _dates_and_rest(text)
            if dates:
                current.dates = dates
                if current.kind == "project":
                    current.stack = rest
                awaiting_meta = False
                continue
        if is_bold:
            if text.lower().startswith("resume one-liner"):
                one_liner = True
            elif "project" in text.lower() and not _DATES.search(text):
                mode, current = "project", None  # e.g. "Dalhousie University Projects"
            elif _DATES.search(text):  # "Title (course) Sept 2025 – Apr 2026 · tools" on one line
                dates, rest = _dates_and_rest(text)
                title = _strip_parens(text[: _DATES.search(text).start()].strip())
                current = start("project", title)
                current.dates, current.stack = dates, rest
                awaiting_meta = False
                mode = "project"
            else:
                group, one_liner = text, False
    # Drop empty sections (e.g. a heading with no bullets yet)
    return [s for s in sections if s.bullets]


# ---- 2/3. Converting bullets into formula parts ---------------------------------------------


class Parts(BaseModel):
    index: int
    action: str
    what: str
    tools: list[str]
    impact: str
    metrics: list[str]
    keywords: list[str]


class PartsBatch(BaseModel):
    bullets: list[Parts]


def _fact_id(section_id: str, text: str) -> str:
    return f"{section_id}-{hashlib.sha1(text.encode()).hexdigest()[:8]}"


def _prompt(items: list[tuple[RawSection, RawBullet]], feedback: str = "") -> str:
    lines = []
    for i, (sec, b) in enumerate(items):
        context = sec.title + (f" at {sec.org}" if sec.org else "")
        if b.group:
            context += f" / {b.group}"
        if sec.stack:
            context += f" [project tools: {sec.stack}]"
        lines.append(f"{i}. ({context}) {b.text}")
    return f"""Split each resume bullet below into parts for this formula:
    [action verb] [what was done] [with what tools or methods], [impact]

For each bullet return:
- index: the bullet's number.
- action: the bullet's opening past-tense verb, exactly as written.
- what: what was done, in the bullet's own words, without the verb, tool phrase or impact.
- tools: the specific tools, languages, platforms or methods named in the bullet
  (e.g. "Power BI", "SQL", "k-means"). If the bullet names none, you may use ones from
  its project tools list that clearly apply; otherwise return an empty list.
- impact: the result or outcome clause in the bullet's own words, or "" if there is none.
- metrics: every quantity in the bullet as a short phrase, copied exactly
  (e.g. "650 hours saved per year", "ROC-AUC 0.73"). Empty list if none.
- keywords: 3-6 skill or domain keywords a recruiter would search for.

RULES: Use only the bullet's words and facts. Never add, round or change a number.

BULLETS:
{chr(10).join(lines)}
{feedback}"""


def _problems(parts: Parts, bullet: RawBullet, section: RawSection) -> list[str]:
    allowed = _numbers(" ".join([bullet.text, section.stack, bullet.group, section.title]))
    combined = " ".join([parts.action, parts.what, *parts.tools, parts.impact, *parts.metrics])
    out = []
    invented = _numbers(combined) - allowed
    if invented:
        out.append(f"numbers not in the bullet: {', '.join(sorted(invented))}")
    if not parts.action.strip() or " " in parts.action.strip():
        out.append("action must be the single opening verb")
    if not parts.what.strip():
        out.append("what is empty")
    return out


def _fallback(bullet: RawBullet) -> dict:
    """Store the bullet in your exact words if Claude's split can't be trusted."""
    first, _, rest = bullet.text.partition(" ")
    return {"action": first, "what": rest.rstrip("."), "tools": [], "impact": "",
            "metrics": [bullet.text] if _numbers(bullet.text) else [], "keywords": []}


def _convert(items: list[tuple[RawSection, RawBullet]]) -> tuple[dict[int, dict], list[str]]:
    from .llm import generate

    results: dict[int, dict] = {}
    notes: list[str] = []
    for start in range(0, len(items), BATCH_SIZE):
        batch = items[start:start + BATCH_SIZE]
        print(f"Converting bullets {start + 1}-{start + len(batch)} of {len(items)}...", flush=True)
        todo = list(range(len(batch)))
        feedback = ""
        for attempt in range(2):
            subset = [batch[i] for i in todo]
            answer = generate(_prompt(subset, feedback), PartsBatch)
            by_index = {p.index: p for p in answer.bullets if 0 <= p.index < len(subset)}
            retry, problems = [], []
            for local, i in enumerate(todo):
                sec, bullet = batch[i]
                parts = by_index.get(local)
                issues = ["missing from answer"] if parts is None else _problems(parts, bullet, sec)
                if issues:
                    retry.append(i)
                    problems.append(f"- bullet {len(retry) - 1}: {'; '.join(issues)}")
                else:
                    results[start + i] = parts.model_dump(exclude={"index"})
            todo = retry
            if not todo:
                break
            feedback = "\nFIX THESE PROBLEMS FROM YOUR LAST ATTEMPT:\n" + "\n".join(problems)
        for i in todo:
            sec, bullet = batch[i]
            results[start + i] = _fallback(bullet)
            notes.append(f"Stored in your exact words (couldn't split cleanly): {bullet.text[:80]}")
    return results, notes


# ---- 4. Writing the profile -----------------------------------------------------------------


def _file_fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sync(force: bool = False) -> dict:
    data = json.loads(PROFILE.read_text(encoding="utf-8"))
    bank = find_bank(data)
    fingerprint = _file_fingerprint(bank)
    if not force and data.get("bullet_bank_fingerprint") == fingerprint:
        return {"changed": False, "file": bank.name}

    sections = parse(bank)
    if not sections:
        raise SystemExit(f"No jobs or projects with bullets were found in {bank.name}.")

    existing = {f["id"]: f for s in data.get("experience", []) + data.get("projects", []) for f in s["facts"]}
    settings = data.get("section_settings", {})

    # Which bullets are new or edited?
    todo: list[tuple[RawSection, RawBullet]] = []
    for sec in sections:
        for b in sec.bullets:
            if _fact_id(sec.id, b.text) not in existing:
                todo.append((sec, b))
    converted, notes = _convert(todo) if todo else ({}, [])
    new_parts = {_fact_id(sec.id, b.text): converted[i] for i, (sec, b) in enumerate(todo)}

    out = {"job": [], "project": []}
    kept_ids = set()
    for sec in sections:
        facts = []
        for b in sec.bullets:
            fid = _fact_id(sec.id, b.text)
            if fid in kept_ids:
                continue  # identical bullet repeated in the same section
            kept_ids.add(fid)
            base = existing.get(fid) or new_parts[fid]
            fact = {k: base.get(k, v) for k, v in
                    {"action": "", "what": "", "tools": [], "impact": "", "metrics": [], "keywords": []}.items()}
            fact.update({"id": fid, "source": b.text, "group": b.group, "one_liner": b.one_liner})
            facts.append(fact)
        max_bullets = settings.get(sec.id, {}).get("max_bullets", DEFAULT_MAX_BULLETS[sec.kind])
        out[sec.kind].append({
            "id": sec.id, "title": settings.get(sec.id, {}).get("title", sec.title),
            "org": sec.org, "dates": sec.dates, "stack": sec.stack,
            "max_bullets": max_bullets, "facts": facts,
        })

    removed = len(set(existing) - kept_ids)
    undated = [s["title"] for s in out["job"] + out["project"] if not s["dates"]]
    data["experience"], data["projects"] = out["job"], out["project"]
    data["bullet_bank_fingerprint"] = fingerprint
    PROFILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    summary = {
        "changed": True, "file": bank.name,
        "jobs": len(out["job"]), "projects": len(out["project"]),
        "facts": len(kept_ids), "added": len(todo), "removed": removed,
        "notes": notes + [f"No dates found for: {t}" for t in undated],
    }
    return summary


def describe(summary: dict) -> str:
    if not summary["changed"]:
        return f"Bullet bank unchanged ({summary['file']})."
    return (f"Synced {summary['file']}: {summary['jobs']} jobs, {summary['projects']} projects, "
            f"{summary['facts']} facts (added {summary['added']}, removed {summary['removed']}).")


if __name__ == "__main__":
    result = sync(force="--force" in sys.argv)
    print(describe(result))
    for note in result.get("notes", []):
        print(f"  ⚠ {note}")
