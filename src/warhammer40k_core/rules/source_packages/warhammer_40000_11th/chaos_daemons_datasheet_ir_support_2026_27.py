from __future__ import annotations

from types import MappingProxyType

from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleCondition,
    RuleConditionKind,
    RuleDuration,
    RuleDurationKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleIRPayload,
    RuleParameter,
    RuleParameterValue,
    RuleTargetKind,
    RuleTargetSpec,
    RuleTrigger,
    RuleTriggerKind,
)

SOURCE_PACKAGE_ID = "gw-11e-chaos-daemons-datasheet-ir-2026-27"
PARSER_VERSION = "manual-source-backed-rule-ir:v1"

BELAKOR_DATASHEET_ID = "000001148"
BELAKOR_DARK_MASTER_ROW_ID = "000001148:5"
BELAKOR_SHADOW_FORM_ROW_ID = "000001148:6"
BELAKOR_WREATHED_IN_SHADOWS_ROW_ID = "000001148:8"
BELAKOR_PALL_OF_DESPAIR_ROW_ID = "000001148:9"
BELAKOR_SHADOW_LORD_ROW_ID = "000001148:10"

BELAKOR_DARK_MASTER_SOURCE_ID = f"{SOURCE_PACKAGE_ID}:datasheet:{BELAKOR_DARK_MASTER_ROW_ID}"
BELAKOR_SHADOW_FORM_SOURCE_ID = f"{SOURCE_PACKAGE_ID}:datasheet:{BELAKOR_SHADOW_FORM_ROW_ID}"
BELAKOR_WREATHED_IN_SHADOWS_SOURCE_ID = (
    f"{SOURCE_PACKAGE_ID}:datasheet:{BELAKOR_WREATHED_IN_SHADOWS_ROW_ID}"
)
BELAKOR_PALL_OF_DESPAIR_SOURCE_ID = (
    f"{SOURCE_PACKAGE_ID}:datasheet:{BELAKOR_PALL_OF_DESPAIR_ROW_ID}"
)
BELAKOR_SHADOW_LORD_SOURCE_ID = f"{SOURCE_PACKAGE_ID}:datasheet:{BELAKOR_SHADOW_LORD_ROW_ID}"

BELAKOR_SHADOW_FORM_SELECTABLE_SOURCE_IDS = (
    BELAKOR_WREATHED_IN_SHADOWS_SOURCE_ID,
    BELAKOR_PALL_OF_DESPAIR_SOURCE_ID,
    BELAKOR_SHADOW_LORD_SOURCE_ID,
)

LEGIONES_DAEMONICA_KEYWORD = "LEGIONES DAEMONICA"
SHADOW_LEGION_KEYWORD = "SHADOW LEGION"

_DARK_MASTER_TEXT = (
    "The area of the battlefield within 6\" of this model is within your army's Shadow of Chaos."
)
_SHADOW_FORM_TEXT = (
    "At the start of the battle round, select one Shadow Form ability (see below). Until the "
    "end of the battle round, this model has that ability."
)
_WREATHED_IN_SHADOWS_TEXT = (
    'While a friendly Legiones Daemonica unit or Shadow Legion unit is within 6" of this model, '
    'that unit can only be targeted by a ranged attack if the attacking model is within 18".'
)
_PALL_OF_DESPAIR_TEXT = (
    "In the Battle-shock step of your opponent's Command phase, if an enemy unit that is below "
    'its Starting Strength is within 9" of this model, that unit must take a Battle-shock test. '
    "For the purposes of this ability, if a unit has a Starting Strength of 1, it is considered "
    "to be below its Starting Strength while it has lost one or more wounds. In addition, for "
    'each enemy unit that fails a Battle-shock test within 9" of this model, this model regains '
    "up to D3 lost wounds."
)
_SHADOW_LORD_TEXT = (
    'While a friendly Legiones Daemonica or Shadow Legion unit is within 6" of this model, each '
    "time a model in that unit makes an attack, re-roll a Hit roll of 1."
)


def supported_datasheet_source_row_ids() -> tuple[str, ...]:
    return tuple(sorted(_RULE_IR_PAYLOADS_BY_SOURCE_ROW_ID))


def datasheet_rule_ir_payload_by_source_row_id(source_row_id: str) -> RuleIRPayload | None:
    return _RULE_IR_PAYLOADS_BY_SOURCE_ROW_ID.get(source_row_id)


def _payload(rule_ir: RuleIR) -> RuleIRPayload:
    return RuleIR.from_payload(rule_ir.to_payload()).to_payload()


def _rule_ir(
    *,
    source_row_id: str,
    normalized_text: str,
    clauses: tuple[RuleClause, ...],
) -> RuleIR:
    return RuleIR(
        rule_id=f"phase17k:chaos-daemons:datasheet:{source_row_id}",
        source_id=f"{SOURCE_PACKAGE_ID}:datasheet:{source_row_id}",
        normalized_text=normalized_text,
        parser_version=PARSER_VERSION,
        clauses=clauses,
    )


def _span(text: str) -> TextSpan:
    return TextSpan(text=text, start=0, end=len(text))


def _parameter(key: str, value: RuleParameterValue) -> RuleParameter:
    return RuleParameter(key=key, value=value)


def _trigger(
    *,
    text: str,
    kind: RuleTriggerKind,
    parameters: tuple[RuleParameter, ...],
) -> RuleTrigger:
    return RuleTrigger(kind=kind, source_span=_span(text), parameters=parameters)


def _condition(
    *,
    text: str,
    kind: RuleConditionKind,
    parameters: tuple[RuleParameter, ...] = (),
) -> RuleCondition:
    return RuleCondition(kind=kind, source_span=_span(text), parameters=parameters)


def _aura_conditions(
    *,
    text: str,
    distance_inches: int,
    required_keyword: str | None = None,
) -> tuple[RuleCondition, ...]:
    conditions = [
        _condition(text=text, kind=RuleConditionKind.AURA),
        _condition(
            text=text,
            kind=RuleConditionKind.DISTANCE_PREDICATE,
            parameters=(
                _parameter("predicate", "within"),
                _parameter("object_kind", "unit"),
                _parameter("object_reference", "this_model"),
                _parameter("distance_inches", distance_inches),
            ),
        ),
    ]
    if required_keyword is not None:
        conditions.append(
            _condition(
                text=text,
                kind=RuleConditionKind.KEYWORD_GATE,
                parameters=(_parameter("required_keyword", required_keyword),),
            )
        )
    return tuple(conditions)


def _aura_target(
    *,
    text: str,
    allegiance: str,
) -> RuleTargetSpec:
    return RuleTargetSpec(
        kind=RuleTargetKind.AURA_UNITS,
        source_span=_span(text),
        parameters=(_parameter("allegiance", allegiance),),
    )


def _this_unit_target(text: str) -> RuleTargetSpec:
    return RuleTargetSpec(kind=RuleTargetKind.THIS_UNIT, source_span=_span(text))


def _effect(
    *,
    text: str,
    kind: RuleEffectKind,
    parameters: tuple[RuleParameter, ...],
) -> RuleEffectSpec:
    return RuleEffectSpec(kind=kind, source_span=_span(text), parameters=parameters)


def _until_end_battle_round(text: str) -> RuleDuration:
    return RuleDuration(
        kind=RuleDurationKind.UNTIL_TIMING_ENDPOINT,
        source_span=_span(text),
        parameters=(
            _parameter("endpoint", "battle round"),
            _parameter("boundary", "end"),
        ),
    )


def _clause(
    *,
    clause_id: str,
    text: str,
    target: RuleTargetSpec | None,
    effects: tuple[RuleEffectSpec, ...],
    conditions: tuple[RuleCondition, ...] = (),
    trigger: RuleTrigger | None = None,
    duration: RuleDuration | None = None,
    template_id: str | None = None,
) -> RuleClause:
    return RuleClause(
        clause_id=clause_id,
        template_id=template_id,
        source_span=_span(text),
        trigger=trigger,
        conditions=conditions,
        target=target,
        effects=effects,
        duration=duration,
    )


def _dark_master_rule_ir() -> RuleIR:
    return _rule_ir(
        source_row_id=BELAKOR_DARK_MASTER_ROW_ID,
        normalized_text=_DARK_MASTER_TEXT,
        clauses=(
            _clause(
                clause_id="belakor-dark-master-shadow-of-chaos-aura",
                template_id="phase17c:aura",
                text=_DARK_MASTER_TEXT,
                conditions=_aura_conditions(text=_DARK_MASTER_TEXT, distance_inches=6),
                target=_aura_target(text=_DARK_MASTER_TEXT, allegiance="friendly"),
                effects=(
                    _effect(
                        text=_DARK_MASTER_TEXT,
                        kind=RuleEffectKind.SET_CONTEXTUAL_STATUS,
                        parameters=(
                            _parameter("status", "within_shadow_of_chaos"),
                            _parameter("rules_context", "shadow_of_chaos"),
                            _parameter("owner", "your_army"),
                        ),
                    ),
                ),
            ),
        ),
    )


def _shadow_form_rule_ir() -> RuleIR:
    return _rule_ir(
        source_row_id=BELAKOR_SHADOW_FORM_ROW_ID,
        normalized_text=_SHADOW_FORM_TEXT,
        clauses=(
            _clause(
                clause_id="belakor-shadow-form-battle-round-selection",
                text=_SHADOW_FORM_TEXT,
                trigger=_trigger(
                    text=_SHADOW_FORM_TEXT,
                    kind=RuleTriggerKind.TIMING_WINDOW,
                    parameters=(
                        _parameter("phase", "battle_round"),
                        _parameter("edge", "start"),
                        _parameter("timing_window", "battle_round_start"),
                    ),
                ),
                target=_this_unit_target(_SHADOW_FORM_TEXT),
                effects=(
                    _effect(
                        text=_SHADOW_FORM_TEXT,
                        kind=RuleEffectKind.SET_CONTEXTUAL_STATUS,
                        parameters=(
                            _parameter("status", "catalog_shadow_form_selection"),
                            _parameter("rules_context", "shadow_form"),
                            _parameter(
                                "selectable_source_ids",
                                BELAKOR_SHADOW_FORM_SELECTABLE_SOURCE_IDS,
                            ),
                        ),
                    ),
                ),
                duration=_until_end_battle_round(_SHADOW_FORM_TEXT),
            ),
        ),
    )


def _wreathed_in_shadows_rule_ir() -> RuleIR:
    return _keyworded_aura_rule_ir(
        source_row_id=BELAKOR_WREATHED_IN_SHADOWS_ROW_ID,
        normalized_text=_WREATHED_IN_SHADOWS_TEXT,
        clause_id_prefix="belakor-wreathed-in-shadows",
        distance_inches=6,
        allegiance="friendly",
        effect=_effect(
            text=_WREATHED_IN_SHADOWS_TEXT,
            kind=RuleEffectKind.SET_CONTEXTUAL_STATUS,
            parameters=(
                _parameter("status", "shooting_target_range_restriction"),
                _parameter("rules_context", "targeting"),
                _parameter("source_effect_kind", "wreathed_in_shadows"),
                _parameter("targeting_max_range_inches", 18),
            ),
        ),
    )


def _pall_of_despair_rule_ir() -> RuleIR:
    return _rule_ir(
        source_row_id=BELAKOR_PALL_OF_DESPAIR_ROW_ID,
        normalized_text=_PALL_OF_DESPAIR_TEXT,
        clauses=(
            _clause(
                clause_id="belakor-pall-of-despair-01-forced-battle-shock",
                template_id="phase17c:aura",
                text=_PALL_OF_DESPAIR_TEXT,
                conditions=_aura_conditions(text=_PALL_OF_DESPAIR_TEXT, distance_inches=9),
                target=_aura_target(text=_PALL_OF_DESPAIR_TEXT, allegiance="enemy"),
                effects=(
                    _effect(
                        text=_PALL_OF_DESPAIR_TEXT,
                        kind=RuleEffectKind.SET_CONTEXTUAL_STATUS,
                        parameters=(
                            _parameter("status", "battle_shock_forced_below_starting_strength"),
                            _parameter("rules_context", "battle_shock"),
                            _parameter("force_battle_shock_below_starting_strength", True),
                            _parameter(
                                "single_model_lost_wounds_counts_below_starting_strength",
                                True,
                            ),
                        ),
                    ),
                ),
                duration=_until_end_battle_round(_PALL_OF_DESPAIR_TEXT),
            ),
            _clause(
                clause_id="belakor-pall-of-despair-02-failed-battle-shock-heal",
                template_id="phase17c:aura",
                text=_PALL_OF_DESPAIR_TEXT,
                conditions=_aura_conditions(text=_PALL_OF_DESPAIR_TEXT, distance_inches=9),
                target=_aura_target(text=_PALL_OF_DESPAIR_TEXT, allegiance="enemy"),
                effects=(
                    _effect(
                        text=_PALL_OF_DESPAIR_TEXT,
                        kind=RuleEffectKind.RESTORE_LOST_WOUNDS,
                        parameters=(
                            _parameter("amount", "D3"),
                            _parameter("trigger", "target_failed_battle_shock"),
                            _parameter("source_reference", "aura_source"),
                        ),
                    ),
                ),
                duration=_until_end_battle_round(_PALL_OF_DESPAIR_TEXT),
            ),
        ),
    )


def _shadow_lord_rule_ir() -> RuleIR:
    return _keyworded_aura_rule_ir(
        source_row_id=BELAKOR_SHADOW_LORD_ROW_ID,
        normalized_text=_SHADOW_LORD_TEXT,
        clause_id_prefix="belakor-shadow-lord",
        distance_inches=6,
        allegiance="friendly",
        effect=_effect(
            text=_SHADOW_LORD_TEXT,
            kind=RuleEffectKind.REROLL_PERMISSION,
            parameters=(
                _parameter("roll_type", "hit"),
                _parameter("attack_role", "attacker"),
                _parameter("timing_window", "attack_sequence.hit"),
                _parameter("reroll_unmodified_value", 1),
            ),
        ),
    )


def _keyworded_aura_rule_ir(
    *,
    source_row_id: str,
    normalized_text: str,
    clause_id_prefix: str,
    distance_inches: int,
    allegiance: str,
    effect: RuleEffectSpec,
) -> RuleIR:
    clauses = tuple(
        _clause(
            clause_id=f"{clause_id_prefix}-{keyword.lower().replace(' ', '-')}",
            template_id="phase17c:aura",
            text=normalized_text,
            conditions=_aura_conditions(
                text=normalized_text,
                distance_inches=distance_inches,
                required_keyword=keyword,
            ),
            target=_aura_target(text=normalized_text, allegiance=allegiance),
            effects=(effect,),
            duration=_until_end_battle_round(normalized_text),
        )
        for keyword in (LEGIONES_DAEMONICA_KEYWORD, SHADOW_LEGION_KEYWORD)
    )
    return _rule_ir(
        source_row_id=source_row_id,
        normalized_text=normalized_text,
        clauses=clauses,
    )


_RULE_IR_PAYLOADS_BY_SOURCE_ROW_ID = MappingProxyType(
    {
        BELAKOR_DARK_MASTER_ROW_ID: _payload(_dark_master_rule_ir()),
        BELAKOR_SHADOW_FORM_ROW_ID: _payload(_shadow_form_rule_ir()),
        BELAKOR_WREATHED_IN_SHADOWS_ROW_ID: _payload(_wreathed_in_shadows_rule_ir()),
        BELAKOR_PALL_OF_DESPAIR_ROW_ID: _payload(_pall_of_despair_rule_ir()),
        BELAKOR_SHADOW_LORD_ROW_ID: _payload(_shadow_lord_rule_ir()),
    }
)
