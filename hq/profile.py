"""The stored profile (data/profile.json): the single source of truth.

Every experience fact is stored in the bullet formula's parts:
    [action verb] [what you did] [with what tools or methods] [impact, ideally quantified]
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

    def source_text(self) -> str:
        """Everything the model is allowed to draw from for this fact."""
        return " ".join([self.action, self.what, *self.tools, self.impact, *self.metrics])

    def embed_text(self, section: "Section") -> str:
        return (
            f"{section.title} ({section.org}). {self.action} {self.what}. "
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
    return Profile.model_validate_json(PROFILE.read_text(encoding="utf-8"))
