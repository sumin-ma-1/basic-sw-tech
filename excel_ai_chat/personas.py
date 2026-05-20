"""Built-in and custom personas for personalization."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

PERSONA_NONE = "__none__"  # legacy / clear-custom → maps to default
CUSTOM_INSTRUCTIONS_ID = "__custom__"
DEFAULT_PERSONA_ID = "default"
MAX_CUSTOM_PERSONAS = 20

_LEGACY_PERSONA_IDS: dict[str, str] = {
    "balanced": "default",
    "concise": "default",
    "teacher": "default",
    "analyst": "default",
}


@dataclass(frozen=True)
class PersonaTemplate:
    id: str
    name: str
    about_user: str
    response_style: str
    tooltip: str


@dataclass
class CustomPersona:
    id: str
    name: str
    about_user: str
    response_style: str

    @staticmethod
    def new_id() -> str:
        return str(uuid.uuid4())

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "name": self.name,
            "about_user": self.about_user,
            "response_style": self.response_style,
        }


BUILTIN_PERSONAS: tuple[PersonaTemplate, ...] = (
    PersonaTemplate(
        id="default",
        name="Default",
        about_user="General-purpose user across everyday tasks.",
        response_style=(
            "Clear, balanced tone. Match depth to the question; use a natural preset style."
        ),
        tooltip="Preset style and tone",
    ),
    PersonaTemplate(
        id="professional",
        name="Professional",
        about_user="Workplace user writing emails, reports, and decisions.",
        response_style=(
            "Polished and precise. Actionable recommendations; structured when the answer is long."
        ),
        tooltip="Polished and precise",
    ),
    PersonaTemplate(
        id="friendly",
        name="Friendly",
        about_user="Casual collaborator who prefers approachable explanations.",
        response_style=(
            "Warm and chatty. Encouraging tone; light humor when appropriate; stay helpful."
        ),
        tooltip="Warm and chatty",
    ),
)

_BUILTIN_BY_ID: dict[str, PersonaTemplate] = {p.id: p for p in BUILTIN_PERSONAS}


def normalize_persona_id(persona_id: str | None) -> str | None:
    """Map legacy built-in ids to current presets."""
    if not persona_id or persona_id == PERSONA_NONE:
        return None
    if persona_id in _LEGACY_PERSONA_IDS:
        return _LEGACY_PERSONA_IDS[persona_id]
    return persona_id


def builtin_persona_ids() -> list[str]:
    return [p.id for p in BUILTIN_PERSONAS]


def is_builtin_persona_id(persona_id: str | None) -> bool:
    if not persona_id:
        return False
    pid = normalize_persona_id(persona_id)
    return pid in _BUILTIN_BY_ID if pid else False


def is_custom_persona_id(persona_id: str | None, custom: list[CustomPersona]) -> bool:
    if not persona_id or persona_id in (PERSONA_NONE, CUSTOM_INSTRUCTIONS_ID):
        return False
    return any(cp.id == persona_id for cp in custom)


def builtin_persona_tooltip(persona_id: str) -> str:
    p = _BUILTIN_BY_ID.get(persona_id)
    return p.tooltip if p else ""


def effective_persona_id(selected: str | None) -> str:
    """Unset or legacy none → default preset."""
    normalized = normalize_persona_id(selected)
    if normalized and normalized in _BUILTIN_BY_ID:
        return normalized
    if normalized:
        return normalized
    return DEFAULT_PERSONA_ID


def format_persona_label(persona_id: str, custom: list[CustomPersona]) -> str:
    if persona_id == PERSONA_NONE:
        return "None"
    if persona_id == CUSTOM_INSTRUCTIONS_ID:
        return "Custom"
    pid = normalize_persona_id(persona_id) or persona_id
    if pid in _BUILTIN_BY_ID:
        return _BUILTIN_BY_ID[pid].name
    for cp in custom:
        if cp.id == persona_id:
            return cp.name
    return persona_id


def resolve_persona(
    persona_id: str | None,
    custom: list[CustomPersona],
) -> PersonaTemplate | CustomPersona | None:
    if not persona_id or persona_id == PERSONA_NONE:
        return None
    pid = normalize_persona_id(persona_id) or persona_id
    if pid in _BUILTIN_BY_ID:
        return _BUILTIN_BY_ID[pid]
    for cp in custom:
        if cp.id == persona_id:
            return cp
    return None


def coerce_custom_personas(data: Any) -> list[CustomPersona]:
    if not isinstance(data, list):
        return []
    out: list[CustomPersona] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        pid = str(item.get("id") or "").strip() or CustomPersona.new_id()
        out.append(
            CustomPersona(
                id=pid,
                name=name,
                about_user=str(item.get("about_user") or "").strip(),
                response_style=str(item.get("response_style") or "").strip(),
            )
        )
    return out


def persona_fields(persona: PersonaTemplate | CustomPersona) -> tuple[str, str]:
    return persona.about_user, persona.response_style
