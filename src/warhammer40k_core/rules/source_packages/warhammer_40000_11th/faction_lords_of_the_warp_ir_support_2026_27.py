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
    CHARACTERISTIC_MODIFIER_TEMPLATE_ID,
    GRANT_ABILITY_TEMPLATE_ID,
    KEYWORD_GATE_TEMPLATE_ID,
    WEAPON_ABILITY_GRANT_TEMPLATE_ID,
)

SOURCE_PACKAGE_ID = "gw-11e-phase17e-faction-coverage-2026-27"
STRATAGEM_TARGET_BINDING_TEMPLATE_ID = "phase17s:stratagem-activation-target-binding"

CHAOS_DAEMONS_FACTION_ID = "chaos-daemons"
LORDS_OF_THE_WARP_DETACHMENT_ID = "lords-of-the-warp"
LORDS_OF_THE_WARP_DETACHMENT_RULE_DESCRIPTOR_ID = "phase17e:chaos-daemons:lords-of-the-warp:rule"
LORDS_OF_THE_WARP_SOURCE_RULE_ID = "phase17f:phase17e:chaos-daemons:lords-of-the-warp:rule"

LEGIONES_DAEMONICA_KEYWORD = "LEGIONES DAEMONICA"
CHARACTER_KEYWORD = "CHARACTER"
MONSTER_KEYWORD = "MONSTER"
KHORNE_KEYWORD = "KHORNE"
NURGLE_KEYWORD = "NURGLE"
SLAANESH_KEYWORD = "SLAANESH"
TZEENTCH_KEYWORD = "TZEENTCH"

FIGHTS_FIRST_ABILITY = "fights_first"
LETHAL_HITS_WEAPON_ABILITY = "Lethal Hits"

SWOLLEN_WITH_POWER_ENHANCEMENT_ID = "chaos-daemons:lords-of-the-warp:swollen-with-power-upgrade"
SWOLLEN_WITH_POWER_SOURCE_ROW_ID = (
    "enhancement:chaos-daemons:lords-of-the-warp:"
    "chaos-daemons:lords-of-the-warp:swollen-with-power-upgrade"
)
SWOLLEN_WITH_POWER_DESCRIPTOR_ID = f"phase17e:{SWOLLEN_WITH_POWER_SOURCE_ROW_ID}"
SWOLLEN_WITH_POWER_SOURCE_RULE_ID = f"phase17f:phase17e:{SWOLLEN_WITH_POWER_SOURCE_ROW_ID}"

CARNIVAL_OF_EXCESS_STRATAGEM_ID = "chaos-daemons:lords-of-the-warp:carnival-of-excess"
CALL_TO_MURDER_STRATAGEM_ID = "chaos-daemons:lords-of-the-warp:call-to-murder"
BILIOUS_BLESSING_STRATAGEM_ID = "chaos-daemons:lords-of-the-warp:bilious-blessing"
SKIRLING_MAGICKS_STRATAGEM_ID = "chaos-daemons:lords-of-the-warp:skirling-magicks"

CARNIVAL_OF_EXCESS_SOURCE_ROW_ID = (
    f"stratagem:chaos-daemons:lords-of-the-warp:{CARNIVAL_OF_EXCESS_STRATAGEM_ID}"
)
CALL_TO_MURDER_SOURCE_ROW_ID = (
    f"stratagem:chaos-daemons:lords-of-the-warp:{CALL_TO_MURDER_STRATAGEM_ID}"
)
BILIOUS_BLESSING_SOURCE_ROW_ID = (
    f"stratagem:chaos-daemons:lords-of-the-warp:{BILIOUS_BLESSING_STRATAGEM_ID}"
)
SKIRLING_MAGICKS_SOURCE_ROW_ID = (
    f"stratagem:chaos-daemons:lords-of-the-warp:{SKIRLING_MAGICKS_STRATAGEM_ID}"
)
LORDS_OF_THE_WARP_STRATAGEM_SOURCE_ROW_IDS = (
    CARNIVAL_OF_EXCESS_SOURCE_ROW_ID,
    CALL_TO_MURDER_SOURCE_ROW_ID,
    BILIOUS_BLESSING_SOURCE_ROW_ID,
    SKIRLING_MAGICKS_SOURCE_ROW_ID,
)
CARNIVAL_OF_EXCESS_DESCRIPTOR_ID = f"phase17e:{CARNIVAL_OF_EXCESS_SOURCE_ROW_ID}"
CALL_TO_MURDER_DESCRIPTOR_ID = f"phase17e:{CALL_TO_MURDER_SOURCE_ROW_ID}"
BILIOUS_BLESSING_DESCRIPTOR_ID = f"phase17e:{BILIOUS_BLESSING_SOURCE_ROW_ID}"
SKIRLING_MAGICKS_DESCRIPTOR_ID = f"phase17e:{SKIRLING_MAGICKS_SOURCE_ROW_ID}"

VISIBLE_ENEMY_UNIT_EFFECT_SELECTION_KIND = "visible_enemy_unit"
BILIOUS_BLESSING_RANGE_INCHES = 8
BILIOUS_BLESSING_REPLAY_EFFECT_KIND = "chaos_daemons_lords_of_the_warp_bilious_blessing"


class LordsOfTheWarpIrSupportError(ValueError):
    """Raised when static Lords of the Warp RuleIR support metadata is inconsistent."""


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
    source_row_id = "chaos-daemons:lords-of-the-warp:rule"
    normalized_text = (
        "Friendly Legiones Daemonica Character models, excluding Monster models, "
        "have +1 Leadership and +1 Objective Control."
    )
    return _coverage_payload(
        source_row_id,
        normalized_text,
        (
            _characteristic_modifier_clause(
                clause_id=_coverage_clause_id(source_row_id, "effect:001"),
                normalized_text=normalized_text,
                source_text="+1 Leadership",
                effect_text="+1 Leadership",
                characteristic="leadership",
                delta=-1,
                extra_parameters=_character_daemon_non_monster_parameters(),
                duration=_permanent_duration(normalized_text),
            ),
            _characteristic_modifier_clause(
                clause_id=_coverage_clause_id(source_row_id, "effect:002"),
                normalized_text=normalized_text,
                source_text="+1 Objective Control",
                effect_text="+1 Objective Control",
                characteristic="objective_control",
                delta=1,
                extra_parameters=_character_daemon_non_monster_parameters(),
                duration=_permanent_duration(normalized_text),
            ),
        ),
    )


def _swollen_with_power_payload() -> RuleIRPayload:
    normalized_text = (
        "Legiones Daemonica Character model only, excluding Monster units. "
        "This model has +2 Wounds."
    )
    return _coverage_payload(
        SWOLLEN_WITH_POWER_SOURCE_ROW_ID,
        normalized_text,
        (
            _character_daemon_non_monster_keyword_gate_clause(
                clause_id=_coverage_clause_id(SWOLLEN_WITH_POWER_SOURCE_ROW_ID, "gate:001"),
                normalized_text=normalized_text,
                source_text="Legiones Daemonica Character model only, excluding Monster units",
            ),
            _characteristic_modifier_clause(
                clause_id=_coverage_clause_id(SWOLLEN_WITH_POWER_SOURCE_ROW_ID, "effect:001"),
                normalized_text=normalized_text,
                source_text="This model has +2 Wounds",
                effect_text="+2 Wounds",
                characteristic="wounds",
                delta=2,
                extra_parameters=_character_daemon_non_monster_parameters(),
                duration=None,
            ),
        ),
    )


def _carnival_of_excess_payload() -> RuleIRPayload:
    rule_id = _coverage_rule_id(CARNIVAL_OF_EXCESS_SOURCE_ROW_ID)
    normalized_text = (
        "stratagem_activation_target_binding\n"
        "Your Legiones Daemonica Character Slaanesh unit, excluding Monster units, "
        "has Fights First and must be the next unit selected to fight."
    )
    return _payload(
        rule_id,
        rule_id,
        normalized_text,
        (
            _stratagem_target_binding_clause(rule_id, normalized_text),
            _ability_clause(
                clause_id=f"{rule_id}:effect:001",
                normalized_text=normalized_text,
                source_text="has Fights First",
                effect_text="Fights First",
                ability=FIGHTS_FIRST_ABILITY,
                extra_parameters=_god_character_daemon_non_monster_parameters(SLAANESH_KEYWORD),
                duration=None,
            ),
        ),
        _stratagem_parser_version(),
    )


def _call_to_murder_payload() -> RuleIRPayload:
    rule_id = _coverage_rule_id(CALL_TO_MURDER_SOURCE_ROW_ID)
    normalized_text = (
        "stratagem_activation_target_binding\n"
        "Until the end of the phase, your Legiones Daemonica Character Khorne unit, "
        "excluding Monster units, has +1 Attacks for melee attacks."
    )
    return _payload(
        rule_id,
        rule_id,
        normalized_text,
        (
            _stratagem_target_binding_clause(rule_id, normalized_text),
            _characteristic_modifier_clause(
                clause_id=f"{rule_id}:effect:001",
                normalized_text=normalized_text,
                source_text="+1 Attacks for melee attacks",
                effect_text="+1 Attacks",
                characteristic="attacks",
                delta=1,
                extra_parameters=(
                    _parameter("weapon_scope", "melee"),
                    *_god_character_daemon_non_monster_parameters(KHORNE_KEYWORD),
                ),
                duration=_end_phase_duration(normalized_text),
            ),
        ),
        _stratagem_parser_version(),
    )


def _bilious_blessing_payload() -> RuleIRPayload:
    rule_id = _coverage_rule_id(BILIOUS_BLESSING_SOURCE_ROW_ID)
    normalized_text = (
        "stratagem_activation_target_binding\n"
        "Select one visible enemy unit within 8 inches of your Legiones Daemonica "
        "Character Nurgle unit, excluding Monster units. Roll seven D6; for each 4+, "
        "that enemy unit suffers 1 mortal wound."
    )
    return _payload(
        rule_id,
        rule_id,
        normalized_text,
        (
            _stratagem_target_binding_clause(rule_id, normalized_text),
            _effect_clause(
                clause_id=f"{rule_id}:effect:001",
                template_id=None,
                normalized_text=normalized_text,
                source_text="for each 4+, that enemy unit suffers 1 mortal wound",
                target=None,
                effects=(
                    _effect(
                        "inflict_mortal_wounds",
                        normalized_text,
                        "that enemy unit suffers 1 mortal wound",
                        (
                            _parameter(
                                "effect_selection_kind",
                                VISIBLE_ENEMY_UNIT_EFFECT_SELECTION_KIND,
                            ),
                            _parameter("roll_quantity", 7),
                            _parameter("roll_sides", 6),
                            _parameter("success_threshold", 4),
                            _parameter("mortal_wounds_per_success", 1),
                            _parameter("roll_type", "mortal_wounds"),
                            _parameter("spill_over", True),
                            _parameter("replay_effect_kind", BILIOUS_BLESSING_REPLAY_EFFECT_KIND),
                            *_god_character_daemon_non_monster_parameters(NURGLE_KEYWORD),
                        ),
                    ),
                ),
                duration=None,
            ),
        ),
        _stratagem_parser_version(),
    )


def _skirling_magicks_payload() -> RuleIRPayload:
    rule_id = _coverage_rule_id(SKIRLING_MAGICKS_SOURCE_ROW_ID)
    normalized_text = (
        "stratagem_activation_target_binding\n"
        "Until the end of the phase, your Legiones Daemonica Character Tzeentch unit, "
        "excluding Monster units, ranged attacks have Lethal Hits."
    )
    return _payload(
        rule_id,
        rule_id,
        normalized_text,
        (
            _stratagem_target_binding_clause(rule_id, normalized_text),
            _effect_clause(
                clause_id=f"{rule_id}:effect:001",
                template_id=WEAPON_ABILITY_GRANT_TEMPLATE_ID,
                normalized_text=normalized_text,
                source_text="ranged attacks have Lethal Hits",
                target=_target("this_unit", normalized_text, "ranged attacks have Lethal Hits"),
                effects=(
                    _effect(
                        "grant_weapon_ability",
                        normalized_text,
                        "Lethal Hits",
                        (
                            _parameter("weapon_ability", LETHAL_HITS_WEAPON_ABILITY),
                            _parameter("weapon_scope", "ranged"),
                            *_god_character_daemon_non_monster_parameters(TZEENTCH_KEYWORD),
                        ),
                    ),
                ),
                duration=_end_phase_duration(normalized_text),
            ),
        ),
        _stratagem_parser_version(),
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
        target=_target("this_unit", normalized_text, source_text),
        effects=(
            _effect(
                "modify_characteristic",
                normalized_text,
                effect_text,
                (
                    _parameter("characteristic", characteristic),
                    _parameter("delta", delta),
                    *extra_parameters,
                ),
            ),
        ),
        duration=duration,
    )


def _stratagem_target_binding_clause(rule_id: str, normalized_text: str) -> RuleClausePayload:
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


def _character_daemon_non_monster_keyword_gate_clause(
    *,
    clause_id: str,
    normalized_text: str,
    source_text: str,
) -> RuleClausePayload:
    return cast(
        RuleClausePayload,
        {
            "clause_id": clause_id,
            "template_id": KEYWORD_GATE_TEMPLATE_ID,
            "source_span": _span(normalized_text, source_text),
            "trigger": None,
            "conditions": [
                _keyword_gate_condition(
                    normalized_text=normalized_text,
                    source_text=source_text,
                    parameters=_character_daemon_non_monster_parameters(),
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
    source_text: str,
    parameters: tuple[RuleParameterPayload, ...],
) -> RuleConditionPayload:
    return cast(
        RuleConditionPayload,
        {
            "kind": "keyword_gate",
            "source_span": _span(normalized_text, source_text),
            "parameters": list(parameters),
        },
    )


def _effect_clause(
    *,
    clause_id: str,
    template_id: str | None,
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


def _target(kind: str, normalized_text: str, source_text: str) -> RuleTargetSpecPayload:
    return cast(
        RuleTargetSpecPayload,
        {
            "kind": kind,
            "source_span": _span(normalized_text, source_text),
            "parameters": [],
        },
    )


def _character_daemon_non_monster_parameters() -> tuple[RuleParameterPayload, ...]:
    return (
        _parameter("required_faction_keyword_sequence", (LEGIONES_DAEMONICA_KEYWORD,)),
        _parameter("required_keyword_sequence", (CHARACTER_KEYWORD,)),
        _parameter("excluded_keyword_sequence", (MONSTER_KEYWORD,)),
    )


def _god_character_daemon_non_monster_parameters(
    god_keyword: str,
) -> tuple[RuleParameterPayload, ...]:
    return (
        _parameter("required_faction_keyword_sequence", (LEGIONES_DAEMONICA_KEYWORD,)),
        _parameter("required_keyword_sequence", (CHARACTER_KEYWORD, god_keyword)),
        _parameter("excluded_keyword_sequence", (MONSTER_KEYWORD,)),
    )


def _coverage_payload(
    source_row_id: str,
    normalized_text: str,
    clauses: tuple[RuleClausePayload, ...],
) -> RuleIRPayload:
    source_id = _coverage_rule_id(source_row_id)
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


def _coverage_rule_id(source_row_id: str) -> str:
    return f"{SOURCE_PACKAGE_ID}:phase17e:{source_row_id}:source-text"


def _coverage_clause_id(source_row_id: str, suffix: str) -> str:
    return f"{_coverage_rule_id(source_row_id)}:{suffix}"


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
            "source_span": _span(normalized_text, "end of the phase"),
            "parameters": [_parameter("endpoint", "phase")],
        },
    )


def _parameter(key: str, value: object) -> RuleParameterPayload:
    return cast(RuleParameterPayload, {"key": key, "value": value})


def _span(normalized_text: str, source_text: str) -> dict[str, str | int]:
    start = normalized_text.index(source_text)
    return {"text": source_text, "start": start, "end": start + len(source_text)}


def _stratagem_parser_version() -> str:
    return "phase17s-stratagem-activation-template-v2"


def _coverage_payloads() -> Mapping[str, RuleIRPayload]:
    return MappingProxyType(
        {
            LORDS_OF_THE_WARP_DETACHMENT_RULE_DESCRIPTOR_ID: _detachment_rule_payload(),
            SWOLLEN_WITH_POWER_DESCRIPTOR_ID: _swollen_with_power_payload(),
            CARNIVAL_OF_EXCESS_DESCRIPTOR_ID: _carnival_of_excess_payload(),
            CALL_TO_MURDER_DESCRIPTOR_ID: _call_to_murder_payload(),
            BILIOUS_BLESSING_DESCRIPTOR_ID: _bilious_blessing_payload(),
            SKIRLING_MAGICKS_DESCRIPTOR_ID: _skirling_magicks_payload(),
        }
    )


_COVERAGE_RULE_IR_PAYLOADS_BY_DESCRIPTOR_ID = _coverage_payloads()
