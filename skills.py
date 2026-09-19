"""The skill shelf - same shape as the den: .agents/skills/<id>/SKILL.md

Front matter carries `name` and `description`; everything after it is the
body. Activation mimics the den: a skill loads when the message names it as
`$id`, `@id`, or `/skill:id`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import paths

SHELF = ".agents/skills"


@dataclass(frozen=True)
class Skill:
    id: str
    name: str
    description: str
    body: str


def _split_front_matter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text.strip()
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text.strip()
    meta: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip()
    return meta, parts[2].strip()


def catalog() -> list[Skill]:
    root = paths.resolve(SHELF)
    if not root.is_dir():
        return []
    found: list[Skill] = []
    for entry in sorted(root.iterdir()):
        skill_file = entry / "SKILL.md"
        if not skill_file.is_file():
            continue
        meta, body = _split_front_matter(skill_file.read_text(encoding="utf-8"))
        found.append(Skill(
            id=entry.name,
            name=meta.get("name", entry.name),
            description=meta.get("description", ""),
            body=body,
        ))
    return found


def load(skill_id: str) -> Skill | None:
    for skill in catalog():
        if skill.id == skill_id.lower():
            return skill
    return None


def trigger_ids(text: str) -> list[str]:
    """Yield candidate skill ids named in the message."""
    ids = {m.group(1) for m in re.finditer(r"[$/]skill:([a-z0-9][a-z0-9\-_]*)", text, re.I)}
    ids |= {m.group(1) for m in re.finditer(r"(?<![\w./@])[$@]([a-z][a-z0-9\-_]{2,})", text, re.I)}
    known = {s.id for s in catalog()}
    return sorted(i.lower() for i in ids if i.lower() in known)
