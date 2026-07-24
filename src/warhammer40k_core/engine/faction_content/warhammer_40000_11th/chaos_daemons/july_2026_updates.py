from __future__ import annotations

from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilitySourceKind,
    AbilityTimingDescriptor,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.stratagems import (
    GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
    StratagemAvailabilityKind,
    StratagemCatalogRecord,
    StratagemCategory,
    StratagemDefinition,
    StratagemRestrictionPolicy,
    StratagemTargetKind,
    StratagemTargetSpec,
    StratagemTimingDescriptor,
)
from warhammer40k_core.engine.stratagems_generic_metadata import (
    COMPANION_FORBIDDEN_IF_WITHIN_ENGAGEMENT_RANGE_KEY,
    COMPANION_REQUIRED_CONTEXTUAL_STATUS_KEY,
    COMPANION_REQUIRED_KEYWORDS_BY_TARGET_KEYWORD_KEY,
    EFFECT_SELECTION_KIND_KEY,
    SELECTED_FRIENDLY_COMPANION_UNIT_EFFECT_SELECTION_KIND,
    TARGET_CONTEXTUAL_STATUS_SHADOW_OF_CHAOS,
    TARGET_REQUIRED_CONTEXTUAL_STATUS_KEY,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
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
    RuleParameter,
    RuleTargetKind,
    RuleTargetSpec,
    RuleTrigger,
    RuleTriggerKind,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_daemonic_incursion_ir_support_2026_27 as predecessor_ir,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    july_faction_packs_2026_07 as july_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.july_faction_packs_2026_07 import (  # noqa: E501
    JulyChaosDaemonsRuntimeRow,
)

from .detachments.daemonic_incursion.rule import (
    DAEMONIC_INCURSION_DETACHMENT_ID,
    LEGIONES_DAEMONICA,
)

CONTRIBUTION_ID = "warhammer_40000_11th:chaos_daemons:july_2026_runtime_updates"
FRIENDLY_UNIT_TARGET_POLICY_ID = "friendly_unit"
TARGET_FORBIDDEN_IF_WITHIN_ENGAGEMENT_RANGE_KEY = "target_forbidden_if_within_engagement_range"
KAIROS_DATASHEET_ID = "000001117"
KAIROS_ABILITY_ID = "000001117:one-head-looks-back-aura"
FLUXMASTER_DATASHEET_ID = "000001464"
FLUXMASTER_ABILITY_ID = "000001464:fluxmaster"
SCREAMERS_DATASHEET_ID = "000001127"


def runtime_contribution() -> RuntimeContentContribution:
    realm_ir = _realm_of_chaos_rule_ir()
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        ability_records=(
            _kairos_record(),
            *_fluxmaster_records(),
        ),
        stratagem_records=(
            _realm_of_chaos_record(
                realm_ir=realm_ir,
                record_suffix="single",
                target_descriptor=(
                    "One friendly Legiones Daemonica unit that is not within Engagement "
                    "Range of one or more enemy units."
                ),
                effect_metadata={
                    "requires_opponent_turn": True,
                    TARGET_FORBIDDEN_IF_WITHIN_ENGAGEMENT_RANGE_KEY: True,
                },
            ),
            _realm_of_chaos_record(
                realm_ir=realm_ir,
                record_suffix="shadow-pair",
                target_descriptor=(
                    "Up to two friendly Legiones Daemonica units within your Shadow of "
                    "Chaos that are not within Engagement Range of one or more enemy units."
                ),
                effect_metadata={
                    "requires_opponent_turn": True,
                    TARGET_FORBIDDEN_IF_WITHIN_ENGAGEMENT_RANGE_KEY: True,
                    TARGET_REQUIRED_CONTEXTUAL_STATUS_KEY: (
                        TARGET_CONTEXTUAL_STATUS_SHADOW_OF_CHAOS
                    ),
                    EFFECT_SELECTION_KIND_KEY: (
                        SELECTED_FRIENDLY_COMPANION_UNIT_EFFECT_SELECTION_KIND
                    ),
                    COMPANION_FORBIDDEN_IF_WITHIN_ENGAGEMENT_RANGE_KEY: True,
                    COMPANION_REQUIRED_CONTEXTUAL_STATUS_KEY: (
                        TARGET_CONTEXTUAL_STATUS_SHADOW_OF_CHAOS
                    ),
                    COMPANION_REQUIRED_KEYWORDS_BY_TARGET_KEYWORD_KEY: {
                        LEGIONES_DAEMONICA: [LEGIONES_DAEMONICA],
                    },
                },
            ),
        ),
    )


def replacement_keywords_for_datasheet(datasheet_id: str) -> tuple[str, ...] | None:
    if datasheet_id != SCREAMERS_DATASHEET_ID:
        return None
    row = _runtime_row("chaos-daemons:screamers:keywords")
    return tuple(row.replacement_keywords)


def unsupported_ability_rows() -> tuple[JulyChaosDaemonsRuntimeRow, ...]:
    return (_runtime_row("chaos-daemons:fluxmaster:altered-reality"),)


def _runtime_row(row_id: str) -> JulyChaosDaemonsRuntimeRow:
    artifact = july_source.chaos_daemons_runtime_updates()
    for row in artifact.rows:
        if row.row_id == row_id:
            return row
    raise GameLifecycleError("Validated July Chaos Daemons runtime row is unavailable.")


def _realm_of_chaos_rule_ir() -> RuleIR:
    row = _runtime_row("chaos-daemons:the-realm-of-chaos")
    text = row.normalized_rule_text
    span = _full_span(text)
    source_id = row.source_row_id
    return RuleIR(
        rule_id=f"phase17s:{source_id}",
        source_id=source_id,
        normalized_text=text,
        parser_version="manual-source-backed-rule-ir:v1",
        clauses=(
            RuleClause(
                clause_id=f"phase17s:{source_id}:clause:001",
                template_id="phase17s:stratagem-activation-target-binding",
                source_span=span,
                target=RuleTargetSpec(kind=RuleTargetKind.FRIENDLY_UNIT, source_span=span),
            ),
            RuleClause(
                clause_id=f"phase17s:{source_id}:clause:002",
                template_id="phase17c:placement-permission",
                source_span=span,
                target=RuleTargetSpec(kind=RuleTargetKind.SELECTED_UNIT, source_span=span),
                effects=(
                    RuleEffectSpec(
                        kind=RuleEffectKind.PLACEMENT_PERMISSION,
                        source_span=span,
                        parameters=_parameters(
                            placement_kind="strategic_reserves",
                            operation="remove_to_reserves",
                            reserve_origin="during_battle_stratagem",
                            required_arrival_timing="next_owner_movement_phase",
                            required_arrival_phase="movement",
                            required_arrival_source_rule_id=source_id,
                            required_arrival_placement_kind="strategic_reserves",
                        ),
                    ),
                ),
            ),
        ),
    )


def _realm_of_chaos_record(
    *,
    realm_ir: RuleIR,
    record_suffix: str,
    target_descriptor: str,
    effect_metadata: dict[str, JsonValue],
) -> StratagemCatalogRecord:
    row = _runtime_row("chaos-daemons:the-realm-of-chaos")
    return StratagemCatalogRecord(
        record_id=f"{CONTRIBUTION_ID}:the-realm-of-chaos:{record_suffix}",
        definition=StratagemDefinition(
            stratagem_id=predecessor_ir.THE_REALM_OF_CHAOS_STRATAGEM_ID,
            name=row.rule_name,
            source_id=row.source_row_id,
            command_point_cost=1,
            category=StratagemCategory.BATTLE_TACTIC,
            when_descriptor="End of your opponent's turn.",
            target_descriptor=target_descriptor,
            effect_descriptor=row.normalized_rule_text,
            restrictions_descriptor="matched play same stratagem per phase",
            timing=StratagemTimingDescriptor(trigger_kind=TimingTriggerKind.END_TURN),
            restriction_policy=StratagemRestrictionPolicy(same_unit_target_per_phase=True),
            target_spec=StratagemTargetSpec(
                target_kind=StratagemTargetKind.FRIENDLY_UNIT,
                enumerable=True,
                target_policy_id=FRIENDLY_UNIT_TARGET_POLICY_ID,
                required_faction_keywords=(LEGIONES_DAEMONICA,),
            ),
            handler_id=GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
            effect_payload=validate_json_value(
                {
                    "rule_ir": realm_ir.to_payload(),
                    **effect_metadata,
                }
            ),
        ),
        availability_kind=StratagemAvailabilityKind.DETACHMENT,
        detachment_id=DAEMONIC_INCURSION_DETACHMENT_ID,
        disabled=False,
    )


def _kairos_record() -> AbilityCatalogRecord:
    row = _runtime_row("chaos-daemons:kairos-fateweaver:one-head-looks-back")
    rule_ir = _kairos_rule_ir(row)
    return _ability_record(
        row=row,
        datasheet_id=KAIROS_DATASHEET_ID,
        ability_id=KAIROS_ABILITY_ID,
        record_suffix="one-head-looks-back",
        timing=AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.ANY_PHASE),
        rule_ir=rule_ir,
        runtime_clause_id=rule_ir.clauses[0].clause_id,
    )


def _kairos_rule_ir(row: JulyChaosDaemonsRuntimeRow) -> RuleIR:
    text = row.normalized_rule_text
    span = _full_span(text)
    source_id = row.source_row_id
    clause_id = f"{source_id}:clause:001"
    return RuleIR(
        rule_id=source_id,
        source_id=source_id,
        normalized_text=text,
        parser_version="manual-source-backed-rule-ir:v1",
        clauses=(
            RuleClause(
                clause_id=clause_id,
                template_id="phase17c:resource-modifier",
                source_span=span,
                trigger=RuleTrigger(
                    kind=RuleTriggerKind.UNIT_SELECTED,
                    source_span=span,
                    parameters=_parameters(
                        selected_unit_allegiance="enemy",
                        selection="stratagem_target",
                        source_relationship=("stratagem_targets_unit_within_source_model_range"),
                        stratagem_user="opponent",
                        timing_window="after_unit_selected_as_stratagem_target",
                        usage_scope="source_model",
                    ),
                ),
                conditions=(
                    RuleCondition(
                        kind=RuleConditionKind.FREQUENCY_LIMIT,
                        source_span=span,
                        parameters=_parameters(scope="turn"),
                    ),
                    RuleCondition(
                        kind=RuleConditionKind.TARGET_CONSTRAINT,
                        source_span=span,
                        parameters=_parameters(
                            gate_subject="stratagem_target",
                            relationship="stratagem_targets_unit_within_source_model_range",
                            selected_unit_allegiance="enemy",
                        ),
                    ),
                    RuleCondition(
                        kind=RuleConditionKind.DISTANCE_PREDICATE,
                        source_span=span,
                        parameters=_parameters(
                            distance_inches=12.0,
                            negated=False,
                            object_kind="model",
                            object_reference="this",
                            predicate="within",
                            qualifier=None,
                            range_kind="numeric_range",
                        ),
                    ),
                ),
                target=RuleTargetSpec(kind=RuleTargetKind.STRATAGEM_USE, source_span=span),
                effects=(
                    RuleEffectSpec(
                        kind=RuleEffectKind.MODIFY_COMMAND_POINTS,
                        source_span=span,
                        parameters=_parameters(
                            affected_player="opponent",
                            application_scope="current_stratagem_use",
                            delta=1,
                            minimum_cost=0,
                            operation="modify_stratagem_cost",
                            optional=True,
                            stacking="cumulative",
                        ),
                    ),
                ),
            ),
        ),
    )


def _fluxmaster_records() -> tuple[AbilityCatalogRecord, ...]:
    row = _runtime_row("chaos-daemons:fluxmaster:fluxmaster")
    rule_ir = _fluxmaster_rule_ir(row)
    stealth_clause, melee_clause = rule_ir.clauses
    return (
        _ability_record(
            row=row,
            datasheet_id=FLUXMASTER_DATASHEET_ID,
            ability_id=FLUXMASTER_ABILITY_ID,
            record_suffix="stealth",
            timing=AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.PASSIVE_QUERY),
            rule_ir=rule_ir,
            runtime_clause_id=stealth_clause.clause_id,
        ),
        _ability_record(
            row=row,
            datasheet_id=FLUXMASTER_DATASHEET_ID,
            ability_id=FLUXMASTER_ABILITY_ID,
            record_suffix="melee-hit-penalty",
            timing=AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL),
            rule_ir=rule_ir,
            runtime_clause_id=melee_clause.clause_id,
        ),
    )


def _fluxmaster_rule_ir(row: JulyChaosDaemonsRuntimeRow) -> RuleIR:
    text = row.normalized_rule_text
    span = _full_span(text)
    source_id = row.source_row_id
    duration = RuleDuration(
        kind=RuleDurationKind.WHILE_CONDITION_TRUE,
        source_span=span,
    )
    return RuleIR(
        rule_id=source_id,
        source_id=source_id,
        normalized_text=text,
        parser_version="manual-source-backed-rule-ir:v1",
        clauses=(
            RuleClause(
                clause_id=f"{source_id}:clause:001",
                template_id="phase17p:passive-self-ability-grant",
                source_span=span,
                target=RuleTargetSpec(kind=RuleTargetKind.THIS_UNIT, source_span=span),
                effects=(
                    RuleEffectSpec(
                        kind=RuleEffectKind.GRANT_ABILITY,
                        source_span=span,
                        parameters=_parameters(
                            ability="stealth",
                            target_scope="this_unit",
                        ),
                    ),
                ),
                duration=duration,
            ),
            RuleClause(
                clause_id=f"{source_id}:clause:002",
                template_id="phase17p:passive-self-defensive-hit-roll-modifier",
                source_span=span,
                trigger=RuleTrigger(
                    kind=RuleTriggerKind.DICE_ROLL,
                    source_span=span,
                    parameters=_parameters(
                        attack_kind="melee",
                        attack_role="target",
                        roll_type="hit",
                        timing_window="attack_sequence.hit",
                    ),
                ),
                target=RuleTargetSpec(kind=RuleTargetKind.THIS_UNIT, source_span=span),
                effects=(
                    RuleEffectSpec(
                        kind=RuleEffectKind.MODIFY_DICE_ROLL,
                        source_span=span,
                        parameters=_parameters(
                            attack_role="target",
                            delta=-1,
                            roll_type="hit",
                            weapon_scope="melee",
                        ),
                    ),
                ),
                duration=duration,
            ),
        ),
    )


def _ability_record(
    *,
    row: JulyChaosDaemonsRuntimeRow,
    datasheet_id: str,
    ability_id: str,
    record_suffix: str,
    timing: AbilityTimingDescriptor,
    rule_ir: RuleIR,
    runtime_clause_id: str,
) -> AbilityCatalogRecord:
    return AbilityCatalogRecord(
        record_id=f"{CONTRIBUTION_ID}:catalog-ability:{datasheet_id}:{record_suffix}",
        definition=AbilityDefinition(
            ability_id=ability_id,
            name=row.rule_name,
            source_id=row.source_row_id,
            when_descriptor="Source-backed datasheet ability timing.",
            effect_descriptor=row.normalized_rule_text,
            restrictions_descriptor="Source-backed datasheet restrictions.",
            timing=timing,
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
            replay_payload=validate_json_value(
                {
                    "rule_ir": rule_ir.to_payload(),
                    "runtime_clause_id": runtime_clause_id,
                }
            ),
        ),
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id=datasheet_id,
    )


def _parameters(**values: str | int | float | bool | None) -> tuple[RuleParameter, ...]:
    return tuple(RuleParameter(key=key, value=value) for key, value in values.items())


def _full_span(text: str) -> TextSpan:
    return TextSpan(text=text, start=0, end=len(text))
