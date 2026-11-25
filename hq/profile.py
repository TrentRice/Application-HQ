"""The stored profile (data/profile.json).

You edit: header, education, skills, projects_to_show, section_settings.
Generated from your Word bullet bank by hq/bullet_bank.py: experience and projects.

Every experience fact is stored in the bullet formula's parts:
    [action verb] [what you did] [with what tools or methods] [impact, ideally quantified]
plus the original bullet text it came from.
"""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, Field

from .paths import PROFILE


class Fact(BaseModel):
    id: str
    action: str
    what: str
    tools: list[str] = Field(default_factory=list)
    impact: str = ""
    metrics: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    source: str = ""  # the original bullet from the bullet bank, word for word
    group: str = ""  # sub-heading it sat under, e.g. "HR Pathfinder (AI knowledge agent)"
    one_liner: bool = False  # listed under "Resume one-liners" in the bullet bank

    def source_text(self) -> str:
        """Everything the model is allowed to draw from for this fact."""
        return " ".join([self.action, self.what, *self.tools, self.impact, *self.metrics, self.source])

    def embed_text(self, section: "Section") -> str:
        return (
            f"{section.title} ({section.org}). {self.group}. {self.action} {self.what}. "
            f"Tools: {', '.join(self.tools)}. Impact: {self.impact} {'; '.join(self.metrics)}. "
            f"Keywords: {', '.join(self.keywords)}"
        )


class Section(BaseModel):
    """A job (experience) or a project."""

    id: str
    title: str
    org: str = ""
    dates: str
    max_bullets: int = 3
    stack: str = ""  # tools line under a project heading in the bullet bank
    facts: list[Fact]


class Link(BaseModel):
    label: str
    url: str


class Header(BaseModel):
    name: str
    title: str
    location: str
    phone: str
    email: str
    links: list[Link] = Field(default_factory=list)
    letter_location: str = ""  # location line on the cover letter; defaults to `location`


class Education(BaseModel):
    degree: str
    school: str
    detail: str = ""
    date: str


class SkillGroup(BaseModel):
    name: str
    max_items: int = 8
    pool: list[str]


class Profile(BaseModel):
    header: Header
    education: list[Education]
    skills: list[SkillGroup]
    projects_to_show: int = 2
    # Per-section overrides keyed by section id, e.g. {"ns-health": {"max_bullets": 2}}
    section_settings: dict[str, dict] = Field(default_factory=dict)
    bullet_bank: str = ""  # file name in data/; empty = the only .docx there
    bullet_bank_fingerprint: str = ""  # hash of the bullet bank at the last sync
    experience: list[Section]
    projects: list[Section] = Field(default_factory=list)

    def sections(self) -> list[Section]:
        return [*self.experience, *self.projects]

    def all_facts(self) -> list[tuple[Section, Fact]]:
        return [(s, f) for s in self.sections() for f in s.facts]

    def fingerprint(self) -> str:
        payload = json.dumps([f.model_dump() for _, f in self.all_facts()], sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()


def load_profile() -> Profile:
    if not PROFILE.exists():
        raise SystemExit(
            "data/profile.json not found. Copy examples/profile.example.json to data/profile.json, "
            "fill in your details, and put your bullet bank .docx in data/ (see README > Setup)."
        )
    return Profile.model_validate_json(PROFILE.read_text(encoding="utf-8"))
