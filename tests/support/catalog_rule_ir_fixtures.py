from __future__ import annotations

from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
)
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
)
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilitySourceKind,
    AbilityTimingDescriptor,
)
from warhammer40k_core.engine.ability_coverage import (
    AbilityCoverageAbilityDatasheetPair,
    AbilityCoverageCategoryRow,
    AbilityCoverageRow,
    AbilityCoverageSupportStage,
)
from warhammer40k_core.engine.effects import (
    EffectExpiration,
    PersistingEffect,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_factory import (
    ModelInstance,
    UnitInstance,
)
from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleDuration,
    RuleDurationKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleParameterValue,
    RuleTargetKind,
    RuleTargetSpec,
    RuleTrigger,
    RuleTriggerKind,
    parameters_from_pairs,
)
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    datasheet_keyword_lexicon_2026_06_14 as datasheet_keyword_lexicon_source,
)

SOURCE_KEYWORD_SEQUENCE_PARTS = (
    datasheet_keyword_lexicon_source.canonical_datasheet_keyword_sequence_parts()
)


def phase17k_named_choice_effect(
    *,
    effect_id: str,
    unit: UnitInstance,
    owner_player_id: str,
    payload: JsonValue,
) -> PersistingEffect:
    return PersistingEffect(
        effect_id=effect_id,
        source_rule_id="phase17k:named-choice:test",
        owner_player_id=owner_player_id,
        target_unit_instance_ids=(unit.unit_instance_id,),
        started_battle_round=1,
        started_phase=BattlePhaseKind.SHOOTING,
        expiration=EffectExpiration.end_phase(
            battle_round=1,
            phase=BattlePhaseKind.SHOOTING,
            player_id=owner_player_id,
        ),
        effect_payload=payload,
    )


def model_bearing_wargear(
    unit: UnitInstance,
    wargear_id: str,
) -> ModelInstance:
    for model in unit.own_models:
        if wargear_id in model.wargear_ids:
            return model
    raise ValueError(f"Missing bearer for wargear: {wargear_id}.")


def catalog_rule_ir(
    effects: tuple[RuleEffectSpec, ...],
    *,
    target_kind: RuleTargetKind,
) -> RuleIR:
    span = TextSpan(text="catalog hook test", start=0, end=17)
    return RuleIR(
        rule_id="test-catalog-hook-rule",
        source_id="test-catalog-hook-source",
        normalized_text=span.text,
        parser_version="test-catalog-hook-parser",
        clauses=(
            RuleClause(
                clause_id="test-catalog-hook-clause",
                source_span=span,
                target=RuleTargetSpec(kind=target_kind, source_span=span),
                effects=effects,
            ),
        ),
    )


def multi_clause_named_weapon_choice_rule_ir() -> RuleIR:
    span = TextSpan(text="catalog hook test", start=0, end=17)
    return RuleIR(
        rule_id="phase17k:test:multi-named-choice",
        source_id="phase17k:test:multi-named-choice",
        normalized_text=span.text,
        parser_version="test-catalog-hook-parser",
        clauses=(
            RuleClause(
                clause_id="phase17k:test:multi-named-choice:clause:001",
                source_span=span,
                trigger=RuleTrigger(
                    kind=RuleTriggerKind.TIMING_WINDOW,
                    source_span=span,
                    parameters=parameters_from_pairs(
                        (
                            ("edge", "during"),
                            ("owner", "active_player"),
                            ("phase", "movement"),
                        )
                    ),
                ),
                target=RuleTargetSpec(kind=RuleTargetKind.THIS_UNIT, source_span=span),
                effects=(
                    effect(
                        RuleEffectKind.GRANT_ABILITY,
                        ability="can_advance_and_charge",
                    ),
                ),
                duration=RuleDuration(
                    kind=RuleDurationKind.PERMANENT,
                    source_span=span,
                ),
            ),
            RuleClause(
                clause_id="phase17k:test:multi-named-choice:clause:002",
                source_span=span,
                trigger=RuleTrigger(
                    kind=RuleTriggerKind.TIMING_WINDOW,
                    source_span=span,
                    parameters=parameters_from_pairs(
                        (
                            ("edge", "during"),
                            ("owner", "active_player"),
                            ("phase", "shooting"),
                        )
                    ),
                ),
                target=RuleTargetSpec(kind=RuleTargetKind.THIS_MODEL, source_span=span),
                effects=(
                    effect(
                        RuleEffectKind.GRANT_WEAPON_ABILITY,
                        selection_kind="select_one",
                        selection_group_id="multi_clause_named_weapon_choice",
                        selection_option_id="option_001_ignores_cover",
                        selection_option_index=1,
                        target_scope="this_model",
                        weapon_name="Bolt of Change",
                        weapon_ability="Ignores Cover",
                    ),
                    effect(
                        RuleEffectKind.GRANT_WEAPON_ABILITY,
                        selection_kind="select_one",
                        selection_group_id="multi_clause_named_weapon_choice",
                        selection_option_id="option_002_lethal_hits",
                        selection_option_index=2,
                        target_scope="this_model",
                        weapon_name="Bolt of Change",
                        weapon_ability="Lethal Hits",
                    ),
                ),
                duration=RuleDuration(
                    kind=RuleDurationKind.UNTIL_TIMING_ENDPOINT,
                    source_span=span,
                    parameters=parameters_from_pairs((("endpoint", "phase"),)),
                ),
            ),
        ),
    )


def multi_clause_named_weapon_choice_record(
    *,
    rule_ir: RuleIR,
    clause_index: int,
    datasheet_id: str,
    trigger_kind: TimingTriggerKind,
) -> AbilityCatalogRecord:
    clause = rule_ir.clauses[clause_index]
    return AbilityCatalogRecord(
        record_id=f"phase17k:test:catalog-ability:{datasheet_id}:multi-daemonspark:{clause.clause_id}",
        definition=AbilityDefinition(
            ability_id="multi-daemonspark",
            name="Multi-Clause Daemonspark",
            source_id="phase17k:test:multi-named-choice",
            when_descriptor="Catalog generic rule IR.",
            effect_descriptor="Multi-clause named weapon ability choice.",
            restrictions_descriptor="Datasheet ability source kind: datasheet.",
            timing=AbilityTimingDescriptor(trigger_kind=trigger_kind),
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
            replay_payload=validate_json_value(
                {
                    "rule_ir": rule_ir.to_payload(),
                    "runtime_clause_id": clause.clause_id,
                }
            ),
        ),
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id=datasheet_id,
    )


def multi_clause_post_shoot_cover_denial_rule_ir() -> RuleIR:
    span = TextSpan(text="catalog hook test", start=0, end=17)
    return RuleIR(
        rule_id="phase17k:test:multi-post-shoot-cover-denial",
        source_id="phase17k:test:multi-post-shoot-cover-denial",
        normalized_text=span.text,
        parser_version="test-catalog-hook-parser",
        clauses=(
            RuleClause(
                clause_id="phase17k:test:multi-post-shoot-cover-denial:clause:001",
                source_span=span,
                trigger=RuleTrigger(
                    kind=RuleTriggerKind.TIMING_WINDOW,
                    source_span=span,
                    parameters=parameters_from_pairs(
                        (
                            ("edge", "during"),
                            ("owner", "active_player"),
                            ("phase", "movement"),
                        )
                    ),
                ),
                target=RuleTargetSpec(kind=RuleTargetKind.THIS_UNIT, source_span=span),
                effects=(
                    effect(
                        RuleEffectKind.GRANT_ABILITY,
                        ability="can_advance_and_charge",
                    ),
                ),
                duration=RuleDuration(
                    kind=RuleDurationKind.PERMANENT,
                    source_span=span,
                ),
            ),
            RuleClause(
                clause_id="phase17k:test:multi-post-shoot-cover-denial:clause:002",
                source_span=span,
                trigger=RuleTrigger(
                    kind=RuleTriggerKind.TIMING_WINDOW,
                    source_span=span,
                    parameters=parameters_from_pairs(
                        (
                            ("edge", "after"),
                            ("owner", "active_player"),
                            ("phase", "shooting"),
                            ("subject", "this_model"),
                            ("timing_window", "just_after_friendly_unit_has_shot"),
                            ("target_relationship", "hit_by_those_attacks"),
                        )
                    ),
                ),
                target=RuleTargetSpec(kind=RuleTargetKind.ENEMY_UNIT, source_span=span),
                effects=(
                    effect(
                        RuleEffectKind.SET_CONTEXTUAL_STATUS,
                        status="benefit_of_cover",
                        status_label="Benefit of Cover",
                        operation="deny",
                        target_scope="selected_unit",
                        rules_context="status_denial",
                    ),
                ),
                duration=RuleDuration(
                    kind=RuleDurationKind.UNTIL_TIMING_ENDPOINT,
                    source_span=span,
                    parameters=parameters_from_pairs((("endpoint", "phase"),)),
                ),
            ),
        ),
    )


def multi_clause_post_shoot_cover_denial_record(
    *,
    rule_ir: RuleIR,
    clause_index: int,
    datasheet_id: str,
    trigger_kind: TimingTriggerKind,
) -> AbilityCatalogRecord:
    clause = rule_ir.clauses[clause_index]
    return AbilityCatalogRecord(
        record_id=(
            f"phase17k:test:catalog-ability:{datasheet_id}:multi-purge-and-cleanse:"
            f"{clause.clause_id}"
        ),
        definition=AbilityDefinition(
            ability_id="multi-purge-and-cleanse",
            name="Multi-Clause Purge and Cleanse",
            source_id="phase17k:test:multi-post-shoot-cover-denial",
            when_descriptor="Catalog generic rule IR.",
            effect_descriptor="Multi-clause post-shoot hit-target status denial.",
            restrictions_descriptor="Datasheet ability source kind: datasheet.",
            timing=AbilityTimingDescriptor(trigger_kind=trigger_kind),
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
            replay_payload=validate_json_value(
                {
                    "rule_ir": rule_ir.to_payload(),
                    "runtime_clause_id": clause.clause_id,
                }
            ),
        ),
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id=datasheet_id,
    )


def charge_end_mortal_wounds_rule_ir() -> RuleIR:
    return compile_rule_source_text(
        RuleSourceText.from_raw(
            source_id="phase17k:test:charge-end-mortal-wounds",
            raw_text=(
                "Each time this unit ends a Charge move, select one enemy unit within "
                "Engagement Range of this unit and roll one D6 for each model in this unit: "
                "for each 4+, that enemy unit suffers D3 mortal wounds."
            ),
        ),
        source_keyword_sequence_parts=SOURCE_KEYWORD_SEQUENCE_PARTS,
    ).rule_ir


def charge_end_mortal_wounds_record(
    *,
    rule_ir: RuleIR,
    datasheet_id: str,
) -> AbilityCatalogRecord:
    return AbilityCatalogRecord(
        record_id=f"phase17k:test:catalog-ability:{datasheet_id}:charge-end-mortal-wounds",
        definition=AbilityDefinition(
            ability_id="charge-end-mortal-wounds",
            name="Charge-End Mortal Wounds",
            source_id="phase17k:test:charge-end-mortal-wounds",
            when_descriptor="Catalog generic rule IR.",
            effect_descriptor="Charge-end selected target mortal wounds.",
            restrictions_descriptor="Datasheet ability source kind: datasheet.",
            timing=AbilityTimingDescriptor(
                trigger_kind=TimingTriggerKind.AFTER_UNIT_ENDS_CHARGE_MOVE,
                phase=BattlePhaseKind.CHARGE,
            ),
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
            replay_payload=validate_json_value({"rule_ir": rule_ir.to_payload()}),
        ),
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id=datasheet_id,
    )


def effect(kind: RuleEffectKind, **parameters: RuleParameterValue) -> RuleEffectSpec:
    span = TextSpan(text="catalog hook test", start=0, end=17)
    return RuleEffectSpec(
        kind=kind,
        source_span=span,
        parameters=parameters_from_pairs(tuple(parameters.items())),
    )


def ability_coverage_row(
    *,
    catalog_id: str = "test-catalog",
    datasheet_id: str = "test-datasheet",
    datasheet_name: str = "Test Datasheet",
    ability_id: str = "test-ability",
    ability_name: str = "Test Ability",
    source_kind: CatalogAbilitySourceKind = CatalogAbilitySourceKind.WARGEAR,
    source_wargear_id: str | None = "test-wargear",
    catalog_support: CatalogAbilitySupport = CatalogAbilitySupport.DESCRIPTOR_ONLY,
    support_stage: AbilityCoverageSupportStage = AbilityCoverageSupportStage.DESCRIPTOR_ONLY,
    semantic_categories: tuple[str, ...] = ("wargear.descriptor",),
    runtime_consumer_ids: tuple[str, ...] = (),
    diagnostic_reasons: tuple[str, ...] = (),
) -> AbilityCoverageRow:
    return AbilityCoverageRow(
        catalog_id=catalog_id,
        datasheet_id=datasheet_id,
        datasheet_name=datasheet_name,
        ability_id=ability_id,
        ability_name=ability_name,
        source_kind=source_kind,
        source_wargear_id=source_wargear_id,
        catalog_support=catalog_support,
        support_stage=support_stage,
        semantic_categories=semantic_categories,
        runtime_consumer_ids=runtime_consumer_ids,
        diagnostic_reasons=diagnostic_reasons,
    )


def ability_datasheet_pair(
    *,
    coverage_row_id: str = "test-row",
    ability_id: str = "test-ability",
    ability_name: str = "Test Ability",
    datasheet_id: str = "test-datasheet",
    datasheet_name: str = "Test Datasheet",
    source_kind: CatalogAbilitySourceKind = CatalogAbilitySourceKind.WARGEAR,
) -> AbilityCoverageAbilityDatasheetPair:
    return AbilityCoverageAbilityDatasheetPair(
        coverage_row_id=coverage_row_id,
        ability_id=ability_id,
        ability_name=ability_name,
        datasheet_id=datasheet_id,
        datasheet_name=datasheet_name,
        source_kind=source_kind,
    )


def ability_coverage_category_row(
    *,
    category_id: str = "wargear.roll_modifier.charge.this_unit",
    category_name: str = "Charge Roll Modifier",
    coverage_row_count: int = 1,
    coverage_row_ids: tuple[str, ...] = ("test-row",),
    ability_datasheet_pairs: tuple[AbilityCoverageAbilityDatasheetPair, ...] | None = None,
    source_kind_counts: tuple[tuple[str, int], ...] = (("wargear", 1),),
    support_stages: tuple[AbilityCoverageSupportStage, ...] = (
        AbilityCoverageSupportStage.DESCRIPTOR_ONLY,
    ),
    runtime_consumer_ids: tuple[str, ...] = (),
    ability_names: tuple[str, ...] = ("Test Ability",),
    datasheet_names: tuple[str, ...] = ("Test Datasheet",),
) -> AbilityCoverageCategoryRow:
    if ability_datasheet_pairs is None:
        ability_datasheet_pairs = (ability_datasheet_pair(),)
    return AbilityCoverageCategoryRow(
        category_id=category_id,
        category_name=category_name,
        coverage_row_count=coverage_row_count,
        coverage_row_ids=coverage_row_ids,
        ability_datasheet_pairs=ability_datasheet_pairs,
        source_kind_counts=source_kind_counts,
        support_stages=support_stages,
        runtime_consumer_ids=runtime_consumer_ids,
        ability_names=ability_names,
        datasheet_names=datasheet_names,
    )
