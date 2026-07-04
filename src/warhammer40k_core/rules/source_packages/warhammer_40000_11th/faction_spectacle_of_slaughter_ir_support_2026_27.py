from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import cast

from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleClausePayload,
    RuleConditionPayload,
    RuleDurationPayload,
    RuleEffectSpecPayload,
    RuleIR,
    RuleIRPayload,
    RuleParameterPayload,
    RuleTargetSpecPayload,
)
from warhammer40k_core.rules.rule_templates import (
    GRANT_ABILITY_TEMPLATE_ID,
    KEYWORD_GATE_TEMPLATE_ID,
    MOVEMENT_DISTANCE_TEMPLATE_ID,
    WEAPON_ABILITY_GRANT_TEMPLATE_ID,
)

SOURCE_PACKAGE_ID = "gw-11e-phase17e-faction-coverage-2026-27"
STRATAGEM_SOURCE_PACKAGE_ID = "gw-11e-phase17e-exact-faction-subrules-2026-27"
STRATAGEM_TARGET_BINDING_TEMPLATE_ID = "phase17s:stratagem-activation-target-binding"

FLAWLESS_BLADES_KEYWORD = "FLAWLESS BLADES"
SNAP_SHOOTING_TARGET_FORBIDDEN_ABILITY = "cannot_be_targeted_by_snap_shooting"
TRIGGERED_NORMAL_MOVE_ABILITY = "triggered_normal_move"

SPECTACLE_OF_SLAUGHTER_DETACHMENT_RULE_DESCRIPTOR_ID = (
    "phase17e:emperors-children:spectacle-of-slaughter:rule"
)
SPECTACLE_OF_SLAUGHTER_ENHANCEMENT_DESCRIPTOR_IDS = (
    "phase17e:enhancement:emperors-children:spectacle-of-slaughter:000010900002",
    "phase17e:enhancement:emperors-children:spectacle-of-slaughter:000010900003",
)
SPECTACLE_OF_SLAUGHTER_STRATAGEM_DESCRIPTOR_IDS = (
    "phase17e:stratagem:emperors-children:spectacle-of-slaughter:000010901002",
    "phase17e:stratagem:emperors-children:spectacle-of-slaughter:000010901003",
    "phase17e:stratagem:emperors-children:spectacle-of-slaughter:000010901004",
)
SPECTACLE_OF_SLAUGHTER_STRATAGEM_PROFILE_IDS = (
    "phase17s:stratagem:emperors-children:spectacle-of-slaughter:000010901002",
    "phase17s:stratagem:emperors-children:spectacle-of-slaughter:000010901003",
    "phase17s:stratagem:emperors-children:spectacle-of-slaughter:000010901004",
)


class SpectacleOfSlaughterIrSupportError(ValueError):
    """Raised when static Spectacle of Slaughter RuleIR metadata is inconsistent."""


def coverage_rule_ir_payload_by_descriptor_id(
    coverage_descriptor_id: str,
) -> RuleIRPayload | None:
    return _COVERAGE_RULE_IR_PAYLOADS_BY_DESCRIPTOR_ID.get(coverage_descriptor_id)


def coverage_rule_ir_hash_by_descriptor_id(coverage_descriptor_id: str) -> str | None:
    payload = coverage_rule_ir_payload_by_descriptor_id(coverage_descriptor_id)
    if payload is None:
        return None
    return payload["ir_hash"]


def stratagem_activation_rule_ir_payload_by_profile_id(
    profile_id: str,
) -> RuleIRPayload | None:
    return _STRATAGEM_ACTIVATION_RULE_IR_PAYLOADS_BY_PROFILE_ID.get(profile_id)


def supported_coverage_descriptor_ids() -> tuple[str, ...]:
    return tuple(sorted(_COVERAGE_RULE_IR_PAYLOADS_BY_DESCRIPTOR_ID))


def supported_stratagem_profile_ids() -> tuple[str, ...]:
    return tuple(sorted(_STRATAGEM_ACTIVATION_RULE_IR_PAYLOADS_BY_PROFILE_ID))


def _detachment_rule_payload() -> RuleIRPayload:
    source_row_id = "emperors-children:spectacle-of-slaughter:rule"
    normalized_text = "Friendly FLAWLESS BLADES units have Fights First."
    clauses = (
        _effect_clause(
            clause_id=_coverage_clause_id(source_row_id, "effect:001"),
            template_id=GRANT_ABILITY_TEMPLATE_ID,
            normalized_text=normalized_text,
            source_text=normalized_text,
            target=None,
            effects=(
                _effect(
                    "grant_ability",
                    normalized_text,
                    "have Fights First",
                    (_parameter("ability", "fights_first"),),
                ),
            ),
            duration=_permanent_duration(normalized_text),
        ),
    )
    return _coverage_payload(source_row_id, normalized_text, clauses)


def _beguiling_grotesquerie_payload() -> RuleIRPayload:
    source_row_id = "enhancement:emperors-children:spectacle-of-slaughter:000010900002"
    normalized_text = (
        "FLAWLESS BLADES unit only. Enemy units cannot target this unit with snap shooting attacks."
    )
    clauses = (
        _keyword_gate_clause(
            clause_id=_coverage_clause_id(source_row_id, "gate:001"),
            normalized_text=normalized_text,
            source_text="FLAWLESS BLADES unit only",
            keyword_text="FLAWLESS BLADES",
            required_keyword=FLAWLESS_BLADES_KEYWORD,
        ),
        _ability_clause(
            clause_id=_coverage_clause_id(source_row_id, "effect:001"),
            template_id=GRANT_ABILITY_TEMPLATE_ID,
            normalized_text=normalized_text,
            source_text="Enemy units cannot target this unit with snap shooting attacks.",
            target_kind="this_unit",
            target_text="this unit",
            effect_text="cannot target this unit with snap shooting attacks",
            ability=SNAP_SHOOTING_TARGET_FORBIDDEN_ABILITY,
            duration=None,
        ),
    )
    return _coverage_payload(source_row_id, normalized_text, clauses)


def _eager_patrons_payload() -> RuleIRPayload:
    source_row_id = "enhancement:emperors-children:spectacle-of-slaughter:000010900003"
    normalized_text = "FLAWLESS BLADES unit only. This unit has +2 inches Move."
    clauses = (
        _keyword_gate_clause(
            clause_id=_coverage_clause_id(source_row_id, "gate:001"),
            normalized_text=normalized_text,
            source_text="FLAWLESS BLADES unit only",
            keyword_text="FLAWLESS BLADES",
            required_keyword=FLAWLESS_BLADES_KEYWORD,
        ),
        _move_modifier_clause(
            clause_id=_coverage_clause_id(source_row_id, "effect:001"),
            normalized_text=normalized_text,
            source_text="This unit has +2 inches Move.",
            target_kind="this_unit",
            target_text="This unit",
            effect_text="+2 inches Move",
            delta=2,
            duration=None,
        ),
    )
    return _coverage_payload(source_row_id, normalized_text, clauses)


def _honour_is_for_fools_payload(*, rule_id: str, source_id: str) -> RuleIRPayload:
    normalized_text = (
        "stratagem_activation_target_binding\n"
        "Until the end of the phase, melee weapons equipped by models in your unit "
        "have the [PRECISION] ability."
    )
    clauses = (
        _stratagem_target_binding_clause(rule_id, normalized_text),
        _weapon_ability_clause(
            clause_id=f"{rule_id}:effect:001",
            normalized_text=normalized_text,
            source_text=normalized_text.split("\n", maxsplit=1)[1],
            effect_text=(
                "melee weapons equipped by models in your unit have the [PRECISION] ability"
            ),
            weapon_ability="Precision",
            weapon_scope="melee",
            duration=_end_phase_duration(normalized_text),
        ),
    )
    return _payload(rule_id, source_id, normalized_text, clauses, _stratagem_parser_version())


def _single_minded_strike_payload(*, rule_id: str, source_id: str) -> RuleIRPayload:
    normalized_text = (
        "stratagem_activation_target_binding\n"
        "Until the end of the phase, models in your unit can move through models, "
        "excluding MONSTER and VEHICLE models."
    )
    clauses = (
        _stratagem_target_binding_clause(rule_id, normalized_text),
        _effect_clause(
            clause_id=f"{rule_id}:effect:001",
            template_id=GRANT_ABILITY_TEMPLATE_ID,
            normalized_text=normalized_text,
            source_text=normalized_text.split("\n", maxsplit=1)[1],
            target=None,
            effects=(
                _effect(
                    "movement_transit_permission",
                    normalized_text,
                    "models in your unit can move through models",
                    (
                        _parameter("permission", "move_through_models"),
                        _parameter("movement_modes", ("charge",)),
                        _parameter("model_allegiance", "any"),
                        _parameter("excluded_model_keyword_any", ("MONSTER", "VEHICLE")),
                    ),
                ),
            ),
            duration=_end_phase_duration(normalized_text),
        ),
    )
    return _payload(rule_id, source_id, normalized_text, clauses, _stratagem_parser_version())


def _intoxicated_by_triumph_payload(*, rule_id: str, source_id: str) -> RuleIRPayload:
    normalized_text = (
        "stratagem_activation_target_binding\n"
        "Your unit can make a normal move of up to D3+3 inches."
    )
    clauses = (
        _stratagem_target_binding_clause(rule_id, normalized_text),
        _ability_clause(
            clause_id=f"{rule_id}:effect:001",
            template_id=GRANT_ABILITY_TEMPLATE_ID,
            normalized_text=normalized_text,
            source_text=normalized_text.split("\n", maxsplit=1)[1],
            target_kind="friendly_unit",
            target_text="Your unit",
            effect_text="can make a normal move of up to D3+3 inches",
            ability=TRIGGERED_NORMAL_MOVE_ABILITY,
            duration=None,
            extra_parameters=(
                _parameter("distance_expression", "D3+3"),
                _parameter("movement_mode", "normal"),
                _parameter("movement_kind", "surge"),
                _parameter("trigger_context", "enemy_fall_back"),
            ),
        ),
    )
    return _payload(rule_id, source_id, normalized_text, clauses, _stratagem_parser_version())


def _coverage_payload(
    source_row_id: str,
    normalized_text: str,
    clauses: tuple[RuleClausePayload, ...],
) -> RuleIRPayload:
    source_id = f"{SOURCE_PACKAGE_ID}:phase17e:{source_row_id}:source-text"
    return _payload(
        source_id,
        source_id,
        normalized_text,
        clauses,
        "phase17c-rule-parser-v1",
    )


def _stratagem_coverage_payload(stratagem_id: str) -> RuleIRPayload:
    source_row_id = f"stratagem:emperors-children:spectacle-of-slaughter:{stratagem_id}"
    rule_id = f"{SOURCE_PACKAGE_ID}:phase17e:{source_row_id}:source-text"
    source_id = rule_id
    return _stratagem_payload_by_id(stratagem_id, rule_id=rule_id, source_id=source_id)


def _stratagem_activation_payload(profile_id: str) -> RuleIRPayload:
    stratagem_id = profile_id.rsplit(":", maxsplit=1)[-1]
    source_id = (
        f"{STRATAGEM_SOURCE_PACKAGE_ID}:stratagem:emperors-children:"
        f"spectacle-of-slaughter:{stratagem_id}"
    )
    return _stratagem_payload_by_id(stratagem_id, rule_id=profile_id, source_id=source_id)


def _stratagem_payload_by_id(
    stratagem_id: str,
    *,
    rule_id: str,
    source_id: str,
) -> RuleIRPayload:
    if stratagem_id == "000010901002":
        return _honour_is_for_fools_payload(rule_id=rule_id, source_id=source_id)
    if stratagem_id == "000010901003":
        return _single_minded_strike_payload(rule_id=rule_id, source_id=source_id)
    if stratagem_id == "000010901004":
        return _intoxicated_by_triumph_payload(rule_id=rule_id, source_id=source_id)
    raise SpectacleOfSlaughterIrSupportError("Unsupported Spectacle of Slaughter Stratagem id.")


def _payload(
    rule_id: str,
    source_id: str,
    normalized_text: str,
    clauses: tuple[RuleClausePayload, ...],
    parser_version: str,
) -> RuleIRPayload:
    return RuleIR(
        rule_id=rule_id,
        source_id=source_id,
        normalized_text=normalized_text,
        parser_version=parser_version,
        schema_version="phase17c-rule-ir-v1",
        clauses=tuple(RuleClause.from_payload(clause) for clause in clauses),
        diagnostics=(),
    ).to_payload()


def _effect_clause(
    *,
    clause_id: str,
    template_id: str,
    normalized_text: str,
    source_text: str,
    target: RuleTargetSpecPayload | None,
    effects: tuple[RuleEffectSpecPayload, ...],
    duration: RuleDurationPayload | None,
    conditions: tuple[RuleConditionPayload, ...] = (),
) -> RuleClausePayload:
    return cast(
        RuleClausePayload,
        {
            "clause_id": clause_id,
            "template_id": template_id,
            "source_span": _span(normalized_text, source_text),
            "trigger": None,
            "conditions": list(conditions),
            "target": target,
            "effects": list(effects),
            "duration": duration,
            "unsupported_reason": None,
            "diagnostics": [],
        },
    )


def _keyword_gate_clause(
    *,
    clause_id: str,
    normalized_text: str,
    source_text: str,
    keyword_text: str,
    required_keyword: str,
) -> RuleClausePayload:
    return cast(
        RuleClausePayload,
        {
            "clause_id": clause_id,
            "template_id": KEYWORD_GATE_TEMPLATE_ID,
            "source_span": _span(normalized_text, source_text),
            "trigger": None,
            "conditions": [
                {
                    "kind": "keyword_gate",
                    "source_span": _span(normalized_text, keyword_text),
                    "parameters": [_parameter("required_keyword", required_keyword)],
                }
            ],
            "target": None,
            "effects": [],
            "duration": None,
            "unsupported_reason": None,
            "diagnostics": [],
        },
    )


def _stratagem_target_binding_clause(
    rule_id: str,
    normalized_text: str,
) -> RuleClausePayload:
    return cast(
        RuleClausePayload,
        {
            "clause_id": f"{rule_id}:target-binding",
            "template_id": STRATAGEM_TARGET_BINDING_TEMPLATE_ID,
            "source_span": _span(normalized_text, "stratagem_activation_target_binding"),
            "trigger": None,
            "conditions": [],
            "target": _target(
                "friendly_unit",
                normalized_text,
                "stratagem_activation_target_binding",
            ),
            "effects": [],
            "duration": None,
            "unsupported_reason": None,
            "diagnostics": [],
        },
    )


def _ability_clause(
    *,
    clause_id: str,
    template_id: str,
    normalized_text: str,
    source_text: str,
    target_kind: str,
    target_text: str,
    effect_text: str,
    ability: str,
    duration: RuleDurationPayload | None,
    extra_parameters: tuple[RuleParameterPayload, ...] = (),
) -> RuleClausePayload:
    return _effect_clause(
        clause_id=clause_id,
        template_id=template_id,
        normalized_text=normalized_text,
        source_text=source_text,
        target=_target(target_kind, normalized_text, target_text),
        effects=(
            _effect(
                "grant_ability",
                normalized_text,
                effect_text,
                (_parameter("ability", ability), *extra_parameters),
            ),
        ),
        duration=duration,
    )


def _weapon_ability_clause(
    *,
    clause_id: str,
    normalized_text: str,
    source_text: str,
    effect_text: str,
    weapon_ability: str,
    weapon_scope: str,
    duration: RuleDurationPayload | None,
) -> RuleClausePayload:
    return _effect_clause(
        clause_id=clause_id,
        template_id=WEAPON_ABILITY_GRANT_TEMPLATE_ID,
        normalized_text=normalized_text,
        source_text=source_text,
        target=None,
        effects=(
            _effect(
                "grant_weapon_ability",
                normalized_text,
                effect_text,
                (
                    _parameter("weapon_ability", weapon_ability),
                    _parameter("weapon_scope", weapon_scope),
                    _parameter("attack_role", "attacker"),
                ),
            ),
        ),
        duration=duration,
    )


def _move_modifier_clause(
    *,
    clause_id: str,
    normalized_text: str,
    source_text: str,
    target_kind: str,
    target_text: str,
    effect_text: str,
    delta: int,
    duration: RuleDurationPayload | None,
) -> RuleClausePayload:
    return _effect_clause(
        clause_id=clause_id,
        template_id=MOVEMENT_DISTANCE_TEMPLATE_ID,
        normalized_text=normalized_text,
        source_text=source_text,
        target=_target(target_kind, normalized_text, target_text),
        effects=(
            _effect(
                "modify_move_distance",
                normalized_text,
                effect_text,
                (_parameter("delta", delta),),
            ),
        ),
        duration=duration,
    )


def _effect(
    kind: str,
    normalized_text: str,
    source_text: str,
    parameters: tuple[RuleParameterPayload, ...],
) -> RuleEffectSpecPayload:
    return cast(
        RuleEffectSpecPayload,
        {
            "kind": kind,
            "source_span": _span(normalized_text, source_text),
            "parameters": list(parameters),
        },
    )


def _target(
    kind: str,
    normalized_text: str,
    source_text: str,
    parameters: tuple[RuleParameterPayload, ...] = (),
) -> RuleTargetSpecPayload:
    return cast(
        RuleTargetSpecPayload,
        {
            "kind": kind,
            "source_span": _span(normalized_text, source_text),
            "parameters": list(parameters),
        },
    )


def _end_phase_duration(normalized_text: str) -> RuleDurationPayload:
    return cast(
        RuleDurationPayload,
        {
            "kind": "until_timing_endpoint",
            "source_span": _span(normalized_text, "Until the end of the phase"),
            "parameters": [_parameter("endpoint", "phase")],
        },
    )


def _permanent_duration(normalized_text: str) -> RuleDurationPayload:
    return cast(
        RuleDurationPayload,
        {
            "kind": "permanent",
            "source_span": _span(normalized_text, normalized_text),
            "parameters": [],
        },
    )


def _parameter(key: str, value: object) -> RuleParameterPayload:
    return cast(RuleParameterPayload, {"key": key, "value": value})


def _span(normalized_text: str, source_text: str) -> dict[str, str | int]:
    start = normalized_text.index(source_text)
    return {"text": source_text, "start": start, "end": start + len(source_text)}


def _coverage_clause_id(source_row_id: str, suffix: str) -> str:
    return f"{SOURCE_PACKAGE_ID}:phase17e:{source_row_id}:source-text:{suffix}"


def _stratagem_parser_version() -> str:
    return "phase17s-stratagem-activation-template-v2"


def _coverage_payloads() -> Mapping[str, RuleIRPayload]:
    payloads = {
        SPECTACLE_OF_SLAUGHTER_DETACHMENT_RULE_DESCRIPTOR_ID: _detachment_rule_payload(),
        SPECTACLE_OF_SLAUGHTER_ENHANCEMENT_DESCRIPTOR_IDS[0]: (_beguiling_grotesquerie_payload()),
        SPECTACLE_OF_SLAUGHTER_ENHANCEMENT_DESCRIPTOR_IDS[1]: _eager_patrons_payload(),
    }
    for descriptor_id in SPECTACLE_OF_SLAUGHTER_STRATAGEM_DESCRIPTOR_IDS:
        stratagem_id = descriptor_id.rsplit(":", maxsplit=1)[-1]
        payloads[descriptor_id] = _stratagem_coverage_payload(stratagem_id)
    return MappingProxyType(payloads)


def _stratagem_activation_payloads() -> Mapping[str, RuleIRPayload]:
    return MappingProxyType(
        {
            profile_id: _stratagem_activation_payload(profile_id)
            for profile_id in SPECTACLE_OF_SLAUGHTER_STRATAGEM_PROFILE_IDS
        }
    )


_COVERAGE_RULE_IR_PAYLOADS_BY_DESCRIPTOR_ID = _coverage_payloads()
_STRATAGEM_ACTIVATION_RULE_IR_PAYLOADS_BY_PROFILE_ID = _stratagem_activation_payloads()
