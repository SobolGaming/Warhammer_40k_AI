from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import cast

from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleClausePayload,
    RuleDurationPayload,
    RuleEffectSpecPayload,
    RuleIR,
    RuleIRPayload,
    RuleParameterPayload,
    RuleTargetSpecPayload,
)
from warhammer40k_core.rules.rule_templates import (
    CHARACTERISTIC_MODIFIER_TEMPLATE_ID,
    CONTEXTUAL_STATUS_TEMPLATE_ID,
    GRANT_ABILITY_TEMPLATE_ID,
    PLACEMENT_TEMPLATE_ID,
    REROLL_PERMISSION_TEMPLATE_ID,
)

SOURCE_PACKAGE_ID = "gw-11e-phase17e-faction-coverage-2026-27"
STRATAGEM_TARGET_BINDING_TEMPLATE_ID = "phase17s:stratagem-activation-target-binding"

DAEMONIC_INCURSION_DETACHMENT_RULE_DESCRIPTOR_ID = "phase17e:chaos-daemons:daemonic-incursion:rule"
DAEMONIC_INCURSION_SOURCE_RULE_ID = "phase17f:phase17e:chaos-daemons:daemonic-incursion:rule"
DAEMONIC_INCURSION_DETACHMENT_ID = "daemonic-incursion"
CHAOS_DAEMONS_FACTION_ID = "chaos-daemons"

LEGIONES_DAEMONICA_KEYWORD = "LEGIONES DAEMONICA"
WARP_RIFTS_PLACEMENT_KIND = "deep_strike"
WARP_RIFTS_HOOK_FAMILY = "reserve_arrival_distance"
WARP_RIFTS_CONDITION_FAMILY = "shadow_of_chaos_or_matching_greater_daemon_anchor"
WARP_RIFTS_ENEMY_DISTANCE_INCHES = 6.0
WARP_RIFTS_HOOK_ID = "warhammer_40000_11th:chaos_daemons:detachment:daemonic_incursion:warp_rifts"
WARP_RIFTS_DEEP_STRIKE_DISTANCE_ABILITY = (
    "chaos-daemons:daemonic-incursion:warp-rifts:deep-strike-distance"
)

CORRUPTED_REALSPACE_STICKY_EFFECT_KIND = "chaos_daemons_corrupted_realspace_objective"
CORRUPTED_REALSPACE_SHADOW_AURA_INCHES = 6.0
DENIZENS_OF_THE_WARP_ENEMY_DISTANCE_INCHES = 6.0
DENIZENS_OF_THE_WARP_HOOK_ID = (
    "warhammer_40000_11th:chaos_daemons:detachment:daemonic_incursion:denizens_of_the_warp"
)
DENIZENS_OF_THE_WARP_DEEP_STRIKE_DISTANCE_ABILITY = (
    "chaos-daemons:daemonic-incursion:denizens-of-the-warp:deep-strike-distance"
)

CORRUPT_REALSPACE_STRATAGEM_ID = "000008437002"
WARP_SURGE_STRATAGEM_ID = "000008437003"
DRAUGHT_OF_TERROR_STRATAGEM_ID = "000008437004"
DENIZENS_OF_THE_WARP_STRATAGEM_ID = "000008437005"
THE_REALM_OF_CHAOS_STRATAGEM_ID = "000008437006"
DAEMONIC_INVULNERABILITY_STRATAGEM_ID = "000008437007"

CORRUPT_REALSPACE_SOURCE_ROW_ID = (
    f"stratagem:chaos-daemons:daemonic-incursion:{CORRUPT_REALSPACE_STRATAGEM_ID}"
)
WARP_SURGE_SOURCE_ROW_ID = f"stratagem:chaos-daemons:daemonic-incursion:{WARP_SURGE_STRATAGEM_ID}"
DRAUGHT_OF_TERROR_SOURCE_ROW_ID = (
    f"stratagem:chaos-daemons:daemonic-incursion:{DRAUGHT_OF_TERROR_STRATAGEM_ID}"
)
DENIZENS_OF_THE_WARP_SOURCE_ROW_ID = (
    f"stratagem:chaos-daemons:daemonic-incursion:{DENIZENS_OF_THE_WARP_STRATAGEM_ID}"
)
THE_REALM_OF_CHAOS_SOURCE_ROW_ID = (
    f"stratagem:chaos-daemons:daemonic-incursion:{THE_REALM_OF_CHAOS_STRATAGEM_ID}"
)
DAEMONIC_INVULNERABILITY_SOURCE_ROW_ID = (
    f"stratagem:chaos-daemons:daemonic-incursion:{DAEMONIC_INVULNERABILITY_STRATAGEM_ID}"
)

DAEMONIC_INCURSION_STRATAGEM_SOURCE_ROW_IDS = (
    CORRUPT_REALSPACE_SOURCE_ROW_ID,
    WARP_SURGE_SOURCE_ROW_ID,
    DRAUGHT_OF_TERROR_SOURCE_ROW_ID,
    DENIZENS_OF_THE_WARP_SOURCE_ROW_ID,
    THE_REALM_OF_CHAOS_SOURCE_ROW_ID,
    DAEMONIC_INVULNERABILITY_SOURCE_ROW_ID,
)

CORRUPT_REALSPACE_DESCRIPTOR_ID = f"phase17e:{CORRUPT_REALSPACE_SOURCE_ROW_ID}"
WARP_SURGE_DESCRIPTOR_ID = f"phase17e:{WARP_SURGE_SOURCE_ROW_ID}"
DRAUGHT_OF_TERROR_DESCRIPTOR_ID = f"phase17e:{DRAUGHT_OF_TERROR_SOURCE_ROW_ID}"
DENIZENS_OF_THE_WARP_DESCRIPTOR_ID = f"phase17e:{DENIZENS_OF_THE_WARP_SOURCE_ROW_ID}"
THE_REALM_OF_CHAOS_DESCRIPTOR_ID = f"phase17e:{THE_REALM_OF_CHAOS_SOURCE_ROW_ID}"
DAEMONIC_INVULNERABILITY_DESCRIPTOR_ID = f"phase17e:{DAEMONIC_INVULNERABILITY_SOURCE_ROW_ID}"

CORRUPT_REALSPACE_SOURCE_RULE_ID = f"phase17f:phase17e:{CORRUPT_REALSPACE_SOURCE_ROW_ID}"
WARP_SURGE_SOURCE_RULE_ID = f"phase17f:phase17e:{WARP_SURGE_SOURCE_ROW_ID}"
DRAUGHT_OF_TERROR_SOURCE_RULE_ID = f"phase17f:phase17e:{DRAUGHT_OF_TERROR_SOURCE_ROW_ID}"
DENIZENS_OF_THE_WARP_SOURCE_RULE_ID = f"phase17f:phase17e:{DENIZENS_OF_THE_WARP_SOURCE_ROW_ID}"
THE_REALM_OF_CHAOS_SOURCE_RULE_ID = f"phase17f:phase17e:{THE_REALM_OF_CHAOS_SOURCE_ROW_ID}"
DAEMONIC_INVULNERABILITY_SOURCE_RULE_ID = (
    f"phase17f:phase17e:{DAEMONIC_INVULNERABILITY_SOURCE_ROW_ID}"
)


class DaemonicIncursionIrSupportError(ValueError):
    """Raised when static Daemonic Incursion RuleIR support metadata is inconsistent."""


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


def _detachment_rule_payload() -> RuleIRPayload:
    source_row_id = "chaos-daemons:daemonic-incursion:rule"
    source_text = (
        "LEGIONES DAEMONICA Deep Strike units can be set up more than 6 inches "
        "horizontally away from enemy models if wholly within Shadow of Chaos or wholly "
        "within 6 inches of a matching named Greater Daemon anchor."
    )
    normalized_text = source_text
    return _coverage_payload(
        source_row_id,
        normalized_text,
        (
            _ability_clause(
                clause_id=_coverage_clause_id(source_row_id, "effect:001"),
                normalized_text=normalized_text,
                source_text=source_text,
                effect_text="can be set up more than 6 inches horizontally away from enemy models",
                ability=WARP_RIFTS_DEEP_STRIKE_DISTANCE_ABILITY,
                extra_parameters=(
                    _parameter("hook_family", WARP_RIFTS_HOOK_FAMILY),
                    _parameter("placement_kind", WARP_RIFTS_PLACEMENT_KIND),
                    _parameter(
                        "enemy_horizontal_distance_inches",
                        WARP_RIFTS_ENEMY_DISTANCE_INCHES,
                    ),
                    _parameter("required_faction_keyword", LEGIONES_DAEMONICA_KEYWORD),
                    _parameter("condition_family", WARP_RIFTS_CONDITION_FAMILY),
                ),
                duration=_permanent_duration(normalized_text),
            ),
        ),
    )


def _corrupt_realspace_payload() -> RuleIRPayload:
    normalized_text = (
        "stratagem_activation_target_binding\n"
        "The selected objective marker is Corrupted and remains under your control, "
        "even if you have no models within range of it, until your opponent controls "
        "it at the start or end of any turn. While that objective marker is Corrupted "
        "and under your control, the area within 6 inches of it is within your army's "
        "Shadow of Chaos."
    )
    return _stratagem_payload(
        CORRUPT_REALSPACE_SOURCE_ROW_ID,
        normalized_text,
        (
            _stratagem_target_binding_clause(CORRUPT_REALSPACE_SOURCE_ROW_ID, normalized_text),
            _contextual_status_clause(
                clause_id=_stratagem_clause_id(CORRUPT_REALSPACE_SOURCE_ROW_ID, "effect:001"),
                normalized_text=normalized_text,
                source_text="The selected objective marker is Corrupted",
                effect_text="selected objective marker is Corrupted",
                status="sticky_objective_control",
                extra_parameters=(
                    _parameter("objective_selection", "selected_controlled_objective_marker"),
                    _parameter("sticky_effect_kind", CORRUPTED_REALSPACE_STICKY_EFFECT_KIND),
                    _parameter(
                        "shadow_of_chaos_aura_inches",
                        CORRUPTED_REALSPACE_SHADOW_AURA_INCHES,
                    ),
                ),
                duration=None,
            ),
        ),
    )


def _warp_surge_payload() -> RuleIRPayload:
    normalized_text = (
        "stratagem_activation_target_binding\n"
        "Until the end of the phase, your unit is eligible to declare a charge in a "
        "turn in which it Advanced."
    )
    return _stratagem_payload(
        WARP_SURGE_SOURCE_ROW_ID,
        normalized_text,
        (
            _stratagem_target_binding_clause(WARP_SURGE_SOURCE_ROW_ID, normalized_text),
            _ability_clause(
                clause_id=_stratagem_clause_id(WARP_SURGE_SOURCE_ROW_ID, "effect:001"),
                normalized_text=normalized_text,
                source_text=(
                    "Until the end of the phase, your unit is eligible to declare a charge "
                    "in a turn in which it Advanced."
                ),
                effect_text="eligible to declare a charge in a turn in which it Advanced",
                ability="can_advance_and_charge",
                extra_parameters=(_parameter("source_effect_kind", "warp_surge"),),
                duration=_end_phase_duration(normalized_text),
            ),
        ),
    )


def _draught_of_terror_payload() -> RuleIRPayload:
    normalized_text = (
        "stratagem_activation_target_binding\n"
        "Until the end of the phase, improve the Armour Penetration characteristic of "
        "weapons equipped by models in that unit by 1. Until the end of the phase, "
        "each time such a weapon targets a unit that is Battle-shocked, you can re-roll "
        "the Wound roll."
    )
    return _stratagem_payload(
        DRAUGHT_OF_TERROR_SOURCE_ROW_ID,
        normalized_text,
        (
            _stratagem_target_binding_clause(DRAUGHT_OF_TERROR_SOURCE_ROW_ID, normalized_text),
            _characteristic_modifier_clause(
                clause_id=_stratagem_clause_id(DRAUGHT_OF_TERROR_SOURCE_ROW_ID, "effect:001"),
                normalized_text=normalized_text,
                source_text="improve the Armour Penetration characteristic",
                effect_text="Armour Penetration characteristic",
                characteristic="armor_penetration",
                delta=-1,
                extra_parameters=(
                    _parameter("attack_role", "attacker"),
                    _parameter("weapon_scope", "all"),
                ),
                duration=_end_phase_duration(normalized_text),
            ),
            _reroll_permission_clause(
                clause_id=_stratagem_clause_id(DRAUGHT_OF_TERROR_SOURCE_ROW_ID, "effect:002"),
                normalized_text=normalized_text,
                source_text="re-roll the Wound roll",
                effect_text="re-roll the Wound roll",
                roll_type="attack_sequence.wound",
                extra_parameters=(
                    _parameter("timing_window", "attack_sequence.wound"),
                    _parameter("attack_role", "attacker"),
                    _parameter("full_reroll_if_target_battle_shocked", True),
                ),
                duration=_end_phase_duration(normalized_text),
            ),
        ),
    )


def _denizens_of_the_warp_payload() -> RuleIRPayload:
    normalized_text = (
        "stratagem_activation_target_binding\n"
        "Until the end of the phase, your unit can be set up anywhere on the battlefield "
        'that is more than 6" horizontally away from all enemy models.'
    )
    return _stratagem_payload(
        DENIZENS_OF_THE_WARP_SOURCE_ROW_ID,
        normalized_text,
        (
            _stratagem_target_binding_clause(DENIZENS_OF_THE_WARP_SOURCE_ROW_ID, normalized_text),
            _ability_clause(
                clause_id=_stratagem_clause_id(DENIZENS_OF_THE_WARP_SOURCE_ROW_ID, "effect:001"),
                normalized_text=normalized_text,
                source_text='more than 6" horizontally away from all enemy models',
                effect_text='more than 6" horizontally away from all enemy models',
                ability=DENIZENS_OF_THE_WARP_DEEP_STRIKE_DISTANCE_ABILITY,
                extra_parameters=(
                    _parameter("hook_family", WARP_RIFTS_HOOK_FAMILY),
                    _parameter("placement_kind", WARP_RIFTS_PLACEMENT_KIND),
                    _parameter(
                        "enemy_horizontal_distance_inches",
                        DENIZENS_OF_THE_WARP_ENEMY_DISTANCE_INCHES,
                    ),
                    _parameter("required_faction_keyword", LEGIONES_DAEMONICA_KEYWORD),
                    _parameter("source_effect_kind", "denizens_of_the_warp"),
                ),
                duration=_end_phase_duration(normalized_text),
            ),
        ),
    )


def _the_realm_of_chaos_payload() -> RuleIRPayload:
    normalized_text = (
        "stratagem_activation_target_binding\n"
        "Remove the targeted units from the battlefield and place them into Strategic "
        "Reserves. They will arrive back on the battlefield in the Reinforcements step "
        "of your next Movement phase using the Deep Strike ability."
    )
    return _stratagem_payload(
        THE_REALM_OF_CHAOS_SOURCE_ROW_ID,
        normalized_text,
        (
            _stratagem_target_binding_clause(THE_REALM_OF_CHAOS_SOURCE_ROW_ID, normalized_text),
            _placement_permission_clause(
                clause_id=_stratagem_clause_id(THE_REALM_OF_CHAOS_SOURCE_ROW_ID, "effect:001"),
                normalized_text=normalized_text,
                source_text="place them into Strategic Reserves",
                effect_text="Strategic Reserves",
                extra_parameters=(
                    _parameter("placement_kind", "strategic_reserves"),
                    _parameter("operation", "remove_to_reserves"),
                    _parameter("reserve_origin", "during_battle_stratagem"),
                    _parameter("required_arrival_battle_round_offset", 1),
                    _parameter("required_arrival_phase", "movement"),
                    _parameter(
                        "required_arrival_source_rule_id", THE_REALM_OF_CHAOS_SOURCE_RULE_ID
                    ),
                    _parameter("required_arrival_placement_kind", "deep_strike"),
                ),
                duration=None,
            ),
        ),
    )


def _daemonic_invulnerability_payload() -> RuleIRPayload:
    normalized_text = (
        "stratagem_activation_target_binding\n"
        "Until the end of the phase, each time an invulnerable saving throw is made for "
        "a model in your unit, re-roll a saving throw of 1."
    )
    return _stratagem_payload(
        DAEMONIC_INVULNERABILITY_SOURCE_ROW_ID,
        normalized_text,
        (
            _stratagem_target_binding_clause(
                DAEMONIC_INVULNERABILITY_SOURCE_ROW_ID,
                normalized_text,
            ),
            _reroll_permission_clause(
                clause_id=_stratagem_clause_id(
                    DAEMONIC_INVULNERABILITY_SOURCE_ROW_ID,
                    "effect:001",
                ),
                normalized_text=normalized_text,
                source_text="re-roll a saving throw of 1",
                effect_text="re-roll a saving throw of 1",
                roll_type="attack_sequence.save.invulnerable",
                extra_parameters=(
                    _parameter("timing_window", "attack_sequence.save.invulnerable"),
                    _parameter("attack_role", "target"),
                    _parameter("reroll_unmodified_value", 1),
                ),
                duration=_end_phase_duration(normalized_text),
            ),
        ),
    )


def _coverage_payload(
    source_row_id: str,
    normalized_text: str,
    clauses: tuple[RuleClausePayload, ...],
) -> RuleIRPayload:
    source_id = _coverage_rule_id(source_row_id)
    return _payload(
        rule_id=source_id,
        source_id=source_id,
        normalized_text=normalized_text,
        clauses=clauses,
        parser_version="phase17c-rule-parser-v1",
    )


def _stratagem_payload(
    source_row_id: str,
    normalized_text: str,
    clauses: tuple[RuleClausePayload, ...],
) -> RuleIRPayload:
    source_id = _coverage_rule_id(source_row_id)
    return _payload(
        rule_id=source_id,
        source_id=source_id,
        normalized_text=normalized_text,
        clauses=clauses,
        parser_version="phase17s-stratagem-activation-static-rule-ir-v1",
    )


def _payload(
    *,
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


def _stratagem_target_binding_clause(
    source_row_id: str,
    normalized_text: str,
) -> RuleClausePayload:
    return cast(
        RuleClausePayload,
        {
            "clause_id": _stratagem_clause_id(source_row_id, "target-binding"),
            "template_id": STRATAGEM_TARGET_BINDING_TEMPLATE_ID,
            "source_span": _span(normalized_text, "stratagem_activation_target_binding"),
            "trigger": None,
            "conditions": [],
            "target": _target(
                "friendly_unit", normalized_text, "stratagem_activation_target_binding"
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
    normalized_text: str,
    source_text: str,
    effect_text: str,
    ability: str,
    extra_parameters: tuple[RuleParameterPayload, ...],
    duration: RuleDurationPayload | None,
) -> RuleClausePayload:
    return _effect_clause(
        clause_id=clause_id,
        template_id=GRANT_ABILITY_TEMPLATE_ID,
        normalized_text=normalized_text,
        source_text=source_text,
        effect_kind="grant_ability",
        effect_text=effect_text,
        parameters=(_parameter("ability", ability), *extra_parameters),
        duration=duration,
    )


def _contextual_status_clause(
    *,
    clause_id: str,
    normalized_text: str,
    source_text: str,
    effect_text: str,
    status: str,
    extra_parameters: tuple[RuleParameterPayload, ...],
    duration: RuleDurationPayload | None,
) -> RuleClausePayload:
    return _effect_clause(
        clause_id=clause_id,
        template_id=CONTEXTUAL_STATUS_TEMPLATE_ID,
        normalized_text=normalized_text,
        source_text=source_text,
        effect_kind="set_contextual_status",
        effect_text=effect_text,
        parameters=(_parameter("status", status), *extra_parameters),
        duration=duration,
    )


def _characteristic_modifier_clause(
    *,
    clause_id: str,
    normalized_text: str,
    source_text: str,
    effect_text: str,
    characteristic: str,
    delta: int,
    extra_parameters: tuple[RuleParameterPayload, ...],
    duration: RuleDurationPayload | None,
) -> RuleClausePayload:
    return _effect_clause(
        clause_id=clause_id,
        template_id=CHARACTERISTIC_MODIFIER_TEMPLATE_ID,
        normalized_text=normalized_text,
        source_text=source_text,
        effect_kind="modify_characteristic",
        effect_text=effect_text,
        parameters=(
            _parameter("characteristic", characteristic),
            _parameter("delta", delta),
            *extra_parameters,
        ),
        duration=duration,
    )


def _placement_permission_clause(
    *,
    clause_id: str,
    normalized_text: str,
    source_text: str,
    effect_text: str,
    extra_parameters: tuple[RuleParameterPayload, ...],
    duration: RuleDurationPayload | None,
) -> RuleClausePayload:
    return _effect_clause(
        clause_id=clause_id,
        template_id=PLACEMENT_TEMPLATE_ID,
        normalized_text=normalized_text,
        source_text=source_text,
        effect_kind="placement_permission",
        effect_text=effect_text,
        parameters=extra_parameters,
        duration=duration,
    )


def _reroll_permission_clause(
    *,
    clause_id: str,
    normalized_text: str,
    source_text: str,
    effect_text: str,
    roll_type: str,
    extra_parameters: tuple[RuleParameterPayload, ...],
    duration: RuleDurationPayload | None,
) -> RuleClausePayload:
    return _effect_clause(
        clause_id=clause_id,
        template_id=REROLL_PERMISSION_TEMPLATE_ID,
        normalized_text=normalized_text,
        source_text=source_text,
        effect_kind="reroll_permission",
        effect_text=effect_text,
        parameters=(_parameter("roll_type", roll_type), *extra_parameters),
        duration=duration,
    )


def _effect_clause(
    *,
    clause_id: str,
    template_id: str,
    normalized_text: str,
    source_text: str,
    effect_kind: str,
    effect_text: str,
    parameters: tuple[RuleParameterPayload, ...],
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
            "target": None,
            "effects": [_effect(effect_kind, normalized_text, effect_text, parameters)],
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


def _end_phase_duration(normalized_text: str) -> RuleDurationPayload:
    return cast(
        RuleDurationPayload,
        {
            "kind": "until_timing_endpoint",
            "source_span": _span(normalized_text, "Until the end of the phase"),
            "parameters": [_parameter("endpoint", "phase")],
        },
    )


def _parameter(key: str, value: object) -> RuleParameterPayload:
    return cast(RuleParameterPayload, {"key": key, "value": value})


def _span(normalized_text: str, source_text: str) -> dict[str, str | int]:
    start = normalized_text.index(source_text)
    return {"text": source_text, "start": start, "end": start + len(source_text)}


def _coverage_rule_id(source_row_id: str) -> str:
    return f"{SOURCE_PACKAGE_ID}:phase17e:{source_row_id}:source-text"


def _coverage_clause_id(source_row_id: str, suffix: str) -> str:
    return f"{_coverage_rule_id(source_row_id)}:{suffix}"


def _stratagem_clause_id(source_row_id: str, suffix: str) -> str:
    return f"{_coverage_rule_id(source_row_id)}:{suffix}"


def _coverage_payloads() -> Mapping[str, RuleIRPayload]:
    return MappingProxyType(
        {
            DAEMONIC_INCURSION_DETACHMENT_RULE_DESCRIPTOR_ID: _detachment_rule_payload(),
            CORRUPT_REALSPACE_DESCRIPTOR_ID: _corrupt_realspace_payload(),
            WARP_SURGE_DESCRIPTOR_ID: _warp_surge_payload(),
            DRAUGHT_OF_TERROR_DESCRIPTOR_ID: _draught_of_terror_payload(),
            DENIZENS_OF_THE_WARP_DESCRIPTOR_ID: _denizens_of_the_warp_payload(),
            THE_REALM_OF_CHAOS_DESCRIPTOR_ID: _the_realm_of_chaos_payload(),
            DAEMONIC_INVULNERABILITY_DESCRIPTOR_ID: _daemonic_invulnerability_payload(),
        }
    )


_COVERAGE_RULE_IR_PAYLOADS_BY_DESCRIPTOR_ID = _coverage_payloads()
