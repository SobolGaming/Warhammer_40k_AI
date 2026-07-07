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
    CONTEXTUAL_STATUS_TEMPLATE_ID,
    GRANT_ABILITY_TEMPLATE_ID,
    KEYWORD_GATE_TEMPLATE_ID,
)

SOURCE_PACKAGE_ID = "gw-11e-phase17e-faction-coverage-2026-27"

RANGERS_KEYWORD = "RANGERS"
SHROUD_RUNNERS_KEYWORD = "SHROUD RUNNERS"
CAMOUFLAGED_SNIPERS_ENHANCEMENT_ID = "aeldari:path-of-the-outcast:camouflaged-snipers-upgrade"
CAMOUFLAGED_SNIPERS_SOURCE_ROW_ID = (
    "enhancement:aeldari:path-of-the-outcast:"
    "aeldari:path-of-the-outcast:camouflaged-snipers-upgrade"
)
CAMOUFLAGED_SNIPERS_ENHANCEMENT_DESCRIPTOR_ID = f"phase17e:{CAMOUFLAGED_SNIPERS_SOURCE_ROW_ID}"
CAMOUFLAGED_SNIPERS_SOURCE_RULE_ID = f"phase17f:{CAMOUFLAGED_SNIPERS_ENHANCEMENT_DESCRIPTOR_ID}"
CAMOUFLAGED_SNIPERS_KEEP_HIDDEN_ABILITY = (
    "aeldari:path-of-the-outcast:camouflaged-snipers:keep-hidden-after-ranged-attacks"
)
ASSASSINS_EYE_ENHANCEMENT_ID = "aeldari:path-of-the-outcast:assassins-eye-upgrade"
ASSASSINS_EYE_SOURCE_ROW_ID = (
    "enhancement:aeldari:path-of-the-outcast:aeldari:path-of-the-outcast:assassins-eye-upgrade"
)
ASSASSINS_EYE_ENHANCEMENT_DESCRIPTOR_ID = f"phase17e:{ASSASSINS_EYE_SOURCE_ROW_ID}"
ASSASSINS_EYE_SOURCE_RULE_ID = f"phase17f:{ASSASSINS_EYE_ENHANCEMENT_DESCRIPTOR_ID}"
ASSASSINS_EYE_CHARACTER_AP_BONUS_ABILITY = (
    "aeldari:path-of-the-outcast:assassins-eye:character-target-ap-bonus"
)

ELDRITCH_SUPPRESSION_SOURCE_ROW_ID = (
    "stratagem:aeldari:path-of-the-outcast:aeldari:path-of-the-outcast:eldritch-suppression"
)
CASTING_BACK_THE_VEIL_SOURCE_ROW_ID = (
    "stratagem:aeldari:path-of-the-outcast:aeldari:path-of-the-outcast:casting-back-the-veil"
)
NOMADS_OF_THE_HIDDEN_WAY_SOURCE_ROW_ID = (
    "stratagem:aeldari:path-of-the-outcast:aeldari:path-of-the-outcast:nomads-of-the-hidden-way"
)

ELDRITCH_SUPPRESSION_DESCRIPTOR_ID = f"phase17e:{ELDRITCH_SUPPRESSION_SOURCE_ROW_ID}"
CASTING_BACK_THE_VEIL_DESCRIPTOR_ID = f"phase17e:{CASTING_BACK_THE_VEIL_SOURCE_ROW_ID}"
NOMADS_OF_THE_HIDDEN_WAY_DESCRIPTOR_ID = f"phase17e:{NOMADS_OF_THE_HIDDEN_WAY_SOURCE_ROW_ID}"

CASTING_BACK_DETECTION_EFFECT_KIND = "aeldari_path_of_the_outcast_casting_back_the_veil"
NOMADS_RESTRICTION_EFFECT_KIND = "aeldari_path_of_the_outcast_nomads_restriction"


class AeldariPathOfTheOutcastIrSupportError(ValueError):
    """Raised when static Path of the Outcast RuleIR metadata is inconsistent."""


def coverage_rule_ir_payload_by_descriptor_id(
    coverage_descriptor_id: str,
) -> RuleIRPayload | None:
    return _COVERAGE_RULE_IR_PAYLOADS_BY_DESCRIPTOR_ID.get(coverage_descriptor_id)


def coverage_rule_ir_hash_by_descriptor_id(coverage_descriptor_id: str) -> str | None:
    payload = coverage_rule_ir_payload_by_descriptor_id(coverage_descriptor_id)
    if payload is None:
        return None
    return payload["ir_hash"]


def supported_coverage_descriptor_ids() -> tuple[str, ...]:
    return tuple(sorted(_COVERAGE_RULE_IR_PAYLOADS_BY_DESCRIPTOR_ID))


def _camouflaged_snipers_payload() -> RuleIRPayload:
    normalized_text = (
        "Rangers unit keeps Hidden status after resolving ranged attacks while it has "
        "the Camouflaged Snipers upgrade."
    )
    effect_text = "keeps Hidden status after resolving ranged attacks"
    return _enhancement_ability_payload(
        source_row_id=CAMOUFLAGED_SNIPERS_SOURCE_ROW_ID,
        normalized_text=normalized_text,
        keyword_text="Rangers",
        required_keyword_parameters=(_parameter("required_keyword_sequence", (RANGERS_KEYWORD,)),),
        source_text=effect_text,
        effect_text=effect_text,
        ability=CAMOUFLAGED_SNIPERS_KEEP_HIDDEN_ABILITY,
        extra_parameters=(
            _parameter("hook_family", "enhancement_effect"),
            _parameter("required_keyword_sequence", (RANGERS_KEYWORD,)),
        ),
    )


def _assassins_eye_payload() -> RuleIRPayload:
    normalized_text = (
        "Rangers or Shroud Runners unit improves the Armour Penetration characteristic "
        "by 1 for ranged attacks that target Character units while it has the Assassins "
        "Eye upgrade."
    )
    effect_text = (
        "improves the Armour Penetration characteristic by 1 for ranged attacks that "
        "target Character units"
    )
    required_keyword_any = (RANGERS_KEYWORD, SHROUD_RUNNERS_KEYWORD)
    return _enhancement_ability_payload(
        source_row_id=ASSASSINS_EYE_SOURCE_ROW_ID,
        normalized_text=normalized_text,
        keyword_text="Rangers or Shroud Runners",
        required_keyword_parameters=(_parameter("required_keyword_any", required_keyword_any),),
        source_text=effect_text,
        effect_text=effect_text,
        ability=ASSASSINS_EYE_CHARACTER_AP_BONUS_ABILITY,
        extra_parameters=(
            _parameter("armor_penetration_bonus", 1),
            _parameter("hook_family", "enhancement_effect"),
            _parameter("required_keyword_any", required_keyword_any),
            _parameter("target_required_keyword", "CHARACTER"),
        ),
    )


def _eldritch_suppression_payload() -> RuleIRPayload:
    normalized_text = (
        "Select one enemy unit hit by Rangers or Shroud Runners ranged attacks. That enemy "
        "unit makes a Battle-shock roll, with -1 if a model in that enemy unit was destroyed "
        "by those attacks."
    )
    return _coverage_payload(
        ELDRITCH_SUPPRESSION_SOURCE_ROW_ID,
        normalized_text,
        (
            _effect_clause(
                clause_id=_coverage_clause_id(ELDRITCH_SUPPRESSION_SOURCE_ROW_ID, "effect:001"),
                template_id=CONTEXTUAL_STATUS_TEMPLATE_ID,
                normalized_text=normalized_text,
                source_text="makes a Battle-shock roll",
                target=None,
                effects=(
                    _effect(
                        "set_contextual_status",
                        normalized_text,
                        "Battle-shock roll",
                        (
                            _parameter("status", "force_battle_shock_test"),
                            _parameter("effect_selection_kind", "hit_enemy_unit"),
                            _parameter("modifier_if_destroyed_target", -1),
                            _parameter("modifier_source_suffix", "eldritch-suppression:-1"),
                        ),
                    ),
                ),
                duration=None,
            ),
        ),
    )


def _casting_back_the_veil_payload() -> RuleIRPayload:
    normalized_text = (
        "Select one enemy unit hit by Rangers or Shroud Runners ranged attacks. That enemy "
        "unit has +6 inches detection range until the end of the Shooting phase."
    )
    return _coverage_payload(
        CASTING_BACK_THE_VEIL_SOURCE_ROW_ID,
        normalized_text,
        (
            _effect_clause(
                clause_id=_coverage_clause_id(CASTING_BACK_THE_VEIL_SOURCE_ROW_ID, "effect:001"),
                template_id=CONTEXTUAL_STATUS_TEMPLATE_ID,
                normalized_text=normalized_text,
                source_text="+6 inches detection range until the end of the Shooting phase",
                target=None,
                effects=(
                    _effect(
                        "set_contextual_status",
                        normalized_text,
                        "+6 inches detection range",
                        (
                            _parameter("status", "detection_range_bonus"),
                            _parameter("effect_selection_kind", "hit_enemy_unit"),
                            _parameter("bonus_inches", 6),
                            _parameter("source_rule_kind", CASTING_BACK_DETECTION_EFFECT_KIND),
                            _parameter("source_unit_context_key", "just_shot_unit"),
                        ),
                    ),
                ),
                duration=_timing_endpoint_duration(
                    normalized_text,
                    "end of the Shooting phase",
                    "phase",
                ),
            ),
        ),
    )


def _nomads_of_the_hidden_way_payload() -> RuleIRPayload:
    normalized_text = (
        "Rangers or Shroud Runners unit can make a Normal move of up to D6 inches. Until "
        "the end of the turn, that unit cannot declare a charge or embark within a Transport."
    )
    return _coverage_payload(
        NOMADS_OF_THE_HIDDEN_WAY_SOURCE_ROW_ID,
        normalized_text,
        (
            _effect_clause(
                clause_id=_coverage_clause_id(NOMADS_OF_THE_HIDDEN_WAY_SOURCE_ROW_ID, "effect:001"),
                template_id=GRANT_ABILITY_TEMPLATE_ID,
                normalized_text=normalized_text,
                source_text="Normal move of up to D6 inches",
                target=_target("this_unit", normalized_text, "Rangers or Shroud Runners unit"),
                effects=(
                    _effect(
                        "grant_ability",
                        normalized_text,
                        "Normal move of up to D6 inches",
                        (
                            _parameter("ability", "triggered_normal_move"),
                            _parameter("movement_kind", "triggered"),
                            _parameter("movement_mode", "normal"),
                            _parameter("roll_quantity", 1),
                            _parameter("roll_sides", 6),
                            _parameter("distance_bonus", 0),
                            _parameter(
                                "roll_type",
                                "generic_rule_ir.nomads_of_the_hidden_way_distance",
                            ),
                            _parameter("source_step", "nomads_of_the_hidden_way"),
                            _parameter(
                                "source_event_id_context_key",
                                "attack_sequence_completed_event_id",
                            ),
                            _parameter("allow_battle_shocked", False),
                            _parameter("allow_within_engagement_range", False),
                            _parameter("optional", True),
                            _parameter("one_per_phase", False),
                            _parameter("replay_effect_kind", "nomads_of_the_hidden_way_move"),
                            _parameter(
                                "phase_body_status",
                                "nomads_of_the_hidden_way_move_pending",
                            ),
                        ),
                    ),
                ),
                duration=None,
            ),
            _effect_clause(
                clause_id=_coverage_clause_id(NOMADS_OF_THE_HIDDEN_WAY_SOURCE_ROW_ID, "effect:002"),
                template_id=CONTEXTUAL_STATUS_TEMPLATE_ID,
                normalized_text=normalized_text,
                source_text="cannot declare a charge or embark within a Transport",
                target=_target("this_unit", normalized_text, "Rangers or Shroud Runners unit"),
                effects=(
                    _effect(
                        "set_contextual_status",
                        normalized_text,
                        "cannot declare a charge or embark within a Transport",
                        (
                            _parameter("status", "unit_action_restriction"),
                            _parameter("effect_kind", NOMADS_RESTRICTION_EFFECT_KIND),
                            _parameter("charge_forbidden", True),
                            _parameter("embark_transport_forbidden", True),
                        ),
                    ),
                ),
                duration=_timing_endpoint_duration(normalized_text, "end of the turn", "turn"),
            ),
        ),
    )


def _enhancement_ability_payload(
    *,
    source_row_id: str,
    normalized_text: str,
    keyword_text: str,
    required_keyword_parameters: tuple[RuleParameterPayload, ...],
    source_text: str,
    effect_text: str,
    ability: str,
    extra_parameters: tuple[RuleParameterPayload, ...],
) -> RuleIRPayload:
    return _coverage_payload(
        source_row_id,
        normalized_text,
        (
            _keyword_gate_clause(
                clause_id=_coverage_clause_id(source_row_id, "gate:001"),
                normalized_text=normalized_text,
                keyword_text=keyword_text,
                parameters=required_keyword_parameters,
            ),
            _ability_clause(
                clause_id=_coverage_clause_id(source_row_id, "effect:001"),
                normalized_text=normalized_text,
                source_text=source_text,
                effect_text=effect_text,
                ability=ability,
                extra_parameters=extra_parameters,
            ),
        ),
    )


def _keyword_gate_clause(
    *,
    clause_id: str,
    normalized_text: str,
    keyword_text: str,
    parameters: tuple[RuleParameterPayload, ...],
) -> RuleClausePayload:
    return cast(
        RuleClausePayload,
        {
            "clause_id": clause_id,
            "template_id": KEYWORD_GATE_TEMPLATE_ID,
            "source_span": _span(normalized_text, keyword_text),
            "trigger": None,
            "conditions": [
                _keyword_gate_condition(
                    normalized_text=normalized_text,
                    keyword_text=keyword_text,
                    parameters=parameters,
                )
            ],
            "target": None,
            "effects": [],
            "duration": None,
            "unsupported_reason": None,
            "diagnostics": [],
        },
    )


def _keyword_gate_condition(
    *,
    normalized_text: str,
    keyword_text: str,
    parameters: tuple[RuleParameterPayload, ...],
) -> RuleConditionPayload:
    return cast(
        RuleConditionPayload,
        {
            "kind": "keyword_gate",
            "source_span": _span(normalized_text, keyword_text),
            "parameters": list(parameters),
        },
    )


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


def _coverage_clause_id(source_row_id: str, suffix: str) -> str:
    source_id = f"{SOURCE_PACKAGE_ID}:phase17e:{source_row_id}:source-text"
    return f"{source_id}:clause:{suffix}"


def _ability_clause(
    *,
    clause_id: str,
    normalized_text: str,
    source_text: str,
    effect_text: str,
    ability: str,
    extra_parameters: tuple[RuleParameterPayload, ...],
) -> RuleClausePayload:
    return _effect_clause(
        clause_id=clause_id,
        template_id=GRANT_ABILITY_TEMPLATE_ID,
        normalized_text=normalized_text,
        source_text=source_text,
        target=_target("this_unit", normalized_text, source_text),
        effects=(
            _effect(
                "grant_ability",
                normalized_text,
                effect_text,
                (
                    _parameter("ability", ability),
                    *extra_parameters,
                ),
            ),
        ),
        duration=_permanent_duration(normalized_text),
    )


def _effect_clause(
    *,
    clause_id: str,
    template_id: str,
    normalized_text: str,
    source_text: str,
    target: RuleTargetSpecPayload | None,
    effects: tuple[RuleEffectSpecPayload, ...],
    duration: RuleDurationPayload | None,
) -> RuleClausePayload:
    return cast(
        RuleClausePayload,
        {
            "clause_id": clause_id,
            "template_id": template_id,
            "source_span": _span(normalized_text, source_text),
            "trigger": None,
            "conditions": [],
            "target": target,
            "effects": list(effects),
            "duration": duration,
            "unsupported_reason": None,
            "diagnostics": [],
        },
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
) -> RuleTargetSpecPayload:
    return cast(
        RuleTargetSpecPayload,
        {
            "kind": kind,
            "source_span": _span(normalized_text, source_text),
            "parameters": [],
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


def _timing_endpoint_duration(
    normalized_text: str,
    source_text: str,
    endpoint: str,
) -> RuleDurationPayload:
    return cast(
        RuleDurationPayload,
        {
            "kind": "until_timing_endpoint",
            "source_span": _span(normalized_text, source_text),
            "parameters": [_parameter("endpoint", endpoint)],
        },
    )


def _parameter(
    key: str,
    value: str | int | float | bool | None | tuple[str, ...],
) -> RuleParameterPayload:
    payload_value = list(value) if type(value) is tuple else value
    return cast(RuleParameterPayload, {"key": key, "value": payload_value})


def _span(normalized_text: str, source_text: str) -> dict[str, str | int]:
    start = normalized_text.index(source_text)
    return {"text": source_text, "start": start, "end": start + len(source_text)}


def _payload_rows() -> Mapping[str, RuleIRPayload]:
    return {
        CAMOUFLAGED_SNIPERS_SOURCE_ROW_ID: _camouflaged_snipers_payload(),
        ASSASSINS_EYE_SOURCE_ROW_ID: _assassins_eye_payload(),
        ELDRITCH_SUPPRESSION_SOURCE_ROW_ID: _eldritch_suppression_payload(),
        CASTING_BACK_THE_VEIL_SOURCE_ROW_ID: _casting_back_the_veil_payload(),
        NOMADS_OF_THE_HIDDEN_WAY_SOURCE_ROW_ID: _nomads_of_the_hidden_way_payload(),
    }


_COVERAGE_RULE_IR_PAYLOADS_BY_DESCRIPTOR_ID = MappingProxyType(
    {f"phase17e:{source_row_id}": payload for source_row_id, payload in _payload_rows().items()}
)
