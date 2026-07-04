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
    RuleTriggerPayload,
)
from warhammer40k_core.rules.rule_templates import (
    CHARACTERISTIC_MODIFIER_TEMPLATE_ID,
    CONTEXTUAL_STATUS_TEMPLATE_ID,
    DICE_ROLL_MODIFIER_TEMPLATE_ID,
    GRANT_ABILITY_TEMPLATE_ID,
    KEYWORD_GATE_TEMPLATE_ID,
    MOVEMENT_DISTANCE_TEMPLATE_ID,
    REROLL_PERMISSION_TEMPLATE_ID,
    WEAPON_ABILITY_GRANT_TEMPLATE_ID,
)

SOURCE_PACKAGE_ID = "gw-11e-phase17e-faction-coverage-2026-27"
STRATAGEM_SOURCE_PACKAGE_ID = "gw-11e-phase17e-exact-faction-subrules-2026-27"
STRATAGEM_TARGET_BINDING_TEMPLATE_ID = "phase17s:stratagem-activation-target-binding"

MORE_DAKKA_DETACHMENT_RULE_DESCRIPTOR_ID = "phase17e:orks:more-dakka:rule"
MORE_DAKKA_ENHANCEMENT_DESCRIPTOR_IDS = ("phase17e:enhancement:orks:more-dakka:000009991002",)
MORE_DAKKA_STRATAGEM_DESCRIPTOR_IDS = (
    "phase17e:stratagem:orks:more-dakka:000009992002",
    "phase17e:stratagem:orks:more-dakka:000009992003",
    "phase17e:stratagem:orks:more-dakka:000009992004",
    "phase17e:stratagem:orks:more-dakka:000009992005",
    "phase17e:stratagem:orks:more-dakka:000009992006",
    "phase17e:stratagem:orks:more-dakka:000009992007",
)
MORE_DAKKA_STRATAGEM_PROFILE_IDS = (
    "phase17s:stratagem:orks:more-dakka:000009992002",
    "phase17s:stratagem:orks:more-dakka:000009992003",
    "phase17s:stratagem:orks:more-dakka:000009992004",
    "phase17s:stratagem:orks:more-dakka:000009992005",
    "phase17s:stratagem:orks:more-dakka:000009992006",
    "phase17s:stratagem:orks:more-dakka:000009992007",
)


class MoreDakkaIrSupportError(ValueError):
    """Raised when static More Dakka RuleIR support metadata is inconsistent."""


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
    source_row_id = "orks:more-dakka:rule"
    normalized_text = (
        "Ranged weapons equipped by Orks Infantry and Orks Walker models from your army "
        "have the [ASSAULT] ability. While the Waaagh! is active for your army, during "
        "your Shooting phase, ranged weapons equipped by Orks Infantry and Orks Walker "
        "models from your army have the [SUSTAINED HITS 1] ability."
    )
    clauses = (
        _weapon_ability_clause(
            clause_id=_coverage_clause_id(source_row_id, "effect:001"),
            normalized_text=normalized_text,
            source_text=(
                "Ranged weapons equipped by Orks Infantry and Orks Walker models from "
                "your army have the [ASSAULT] ability."
            ),
            effect_text=(
                "Ranged weapons equipped by Orks Infantry and Orks Walker models from "
                "your army have the [ASSAULT] ability"
            ),
            weapon_ability="Assault",
            duration=_permanent_duration(normalized_text),
        ),
        _weapon_ability_clause(
            clause_id=_coverage_clause_id(source_row_id, "effect:002"),
            normalized_text=normalized_text,
            source_text=(
                "While the Waaagh! is active for your army, during your Shooting phase, "
                "ranged weapons equipped by Orks Infantry and Orks Walker models from "
                "your army have the [SUSTAINED HITS 1] ability."
            ),
            effect_text=(
                "ranged weapons equipped by Orks Infantry and Orks Walker models from "
                "your army have the [SUSTAINED HITS 1] ability"
            ),
            weapon_ability="Sustained Hits",
            weapon_ability_value=1,
            duration=_permanent_duration(normalized_text),
            extra_parameters=(
                _parameter("source_phase", "shooting"),
                _parameter("requires_waaagh_active_for_unit", True),
            ),
        ),
    )
    return _coverage_payload(source_row_id, normalized_text, clauses)


def _da_gobshot_payload() -> RuleIRPayload:
    source_row_id = "enhancement:orks:more-dakka:000009991002"
    normalized_text = (
        "ORKS model only. Ranged weapons equipped by the bearer have the "
        "[DEVASTATING WOUNDS] and [HAZARDOUS] abilities."
    )
    clauses = (
        _keyword_gate_clause(
            clause_id=_coverage_clause_id(source_row_id, "gate:001"),
            normalized_text=normalized_text,
            source_text="ORKS model only",
            keyword_text="ORKS",
            required_keyword="ORKS",
        ),
        _weapon_ability_clause(
            clause_id=_coverage_clause_id(source_row_id, "effect:001"),
            normalized_text=normalized_text,
            source_text=(
                "Ranged weapons equipped by the bearer have the [DEVASTATING WOUNDS] "
                "and [HAZARDOUS] abilities."
            ),
            effect_text=("Ranged weapons equipped by the bearer have the [DEVASTATING WOUNDS]"),
            weapon_ability="Devastating Wounds",
        ),
        _weapon_ability_clause(
            clause_id=_coverage_clause_id(source_row_id, "effect:002"),
            normalized_text=normalized_text,
            source_text=(
                "Ranged weapons equipped by the bearer have the [DEVASTATING WOUNDS] "
                "and [HAZARDOUS] abilities."
            ),
            effect_text="[HAZARDOUS]",
            weapon_ability="Hazardous",
        ),
    )
    return _coverage_payload(source_row_id, normalized_text, clauses)


def _orks_is_still_orks_payload(*, rule_id: str, source_id: str) -> RuleIRPayload:
    normalized_text = (
        "stratagem_activation_target_binding\n"
        "Until the end of the phase, each time a model in your unit makes an attack "
        "that targets an enemy unit, re-roll a Wound roll of 1. If that enemy unit "
        "is within range of an objective marker, you can re-roll the Wound roll instead."
    )
    clauses = (
        _stratagem_target_binding_clause(rule_id, normalized_text),
        _effect_clause(
            clause_id=f"{rule_id}:effect:001",
            template_id=REROLL_PERMISSION_TEMPLATE_ID,
            normalized_text=normalized_text,
            source_text=normalized_text.split("\n", maxsplit=1)[1],
            trigger=_dice_roll_trigger(
                normalized_text,
                ("each time a model in your unit makes an attack that targets an enemy unit"),
                roll_type="wound",
            ),
            target=None,
            effects=(
                _effect(
                    "reroll_permission",
                    normalized_text,
                    "re-roll a Wound roll of 1",
                    (
                        _parameter("roll_type", "wound"),
                        _parameter("timing_window", "attack.wound"),
                        _parameter("attack_role", "attacker"),
                        _parameter("reroll_unmodified_value", 1),
                        _parameter(
                            "full_reroll_if_target_within_objective_range",
                            True,
                        ),
                    ),
                ),
            ),
            duration=_end_phase_duration(normalized_text),
        ),
    )
    return _payload(rule_id, source_id, normalized_text, clauses, _stratagem_parser_version())


def _get_stuck_in_payload(*, rule_id: str, source_id: str) -> RuleIRPayload:
    normalized_text = (
        "stratagem_activation_target_binding\n"
        "Until the start of your next Command phase, the Waaagh! is active for your unit."
    )
    clauses = (
        _stratagem_target_binding_clause(rule_id, normalized_text),
        _effect_clause(
            clause_id=f"{rule_id}:effect:001",
            template_id=CONTEXTUAL_STATUS_TEMPLATE_ID,
            normalized_text=normalized_text,
            source_text=(
                "Until the start of your next Command phase, the Waaagh! is active for your unit."
            ),
            trigger=None,
            target=None,
            effects=(
                _effect(
                    "set_contextual_status",
                    normalized_text,
                    "the Waaagh! is active for your unit",
                    (
                        _parameter("status", "orks_waaagh_active"),
                        _parameter("scope", "unit"),
                    ),
                ),
            ),
            duration=_until_next_command_start_duration(normalized_text),
        ),
    )
    return _payload(rule_id, source_id, normalized_text, clauses, _stratagem_parser_version())


def _huge_show_offs_payload(*, rule_id: str, source_id: str) -> RuleIRPayload:
    normalized_text = (
        "stratagem_activation_target_binding\n"
        "Until the start of your next Command phase, improve your unit's Move, "
        "Leadership and Objective Control characteristics by 1, and each time a model "
        "in your unit makes an attack, add 1 to the Hit roll."
    )
    duration = _until_next_command_start_duration(normalized_text)
    clauses = (
        _stratagem_target_binding_clause(rule_id, normalized_text),
        _move_modifier_clause(
            rule_id=rule_id,
            clause_suffix="effect:001",
            normalized_text=normalized_text,
            source_text="improve your unit's Move",
            delta=1,
            duration=duration,
        ),
        _characteristic_modifier_clause(
            rule_id=rule_id,
            clause_suffix="effect:002",
            normalized_text=normalized_text,
            source_text="Leadership",
            characteristic="leadership",
            delta=-1,
            duration=duration,
        ),
        _characteristic_modifier_clause(
            rule_id=rule_id,
            clause_suffix="effect:003",
            normalized_text=normalized_text,
            source_text="Objective Control",
            characteristic="objective_control",
            delta=1,
            duration=duration,
        ),
        _dice_roll_modifier_clause(
            rule_id=rule_id,
            clause_suffix="effect:004",
            normalized_text=normalized_text,
            source_text="each time a model in your unit makes an attack, add 1 to the Hit roll",
            effect_text="add 1 to the Hit roll",
            roll_type="hit",
            delta=1,
            duration=duration,
            extra_parameters=(_parameter("attack_role", "attacker"),),
        ),
    )
    return _payload(rule_id, source_id, normalized_text, clauses, _stratagem_parser_version())


def _long_uncontrolled_bursts_payload(*, rule_id: str, source_id: str) -> RuleIRPayload:
    normalized_text = (
        "stratagem_activation_target_binding\n"
        "Until the end of the phase, ranged weapons equipped by models in your unit "
        "have the [IGNORES COVER] ability."
    )
    clauses = (
        _stratagem_target_binding_clause(rule_id, normalized_text),
        _weapon_ability_clause(
            clause_id=f"{rule_id}:effect:001",
            normalized_text=normalized_text,
            source_text=normalized_text.split("\n", maxsplit=1)[1],
            effect_text=(
                "ranged weapons equipped by models in your unit have the [IGNORES COVER] ability"
            ),
            weapon_ability="Ignores Cover",
            duration=_end_phase_duration(normalized_text),
        ),
    )
    return _payload(rule_id, source_id, normalized_text, clauses, _stratagem_parser_version())


def _speshul_shells_payload(*, rule_id: str, source_id: str) -> RuleIRPayload:
    normalized_text = (
        "stratagem_activation_target_binding\n"
        "Until the end of the phase, each time a model in your unit makes a ranged "
        "attack that targets the closest eligible target within 18 inches, improve "
        "the Armour Penetration characteristic of ranged weapons equipped by models "
        "in your unit by 1."
    )
    clauses = (
        _stratagem_target_binding_clause(rule_id, normalized_text),
        _effect_clause(
            clause_id=f"{rule_id}:effect:001",
            template_id=CHARACTERISTIC_MODIFIER_TEMPLATE_ID,
            normalized_text=normalized_text,
            source_text=normalized_text.split("\n", maxsplit=1)[1],
            trigger=_dice_roll_trigger(
                normalized_text,
                "each time a model in your unit makes a ranged attack",
                roll_type="attack",
            ),
            target=None,
            effects=(
                _effect(
                    "modify_characteristic",
                    normalized_text,
                    "improve the Armour Penetration characteristic",
                    (
                        _parameter("characteristic", "armor_penetration"),
                        _parameter("delta", 1),
                        _parameter("weapon_scope", "ranged"),
                        _parameter("attack_role", "attacker"),
                        _parameter(
                            "target_constraint",
                            "closest_eligible_target_within_18",
                        ),
                    ),
                ),
            ),
            duration=_end_phase_duration(normalized_text),
        ),
    )
    return _payload(rule_id, source_id, normalized_text, clauses, _stratagem_parser_version())


def _call_dat_dakka_payload(*, rule_id: str, source_id: str) -> RuleIRPayload:
    normalized_text = (
        "stratagem_activation_target_binding\n"
        "Your unit can shoot as if it were your Shooting phase, but must target only "
        "that enemy unit when doing so, and can only do so if that enemy unit is an "
        "eligible target."
    )
    clauses = (
        _stratagem_target_binding_clause(rule_id, normalized_text),
        _effect_clause(
            clause_id=f"{rule_id}:effect:001",
            template_id=GRANT_ABILITY_TEMPLATE_ID,
            normalized_text=normalized_text,
            source_text=normalized_text.split("\n", maxsplit=1)[1],
            trigger=None,
            target=None,
            effects=(
                _effect(
                    "grant_ability",
                    normalized_text,
                    "Your unit can shoot as if it were your Shooting phase",
                    (
                        _parameter("ability", "out_of_phase_shoot"),
                        _parameter("allowed_target_context", "just_shot_unit"),
                    ),
                ),
            ),
            duration=None,
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
    source_row_id = f"stratagem:orks:more-dakka:{stratagem_id}"
    rule_id = f"{SOURCE_PACKAGE_ID}:phase17e:{source_row_id}:source-text"
    source_id = rule_id
    return _stratagem_payload_by_id(stratagem_id, rule_id=rule_id, source_id=source_id)


def _stratagem_activation_payload(profile_id: str) -> RuleIRPayload:
    stratagem_id = profile_id.rsplit(":", maxsplit=1)[-1]
    source_id = f"{STRATAGEM_SOURCE_PACKAGE_ID}:stratagem:orks:more-dakka:{stratagem_id}"
    return _stratagem_payload_by_id(stratagem_id, rule_id=profile_id, source_id=source_id)


def _stratagem_payload_by_id(
    stratagem_id: str,
    *,
    rule_id: str,
    source_id: str,
) -> RuleIRPayload:
    if stratagem_id == "000009992002":
        return _orks_is_still_orks_payload(rule_id=rule_id, source_id=source_id)
    if stratagem_id == "000009992003":
        return _get_stuck_in_payload(rule_id=rule_id, source_id=source_id)
    if stratagem_id == "000009992004":
        return _huge_show_offs_payload(rule_id=rule_id, source_id=source_id)
    if stratagem_id == "000009992005":
        return _long_uncontrolled_bursts_payload(rule_id=rule_id, source_id=source_id)
    if stratagem_id == "000009992006":
        return _speshul_shells_payload(rule_id=rule_id, source_id=source_id)
    if stratagem_id == "000009992007":
        return _call_dat_dakka_payload(rule_id=rule_id, source_id=source_id)
    raise MoreDakkaIrSupportError("Unsupported More Dakka Stratagem id.")


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
    trigger: RuleTriggerPayload | None,
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
            "trigger": trigger,
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


def _weapon_ability_clause(
    *,
    clause_id: str,
    normalized_text: str,
    source_text: str,
    effect_text: str,
    weapon_ability: str,
    weapon_ability_value: int | None = None,
    duration: RuleDurationPayload | None = None,
    extra_parameters: tuple[RuleParameterPayload, ...] = (),
) -> RuleClausePayload:
    parameters = [
        _parameter("weapon_ability", weapon_ability),
        _parameter("weapon_scope", "ranged"),
        *extra_parameters,
    ]
    if weapon_ability_value is not None:
        parameters.insert(1, _parameter("weapon_ability_value", weapon_ability_value))
    return _effect_clause(
        clause_id=clause_id,
        template_id=WEAPON_ABILITY_GRANT_TEMPLATE_ID,
        normalized_text=normalized_text,
        source_text=source_text,
        trigger=None,
        target=None,
        effects=(
            _effect(
                "grant_weapon_ability",
                normalized_text,
                effect_text,
                tuple(parameters),
            ),
        ),
        duration=duration,
    )


def _move_modifier_clause(
    *,
    rule_id: str,
    clause_suffix: str,
    normalized_text: str,
    source_text: str,
    delta: int,
    duration: RuleDurationPayload,
) -> RuleClausePayload:
    return _effect_clause(
        clause_id=f"{rule_id}:{clause_suffix}",
        template_id=MOVEMENT_DISTANCE_TEMPLATE_ID,
        normalized_text=normalized_text,
        source_text=source_text,
        trigger=None,
        target=None,
        effects=(
            _effect(
                "modify_move_distance",
                normalized_text,
                source_text,
                (_parameter("delta", delta),),
            ),
        ),
        duration=duration,
    )


def _characteristic_modifier_clause(
    *,
    rule_id: str,
    clause_suffix: str,
    normalized_text: str,
    source_text: str,
    characteristic: str,
    delta: int,
    duration: RuleDurationPayload,
) -> RuleClausePayload:
    return _effect_clause(
        clause_id=f"{rule_id}:{clause_suffix}",
        template_id=CHARACTERISTIC_MODIFIER_TEMPLATE_ID,
        normalized_text=normalized_text,
        source_text=source_text,
        trigger=None,
        target=None,
        effects=(
            _effect(
                "modify_characteristic",
                normalized_text,
                source_text,
                (
                    _parameter("characteristic", characteristic),
                    _parameter("delta", delta),
                ),
            ),
        ),
        duration=duration,
    )


def _dice_roll_modifier_clause(
    *,
    rule_id: str,
    clause_suffix: str,
    normalized_text: str,
    source_text: str,
    effect_text: str,
    roll_type: str,
    delta: int,
    duration: RuleDurationPayload,
    extra_parameters: tuple[RuleParameterPayload, ...] = (),
) -> RuleClausePayload:
    return _effect_clause(
        clause_id=f"{rule_id}:{clause_suffix}",
        template_id=DICE_ROLL_MODIFIER_TEMPLATE_ID,
        normalized_text=normalized_text,
        source_text=source_text,
        trigger=_dice_roll_trigger(normalized_text, source_text, roll_type=roll_type),
        target=None,
        effects=(
            _effect(
                "modify_dice_roll",
                normalized_text,
                effect_text,
                (
                    _parameter("delta", delta),
                    _parameter("roll_type", roll_type),
                    *extra_parameters,
                ),
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


def _dice_roll_trigger(
    normalized_text: str,
    source_text: str,
    *,
    roll_type: str,
) -> RuleTriggerPayload:
    return cast(
        RuleTriggerPayload,
        {
            "kind": "dice_roll",
            "source_span": _span(normalized_text, source_text),
            "parameters": [_parameter("roll_type", roll_type)],
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


def _until_next_command_start_duration(normalized_text: str) -> RuleDurationPayload:
    return cast(
        RuleDurationPayload,
        {
            "kind": "until_timing_endpoint",
            "source_span": _span(
                normalized_text,
                "Until the start of your next Command phase",
            ),
            "parameters": [
                _parameter("endpoint", "phase"),
                _parameter("relative", "next"),
                _parameter("phase", "command"),
                _parameter("boundary", "start"),
                _parameter("owner", "self"),
            ],
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
        MORE_DAKKA_DETACHMENT_RULE_DESCRIPTOR_ID: _detachment_rule_payload(),
        MORE_DAKKA_ENHANCEMENT_DESCRIPTOR_IDS[0]: _da_gobshot_payload(),
    }
    for descriptor_id in MORE_DAKKA_STRATAGEM_DESCRIPTOR_IDS:
        stratagem_id = descriptor_id.rsplit(":", maxsplit=1)[-1]
        payloads[descriptor_id] = _stratagem_coverage_payload(stratagem_id)
    return MappingProxyType(payloads)


def _stratagem_activation_payloads() -> Mapping[str, RuleIRPayload]:
    return MappingProxyType(
        {
            profile_id: _stratagem_activation_payload(profile_id)
            for profile_id in MORE_DAKKA_STRATAGEM_PROFILE_IDS
        }
    )


_COVERAGE_RULE_IR_PAYLOADS_BY_DESCRIPTOR_ID = _coverage_payloads()
_STRATAGEM_ACTIVATION_RULE_IR_PAYLOADS_BY_PROFILE_ID = _stratagem_activation_payloads()
