from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_subrules_2026_27,
)

ROOT = Path(__file__).resolve().parents[1]
RAW_STRATAGEMS_PATH = (
    ROOT
    / "data"
    / "source_snapshots"
    / "wahapedia"
    / "10th-edition"
    / "2026-06-14"
    / "json"
    / "Stratagems.json"
)
OUTPUT_PATH = (
    ROOT
    / "src"
    / "warhammer40k_core"
    / "rules"
    / "source_packages"
    / "warhammer_40000_11th"
    / "faction_stratagem_activation_2026_27.py"
)

SOURCE_PACKAGE_ID = "gw-11e-phase17s-faction-stratagem-activation-2026-27"
SOURCE_TITLE = "Warhammer 40,000 11th Edition Faction Stratagem Activation Support"
SOURCE_VERSION = "2026-27"
SOURCE_DATE = "2026-06-21"
IMPORTED_AT_SCHEMA_VERSION = "core-v2-phase17s-stratagem-activation-v1"
RULE_IR_NORMALIZED_TEXT = "stratagem_activation_target_binding"
RULE_IR_PARSER_VERSION = "phase17s-stratagem-activation-template-v1"
RULE_IR_SCHEMA_VERSION = "phase17c-rule-ir-v1"
RULE_IR_TEMPLATE_ID = "phase17s:stratagem-activation-target-binding"

UNTYPED_STRATAGEM_CATEGORIES_AS_STRATEGIC_PLOY = frozenset(
    (
        "Court of the Phoenician \u2013 Stratagem",
        "Grizzled Company \u2013 Stratagem",
        "Nightmare Hunt \u2013 Stratagem",
        "Serpent\u2019s Brood \u2013 Stratagem",
    )
)
REGULAR_TARGET_KEYWORDS = (
    "AIRCRAFT",
    "BATTLELINE",
    "BEAST",
    "CAVALRY",
    "CHARACTER",
    "DEDICATED TRANSPORT",
    "FLY",
    "FORTIFICATION",
    "GRENADES",
    "INFANTRY",
    "MONSTER",
    "MOUNTED",
    "PSYKER",
    "SMOKE",
    "SWARM",
    "TITANIC",
    "TRANSPORT",
    "VEHICLE",
    "WALKER",
)


@dataclass(frozen=True, slots=True)
class ActivationProfile:
    profile_id: str
    source_row_id: str
    source_id: str
    faction_id: str
    detachment_id: str
    stratagem_id: str
    name: str
    command_point_cost: int
    category: str
    when_descriptor: str
    target_descriptor: str
    effect_descriptor: str
    restrictions_descriptor: str
    trigger_kind: str
    phase_tokens: tuple[str, ...]
    target_kind: str
    target_policy_id: str
    required_keywords: tuple[str, ...]
    required_keywords_any: tuple[str, ...]
    required_faction_keywords: tuple[str, ...]
    excluded_keywords: tuple[str, ...]
    excluded_faction_keywords: tuple[str, ...]
    rule_ir_hash: str

    def constructor_line(self) -> str:
        values = (
            self.profile_id,
            self.source_row_id,
            self.source_id,
            self.faction_id,
            self.detachment_id,
            self.stratagem_id,
            self.name,
            self.command_point_cost,
            self.category,
            self.when_descriptor,
            self.target_descriptor,
            self.effect_descriptor,
            self.restrictions_descriptor,
            self.trigger_kind,
            self.phase_tokens,
            self.target_kind,
            self.target_policy_id,
            self.required_keywords,
            self.required_keywords_any,
            self.required_faction_keywords,
            self.excluded_keywords,
            self.excluded_faction_keywords,
            self.rule_ir_hash,
        )
        arguments = ", ".join(_py_value(value) for value in values)
        return f"    SourceStratagemActivationProfile({arguments}),"


def main() -> None:
    raw_rows = _raw_stratagem_rows_by_id()
    profiles = tuple(
        _activation_profile(source_row=row, raw_row=raw_rows[row.stratagem_id])
        for row in faction_subrules_2026_27.stratagem_rows()
        if not row.runtime_consumer_ids
    )
    _validate_profile_coverage(profiles)
    OUTPUT_PATH.write_text(_module_text(profiles), encoding="utf-8", newline="\n")


def _raw_stratagem_rows_by_id() -> dict[str, dict[str, object]]:
    payload = json.loads(RAW_STRATAGEMS_PATH.read_text(encoding="utf-8"))
    rows = payload["rows"]
    if type(rows) is not list:
        raise ValueError("Stratagem source snapshot rows must be a list.")
    raw_rows: dict[str, dict[str, object]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise TypeError("Stratagem source snapshot row must be an object.")
        source_row_id = row.get("source_row_id")
        if type(source_row_id) is not str:
            raise ValueError("Stratagem source snapshot row is missing source_row_id.")
        raw_rows[source_row_id] = row
    return raw_rows


def _activation_profile(
    *,
    source_row: faction_subrules_2026_27.SourceStratagemRow,
    raw_row: dict[str, object],
) -> ActivationProfile:
    fields = raw_row["fields"]
    if not isinstance(fields, dict):
        raise TypeError("Raw Stratagem row fields must be an object.")
    description = _field_string(fields, "description")
    sections = _description_sections(description)
    target_descriptor = sections["target"]
    target_kind, target_policy_id = _target_kind_and_policy(
        when_descriptor=sections["when"],
        target_descriptor=target_descriptor,
    )
    profile_id = (
        "phase17s:stratagem:"
        f"{source_row.faction_id}:{source_row.detachment_id}:{source_row.stratagem_id}"
    )
    rule_target_kind = _rule_target_kind(
        target_kind=target_kind,
        target_policy_id=target_policy_id,
    )
    rule_ir_hash = _rule_ir_hash(
        profile_id=profile_id,
        source_id=source_row.source_id,
        rule_target_kind=rule_target_kind,
    )
    return ActivationProfile(
        profile_id=profile_id,
        source_row_id=source_row.source_row_id,
        source_id=source_row.source_id,
        faction_id=source_row.faction_id,
        detachment_id=source_row.detachment_id,
        stratagem_id=source_row.stratagem_id,
        name=source_row.name,
        command_point_cost=source_row.command_point_cost,
        category=_category_token(source_row.category),
        when_descriptor=sections["when"],
        target_descriptor=target_descriptor,
        effect_descriptor=sections["effect"],
        restrictions_descriptor="matched play same stratagem per phase",
        trigger_kind=_trigger_kind(sections["when"]),
        phase_tokens=_phase_tokens(_field_string(fields, "phase")),
        target_kind=target_kind,
        target_policy_id=target_policy_id,
        required_keywords=_required_keywords(target_descriptor),
        required_keywords_any=(),
        required_faction_keywords=(),
        excluded_keywords=_excluded_keywords(target_descriptor),
        excluded_faction_keywords=(),
        rule_ir_hash=rule_ir_hash,
    )


def _field_string(fields: dict[object, object], key: str) -> str:
    value = fields.get(key)
    if type(value) is not str:
        raise ValueError(f"Raw Stratagem field {key} must be a string.")
    return value.strip()


def _description_sections(description: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {"when": [], "target": [], "effect": []}
    current: str | None = None
    for raw_line in description.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        upper = line.upper()
        if upper.startswith("WHEN:"):
            current = "when"
            sections[current].append(line.removeprefix("WHEN:").strip())
            continue
        if upper.startswith("TARGET:"):
            current = "target"
            sections[current].append(line.removeprefix("TARGET:").strip())
            continue
        if upper.startswith("EFFECT:"):
            current = "effect"
            sections[current].append(line.removeprefix("EFFECT:").strip())
            continue
        if current is None:
            raise ValueError("Stratagem description line appears before a section header.")
        sections[current].append(line)
    resolved = {section: " ".join(parts).strip() for section, parts in sections.items()}
    for section, text in resolved.items():
        if not text:
            raise ValueError(f"Stratagem description is missing {section}.")
    return resolved


def _category_token(category: str) -> str:
    text = category.lower()
    if "battle_tactic" in text or "battle tactic" in text:
        return "battle_tactic"
    if "epic_deed" in text or "epic deed" in text:
        return "epic_deed"
    if "strategic_ploy" in text or "strategic ploy" in text:
        return "strategic_ploy"
    if "wargear" in text:
        return "wargear"
    if category in UNTYPED_STRATAGEM_CATEGORIES_AS_STRATEGIC_PLOY:
        return "strategic_ploy"
    raise ValueError(f"Unsupported Stratagem category: {category}.")


def _phase_tokens(raw_phase: str) -> tuple[str, ...]:
    text = raw_phase.lower()
    if "any phase" in text:
        return ("any",)
    phases: list[str] = []
    for token, label in (
        ("command", "command"),
        ("movement", "movement"),
        ("shooting", "shooting"),
        ("charge", "charge"),
        ("fight", "fight"),
    ):
        if label in text:
            phases.append(token)
    if not phases:
        raise ValueError(f"Unsupported Stratagem phase: {raw_phase}.")
    return tuple(phases)


def _trigger_kind(when_descriptor: str) -> str:
    text = when_descriptor.lower()
    if "dice roll" in text or "saving throw" in text or "hazardous test" in text:
        return "after_dice_roll"
    if "selected as the target" in text or "selected its targets" in text:
        return "after_unit_selected_as_target"
    if "selected to move" in text:
        return "just_after_friendly_unit_selected_to_move"
    if "selected to fight" in text:
        return "just_after_friendly_unit_selected_to_fight"
    if "enemy unit has fought" in text or "enemy unit has resolved its attacks" in text:
        return "just_after_enemy_unit_has_fought"
    if "enemy unit has shot" in text or "attacking unit has shot" in text:
        return "just_after_enemy_unit_has_shot"
    if "unit from your army has shot" in text or "friendly unit has shot" in text:
        return "just_after_friendly_unit_has_shot"
    if "ends a charge move" in text:
        return "after_unit_ends_charge_move"
    if "enemy unit ends" in text and "move" in text:
        return "after_enemy_unit_ends_move"
    if "enemy unit" in text and "fall back" in text:
        return "just_after_enemy_unit_selected_to_fall_back"
    if "unit from your army" in text and "fall back" in text:
        return "just_after_friendly_unit_falls_back"
    if text.startswith("end of") or "at the end of" in text:
        return "end_phase"
    return "start_phase"


def _target_kind_and_policy(
    *,
    when_descriptor: str,
    target_descriptor: str,
) -> tuple[str, str]:
    text = target_descriptor.lower()
    when_text = when_descriptor.lower()
    if "enemy unit" in text and "from your army" not in text:
        return ("any_unit", "enemy_unit")
    if "selected as the target" in text or "was selected as the target" in text:
        return ("friendly_unit", "selected_target_unit")
    if (
        "has not been selected to shoot" in text or "not already been selected to shoot" in text
    ) and "fight" not in text:
        return ("friendly_unit", "not_selected_to_shoot_unit")
    if (
        "has not been selected to fight" in text or "not already been selected to fight" in text
    ) and "shoot" not in text:
        return ("friendly_unit", "not_selected_to_fight_unit")
    if "selected to move" in text or "selected to make a normal" in when_text:
        return ("friendly_unit", "selected_to_move_unit")
    if "just shot" in text or "has just shot" in text:
        return ("friendly_unit", "just_shot_unit")
    if "fall back" in text and "enemy unit" in when_text:
        return ("friendly_unit", "engaged_with_fall_back_unit")
    return ("friendly_unit", "friendly_unit")


def _required_keywords(target_descriptor: str) -> tuple[str, ...]:
    canonical = _canonical_keyword_text(target_descriptor)
    required = [
        keyword
        for keyword in REGULAR_TARGET_KEYWORDS
        if re.search(rf"(?<![A-Z0-9_]){re.escape(keyword)}(?![A-Z0-9_])", canonical)
    ]
    return tuple(required)


def _excluded_keywords(target_descriptor: str) -> tuple[str, ...]:
    excluded: list[str] = []
    for match in re.finditer(r"\bexcluding\s+([^)]+)", target_descriptor, flags=re.IGNORECASE):
        text = match.group(1)
        text = re.sub(r"\b(models?|units?)\b", "", text, flags=re.IGNORECASE)
        for piece in re.split(r",|\bor\b|\band\b", text, flags=re.IGNORECASE):
            keyword = _canonical_keyword_text(piece).strip()
            if keyword:
                excluded.append(keyword)
    return tuple(sorted(set(excluded)))


def _canonical_keyword_text(value: str) -> str:
    text = value.upper().replace("'", "").replace("\u2019", "")
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _rule_target_kind(*, target_kind: str, target_policy_id: str) -> str:
    if target_kind == "none":
        return "selected_unit"
    if target_policy_id == "enemy_unit":
        return "enemy_unit"
    if target_policy_id == "selected_target_unit":
        return "selected_target"
    if target_kind == "any_unit":
        return "selected_unit"
    return "friendly_unit"


def _rule_ir_hash(*, profile_id: str, source_id: str, rule_target_kind: str) -> str:
    payload = _rule_ir_payload(
        profile_id=profile_id,
        source_id=source_id,
        rule_target_kind=rule_target_kind,
        rule_ir_hash="",
    )
    return _sha256_payload(payload)


def _rule_ir_payload(
    *,
    profile_id: str,
    source_id: str,
    rule_target_kind: str,
    rule_ir_hash: str,
) -> dict[str, object]:
    span = {
        "text": RULE_IR_NORMALIZED_TEXT,
        "start": 0,
        "end": len(RULE_IR_NORMALIZED_TEXT),
    }
    return {
        "rule_id": profile_id,
        "source_id": source_id,
        "normalized_text": RULE_IR_NORMALIZED_TEXT,
        "parser_version": RULE_IR_PARSER_VERSION,
        "schema_version": RULE_IR_SCHEMA_VERSION,
        "clauses": [
            {
                "clause_id": f"{profile_id}:target-binding",
                "template_id": RULE_IR_TEMPLATE_ID,
                "source_span": span,
                "trigger": None,
                "conditions": [],
                "target": {
                    "kind": rule_target_kind,
                    "source_span": span,
                    "parameters": [],
                },
                "effects": [],
                "duration": None,
                "unsupported_reason": None,
                "diagnostics": [],
            }
        ],
        "diagnostics": [],
        "ir_hash": rule_ir_hash,
    }


def _validate_profile_coverage(profiles: tuple[ActivationProfile, ...]) -> None:
    source_only_rows = tuple(
        row for row in faction_subrules_2026_27.stratagem_rows() if not row.runtime_consumer_ids
    )
    expected = {row.source_row_id for row in source_only_rows}
    actual = {profile.source_row_id for profile in profiles}
    if actual != expected:
        raise ValueError("Generated Stratagem activation profiles do not cover source-only rows.")


def _module_text(profiles: tuple[ActivationProfile, ...]) -> str:
    profile_lines = "\n".join(profile.constructor_line() for profile in profiles)
    return "\n".join(
        (
            "# Generated by tools/generate_faction_stratagem_activation_support.py.",
            (
                "# Regenerate with `uv run python "
                "tools/generate_faction_stratagem_activation_support.py`."
            ),
            "# ruff: noqa: E501",
            "# fmt: off",
            "from __future__ import annotations",
            "",
            "import hashlib",
            "import json",
            "from dataclasses import dataclass",
            "",
            f'SOURCE_PACKAGE_ID = "{SOURCE_PACKAGE_ID}"',
            f'SOURCE_TITLE = "{SOURCE_TITLE}"',
            f'SOURCE_VERSION = "{SOURCE_VERSION}"',
            f'SOURCE_DATE = "{SOURCE_DATE}"',
            f'IMPORTED_AT_SCHEMA_VERSION = "{IMPORTED_AT_SCHEMA_VERSION}"',
            f'RULE_IR_NORMALIZED_TEXT = "{RULE_IR_NORMALIZED_TEXT}"',
            f'RULE_IR_PARSER_VERSION = "{RULE_IR_PARSER_VERSION}"',
            f'RULE_IR_SCHEMA_VERSION = "{RULE_IR_SCHEMA_VERSION}"',
            f'RULE_IR_TEMPLATE_ID = "{RULE_IR_TEMPLATE_ID}"',
            "",
            "",
            "@dataclass(frozen=True, slots=True)",
            "class SourceStratagemActivationProfile:",
            "    profile_id: str",
            "    source_row_id: str",
            "    source_id: str",
            "    faction_id: str",
            "    detachment_id: str",
            "    stratagem_id: str",
            "    name: str",
            "    command_point_cost: int",
            "    category: str",
            "    when_descriptor: str",
            "    target_descriptor: str",
            "    effect_descriptor: str",
            "    restrictions_descriptor: str",
            "    trigger_kind: str",
            "    phase_tokens: tuple[str, ...]",
            "    target_kind: str",
            "    target_policy_id: str",
            "    required_keywords: tuple[str, ...] = ()",
            "    required_keywords_any: tuple[str, ...] = ()",
            "    required_faction_keywords: tuple[str, ...] = ()",
            "    excluded_keywords: tuple[str, ...] = ()",
            "    excluded_faction_keywords: tuple[str, ...] = ()",
            '    rule_ir_hash: str = ""',
            "",
            "    def rule_ir_payload(self) -> dict[str, object]:",
            "        return _rule_ir_payload(",
            "            profile_id=self.profile_id,",
            "            source_id=self.source_id,",
            "            rule_target_kind=_rule_target_kind(",
            "                target_kind=self.target_kind,",
            "                target_policy_id=self.target_policy_id,",
            "            ),",
            "            rule_ir_hash=self.rule_ir_hash,",
            "        )",
            "",
            "    def effect_payload(self) -> dict[str, object]:",
            "        return {",
            '            "rule_ir": self.rule_ir_payload(),',
            '            "activation_profile_id": self.profile_id,',
            '            "activation_template_id": RULE_IR_TEMPLATE_ID,',
            "        }",
            "",
            "    def to_payload(self) -> dict[str, object]:",
            "        return {",
            '            "profile_id": self.profile_id,',
            '            "source_row_id": self.source_row_id,',
            '            "source_id": self.source_id,',
            '            "faction_id": self.faction_id,',
            '            "detachment_id": self.detachment_id,',
            '            "stratagem_id": self.stratagem_id,',
            '            "name": self.name,',
            '            "command_point_cost": self.command_point_cost,',
            '            "category": self.category,',
            '            "trigger_kind": self.trigger_kind,',
            '            "phase_tokens": list(self.phase_tokens),',
            '            "target_kind": self.target_kind,',
            '            "target_policy_id": self.target_policy_id,',
            '            "required_keywords": list(self.required_keywords),',
            '            "required_keywords_any": list(self.required_keywords_any),',
            '            "required_faction_keywords": list(self.required_faction_keywords),',
            '            "excluded_keywords": list(self.excluded_keywords),',
            '            "excluded_faction_keywords": list(self.excluded_faction_keywords),',
            '            "rule_ir_hash": self.rule_ir_hash,',
            "        }",
            "",
            "",
            "def stratagem_activation_profiles() -> tuple[SourceStratagemActivationProfile, ...]:",
            "    return _PROFILES",
            "",
            "",
            "def source_package_identity_payload() -> dict[str, str]:",
            "    return {",
            '        "source_package_id": SOURCE_PACKAGE_ID,',
            '        "source_title": SOURCE_TITLE,',
            '        "source_version": SOURCE_VERSION,',
            '        "source_date": SOURCE_DATE,',
            '        "source_commit_or_import_hash": _import_hash(),',
            '        "imported_at_schema_version": IMPORTED_AT_SCHEMA_VERSION,',
            "    }",
            "",
            "",
            "def _rule_ir_payload(",
            "    *,",
            "    profile_id: str,",
            "    source_id: str,",
            "    rule_target_kind: str,",
            "    rule_ir_hash: str,",
            ") -> dict[str, object]:",
            "    span = {",
            '        "text": RULE_IR_NORMALIZED_TEXT,',
            '        "start": 0,',
            '        "end": len(RULE_IR_NORMALIZED_TEXT),',
            "    }",
            "    return {",
            '        "rule_id": profile_id,',
            '        "source_id": source_id,',
            '        "normalized_text": RULE_IR_NORMALIZED_TEXT,',
            '        "parser_version": RULE_IR_PARSER_VERSION,',
            '        "schema_version": RULE_IR_SCHEMA_VERSION,',
            '        "clauses": [',
            "            {",
            '                "clause_id": f"{profile_id}:target-binding",',
            '                "template_id": RULE_IR_TEMPLATE_ID,',
            '                "source_span": span,',
            '                "trigger": None,',
            '                "conditions": [],',
            '                "target": {',
            '                    "kind": rule_target_kind,',
            '                    "source_span": span,',
            '                    "parameters": [],',
            "                },",
            '                "effects": [],',
            '                "duration": None,',
            '                "unsupported_reason": None,',
            '                "diagnostics": [],',
            "            }",
            "        ],",
            '        "diagnostics": [],',
            '        "ir_hash": rule_ir_hash,',
            "    }",
            "",
            "",
            "def _rule_target_kind(*, target_kind: str, target_policy_id: str) -> str:",
            '    if target_policy_id == "enemy_unit":',
            '        return "enemy_unit"',
            '    if target_policy_id == "selected_target_unit":',
            '        return "selected_target"',
            '    if target_kind == "any_unit":',
            '        return "selected_unit"',
            '    return "friendly_unit"',
            "",
            "",
            "def _import_hash() -> str:",
            "    payload = [profile.to_payload() for profile in _PROFILES]",
            "    return _sha256_payload(payload)",
            "",
            "",
            "def _sha256_payload(payload: object) -> str:",
            '    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()',
            "    return hashlib.sha256(canonical).hexdigest()",
            "",
            "",
            "def _validate_profiles(",
            "    profiles: tuple[SourceStratagemActivationProfile, ...]",
            ") -> tuple[SourceStratagemActivationProfile, ...]:",
            "    seen: set[str] = set()",
            "    for profile in profiles:",
            "        if type(profile) is not SourceStratagemActivationProfile:",
            '            raise ValueError("Stratagem activation profiles must be typed profiles.")',
            "        if profile.source_row_id in seen:",
            (
                '            raise ValueError("Stratagem activation profiles must be unique '
                'by source row.")'
            ),
            "        seen.add(profile.source_row_id)",
            "        if not profile.phase_tokens:",
            (
                '            raise ValueError("Stratagem activation profile phases must not '
                'be empty.")'
            ),
            "    return profiles",
            "",
            "",
            "_PROFILES: tuple[SourceStratagemActivationProfile, ...] = _validate_profiles((",
            profile_lines,
            "))",
            "# fmt: on",
            "",
        )
    )


def _sha256_payload(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def _py_value(value: object) -> str:
    if type(value) is tuple:
        if not value:
            return "()"
        return f"({', '.join(_py_value(item) for item in value)},)"
    if type(value) is int:
        return str(value)
    if type(value) is str:
        return ascii(value)
    raise ValueError(f"Unsupported constructor value type: {type(value).__name__}.")


if __name__ == "__main__":
    main()
