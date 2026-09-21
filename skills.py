"""The skill shelf - same shape as the den: .agents/skills/<id>/SKILL.md

Front matter carries `name` and `description`; everything after it is the
body. Activation mimics the den: a skill loads when the message names it as
`$id`, `@id`, or `/skill:id`.

A skill also carries an ADDENDUM - `RULES.md` beside it - holding rules added
after the fact. It is a second file on purpose; see ADDENDUM below.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import paths

SHELF = ".agents/skills"
# Additions to a skill live in their OWN file, never in SKILL.md. The reason is
# narrow and worth keeping: composing a SKILL.md means composing the WHOLE file,
# so a one-line rule written that way replaces the skill it was meant to sit
# beside - and `website` is 31 KB of craft that one call could have flattened.
# A file that only ever holds additions cannot do that.
ADDENDUM = "RULES.md"
# An addendum rides in my prompt whenever its skill loads, and on an
# always-loaded skill that is EVERY turn. So a rule is a line and not an essay,
# and the whole file is capped. When it fills up, the right move is to prune it.
RULE_MAX = 400
RULES_MAX = 4000
# The always-loaded voice is my identity AND my limits, so nothing is appended to
# it: master edits that file himself. A list rather than an absence, so relaxing
# this is a visible decision instead of an accident.
RULES_LOCKED = ("lulu-voice",)


@dataclass(frozen=True)
class Skill:
    id: str
    name: str
    description: str
    body: str
    # What master told me since, in the addendum beside SKILL.md. Kept separate
    # from `body` so the curated file stays byte-identical.
    rules: str = ""
    # Words that make `rules` relevant on their own, declared in the addendum's
    # front matter. Naming a skill outright still loads everything.
    triggers: tuple[str, ...] = ()

    @property
    def text(self) -> str:
        """What I actually read: the skill, then whatever was added to it."""
        if not self.rules:
            return self.body
        return f"{self.body}\n\n{self.rules}"


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


def _addendum(entry) -> tuple[str, tuple[str, ...]]:
    """The added rules beside a skill, and the words that make them relevant."""
    path = entry / ADDENDUM
    if not path.is_file():
        return "", ()
    meta, body = _split_front_matter(path.read_text(encoding="utf-8"))
    declared = meta.get("triggers", "")
    triggers = tuple(w.strip().lower() for w in re.split(r"[,\n]", declared)
                     if w.strip())
    return body.strip(), triggers


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
        rules, triggers = _addendum(entry)
        found.append(Skill(
            id=entry.name,
            name=meta.get("name", entry.name),
            description=meta.get("description", ""),
            body=body,
            rules=rules,
            triggers=triggers,
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


def keyword_ids(text: str) -> list[str]:
    """Skills whose DECLARED triggers appear in the message.

    Naming a skill is a request to read it; this is the other half, so a rule can
    be relevant without being named. Only a skill carrying an addendum can
    declare triggers, and only the addendum rides along for one of these - the
    whole craft body on a passing keyword would be thousands of tokens a message,
    which is a different thing from relevance.
    """
    hay = (text or "").lower()
    if not hay:
        return []
    hits: list[str] = []
    for skill in catalog():
        if not skill.rules or not skill.triggers:
            continue
        for trigger in skill.triggers:
            if re.search(rf"(?<![\w-]){re.escape(trigger)}(?![\w-])", hay):
                hits.append(skill.id)
                break
    return hits


def keyword_rules(text: str) -> list[tuple[str, str]]:
    """`(skill id, addendum)` for every skill a passing keyword made relevant.

    These RIDE WITH a turn as context and never stand in for the reply. That
    distinction IS the fix, so it is worth spelling out: the first version
    returned the addendum from `lulu_bot.skill_command`, and that method's
    return value REPLACES the turn - on_message calls it first and only runs
    the brain when it gets `None` back. So a message that merely contained the
    word "sigil" got the rules recited as her answer and the brain never ran.
    Master: "we broke her with the rule, she just responds with the rule."

    She was not confused and she was not refusing. She was never asked.
    """
    rules: list[tuple[str, str]] = []
    for skill_id in keyword_ids(text):
        skill = load(skill_id)
        if skill and skill.rules:
            rules.append((skill.id, skill.rules))
    return rules


def append_rule(skill_id: str, rule: str, existing: str = "",
                triggers: str = "") -> str:
    """`existing` addendum text plus one more rule, ready to stage.

    Raises ValueError with the reason, the way compose_skill does, so the caller
    can hand the refusal back as a tool result in the turn she made it. Only
    ADDITIONS are composed here - the skill's own SKILL.md is neither read nor
    written, which is the entire point of the second file.
    """
    sid = (skill_id or "").strip().lower()
    if sid in RULES_LOCKED:
        raise ValueError(
            f"{sid} is my always-loaded voice - master edits that one himself, "
            f"so a rule cannot be appended to it")
    rule = " ".join(str(rule or "").split())
    if not rule:
        raise ValueError("a rule needs words in it")
    if len(rule) > RULE_MAX:
        raise ValueError(f"that is {len(rule)} chars - a rule is one line (under "
                         f"{RULE_MAX}), not a paragraph")
    old_meta: dict = {}
    old_body = ""
    if (existing or "").strip():
        old_meta, old_body = _split_front_matter(existing)
    kept: list[str] = []
    for line in old_body.splitlines():
        line = line.strip()
        if line.startswith(("-", "*")):
            kept.append(line.lstrip("-* ").strip())
    kept = [k for k in kept if k]
    if rule in kept:
        raise ValueError("that rule is already on this skill")
    declared = " ".join((triggers or "").split()) or old_meta.get("triggers", "")
    body = "## Rules\n" + "\n".join(f"- {r}" for r in kept + [rule]) + "\n"
    text = f"---\ntriggers: {declared}\n---\n\n{body}" if declared else body
    if len(text) > RULES_MAX:
        raise ValueError(
            f"that would make {sid}'s addendum {len(text)} chars, over the "
            f"{RULES_MAX} cap - it rides in the prompt every time the skill "
            f"loads, so prune it before adding more")
    return text


def rule_count(skill: Skill) -> int:
    """How many rules are already filed against a skill.

    The shelf shows this so a second copy of a rule is visible AS a second copy.
    Rules ending up "all over the place" is not something a bare list of names and
    descriptions can show you, and she is the one who has to notice.
    """
    return sum(1 for line in skill.rules.splitlines()
               if line.strip().startswith("-"))
