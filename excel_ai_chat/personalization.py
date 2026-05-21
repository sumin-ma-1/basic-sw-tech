"""User personalization (presets + custom personas) — persisted locally, merged at API time."""

from __future__ import annotations

import html as _html
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import streamlit as st

from excel_ai_chat.paths import personalization_path
from excel_ai_chat.personas import (
    BUILTIN_PERSONAS,
    CUSTOM_INSTRUCTIONS_ID,
    DEFAULT_PERSONA_ID,
    EXCEL_EXPERT_PERSONA,
    EXCEL_EXPERT_PERSONA_ID,
    PERSONA_NONE,
    CustomPersona,
    MAX_CUSTOM_PERSONAS,
    PersonaTemplate,
    builtin_persona_ids,
    coerce_custom_personas,
    format_persona_label,
    is_builtin_persona_id,
    is_custom_persona_id,
    normalize_persona_id,
    persona_fields,
    resolve_persona,
)

PERSONALIZATION_VERSION = 4

PROFILE_LANGUAGE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("", "Auto (match your messages)"),
    ("ko", "Korean"),
    ("en", "English"),
    ("ja", "Japanese"),
    ("zh", "Chinese"),
    ("es", "Spanish"),
    ("fr", "French"),
    ("de", "German"),
)

PROFILE_TIMEZONE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("", "Not set"),
    ("UTC", "UTC"),
    ("America/New_York", "Eastern Time (US & Canada)"),
    ("America/Chicago", "Central Time (US & Canada)"),
    ("America/Denver", "Mountain Time (US & Canada)"),
    ("America/Los_Angeles", "Pacific Time (US & Canada)"),
    ("America/Sao_Paulo", "São Paulo"),
    ("Europe/London", "London"),
    ("Europe/Paris", "Paris / Central Europe"),
    ("Europe/Berlin", "Berlin"),
    ("Europe/Moscow", "Moscow"),
    ("Africa/Cairo", "Cairo"),
    ("Asia/Dubai", "Dubai / Gulf"),
    ("Asia/Kolkata", "India"),
    ("Asia/Bangkok", "Bangkok"),
    ("Asia/Singapore", "Singapore"),
    ("Asia/Shanghai", "Shanghai / China"),
    ("Asia/Hong_Kong", "Hong Kong"),
    ("Asia/Tokyo", "Tokyo"),
    ("Asia/Seoul", "Seoul"),
    ("Australia/Sydney", "Sydney"),
    ("Pacific/Auckland", "Auckland"),
)


def _pers_kicker(label: str) -> None:
    st.markdown(
        f'<p class="bst-sidebar-fm-kicker bst-pers-kicker">{_html.escape(label)}</p>',
        unsafe_allow_html=True,
    )


@dataclass
class PersonalizationSettings:
    enabled: bool = False
    preferred_name: str = ""
    default_language: str = ""
    timezone_region: str = ""
    global_context: str = ""
    about_user: str = ""
    response_style: str = ""
    selected_persona_id: str | None = None
    custom_personas: list[CustomPersona] = field(default_factory=list)

    def has_global_profile(self) -> bool:
        return bool(
            self.preferred_name.strip()
            or self.default_language.strip()
            or self.timezone_region.strip()
            or self.global_context.strip()
        )

    def profile_button_label(self) -> str:
        name = self.preferred_name.strip()
        return name if name else "Profile"

    def selected_custom_persona(self) -> CustomPersona | None:
        if not is_custom_persona_id(self.selected_persona_id, self.custom_personas):
            return None
        for cp in self.custom_personas:
            if cp.id == self.selected_persona_id:
                return cp
        return None

    def is_active(self) -> bool:
        if not self.enabled:
            return False
        cp = self.selected_custom_persona()
        if cp is not None:
            return bool(cp.about_user.strip() or cp.response_style.strip())
        return is_builtin_persona_id(self.selected_persona_id) or bool(
            effective_builtin_id(self.selected_persona_id)
        )

    def active_persona_label(self) -> str | None:
        if not self.enabled or not self.selected_persona_id:
            return None
        label = format_persona_label(self.selected_persona_id, self.custom_personas)
        return label if label != self.selected_persona_id else None

    def resolved_instruction_fields(self) -> tuple[str, str, str]:
        name = self.preferred_name
        cp = self.selected_custom_persona()
        if cp is not None:
            return name, cp.about_user, cp.response_style
        pid = effective_builtin_id(self.selected_persona_id)
        persona = resolve_persona(pid, self.custom_personas)
        if persona is None:
            return name, "", ""
        about, style = persona_fields(persona)
        return name, about, style


def effective_builtin_id(selected: str | None) -> str:
    if is_builtin_persona_id(selected):
        return normalize_persona_id(selected) or DEFAULT_PERSONA_ID
    return DEFAULT_PERSONA_ID


def _migrate_settings(settings: PersonalizationSettings) -> PersonalizationSettings:
    """Legacy single custom-instructions → first custom persona."""
    if settings.selected_persona_id != CUSTOM_INSTRUCTIONS_ID and not (
        settings.about_user.strip() or settings.response_style.strip()
    ):
        return settings
    if settings.custom_personas and settings.selected_persona_id == CUSTOM_INSTRUCTIONS_ID:
        cp = settings.custom_personas[0]
        return PersonalizationSettings(
            enabled=settings.enabled,
            preferred_name=settings.preferred_name,
            default_language=settings.default_language,
            timezone_region=settings.timezone_region,
            global_context=settings.global_context,
            about_user="",
            response_style="",
            selected_persona_id=cp.id,
            custom_personas=settings.custom_personas,
        )
    if not (settings.about_user.strip() or settings.response_style.strip()):
        if settings.selected_persona_id == CUSTOM_INSTRUCTIONS_ID:
            return PersonalizationSettings(
                enabled=settings.enabled,
                preferred_name=settings.preferred_name,
                default_language=settings.default_language,
                timezone_region=settings.timezone_region,
                global_context=settings.global_context,
                selected_persona_id=DEFAULT_PERSONA_ID,
                custom_personas=settings.custom_personas,
            )
        return settings
    cp = CustomPersona(
        id=CustomPersona.new_id(),
        name="My instructions",
        about_user=settings.about_user,
        response_style=settings.response_style,
    )
    personas = [cp, *settings.custom_personas]
    selected = cp.id if settings.selected_persona_id == CUSTOM_INSTRUCTIONS_ID else settings.selected_persona_id
    return PersonalizationSettings(
        enabled=settings.enabled,
        preferred_name=settings.preferred_name,
        default_language=settings.default_language,
        timezone_region=settings.timezone_region,
        global_context=settings.global_context,
        about_user="",
        response_style="",
        selected_persona_id=selected,
        custom_personas=personas,
    )


def _coerce_settings(data: Any) -> PersonalizationSettings:
    if not isinstance(data, dict):
        return PersonalizationSettings()
    selected = data.get("selected_persona_id")
    if selected is not None:
        raw = str(selected).strip() or None
        if raw and raw != CUSTOM_INSTRUCTIONS_ID:
            selected = normalize_persona_id(raw) if is_builtin_persona_id(raw) else raw
        elif raw == CUSTOM_INSTRUCTIONS_ID:
            selected = CUSTOM_INSTRUCTIONS_ID
        else:
            selected = None
    settings = PersonalizationSettings(
        enabled=bool(data.get("enabled", False)),
        preferred_name=str(data.get("preferred_name") or "").strip(),
        default_language=str(data.get("default_language") or "").strip(),
        timezone_region=str(data.get("timezone_region") or "").strip(),
        global_context=str(data.get("global_context") or "").strip(),
        about_user=str(data.get("about_user") or "").strip(),
        response_style=str(data.get("response_style") or "").strip(),
        selected_persona_id=selected,
        custom_personas=coerce_custom_personas(data.get("custom_personas")),
    )
    return _migrate_settings(settings)


def load_personalization(path: Path | None = None) -> PersonalizationSettings:
    p = path or personalization_path()
    if not p.is_file():
        return PersonalizationSettings()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return PersonalizationSettings()
    if isinstance(raw, dict) and "settings" in raw:
        return _coerce_settings(raw.get("settings"))
    return _coerce_settings(raw)


def save_personalization(settings: PersonalizationSettings, path: Path | None = None) -> None:
    p = path or personalization_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    clean = PersonalizationSettings(
        enabled=settings.enabled,
        preferred_name=settings.preferred_name,
        default_language=settings.default_language,
        timezone_region=settings.timezone_region,
        global_context=settings.global_context,
        about_user="",
        response_style="",
        selected_persona_id=settings.selected_persona_id,
        custom_personas=settings.custom_personas,
    )
    payload = {
        "version": PERSONALIZATION_VERSION,
        "settings": {
            **asdict(clean),
            "custom_personas": [cp.to_dict() for cp in clean.custom_personas],
        },
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _language_label(code: str) -> str:
    for value, label in PROFILE_LANGUAGE_OPTIONS:
        if value == code:
            return label
    return code


def _language_profile_line(code: str) -> str:
    label = _language_label(code)
    return (
        f"- Response language: {label}. Write the entire assistant reply in {label} only. "
        "Do not add English or other languages in parentheses, as a translation, "
        "or in parallel unless the user explicitly asks for bilingual output or another language."
    )


def _global_profile_lines(settings: PersonalizationSettings) -> list[str]:
    lines: list[str] = []
    if settings.preferred_name.strip():
        lines.append(f"- Preferred name for the user: {settings.preferred_name.strip()}")
    if settings.default_language.strip():
        lines.append(_language_profile_line(settings.default_language.strip()))
    if settings.timezone_region.strip():
        lines.append(
            "- Timezone/region (for local time and regional context only — "
            "does not set response language): "
            f"{settings.timezone_region.strip()}"
        )
    if settings.global_context.strip():
        lines.append(
            f"<user_profile>\n{settings.global_context.strip()}\n</user_profile>"
        )
    return lines


def _persona_layer_lines(
    label: str,
    persona: PersonaTemplate | CustomPersona,
) -> list[str]:
    about, style = persona_fields(persona)
    lines: list[str] = [f"- {label}: {persona.name}"]
    if about.strip():
        lines.append(f"<user_context>\n{about.strip()}\n</user_context>")
    if style.strip():
        lines.append(f"<response_preferences>\n{style.strip()}\n</response_preferences>")
    return lines


def _include_alpha_persona(settings: PersonalizationSettings) -> bool:
    """User-selected sidebar persona as Alpha (skip default / excel_expert / inactive)."""
    if not settings.is_active():
        return False
    selected = settings.selected_persona_id
    if selected == EXCEL_EXPERT_PERSONA_ID:
        return False
    if is_custom_persona_id(selected, settings.custom_personas):
        return True
    return effective_builtin_id(selected) != DEFAULT_PERSONA_ID


def _alpha_persona_layer(settings: PersonalizationSettings) -> list[str]:
    if not _include_alpha_persona(settings):
        return []
    selected = settings.selected_persona_id
    if is_custom_persona_id(selected, settings.custom_personas):
        cp = settings.selected_custom_persona()
        if cp is None:
            return []
        return _persona_layer_lines(
            "Alpha persona (user-selected — tone and context; highest priority among personas)",
            cp,
        )
    pid = effective_builtin_id(selected)
    persona = resolve_persona(pid, settings.custom_personas)
    if persona is None:
        return []
    return _persona_layer_lines(
        "Alpha persona (user-selected — tone and context; highest priority among personas)",
        persona,
    )


def _excel_expert_layer() -> list[str]:
    return _persona_layer_lines(
        "Excel Expert (mode — spreadsheet workflow; follow when compatible with Alpha above)",
        EXCEL_EXPERT_PERSONA,
    )


def personalization_system_block(
    settings: PersonalizationSettings | None,
    *,
    mode: str = "chat",
) -> str:
    if settings is None:
        return ""
    global_lines = _global_profile_lines(settings)
    if mode == "excel":
        alpha_lines = _alpha_persona_layer(settings)
        excel_lines = _excel_expert_layer()
        persona_lines = [*alpha_lines, *excel_lines]
        persona_active = bool(persona_lines)
    else:
        persona_active = settings.is_active()
        persona_lines = []
        if persona_active:
            _name, about, style = settings.resolved_instruction_fields()
            persona_label = settings.active_persona_label()
            if persona_label:
                persona_lines.append(f"- Active persona: {persona_label}")
            if about.strip():
                persona_lines.append(f"<user_context>\n{about.strip()}\n</user_context>")
            if style.strip():
                persona_lines.append(
                    f"<response_preferences>\n{style.strip()}\n</response_preferences>"
                )

    if not global_lines and not persona_active:
        return ""
    parts: list[str] = [
        "Personalization (user preferences from app settings — follow when compatible "
        "with safety rules and app capabilities above):",
    ]
    parts.extend(global_lines)
    parts.extend(persona_lines)
    return "\n".join(parts)


_BASE_MATCH_USER_LANGUAGE_PHRASES: tuple[str, ...] = (
    "Respond in the same language as the user's latest message unless they ask for another language.",
    "Respond in the same language as the user's latest visible message unless they ask otherwise.",
)


def _strip_match_user_language_rules(base_system: str) -> str:
    text = base_system
    for phrase in _BASE_MATCH_USER_LANGUAGE_PHRASES:
        text = text.replace(phrase, "")
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.strip()


def merge_system_with_personalization(
    base_system: str,
    settings: PersonalizationSettings | None,
    *,
    mode: str = "chat",
) -> str:
    base = (base_system or "").strip()
    lang = settings.default_language.strip() if settings else ""
    if lang:
        base = _strip_match_user_language_rules(base)
    extra = personalization_system_block(settings, mode=mode).strip()
    if not extra:
        if not lang:
            return base
        label = _language_label(lang)
        return (
            f"{base}\n\n"
            f"[Language priority] Profile setting requires {label} for all assistant messages. "
            "Do not add English or other languages unless the user explicitly asks."
        ).strip()
    if not base:
        merged = extra
    else:
        merged = f"{base}\n\n{extra}"
    if lang:
        label = _language_label(lang)
        merged = (
            f"{merged}\n\n"
            f"[Language priority] Profile setting requires {label} for all assistant messages. "
            "Do not add English or other languages unless the user explicitly asks."
        )
    return merged


# ── Session-state keys ────────────────────────────────────────────────────────

_BST_PERSONALIZATION_HYDRATED = "_bst_personalization_hydrated"
_BST_PERSONALIZATION_RELOAD_PENDING = "_bst_personalization_reload_pending"
_BST_PERSONA_SELECT_PENDING = "_bst_persona_select_pending"
_BST_PERSONA_DELETE_PENDING = "_bst_persona_delete_pending"
_BST_PERSONA_SAVE_PENDING = "_bst_persona_save_pending"
_BST_PERSONA_MODAL_OPEN = "_bst_persona_modal_open"
_BST_PROFILE_MODAL_OPEN = "_bst_profile_modal_open"
_BST_PROFILE_SAVE_REQUESTED = "_bst_profile_save_requested"
_BST_PROFILE_SNAPSHOT = "_bst_profile_editor_snapshot"
_BST_PROFILE_SAVE_PENDING = "_bst_profile_save_pending"  # legacy; cleared if present

BST_PERSONALIZATION_ENABLED = "bst_personalization_enabled"
BST_PERSONALIZATION_NAME = "bst_personalization_name"
BST_PROFILE_LANGUAGE = "bst_profile_default_language"
BST_PROFILE_TIMEZONE = "bst_profile_timezone_region"
BST_PROFILE_CONTEXT = "bst_profile_global_context"
# Widget keys scoped to the profile form (avoids stale global keys inside @st.dialog).
BST_PROFILE_FORM_NAME = "bst_profile_form_name"
BST_PROFILE_FORM_LANGUAGE = "bst_profile_form_language"
BST_PROFILE_FORM_TIMEZONE = "bst_profile_form_timezone"
BST_PROFILE_FORM_CONTEXT = "bst_profile_form_context"
BST_PERSONA_RADIO = "bst_persona_radio"
BST_BUILTIN_PRESET_WIDGET = "bst_builtin_persona_select"
BST_SELECTED_PERSONA = "bst_selected_persona"
BST_CUSTOM_PERSONAS = "bst_custom_personas"
BST_PERSONA_EDITING = "bst_persona_editing"
BST_PERSONA_FORM_NAME = "bst_persona_form_name"
BST_PERSONA_FORM_ABOUT = "bst_persona_form_about"
BST_PERSONA_FORM_STYLE = "bst_persona_form_style"


def _custom_personas_from_session() -> list[CustomPersona]:
    raw = st.session_state.get(BST_CUSTOM_PERSONAS, [])
    if not isinstance(raw, list):
        return []
    return coerce_custom_personas(raw)


def _set_custom_personas_in_session(personas: list[CustomPersona]) -> None:
    st.session_state[BST_CUSTOM_PERSONAS] = [cp.to_dict() for cp in personas]


def _apply_personalization_from_disk() -> None:
    saved = load_personalization()
    st.session_state[BST_PERSONALIZATION_ENABLED] = saved.enabled
    st.session_state[BST_PERSONALIZATION_NAME] = saved.preferred_name
    st.session_state[BST_PROFILE_LANGUAGE] = saved.default_language
    st.session_state[BST_PROFILE_TIMEZONE] = saved.timezone_region
    st.session_state[BST_PROFILE_CONTEXT] = saved.global_context
    st.session_state[BST_SELECTED_PERSONA] = saved.selected_persona_id
    _set_custom_personas_in_session(saved.custom_personas)
    if is_builtin_persona_id(saved.selected_persona_id):
        st.session_state[BST_PERSONA_RADIO] = effective_builtin_id(saved.selected_persona_id)
    else:
        st.session_state[BST_PERSONA_RADIO] = DEFAULT_PERSONA_ID


def _request_reload_personalization_from_disk() -> None:
    st.session_state[_BST_PERSONALIZATION_RELOAD_PENDING] = True
    st.session_state[_BST_PERSONALIZATION_HYDRATED] = False
    st.session_state.pop(BST_PERSONA_EDITING, None)
    st.session_state[_BST_PROFILE_MODAL_OPEN] = False
    st.session_state[_BST_PERSONA_MODAL_OPEN] = False


def _hydrate_personalization_widgets() -> None:
    if st.session_state.get(_BST_PERSONALIZATION_RELOAD_PENDING):
        _apply_personalization_from_disk()
        st.session_state[_BST_PERSONALIZATION_RELOAD_PENDING] = False
        st.session_state[_BST_PERSONALIZATION_HYDRATED] = True
        return
    if st.session_state.get(_BST_PERSONALIZATION_HYDRATED):
        return
    _apply_personalization_from_disk()
    st.session_state[_BST_PERSONALIZATION_HYDRATED] = True


def _settings_from_session() -> PersonalizationSettings:
    selected = st.session_state.get(BST_SELECTED_PERSONA)
    radio = st.session_state.get(BST_PERSONA_RADIO, DEFAULT_PERSONA_ID)
    custom = _custom_personas_from_session()
    if is_custom_persona_id(selected, custom):
        persona_id: str | None = selected
    elif is_builtin_persona_id(selected):
        persona_id = normalize_persona_id(selected)
    else:
        persona_id = radio if is_builtin_persona_id(radio) else DEFAULT_PERSONA_ID
    return PersonalizationSettings(
        enabled=bool(st.session_state.get(BST_PERSONALIZATION_ENABLED, False)),
        preferred_name=str(st.session_state.get(BST_PERSONALIZATION_NAME) or "").strip(),
        default_language=str(st.session_state.get(BST_PROFILE_LANGUAGE) or "").strip(),
        timezone_region=str(st.session_state.get(BST_PROFILE_TIMEZONE) or "").strip(),
        global_context=str(st.session_state.get(BST_PROFILE_CONTEXT) or "").strip(),
        selected_persona_id=persona_id,
        custom_personas=custom,
    )


def _persist_settings(settings: PersonalizationSettings) -> None:
    save_personalization(settings)


def _select_persona(persona_id: str) -> None:
    st.session_state[BST_SELECTED_PERSONA] = persona_id
    if is_builtin_persona_id(persona_id):
        st.session_state[BST_PERSONA_RADIO] = normalize_persona_id(persona_id) or DEFAULT_PERSONA_ID
    st.session_state[BST_PERSONALIZATION_ENABLED] = True
    _persist_settings(_settings_from_session())


def _clear_profile_editor_init() -> None:
    for k in list(st.session_state.keys()):
        if str(k).startswith("_bst_profile_edit_init"):
            st.session_state.pop(k, None)


def _coerce_profile_language(code: str) -> str:
    lang = str(code or "").strip()
    allowed = {value for value, _ in PROFILE_LANGUAGE_OPTIONS}
    return lang if lang in allowed else ""


def _option_index(options: list[str], value: str) -> int:
    try:
        return options.index(value)
    except ValueError:
        return 0


def _apply_profile_snapshot(snapshot: dict[str, str], *, sync_form_keys: bool = False) -> None:
    """Sync snapshot into session. Form keys only before widgets exist (init / full-app run)."""
    name = str(snapshot.get("preferred_name") or "").strip()
    lang = _coerce_profile_language(str(snapshot.get("default_language") or ""))
    tz = str(snapshot.get("timezone_region") or "").strip()
    ctx = str(snapshot.get("global_context") or "").strip()
    for key, val in (
        (BST_PERSONALIZATION_NAME, name),
        (BST_PROFILE_LANGUAGE, lang),
        (BST_PROFILE_TIMEZONE, tz),
        (BST_PROFILE_CONTEXT, ctx),
    ):
        st.session_state[key] = val
    if sync_form_keys:
        for key, val in (
            (BST_PROFILE_FORM_NAME, name),
            (BST_PROFILE_FORM_LANGUAGE, lang),
            (BST_PROFILE_FORM_TIMEZONE, tz),
            (BST_PROFILE_FORM_CONTEXT, ctx),
        ):
            st.session_state[key] = val


def _profile_snapshot_from_form() -> dict[str, str]:
    return {
        "preferred_name": str(st.session_state.get(BST_PROFILE_FORM_NAME) or "").strip(),
        "default_language": str(st.session_state.get(BST_PROFILE_FORM_LANGUAGE) or "").strip(),
        "timezone_region": str(st.session_state.get(BST_PROFILE_FORM_TIMEZONE) or "").strip(),
        "global_context": str(st.session_state.get(BST_PROFILE_FORM_CONTEXT) or "").strip(),
    }


def _persist_profile_snapshot(snapshot: dict[str, str]) -> None:
    """Write profile fields to personalization.json and app session keys."""
    current = _settings_from_session()
    updated = PersonalizationSettings(
        enabled=current.enabled,
        preferred_name=str(snapshot.get("preferred_name") or "").strip(),
        default_language=_coerce_profile_language(
            str(snapshot.get("default_language") or "")
        ),
        timezone_region=str(snapshot.get("timezone_region") or "").strip(),
        global_context=str(snapshot.get("global_context") or "").strip(),
        selected_persona_id=current.selected_persona_id,
        custom_personas=current.custom_personas,
    )
    save_personalization(updated)
    _apply_profile_snapshot(snapshot, sync_form_keys=False)


def _process_profile_save_pending() -> None:
    """Apply a profile save queued from the dialog (must run on a full-app rerun)."""
    st.session_state.pop(_BST_PROFILE_SAVE_PENDING, None)
    snapshot = st.session_state.pop(_BST_PROFILE_SNAPSHOT, None)
    if isinstance(snapshot, dict):
        _persist_profile_snapshot(snapshot)
        _apply_profile_snapshot(snapshot, sync_form_keys=True)
        _clear_profile_editor_init()
        return
    if not st.session_state.pop(_BST_PROFILE_SAVE_REQUESTED, False):
        return
    _clear_profile_editor_init()
    snap = _profile_snapshot_from_form()
    _persist_profile_snapshot(snap)
    _apply_profile_snapshot(snap, sync_form_keys=True)


def _persona_editor_init_key(edit_id: str | None) -> str:
    return f"_bst_persona_edit_init_{edit_id or '__new__'}"


def _clear_persona_editor_init(edit_id: str | None = None) -> None:
    if edit_id is not None:
        st.session_state.pop(_persona_editor_init_key(edit_id), None)
        return
    for k in list(st.session_state.keys()):
        if str(k).startswith("_bst_persona_edit_init"):
            st.session_state.pop(k, None)


def _persona_snapshot_from_form() -> dict[str, str]:
    return {
        "name": str(st.session_state.get(BST_PERSONA_FORM_NAME) or "").strip(),
        "about_user": str(st.session_state.get(BST_PERSONA_FORM_ABOUT) or "").strip(),
        "response_style": str(st.session_state.get(BST_PERSONA_FORM_STYLE) or "").strip(),
    }


def _apply_persona_form_fields(
    name: str,
    about: str,
    style: str,
    *,
    sync_form_keys: bool = False,
) -> None:
    if sync_form_keys:
        st.session_state[BST_PERSONA_FORM_NAME] = name
        st.session_state[BST_PERSONA_FORM_ABOUT] = about
        st.session_state[BST_PERSONA_FORM_STYLE] = style


def _init_profile_editor_fields() -> None:
    if st.session_state.get("_bst_profile_edit_init"):
        return
    _hydrate_personalization_widgets()
    saved = load_personalization()
    lang = _coerce_profile_language(saved.default_language)
    snapshot = {
        "preferred_name": saved.preferred_name,
        "default_language": lang,
        "timezone_region": saved.timezone_region,
        "global_context": saved.global_context,
    }
    _apply_profile_snapshot(snapshot, sync_form_keys=True)
    st.session_state["_bst_profile_edit_init"] = True


def _process_persona_pending_actions() -> None:
    select_id = st.session_state.pop(_BST_PERSONA_SELECT_PENDING, None)
    if select_id is not None:
        _select_persona(select_id)
        return

    delete_id = st.session_state.pop(_BST_PERSONA_DELETE_PENDING, None)
    if delete_id:
        remaining = [cp for cp in _custom_personas_from_session() if cp.id != delete_id]
        _set_custom_personas_in_session(remaining)
        if st.session_state.get(BST_SELECTED_PERSONA) == delete_id:
            st.session_state[BST_SELECTED_PERSONA] = DEFAULT_PERSONA_ID
            st.session_state[BST_PERSONA_RADIO] = DEFAULT_PERSONA_ID
        _persist_settings(_settings_from_session())

    payload = st.session_state.pop(_BST_PERSONA_SAVE_PENDING, None)
    if isinstance(payload, dict):
        _save_persona_from_payload(payload)


def _save_persona_from_payload(payload: dict[str, str]) -> None:
    edit_id = payload.get("edit_id")
    name = str(payload.get("name") or "").strip()
    if not name:
        return
    about = str(payload.get("about_user") or "").strip()
    style = str(payload.get("response_style") or "").strip()
    personas = _custom_personas_from_session()

    if edit_id and edit_id != "__new__":
        updated: list[CustomPersona] = []
        saved_id = edit_id
        for cp in personas:
            if cp.id == edit_id:
                updated.append(
                    CustomPersona(id=cp.id, name=name, about_user=about, response_style=style)
                )
            else:
                updated.append(cp)
    else:
        if len(personas) >= MAX_CUSTOM_PERSONAS:
            return
        saved_id = CustomPersona.new_id()
        updated = personas + [
            CustomPersona(id=saved_id, name=name, about_user=about, response_style=style)
        ]

    _set_custom_personas_in_session(updated)
    st.session_state[BST_SELECTED_PERSONA] = saved_id
    st.session_state[BST_PERSONA_RADIO] = DEFAULT_PERSONA_ID
    st.session_state[BST_PERSONALIZATION_ENABLED] = True
    st.session_state.pop(BST_PERSONA_EDITING, None)
    _clear_persona_editor_init()
    _persist_settings(_settings_from_session())


def _init_persona_editor_fields(edit_id: str | None) -> None:
    init_key = _persona_editor_init_key(edit_id)
    if st.session_state.get(init_key):
        return
    _hydrate_personalization_widgets()
    if edit_id and edit_id != "__new__":
        cp = next((p for p in _custom_personas_from_session() if p.id == edit_id), None)
        if cp is None:
            return
        _apply_persona_form_fields(cp.name, cp.about_user, cp.response_style, sync_form_keys=True)
    else:
        _apply_persona_form_fields("", "", "", sync_form_keys=True)
    st.session_state[init_key] = True


def _open_persona_editor(edit_id: str) -> None:
    st.session_state.pop(_persona_editor_init_key(edit_id), None)
    st.session_state[BST_PERSONA_EDITING] = edit_id
    st.session_state[_BST_PERSONA_MODAL_OPEN] = True


def _personalization_from_session() -> PersonalizationSettings:
    _hydrate_personalization_widgets()
    return _settings_from_session()


def _system_prompt_for_hub(mode: str) -> str:
    from excel_ai_chat.prompts import system_prompt_for_mode

    return system_prompt_for_mode(mode, personalization=_personalization_from_session())


_BUILTIN_PRESET_IDS: tuple[str, ...] = tuple(p.id for p in BUILTIN_PERSONAS)
_BUILTIN_PRESET_NAME_TO_ID: dict[str, str] = {p.name: p.id for p in BUILTIN_PERSONAS}
_BUILTIN_PRESET_ID_TO_NAME: dict[str, str] = {p.id: p.name for p in BUILTIN_PERSONAS}


def _coerce_builtin_preset_widget_id(value: Any) -> str:
    if value in _BUILTIN_PRESET_IDS:
        return str(value)
    if isinstance(value, str) and value in _BUILTIN_PRESET_NAME_TO_ID:
        return _BUILTIN_PRESET_NAME_TO_ID[value]
    return DEFAULT_PERSONA_ID


def _render_sidebar_builtin_presets() -> None:
    selected = st.session_state.get(BST_SELECTED_PERSONA)
    custom = _custom_personas_from_session()
    using_custom = is_custom_persona_id(selected, custom)

    if BST_BUILTIN_PRESET_WIDGET not in st.session_state:
        rid = st.session_state.get(BST_PERSONA_RADIO, DEFAULT_PERSONA_ID)
        st.session_state[BST_BUILTIN_PRESET_WIDGET] = (
            rid if rid in _BUILTIN_PRESET_IDS else DEFAULT_PERSONA_ID
        )
    else:
        st.session_state[BST_BUILTIN_PRESET_WIDGET] = _coerce_builtin_preset_widget_id(
            st.session_state[BST_BUILTIN_PRESET_WIDGET]
        )

    if not using_custom and selected and is_builtin_persona_id(str(selected)):
        nid = normalize_persona_id(str(selected)) or DEFAULT_PERSONA_ID
        st.session_state[BST_BUILTIN_PRESET_WIDGET] = nid

    def _on_builtin_preset_change() -> None:
        pid = st.session_state.get(BST_BUILTIN_PRESET_WIDGET)
        if pid in _BUILTIN_PRESET_IDS:
            st.session_state[_BST_PERSONA_SELECT_PENDING] = pid

    st.selectbox(
        "Built-in preset",
        options=list(_BUILTIN_PRESET_IDS),
        format_func=lambda pid: _BUILTIN_PRESET_ID_TO_NAME.get(str(pid), str(pid)),
        key=BST_BUILTIN_PRESET_WIDGET,
        on_change=_on_builtin_preset_change,
        label_visibility="collapsed",
    )


def _render_sidebar_custom_personas() -> None:
    _pers_kicker("Your personas")
    selected = st.session_state.get(BST_SELECTED_PERSONA)
    personas = _custom_personas_from_session()
    if not personas:
        st.caption("No custom personas yet. Create one below.")
    for cp in personas:
        c_sel, c_edit, c_del = st.columns(
            [6, 1, 1], gap="small", vertical_alignment="center"
        )
        with c_sel:
            is_active = selected == cp.id
            if st.button(
                cp.name,
                key=f"bst_cp_sel_{cp.id}",
                use_container_width=True,
                help="Use this persona",
                type="primary" if is_active else "secondary",
            ):
                st.session_state[_BST_PERSONA_SELECT_PENDING] = cp.id
                st.rerun()
        with c_edit:
            if st.button(
                "",
                icon=":material/edit:",
                key=f"bst_cp_edit_{cp.id}",
                help="Edit",
            ):
                _open_persona_editor(cp.id)
                st.rerun(scope="app")
        with c_del:
            if st.button(
                "",
                icon=":material/delete:",
                key=f"bst_cp_del_{cp.id}",
                help="Delete",
            ):
                st.session_state[_BST_PERSONA_DELETE_PENDING] = cp.id
                st.rerun()

    at_limit = len(personas) >= MAX_CUSTOM_PERSONAS
    if st.button(
        "+ New persona",
        key="bst_persona_create",
        use_container_width=True,
        disabled=at_limit,
        help=f"Maximum {MAX_CUSTOM_PERSONAS} custom personas"
        if at_limit
        else "Create a new custom persona",
    ):
        _open_persona_editor("__new__")
        st.rerun(scope="app")


def _persona_editor_dialog_content() -> None:
    edit_id = st.session_state.get(BST_PERSONA_EDITING)
    if not edit_id:
        return
    _init_persona_editor_fields(str(edit_id))
    st.markdown(
        '<span id="bst-personalization-dialog" aria-hidden="true"></span>',
        unsafe_allow_html=True,
    )
    st.caption("Save applies this persona and selects it for the next request.")
    with st.form("bst_persona_editor_form", clear_on_submit=False, border=False):
        st.text_input(
            "Persona name",
            key=BST_PERSONA_FORM_NAME,
            placeholder="e.g. Work, Study",
        )
        st.text_area(
            "About you",
            key=BST_PERSONA_FORM_ABOUT,
            height=100,
            placeholder="What should the assistant know about you in this persona?",
            label_visibility="visible",
        )
        st.text_area(
            "Response style",
            key=BST_PERSONA_FORM_STYLE,
            height=100,
            placeholder="e.g. Concise, technical, use bullet points",
            label_visibility="visible",
        )
        save_p, cancel_p = st.columns(2, gap="small")
        with save_p:
            saved = st.form_submit_button(
                "Save",
                type="primary",
                use_container_width=True,
            )
        with cancel_p:
            cancelled = st.form_submit_button("Cancel", use_container_width=True)

    if saved:
        snap = _persona_snapshot_from_form()
        if not snap["name"]:
            return
        _save_persona_from_payload(
            {
                "edit_id": str(edit_id),
                "name": snap["name"],
                "about_user": snap["about_user"],
                "response_style": snap["response_style"],
            }
        )
        st.session_state[_BST_PERSONA_MODAL_OPEN] = False
        _clear_persona_editor_init(str(edit_id))
        st.rerun(scope="app")
    if cancelled:
        st.session_state.pop(BST_PERSONA_EDITING, None)
        st.session_state[_BST_PERSONA_MODAL_OPEN] = False
        _clear_persona_editor_init(str(edit_id))
        _request_reload_personalization_from_disk()
        st.rerun(scope="app")


@st.dialog(
    "New persona",
    width="large",
    dismissible=False,
    on_dismiss=_request_reload_personalization_from_disk,
)
def _new_persona_editor_dialog() -> None:
    if st.session_state.get(BST_PERSONA_EDITING) != "__new__":
        return
    _persona_editor_dialog_content()


@st.dialog(
    "Edit persona",
    width="large",
    dismissible=False,
    on_dismiss=_request_reload_personalization_from_disk,
)
def _edit_persona_editor_dialog() -> None:
    edit_id = st.session_state.get(BST_PERSONA_EDITING)
    if not edit_id or edit_id == "__new__":
        return
    _persona_editor_dialog_content()


def _persona_editor_dialog() -> None:
    if st.session_state.get(BST_PERSONA_EDITING) == "__new__":
        _new_persona_editor_dialog()
    else:
        _edit_persona_editor_dialog()


@st.dialog(
    "Your profile",
    width="large",
    dismissible=False,
    on_dismiss=_request_reload_personalization_from_disk,
)
def _profile_editor_dialog() -> None:
    _init_profile_editor_fields()
    st.markdown(
        '<span id="bst-profile-dialog" aria-hidden="true"></span>',
        unsafe_allow_html=True,
    )
    st.caption("These settings apply to every chat, regardless of persona.")
    lang_codes = [code for code, _ in PROFILE_LANGUAGE_OPTIONS]
    lang_labels = {code: label for code, label in PROFILE_LANGUAGE_OPTIONS}

    tz_codes = [code for code, _ in PROFILE_TIMEZONE_OPTIONS]
    tz_labels = {code: label for code, label in PROFILE_TIMEZONE_OPTIONS}
    cur_tz = str(st.session_state.get(BST_PROFILE_FORM_TIMEZONE) or "").strip()
    if cur_tz and cur_tz not in tz_codes:
        tz_codes = [cur_tz, *tz_codes]
        tz_labels[cur_tz] = cur_tz

    with st.form("bst_profile_editor_form", clear_on_submit=False, border=False):
        st.text_input(
            "Name",
            key=BST_PROFILE_FORM_NAME,
            placeholder="How the assistant should address you",
        )
        st.selectbox(
            "Default response language",
            options=lang_codes,
            format_func=lambda c: lang_labels.get(c, c),
            key=BST_PROFILE_FORM_LANGUAGE,
        )
        st.selectbox(
            "Timezone / region",
            options=tz_codes,
            format_func=lambda c: tz_labels.get(c, c),
            key=BST_PROFILE_FORM_TIMEZONE,
        )
        st.text_area(
            "Short identity",
            key=BST_PROFILE_FORM_CONTEXT,
            height=72,
            placeholder="e.g. Software engineer working on data tools",
            label_visibility="visible",
        )
        save_p, cancel_p = st.columns(2, gap="small")
        with save_p:
            saved = st.form_submit_button(
                "Save",
                type="primary",
                use_container_width=True,
            )
        with cancel_p:
            cancelled = st.form_submit_button("Cancel", use_container_width=True)

    if saved:
        snapshot = _profile_snapshot_from_form()
        _persist_profile_snapshot(snapshot)
        st.session_state[_BST_PROFILE_SNAPSHOT] = snapshot
        st.session_state[_BST_PROFILE_MODAL_OPEN] = False
        _clear_profile_editor_init()
        st.rerun(scope="app")
    if cancelled:
        _clear_profile_editor_init()
        st.session_state[_BST_PROFILE_MODAL_OPEN] = False
        _request_reload_personalization_from_disk()
        st.rerun(scope="app")


def _render_sidebar_excel_expert_badge() -> None:
    """Small status badge when hub is in Excel analyze mode (not persisted persona)."""
    if st.session_state.get("nav_page") != "hub":
        return
    if st.session_state.get("hub_mode") != "excel":
        return
    settings = _settings_from_session()
    title_attr = ""
    if _include_alpha_persona(settings):
        label = settings.active_persona_label()
        if label:
            title_attr = (
                f' title="Excel Expert (mode) + Alpha persona: {_html.escape(label)}"'
            )
    st.markdown(
        f'<div class="bst-excel-expert-badge"{title_attr}>'
        '<span class="bst-excel-expert-badge__led" aria-hidden="true"></span>'
        '<span class="bst-excel-expert-badge__label">Excel Expert</span>'
        "</div>"
        '<span id="bst-excel-expert-badge-anchor" aria-hidden="true"></span>',
        unsafe_allow_html=True,
    )


def _render_sidebar_personalization() -> None:
    _process_profile_save_pending()
    _process_persona_pending_actions()
    _hydrate_personalization_widgets()
    st.markdown(
        '<p class="bst-sidebar-fm-kicker">Preset personalization</p>'
        '<span id="bst-sidebar-pers-anchor" aria-hidden="true"></span>',
        unsafe_allow_html=True,
    )
    _render_sidebar_excel_expert_badge()
    _render_sidebar_builtin_presets()
    _render_sidebar_custom_personas()
    if st.session_state.get(_BST_PERSONA_MODAL_OPEN, False):
        _persona_editor_dialog()


def _render_floating_profile_control() -> None:
    """Profile chip fixed on the viewport (main area), always visible."""
    _process_profile_save_pending()
    _hydrate_personalization_widgets()
    settings = _settings_from_session()
    label = settings.profile_button_label()
    st.markdown(
        '<span id="bst-profile-fab-anchor" aria-hidden="true"></span>',
        unsafe_allow_html=True,
    )
    if st.button(
        label,
        key="bst_profile_open",
        use_container_width=False,
        icon=":material/account_circle:",
    ):
        st.session_state.pop("_bst_profile_edit_init", None)
        st.session_state[_BST_PROFILE_MODAL_OPEN] = True
        st.rerun(scope="app")
    if st.session_state.get(_BST_PROFILE_MODAL_OPEN, False):
        _profile_editor_dialog()


def _render_sidebar_profile_footer() -> None:
    """Deprecated alias — use _render_floating_profile_control outside the sidebar."""
    _render_floating_profile_control()
