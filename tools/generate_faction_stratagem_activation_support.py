from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.rule_ir import RuleIR, RuleIRPayload
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    datasheet_keyword_lexicon_2026_06_14,
    faction_subrules_2026_27,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_court_of_the_phoenician_ir_support_2026_27 as court_ir,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_spectacle_of_slaughter_ir_support_2026_27 as spectacle_ir,
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
RULE_IR_PARSER_VERSION = "phase17s-stratagem-activation-template-v2"
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

SOURCE_ROW_REQUIRED_KEYWORD_OVERRIDES: dict[str, tuple[str, ...]] = {
    "stratagem:emperors-children:court-of-the-phoenician:000010655004": ("DAEMON",),
    "stratagem:emperors-children:court-of-the-phoenician:000010655006": ("DAEMON",),
}


@dataclass(frozen=True, slots=True)
class SourceOnlyActivationMetadata:
    when_descriptor: str
    target_descriptor: str
    effect_descriptor: str
    trigger_kind: str
    phase_tokens: tuple[str, ...]
    target_kind: str
    target_policy_id: str
    required_keywords: tuple[str, ...] = ()
    required_keywords_any: tuple[str, ...] = ()
    required_faction_keywords: tuple[str, ...] = ()
    excluded_keywords: tuple[str, ...] = ()
    excluded_faction_keywords: tuple[str, ...] = ()


SOURCE_ONLY_ACTIVATION_METADATA_BY_ROW_ID: dict[str, SourceOnlyActivationMetadata] = {
    "stratagem:emperors-children:spectacle-of-slaughter:000010901002": (
        SourceOnlyActivationMetadata(
            when_descriptor="Either player's turn; Fight phase",
            target_descriptor="One friendly FLAWLESS BLADES unit that was selected to fight.",
            effect_descriptor=(
                "Until the end of the phase, melee weapons equipped by models in your unit "
                "have the [PRECISION] ability."
            ),
            trigger_kind="just_after_friendly_unit_selected_to_fight",
            phase_tokens=("fight",),
            target_kind="friendly_unit",
            target_policy_id="friendly_unit",
            required_faction_keywords=("FLAWLESS BLADES",),
        )
    ),
    "stratagem:emperors-children:spectacle-of-slaughter:000010901003": (
        SourceOnlyActivationMetadata(
            when_descriptor="Your Charge phase, when a FLAWLESS BLADES unit starts a Charge move.",
            target_descriptor="One friendly FLAWLESS BLADES unit that is starting a Charge move.",
            effect_descriptor=(
                "Until the end of the phase, models in your unit can move through models, "
                "excluding MONSTER and VEHICLE models."
            ),
            trigger_kind="start_phase",
            phase_tokens=("charge",),
            target_kind="friendly_unit",
            target_policy_id="friendly_unit",
            required_faction_keywords=("FLAWLESS BLADES",),
        )
    ),
    "stratagem:emperors-children:spectacle-of-slaughter:000010901004": (
        SourceOnlyActivationMetadata(
            when_descriptor=(
                "Your opponent's Movement phase, just after an enemy unit that was within "
                "Engagement Range of a friendly FLAWLESS BLADES unit ends a Fall Back move."
            ),
            target_descriptor=(
                "One friendly FLAWLESS BLADES unit that was within Engagement Range of that "
                "enemy unit and is not within Engagement Range of one or more enemy units."
            ),
            effect_descriptor="Your unit can make a Normal move of up to D3+3 inches.",
            trigger_kind="after_enemy_unit_ends_move",
            phase_tokens=("movement",),
            target_kind="friendly_unit",
            target_policy_id="friendly_unit",
            required_faction_keywords=("FLAWLESS BLADES",),
        )
    ),
}


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
    compiled_rule_ir_payload: RuleIRPayload | None
    effect_selection_kind: str | None

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
        _activation_profile_for_source_row(source_row=row, raw_rows=raw_rows)
        for row in _source_rows_with_activation_profiles(raw_rows)
    )
    _validate_profile_coverage(profiles, raw_rows=raw_rows)
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


def _source_rows_with_activation_profiles(
    raw_rows: dict[str, dict[str, object]],
) -> tuple[faction_subrules_2026_27.SourceStratagemRow, ...]:
    rows: list[faction_subrules_2026_27.SourceStratagemRow] = []
    for row in faction_subrules_2026_27.stratagem_rows():
        if row.runtime_consumer_ids:
            continue
        if (
            row.stratagem_id in raw_rows
            or row.source_row_id in SOURCE_ONLY_ACTIVATION_METADATA_BY_ROW_ID
        ):
            rows.append(row)
    return tuple(rows)


def _activation_profile_for_source_row(
    *,
    source_row: faction_subrules_2026_27.SourceStratagemRow,
    raw_rows: dict[str, dict[str, object]],
) -> ActivationProfile:
    raw_row = raw_rows.get(source_row.stratagem_id)
    if raw_row is not None:
        return _activation_profile(source_row=source_row, raw_row=raw_row)
    metadata = SOURCE_ONLY_ACTIVATION_METADATA_BY_ROW_ID.get(source_row.source_row_id)
    if metadata is None:
        raise ValueError(
            f"Stratagem source row lacks raw source and source-only metadata: "
            f"{source_row.source_row_id}."
        )
    return _activation_profile_from_source_only_metadata(
        source_row=source_row,
        metadata=metadata,
    )


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
    compiled_rule_ir_payload = _compiled_stratagem_rule_ir_payload_or_none(
        profile_id=profile_id,
        source_id=source_row.source_id,
        rule_target_kind=rule_target_kind,
        effect_descriptor=sections["effect"],
    )
    overlay_rule_ir_payload = _overlay_rule_ir_payload_or_none(profile_id)
    effective_rule_ir_payload = overlay_rule_ir_payload
    if effective_rule_ir_payload is None:
        effective_rule_ir_payload = compiled_rule_ir_payload
    if effective_rule_ir_payload is None:
        rule_ir_hash = _rule_ir_hash(
            profile_id=profile_id,
            source_id=source_row.source_id,
            rule_target_kind=rule_target_kind,
        )
    else:
        rule_ir_hash = str(effective_rule_ir_payload["ir_hash"])
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
        required_keywords=_required_keywords(
            source_row_id=source_row.source_row_id,
            target_descriptor=target_descriptor,
        ),
        required_keywords_any=(),
        required_faction_keywords=(),
        excluded_keywords=_excluded_keywords(target_descriptor),
        excluded_faction_keywords=(),
        rule_ir_hash=rule_ir_hash,
        compiled_rule_ir_payload=compiled_rule_ir_payload,
        effect_selection_kind=_effect_selection_kind_from_rule_ir_payload(
            effective_rule_ir_payload
        ),
    )


def _activation_profile_from_source_only_metadata(
    *,
    source_row: faction_subrules_2026_27.SourceStratagemRow,
    metadata: SourceOnlyActivationMetadata,
) -> ActivationProfile:
    profile_id = (
        "phase17s:stratagem:"
        f"{source_row.faction_id}:{source_row.detachment_id}:{source_row.stratagem_id}"
    )
    overlay_rule_ir_payload = _overlay_rule_ir_payload_or_none(profile_id)
    if overlay_rule_ir_payload is None:
        raise ValueError(f"Source-only activation profile lacks RuleIR overlay: {profile_id}.")
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
        when_descriptor=metadata.when_descriptor,
        target_descriptor=metadata.target_descriptor,
        effect_descriptor=metadata.effect_descriptor,
        restrictions_descriptor="matched play same stratagem per phase",
        trigger_kind=metadata.trigger_kind,
        phase_tokens=metadata.phase_tokens,
        target_kind=metadata.target_kind,
        target_policy_id=metadata.target_policy_id,
        required_keywords=metadata.required_keywords,
        required_keywords_any=metadata.required_keywords_any,
        required_faction_keywords=metadata.required_faction_keywords,
        excluded_keywords=metadata.excluded_keywords,
        excluded_faction_keywords=metadata.excluded_faction_keywords,
        rule_ir_hash=str(overlay_rule_ir_payload["ir_hash"]),
        compiled_rule_ir_payload=None,
        effect_selection_kind=_effect_selection_kind_from_rule_ir_payload(overlay_rule_ir_payload),
    )


def _overlay_rule_ir_payload_or_none(profile_id: str) -> RuleIRPayload | None:
    court_payload = court_ir.stratagem_activation_rule_ir_payload_by_profile_id(profile_id)
    if court_payload is not None:
        return court_payload
    return spectacle_ir.stratagem_activation_rule_ir_payload_by_profile_id(profile_id)


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


def _required_keywords(*, source_row_id: str, target_descriptor: str) -> tuple[str, ...]:
    canonical = _canonical_keyword_text(target_descriptor)
    required = [
        keyword
        for keyword in REGULAR_TARGET_KEYWORDS
        if re.search(rf"(?<![A-Z0-9_]){re.escape(keyword)}(?![A-Z0-9_])", canonical)
    ]
    for keyword in SOURCE_ROW_REQUIRED_KEYWORD_OVERRIDES.get(source_row_id, ()):
        if keyword not in required:
            required.append(keyword)
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


def _compiled_stratagem_rule_ir_payload_or_none(
    *,
    profile_id: str,
    source_id: str,
    rule_target_kind: str,
    effect_descriptor: str,
) -> RuleIRPayload | None:
    compiled = compile_rule_source_text(
        RuleSourceText.from_raw(source_id=source_id, raw_text=effect_descriptor),
        source_keyword_sequence_parts=(
            datasheet_keyword_lexicon_2026_06_14.canonical_datasheet_keyword_sequence_parts()
        ),
    ).rule_ir
    if not compiled.is_supported or not any(clause.effects for clause in compiled.clauses):
        return None
    effect_payload = compiled.to_payload()
    activation_text = RULE_IR_NORMALIZED_TEXT
    effect_text = str(effect_payload["normalized_text"])
    normalized_text = f"{activation_text}\n{effect_text}"
    activation_span = {
        "text": activation_text,
        "start": 0,
        "end": len(activation_text),
    }
    effect_offset = len(activation_text) + 1
    clauses: list[dict[str, object]] = [
        _target_binding_clause_payload(
            profile_id=profile_id,
            rule_target_kind=rule_target_kind,
            span=activation_span,
        )
    ]
    for index, clause in enumerate(effect_payload["clauses"], start=1):
        clauses.append(
            _shift_clause_payload(
                clause=clause,
                offset=effect_offset,
                clause_id=f"{profile_id}:effect:{index:03d}",
            )
        )
    clauses = _clauses_with_stratagem_effect_selection_parameters(tuple(clauses))
    payload = {
        "rule_id": profile_id,
        "source_id": source_id,
        "normalized_text": normalized_text,
        "parser_version": RULE_IR_PARSER_VERSION,
        "schema_version": RULE_IR_SCHEMA_VERSION,
        "clauses": clauses,
        "diagnostics": [],
        "ir_hash": "",
    }
    payload["ir_hash"] = _sha256_payload(payload)
    return RuleIR.from_payload(cast(RuleIRPayload, payload)).to_payload()


def _clauses_with_stratagem_effect_selection_parameters(
    clauses: tuple[dict[str, object], ...],
) -> list[dict[str, object]]:
    return [
        _clause_with_hit_enemy_effect_selection(clause)
        if _clause_uses_hit_enemy_effect_selection(clause)
        else clause
        for clause in clauses
    ]


def _clause_uses_hit_enemy_effect_selection(clause: dict[str, object]) -> bool:
    target = clause.get("target")
    if not isinstance(target, dict):
        return False
    if target.get("kind") != "enemy_unit":
        return False
    target_parameters = _component_parameter_mapping(target)
    if target_parameters.get("target_relationship") != "hit_by_those_attacks":
        return False
    return any(
        _effect_is_benefit_of_cover_denial(effect)
        for effect in _object_list(clause.get("effects"), "effects")
    )


def _clause_with_hit_enemy_effect_selection(clause: dict[str, object]) -> dict[str, object]:
    updated = dict(clause)
    updated["effects"] = [
        _effect_with_parameter(effect, key="effect_selection_kind", value="hit_enemy_unit")
        if _effect_is_benefit_of_cover_denial(effect)
        else effect
        for effect in _object_list(clause.get("effects"), "effects")
    ]
    return updated


def _effect_is_benefit_of_cover_denial(effect: object) -> bool:
    if not isinstance(effect, dict):
        raise TypeError("Compiled RuleIR effect must be an object.")
    if effect.get("kind") != "set_contextual_status":
        return False
    parameters = _component_parameter_mapping(effect)
    return (
        parameters.get("rules_context") == "status_denial"
        and parameters.get("operation") == "deny"
        and parameters.get("status") == "benefit_of_cover"
        and parameters.get("target_scope") in {"selected_unit", "models_in_selected_unit"}
    )


def _effect_with_parameter(effect: object, *, key: str, value: str) -> dict[str, object]:
    if not isinstance(effect, dict):
        raise TypeError("Compiled RuleIR effect must be an object.")
    parameters = _object_list(effect.get("parameters"), "parameters")
    existing_value = _parameter_value(parameters, key)
    if existing_value is not None and existing_value != value:
        raise ValueError("Compiled RuleIR effect selection kind drift.")
    if existing_value == value:
        return dict(effect)
    updated = dict(effect)
    updated["parameters"] = sorted(
        [*parameters, {"key": key, "value": value}],
        key=_parameter_sort_key,
    )
    return updated


def _parameter_sort_key(parameter: object) -> str:
    if not isinstance(parameter, dict):
        raise TypeError("Compiled RuleIR parameter must be an object.")
    key = parameter.get("key")
    if type(key) is not str:
        raise TypeError("Compiled RuleIR parameter key must be a string.")
    return key


def _component_parameter_mapping(component: dict[str, object]) -> dict[str, object]:
    parameters = _object_list(component.get("parameters"), "parameters")
    mapping: dict[str, object] = {}
    for parameter in parameters:
        if not isinstance(parameter, dict):
            raise TypeError("Compiled RuleIR parameter must be an object.")
        key = parameter.get("key")
        if type(key) is not str:
            raise TypeError("Compiled RuleIR parameter key must be a string.")
        mapping[key] = parameter.get("value")
    return mapping


def _parameter_value(parameters: list[object], key: str) -> object:
    for parameter in parameters:
        if not isinstance(parameter, dict):
            raise TypeError("Compiled RuleIR parameter must be an object.")
        if parameter.get("key") == key:
            return parameter.get("value")
    return None


def _effect_selection_kind_from_rule_ir_payload(
    rule_ir_payload: RuleIRPayload | None,
) -> str | None:
    if rule_ir_payload is None:
        return None
    kinds: set[str] = set()
    for clause in _object_list(rule_ir_payload.get("clauses"), "clauses"):
        if not isinstance(clause, dict):
            raise TypeError("Compiled RuleIR clause must be an object.")
        for effect in _object_list(clause.get("effects"), "effects"):
            if not isinstance(effect, dict):
                raise TypeError("Compiled RuleIR effect must be an object.")
            value = _component_parameter_mapping(effect).get("effect_selection_kind")
            if value is None:
                continue
            if type(value) is not str:
                raise TypeError("Compiled RuleIR effect_selection_kind must be a string.")
            kinds.add(value)
    if not kinds:
        return None
    if kinds != {"hit_enemy_unit"}:
        raise ValueError("Compiled RuleIR has unsupported effect selection kind.")
    return "hit_enemy_unit"


def _target_binding_clause_payload(
    *,
    profile_id: str,
    rule_target_kind: str,
    span: dict[str, object],
) -> dict[str, object]:
    return {
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


def _shift_clause_payload(
    *,
    clause: object,
    offset: int,
    clause_id: str,
) -> dict[str, object]:
    if not isinstance(clause, dict):
        raise TypeError("Compiled RuleIR clause payload must be an object.")
    shifted = dict(clause)
    shifted["clause_id"] = clause_id
    shifted["source_span"] = _shift_span_payload(shifted["source_span"], offset=offset)
    trigger = shifted["trigger"]
    if trigger is not None:
        shifted["trigger"] = _shift_component_payload(trigger, offset=offset)
    shifted["conditions"] = [
        _shift_component_payload(condition, offset=offset)
        for condition in _object_list(shifted["conditions"], "conditions")
    ]
    target = shifted["target"]
    if target is not None:
        shifted["target"] = _shift_component_payload(target, offset=offset)
    shifted["effects"] = [
        _shift_component_payload(effect, offset=offset)
        for effect in _object_list(shifted["effects"], "effects")
    ]
    duration = shifted["duration"]
    if duration is not None:
        shifted["duration"] = _shift_component_payload(duration, offset=offset)
    shifted["diagnostics"] = [
        _shift_component_payload(diagnostic, offset=offset)
        for diagnostic in _object_list(shifted["diagnostics"], "diagnostics")
    ]
    return shifted


def _shift_component_payload(component: object, *, offset: int) -> dict[str, object]:
    if not isinstance(component, dict):
        raise TypeError("Compiled RuleIR component payload must be an object.")
    shifted = dict(component)
    shifted["source_span"] = _shift_span_payload(shifted["source_span"], offset=offset)
    return shifted


def _shift_span_payload(span: object, *, offset: int) -> dict[str, object]:
    if not isinstance(span, dict):
        raise TypeError("Compiled RuleIR span payload must be an object.")
    start = span["start"]
    end = span["end"]
    if type(start) is not int or type(end) is not int:
        raise TypeError("Compiled RuleIR span boundaries must be integers.")
    return {
        "text": span["text"],
        "start": start + offset,
        "end": end + offset,
    }


def _object_list(value: object, field_name: str) -> list[object]:
    if not isinstance(value, list):
        raise TypeError(f"Compiled RuleIR {field_name} must be a list.")
    return value


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
            _target_binding_clause_payload(
                profile_id=profile_id,
                rule_target_kind=rule_target_kind,
                span=span,
            )
        ],
        "diagnostics": [],
        "ir_hash": rule_ir_hash,
    }


def _validate_profile_coverage(
    profiles: tuple[ActivationProfile, ...],
    *,
    raw_rows: dict[str, dict[str, object]],
) -> None:
    source_only_rows = tuple(
        row
        for row in faction_subrules_2026_27.stratagem_rows()
        if not row.runtime_consumer_ids
        and (
            row.stratagem_id in raw_rows
            or row.source_row_id in SOURCE_ONLY_ACTIVATION_METADATA_BY_ROW_ID
        )
    )
    expected = {row.source_row_id for row in source_only_rows}
    actual = {profile.source_row_id for profile in profiles}
    if actual != expected:
        raise ValueError("Generated Stratagem activation profiles do not cover source-only rows.")


def _module_text(profiles: tuple[ActivationProfile, ...]) -> str:
    profile_lines = "\n".join(profile.constructor_line() for profile in profiles)
    static_payload_lines = "\n".join(
        (f"    {_py_value(profile.profile_id)}: {_py_value(profile.compiled_rule_ir_payload)},")
        for profile in profiles
        if profile.compiled_rule_ir_payload is not None
    )
    effect_selection_kind_lines = "\n".join(
        (f"    {_py_value(profile.profile_id)}: {_py_value(profile.effect_selection_kind)},")
        for profile in profiles
        if profile.effect_selection_kind is not None
    )
    return "\n".join(
        (
            "# Generated by tools/generate_faction_stratagem_activation_support.py.",
            (
                "# Regenerate with `uv run python "
                "tools/generate_faction_stratagem_activation_support.py`."
            ),
            "# ruff: noqa: E501, I001",
            "# fmt: off",
            "from __future__ import annotations",
            "",
            "import hashlib",
            "import json",
            "from copy import deepcopy",
            "from dataclasses import dataclass",
            "",
            "from warhammer40k_core.rules.source_packages.warhammer_40000_11th import "
            "faction_court_of_the_phoenician_ir_support_2026_27 as court_ir",
            "from warhammer40k_core.rules.source_packages.warhammer_40000_11th import "
            "faction_spectacle_of_slaughter_ir_support_2026_27 as spectacle_ir",
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
            "        static_payload = _static_rule_ir_payload_by_profile_id(self.profile_id)",
            "        if static_payload is not None:",
            "            return deepcopy(static_payload)",
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
            "        payload: dict[str, object] = {",
            '            "rule_ir": self.rule_ir_payload(),',
            '            "activation_profile_id": self.profile_id,',
            '            "activation_template_id": RULE_IR_TEMPLATE_ID,',
            "        }",
            "        effect_selection_kind = _EFFECT_SELECTION_KIND_BY_PROFILE_ID.get(",
            "            self.profile_id",
            "        )",
            "        if effect_selection_kind is not None:",
            '            payload["effect_selection_kind"] = effect_selection_kind',
            "        return payload",
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
            "_STATIC_RULE_IR_PAYLOADS_BY_PROFILE_ID: dict[str, dict[str, object]] = {",
            static_payload_lines,
            "}",
            "",
            "",
            "_EFFECT_SELECTION_KIND_BY_PROFILE_ID: dict[str, str] = {",
            effect_selection_kind_lines,
            "}",
            "",
            "",
            "def _static_rule_ir_payload_by_profile_id(",
            "    profile_id: str,",
            ") -> dict[str, object] | None:",
            "    court_payload = court_ir.stratagem_activation_rule_ir_payload_by_profile_id(",
            "        profile_id",
            "    )",
            "    if court_payload is not None:",
            "        return dict(court_payload)",
            "    static_payload = _STATIC_RULE_IR_PAYLOADS_BY_PROFILE_ID.get(profile_id)",
            "    if static_payload is not None:",
            "        return static_payload",
            "    spectacle_payload = (",
            "        spectacle_ir.stratagem_activation_rule_ir_payload_by_profile_id(",
            "            profile_id",
            "        )",
            "    )",
            "    if spectacle_payload is None:",
            "        return None",
            "    return dict(spectacle_payload)",
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
            "        static_payload = _static_rule_ir_payload_by_profile_id(",
            "            profile.profile_id",
            "        )",
            "        if static_payload is not None:",
            "            hash_payload = dict(static_payload)",
            '            hash_payload["ir_hash"] = ""',
            "            if _sha256_payload(hash_payload) != profile.rule_ir_hash:",
            '                raise ValueError("Stratagem activation static RuleIR hash drift.")',
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
    if value is None:
        return "None"
    if type(value) is bool:
        return "True" if value else "False"
    if type(value) is tuple:
        if not value:
            return "()"
        return f"({', '.join(_py_value(item) for item in value)},)"
    if type(value) is list:
        return f"[{', '.join(_py_value(item) for item in value)}]"
    if type(value) is dict:
        return (
            "{"
            + ", ".join(f"{_py_value(key)}: {_py_value(item)}" for key, item in value.items())
            + "}"
        )
    if type(value) is int:
        return str(value)
    if type(value) is float:
        return repr(value)
    if type(value) is str:
        return ascii(value)
    raise ValueError(f"Unsupported constructor value type: {type(value).__name__}.")


if __name__ == "__main__":
    main()
