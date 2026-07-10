from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any, cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind, RulesetDescriptor
from warhammer40k_core.engine import (
    catalog_command_point_runtime as command_point_runtime,
)
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilitySourceKind,
    AbilityTimingDescriptor,
)
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
    EnhancementAssignment,
    muster_army,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    ModelPlacement,
    PlacedArmy,
    UnitPlacement,
)
from warhammer40k_core.engine.catalog_command_point_runtime import (
    CATALOG_IR_COMMAND_POINT_GAIN_EVENT,
    CATALOG_IR_COMMAND_POINT_LEADERSHIP_TEST_EVENT,
    CATALOG_IR_COMMAND_POINT_PHASE_GAIN_EVENT,
    CATALOG_IR_STRATAGEM_COST_CHOICE_EVENT,
    CatalogCommandPointRuntime,
)
from warhammer40k_core.engine.catalog_command_point_support import (
    CATALOG_IR_COMMAND_POINT_GAIN_CONSUMER_ID,
    CATALOG_IR_STRATAGEM_COST_MODIFIER_CONSUMER_ID,
)
from warhammer40k_core.engine.catalog_desperate_escape import (
    CATALOG_FORCED_DESPERATE_ESCAPE_SOURCE_KIND,
    catalog_forced_desperate_escape_sources_for_unit,
)
from warhammer40k_core.engine.catalog_once_per_battle_runtime import (
    CATALOG_ONCE_PER_BATTLE_ABILITY_ACTIVATED_EVENT,
    CATALOG_ONCE_PER_BATTLE_ABILITY_DECLINED_EVENT,
    CatalogOncePerBattleRuntime,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_clauses_from_record,
)
from warhammer40k_core.engine.catalog_selected_target_effects import (
    CATALOG_SELECTED_TARGET_EFFECT_SELECTED_EVENT,
    CatalogSelectedTargetEffectRuntime,
    apply_catalog_post_shoot_hit_target_effect_result,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    active_player_id,
    any_models_satisfy_distance,
    battle_phase_kind,
    catalog_selected_target_clauses_from_record,
    clause_is_fight_start_selection,
    clause_is_post_shoot_hit_target_selection,
    effect_target_unit_ids,
    effect_with_selected_target,
    eligible_selection_target_unit_ids,
    has_fight_start_selected_target_records,
    has_post_shoot_hit_target_effect_records,
    payload_effect_records,
    payload_int,
    payload_object,
    payload_string,
    payload_string_tuple,
    records_for_timing,
    required_keywords_for_clause,
    runtime_clause_id_from_record,
    selected_effect_clauses_after,
    selected_payload,
    selected_target_status_gate_allows,
    selection_source_model_ids,
    timing_window_id,
    validate_effect_record_tuple,
    validate_identifier_tuple,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.activation import RuntimeContentActivation
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.events import (
    RuntimeContentEvent,
    RuntimeContentEventHandlerRegistry,
    RuntimeContentEventIndex,
    RuntimeContentEventResult,
)
from warhammer40k_core.engine.fight_phase_start_hooks import (
    SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE,
    FightPhaseStartRequestContext,
    FightPhaseStartResultContext,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.list_validation import (
    AttachmentDeclaration,
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.rule_frequency import RULE_FREQUENCY_LIMIT_CONSUMED_EVENT
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.stratagem_cost_choice_hooks import (
    StratagemCostChoiceRequestContext,
    StratagemCostChoiceResultContext,
)
from warhammer40k_core.engine.stratagem_cost_modifiers import (
    StratagemCostModifierContext,
    StratagemCostModifierRegistry,
)
from warhammer40k_core.engine.stratagems import (
    STRATAGEM_DECISION_TYPE,
    StratagemCategory,
    StratagemDefinition,
    StratagemEligibilityContext,
    StratagemTargetBinding,
    StratagemTargetKind,
    StratagemTimingDescriptor,
    StratagemUseRecord,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_destroyed_hooks import UnitDestroyedContext
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
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
    RuleParameterValue,
    RuleTargetKind,
    RuleTargetSpec,
    RuleTrigger,
    RuleTriggerKind,
    parameter_payload,
    parameters_from_pairs,
)
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    datasheet_keyword_lexicon_2026_06_14 as datasheet_keyword_lexicon_source,
)

SOURCE_KEYWORD_SEQUENCE_PARTS = (
    datasheet_keyword_lexicon_source.canonical_datasheet_keyword_sequence_parts()
)
ONCE_PER_BATTLE_FIGHT_BOOST_TEXT = (
    "Once per battle, at the start of the Fight phase, this model can use this ability. "
    "If it does, until the end of the phase, add 3 to the Attacks characteristic of melee "
    "weapons equipped by this model and those weapons have the [DEVASTATING WOUNDS] ability."
)
DESTROYED_CHARACTER_COMMAND_POINT_TEXT = (
    "Each time this model makes an attack that targets a Character unit, you can re-roll "
    "the Hit roll and you can re-roll the Wound roll. Each time this model destroys an "
    "enemy Character unit, you gain 1CP."
)
OPPONENT_STRATAGEM_COST_TEXT = (
    'Once per turn, when your opponent targets a unit from their army within 12" of this '
    "model with a stratagem, you can use this ability. If you do, increase the CP cost of "
    "the use of that stratagem by 1CP."
)
OWN_STRATAGEM_COST_TEXT = (
    "Once per battle round, one unit from your army with this ability can use it when its "
    "unit is targeted with a Stratagem. If it does, reduce the CP cost of that use of that "
    "Stratagem by 1CP."
)
LEADERSHIP_COMMAND_POINT_TEXT = (
    "At the end of your Command phase, if this model is on the battlefield, take a "
    "Leadership test for this model; if that test is passed, you gain 1CP."
)
DIRECT_PHASE_COMMAND_POINT_TEXT = (
    "At the start of your Command phase, if this model is on the battlefield, you gain 1CP."
)
FIXED_ROLL_COMMAND_POINT_TEXT = (
    "At the end of your Command phase, roll one D6: on a 1+, you gain 1CP."
)


def test_catalog_desperate_escape_consumer_uses_source_rule_ir_and_state_context() -> None:
    target_army, source_army = _mustered_core_armies()
    target_unit = target_army.units[0]
    source_unit = source_army.units[0]
    battlefield = _battlefield_for_units(
        source_army=source_army,
        source_unit=source_unit,
        source_x=10.4,
        target_army=target_army,
        target_unit=target_unit,
        target_x=10.0,
    )
    state = _state_with_battlefield(
        armies=(target_army, source_army),
        battlefield=battlefield,
        active_player_id=target_army.player_id,
        phase=BattlePhase.MOVEMENT,
    )
    state.battle_shocked_unit_ids = [target_unit.unit_instance_id]
    record = _desperate_escape_record(source_unit=source_unit)

    sources = catalog_forced_desperate_escape_sources_for_unit(
        state=state,
        unit_instance_id=target_unit.unit_instance_id,
        ability_indexes_by_player_id={
            target_army.player_id: AbilityCatalogIndex.from_records(()),
            source_army.player_id: AbilityCatalogIndex.from_records((record,)),
        },
        armies=(target_army, source_army),
    )

    assert len(sources) == 1
    source = sources[0]
    assert source["source_kind"] == CATALOG_FORCED_DESPERATE_ESCAPE_SOURCE_KIND
    assert source["catalog_record_id"] == record.record_id
    assert source["forcing_unit_instance_id"] == source_unit.unit_instance_id
    assert source["fall_back_unit_instance_id"] == target_unit.unit_instance_id
    assert source["required_fall_back_mode"] == "desperate_escape"
    assert source["desperate_escape_roll_modifier"] == -1
    assert source["battle_round"] == 1
    assert source["phase"] == BattlePhase.MOVEMENT.value


def test_catalog_desperate_escape_consumer_filters_keywords_distance_and_shape_drift() -> None:
    target_army, source_army = _mustered_core_armies()
    target_unit = target_army.units[0]
    source_unit = source_army.units[0]
    record = _desperate_escape_record(source_unit=source_unit)
    indexes = {
        target_army.player_id: AbilityCatalogIndex.from_records(()),
        source_army.player_id: AbilityCatalogIndex.from_records((record,)),
    }
    far_state = _state_with_battlefield(
        armies=(target_army, source_army),
        battlefield=_battlefield_for_units(
            source_army=source_army,
            source_unit=source_unit,
            source_x=40.0,
            target_army=target_army,
            target_unit=target_unit,
            target_x=10.0,
        ),
        active_player_id=target_army.player_id,
        phase=BattlePhase.MOVEMENT,
    )

    assert (
        catalog_forced_desperate_escape_sources_for_unit(
            state=far_state,
            unit_instance_id=target_unit.unit_instance_id,
            ability_indexes_by_player_id=indexes,
            armies=(target_army, source_army),
        )
        == ()
    )

    monster_target = replace(
        target_unit,
        keywords=tuple(sorted((*target_unit.keywords, "MONSTER"))),
    )
    monster_target_army = _army_with_unit(target_army, monster_target)
    monster_state = _state_with_battlefield(
        armies=(monster_target_army, source_army),
        battlefield=_battlefield_for_units(
            source_army=source_army,
            source_unit=source_unit,
            source_x=10.4,
            target_army=monster_target_army,
            target_unit=monster_target,
            target_x=10.0,
        ),
        active_player_id=monster_target_army.player_id,
        phase=BattlePhase.MOVEMENT,
    )

    assert (
        catalog_forced_desperate_escape_sources_for_unit(
            state=monster_state,
            unit_instance_id=monster_target.unit_instance_id,
            ability_indexes_by_player_id=indexes,
            armies=(monster_target_army, source_army),
        )
        == ()
    )
    with pytest.raises(GameLifecycleError, match="requires GameState"):
        catalog_forced_desperate_escape_sources_for_unit(
            state=cast(GameState, object()),
            unit_instance_id=target_unit.unit_instance_id,
            ability_indexes_by_player_id=indexes,
            armies=(target_army, source_army),
        )
    with pytest.raises(GameLifecycleError, match="missing ability index"):
        catalog_forced_desperate_escape_sources_for_unit(
            state=far_state,
            unit_instance_id=target_unit.unit_instance_id,
            ability_indexes_by_player_id={target_army.player_id: indexes[target_army.player_id]},
            armies=(target_army, source_army),
        )


def test_catalog_desperate_escape_consumer_ignores_dead_engagement_placements() -> None:
    target_army, source_army = _mustered_core_armies()
    target_unit = target_army.units[0]
    source_unit = source_army.units[0]

    dead_source_unit = _unit_with_dead_model(source_unit, index=0)
    dead_source_army = _army_with_unit(source_army, dead_source_unit)
    dead_source_record = _desperate_escape_record(source_unit=dead_source_unit)
    dead_source_state = _state_with_battlefield(
        armies=(target_army, dead_source_army),
        battlefield=_battlefield_for_units_with_model_xs(
            source_army=dead_source_army,
            source_unit=dead_source_unit,
            source_model_xs=(10.4, 40.0, 42.0, 44.0, 46.0),
            target_army=target_army,
            target_unit=target_unit,
            target_model_xs=(10.0, 50.0, 52.0, 54.0, 56.0),
        ),
        active_player_id=target_army.player_id,
        phase=BattlePhase.MOVEMENT,
    )

    assert (
        catalog_forced_desperate_escape_sources_for_unit(
            state=dead_source_state,
            unit_instance_id=target_unit.unit_instance_id,
            ability_indexes_by_player_id={
                target_army.player_id: AbilityCatalogIndex.from_records(()),
                dead_source_army.player_id: AbilityCatalogIndex.from_records((dead_source_record,)),
            },
            armies=(target_army, dead_source_army),
        )
        == ()
    )

    dead_target_unit = _unit_with_dead_model(target_unit, index=0)
    dead_target_army = _army_with_unit(target_army, dead_target_unit)
    source_record = _desperate_escape_record(source_unit=source_unit)
    dead_target_state = _state_with_battlefield(
        armies=(dead_target_army, source_army),
        battlefield=_battlefield_for_units_with_model_xs(
            source_army=source_army,
            source_unit=source_unit,
            source_model_xs=(10.4, 40.0, 42.0, 44.0, 46.0),
            target_army=dead_target_army,
            target_unit=dead_target_unit,
            target_model_xs=(10.0, 50.0, 52.0, 54.0, 56.0),
        ),
        active_player_id=dead_target_army.player_id,
        phase=BattlePhase.MOVEMENT,
    )

    assert (
        catalog_forced_desperate_escape_sources_for_unit(
            state=dead_target_state,
            unit_instance_id=dead_target_unit.unit_instance_id,
            ability_indexes_by_player_id={
                dead_target_army.player_id: AbilityCatalogIndex.from_records(()),
                source_army.player_id: AbilityCatalogIndex.from_records((source_record,)),
            },
            armies=(dead_target_army, source_army),
        )
        == ()
    )


def test_catalog_selected_target_support_classifies_selection_and_effect_clauses() -> None:
    fight_selection = _fight_start_selection_clause()
    post_shoot_selection = _post_shoot_hit_selection_clause()
    skipped_effect = _effect_clause(
        clause_id="test:selected-target:effect:skipped",
        duration=None,
        effect_kind=RuleEffectKind.MODIFY_DICE_ROLL,
        roll_type="attack_sequence.hit",
        delta=1,
    )
    selected_effect = _effect_clause(
        clause_id="test:selected-target:effect:applied",
        duration=_duration("phase"),
        effect_kind=RuleEffectKind.MODIFY_DICE_ROLL,
        roll_type="attack_sequence.hit",
        delta=1,
    )
    breaker = _fight_start_selection_clause(clause_id="test:selected-target:selection:next")

    assert clause_is_fight_start_selection(fight_selection)
    assert not clause_is_fight_start_selection(post_shoot_selection)
    assert clause_is_post_shoot_hit_target_selection(post_shoot_selection)
    assert not clause_is_post_shoot_hit_target_selection(fight_selection)
    assert selected_effect_clauses_after(
        (fight_selection, skipped_effect, selected_effect, breaker),
        0,
    ) == (selected_effect,)

    effect = _effect(
        RuleEffectKind.MODIFY_DICE_ROLL,
        ("roll_type", "attack_sequence.hit"),
        ("delta", 1),
        ("selected_target_unit_instance_id", "old-target"),
    )
    transformed = effect_with_selected_target(
        effect,
        selected_target_unit_instance_id="new-target",
    )

    assert parameter_payload(transformed.parameters) == {
        "delta": 1,
        "roll_type": "attack_sequence.hit",
        "selected_target_unit_instance_id": "new-target",
    }
    with pytest.raises(GameLifecycleError, match="requires RuleClause"):
        clause_is_fight_start_selection(cast(RuleClause, object()))
    with pytest.raises(GameLifecycleError, match="requires RuleClause"):
        clause_is_post_shoot_hit_target_selection(cast(RuleClause, object()))


def test_catalog_selected_target_support_filters_generic_records_by_timing() -> None:
    fight_selection = _fight_start_selection_clause()
    fight_rule_ir = _rule_ir(
        source_id="test:selected-target:fight",
        clauses=(
            fight_selection,
            _effect_clause(
                clause_id="test:selected-target:selection:fight:effect",
                duration=_duration("phase"),
                effect_kind=RuleEffectKind.REROLL_PERMISSION,
                roll_type="attack_sequence.hit",
            ),
        ),
    )
    fight_record = _ability_record(
        record_id="record:selected-target:fight",
        rule_ir=fight_rule_ir,
        trigger_kind=TimingTriggerKind.START_PHASE,
        runtime_clause_id=fight_selection.clause_id,
    )
    any_phase_record = _ability_record(
        record_id="record:selected-target:any-phase",
        rule_ir=fight_rule_ir,
        trigger_kind=TimingTriggerKind.ANY_PHASE,
        runtime_clause_id=fight_selection.clause_id,
    )
    non_generic_record = _ability_record(
        record_id="record:selected-target:non-generic",
        rule_ir=fight_rule_ir,
        trigger_kind=TimingTriggerKind.START_PHASE,
        handler_id="record-only",
    )
    post_shoot_rule_ir = _rule_ir(
        source_id="test:selected-target:post-shoot",
        clauses=(
            _post_shoot_hit_selection_clause(),
            _effect_clause(
                clause_id="test:selected-target:selection:post-shoot:effect",
                duration=_duration("phase"),
                effect_kind=RuleEffectKind.SET_CONTEXTUAL_STATUS,
                status="benefit_of_cover",
                operation="deny",
            ),
        ),
    )
    post_shoot_record = _ability_record(
        record_id="record:selected-target:post-shoot",
        rule_ir=post_shoot_rule_ir,
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT,
    )
    index = AbilityCatalogIndex.from_records(
        (fight_record, any_phase_record, non_generic_record, post_shoot_record)
    )

    assert records_for_timing(index, TimingTriggerKind.START_PHASE) == (
        any_phase_record,
        fight_record,
    )
    assert has_fight_start_selected_target_records({"player-a": index})
    assert has_post_shoot_hit_target_effect_records({"player-a": index})
    assert catalog_selected_target_clauses_from_record(fight_record) == fight_rule_ir.clauses
    assert runtime_clause_id_from_record(fight_record) == fight_selection.clause_id
    with pytest.raises(GameLifecycleError, match="requires AbilityCatalogRecord"):
        catalog_selected_target_clauses_from_record(cast(AbilityCatalogRecord, object()))
    with pytest.raises(GameLifecycleError, match="requires AbilityCatalogRecord"):
        runtime_clause_id_from_record(cast(AbilityCatalogRecord, object()))


def test_catalog_selected_target_fight_start_runtime_records_selected_effect() -> None:
    source_army, target_army = _mustered_core_armies()
    source_unit = source_army.units[0]
    target_unit = target_army.units[0]
    battlefield = _battlefield_for_units(
        source_army=source_army,
        source_unit=source_unit,
        source_x=10.0,
        target_army=target_army,
        target_unit=target_unit,
        target_x=10.4,
    )
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=battlefield,
        active_player_id=source_army.player_id,
        phase=BattlePhase.FIGHT,
    )
    selection_clause = _fight_start_selection_clause()
    effect_clause = _effect_clause(
        clause_id="test:selected-target:selection:fight:effect",
        duration=_duration("phase"),
        effect_kind=RuleEffectKind.REROLL_PERMISSION,
        roll_type="attack_sequence.hit",
    )
    rule_ir = _rule_ir(
        source_id="test:selected-target:fight-runtime",
        clauses=(selection_clause, effect_clause),
    )
    record = _ability_record(
        record_id="record:selected-target:fight-runtime",
        rule_ir=rule_ir,
        trigger_kind=TimingTriggerKind.START_PHASE,
        runtime_clause_id=selection_clause.clause_id,
    )
    runtime = CatalogSelectedTargetEffectRuntime(
        ability_indexes_by_player_id={
            source_army.player_id: AbilityCatalogIndex.from_records((record,)),
            target_army.player_id: AbilityCatalogIndex.from_records(()),
        },
        armies=(source_army, target_army),
    )
    decisions = DecisionController()

    bindings = runtime.fight_phase_start_bindings()
    request = runtime.fight_phase_start_request(
        FightPhaseStartRequestContext(state=state, decisions=decisions)
    )

    assert len(bindings) == 1
    assert request is not None
    assert request.decision_type == SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE
    assert [option.option_id for option in request.options] == sorted(
        option.option_id for option in request.options
    )
    assert len(request.options) == 1
    request_payload = cast(dict[str, JsonValue], request.payload)
    assert request_payload["catalog_record_id"] == record.record_id
    assert request_payload["available_target_unit_instance_ids"] == [target_unit.unit_instance_id]

    queued = decisions.request_decision(request)
    result = DecisionResult.for_request(
        result_id="result:selected-target:fight-runtime",
        request=queued,
        selected_option_id=queued.options[0].option_id,
    )
    decisions.submit_result(result)
    applied = runtime.apply_fight_phase_start_result(
        FightPhaseStartResultContext(
            state=state,
            decisions=decisions,
            request=queued,
            result=result,
        )
    )

    assert applied is True
    assert len(state.persisting_effects) == 1
    effect = state.persisting_effects[0]
    assert effect.owner_player_id == source_army.player_id
    assert effect.target_unit_instance_ids == (target_unit.unit_instance_id,)
    effect_payload = cast(dict[str, JsonValue], effect.effect_payload)
    selected_metadata = cast(dict[str, JsonValue], effect_payload["catalog_selected_target"])
    transformed_effect = cast(dict[str, JsonValue], effect_payload["effect"])
    assert selected_metadata["selected_target_unit_instance_id"] == target_unit.unit_instance_id
    assert selected_metadata["source_unit_instance_id"] == source_unit.unit_instance_id
    assert transformed_effect["kind"] == RuleEffectKind.REROLL_PERMISSION.value
    effect_parameters = cast(list[dict[str, JsonValue]], transformed_effect["parameters"])
    assert {cast(str, parameter["key"]): parameter["value"] for parameter in effect_parameters}[
        "selected_target_unit_instance_id"
    ] == target_unit.unit_instance_id
    assert (
        decisions.event_log.records[-1].event_type == CATALOG_SELECTED_TARGET_EFFECT_SELECTED_EVENT
    )


def test_catalog_once_per_battle_runtime_declines_then_activates_once_with_replay() -> None:
    source_army, target_army = _mustered_once_per_battle_armies()
    source_unit = source_army.units[0]
    target_unit = target_army.units[0]
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=_battlefield_for_units(
            source_army=source_army,
            source_unit=source_unit,
            source_x=10.0,
            target_army=target_army,
            target_unit=target_unit,
            target_x=20.0,
        ),
        active_player_id=source_army.player_id,
        phase=BattlePhase.FIGHT,
    )
    record = _once_per_battle_record(source_unit=source_unit)
    runtime = CatalogOncePerBattleRuntime(
        ability_indexes_by_player_id={
            source_army.player_id: AbilityCatalogIndex.from_records((record,)),
            target_army.player_id: AbilityCatalogIndex.from_records(()),
        },
        armies=(source_army, target_army),
    )
    decisions = DecisionController()

    request = runtime.fight_phase_start_request(
        FightPhaseStartRequestContext(state=state, decisions=decisions)
    )
    assert request is not None
    assert DecisionRequest.from_payload(request.to_payload()) == request
    assert request.decision_type == SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE
    activation_choices = [
        cast(dict[str, JsonValue], option.payload)["activate"] for option in request.options
    ]
    assert activation_choices == [False, True]

    queued = decisions.request_decision(request)
    declined = DecisionResult.for_request(
        result_id="result:once-per-battle:declined",
        request=queued,
        selected_option_id=queued.options[0].option_id,
    )
    decisions.submit_result(declined)
    assert (
        runtime.apply_fight_phase_start_result(
            FightPhaseStartResultContext(
                state=state,
                decisions=decisions,
                request=queued,
                result=declined,
            )
        )
        is True
    )
    assert not state.persisting_effects
    assert decisions.event_log.records[-1].event_type == (
        CATALOG_ONCE_PER_BATTLE_ABILITY_DECLINED_EVENT
    )
    assert (
        runtime.fight_phase_start_request(
            FightPhaseStartRequestContext(state=state, decisions=decisions)
        )
        is None
    )

    state.battle_round = 2
    activation_request = runtime.fight_phase_start_request(
        FightPhaseStartRequestContext(state=state, decisions=decisions)
    )
    assert activation_request is not None
    queued_activation = decisions.request_decision(activation_request)
    activated = DecisionResult.for_request(
        result_id="result:once-per-battle:activated",
        request=queued_activation,
        selected_option_id=queued_activation.options[1].option_id,
    )
    decisions.submit_result(activated)
    assert (
        runtime.apply_fight_phase_start_result(
            FightPhaseStartResultContext(
                state=state,
                decisions=decisions,
                request=queued_activation,
                result=activated,
            )
        )
        is True
    )

    assert len(state.persisting_effects) == 2
    assert any(
        event.event_type == RULE_FREQUENCY_LIMIT_CONSUMED_EVENT
        for event in decisions.event_log.records
    )
    assert decisions.event_log.records[-1].event_type == (
        CATALOG_ONCE_PER_BATTLE_ABILITY_ACTIVATED_EVENT
    )
    assert (
        runtime.fight_phase_start_request(
            FightPhaseStartRequestContext(state=state, decisions=decisions)
        )
        is None
    )
    assert DecisionController.from_payload(decisions.to_payload()).to_payload() == (
        decisions.to_payload()
    )
    restored_state = GameState.from_payload(state.to_payload())
    assert [effect.to_payload() for effect in restored_state.persisting_effects] == [
        effect.to_payload() for effect in state.persisting_effects
    ]


def test_catalog_once_per_battle_runtime_rejects_source_model_drift_without_mutation() -> None:
    source_army, target_army = _mustered_once_per_battle_armies()
    source_unit = source_army.units[0]
    source_model = source_unit.own_models[0]
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=_battlefield_for_units(
            source_army=source_army,
            source_unit=source_unit,
            source_x=10.0,
            target_army=target_army,
            target_unit=target_army.units[0],
            target_x=20.0,
        ),
        active_player_id=source_army.player_id,
        phase=BattlePhase.FIGHT,
    )
    runtime = CatalogOncePerBattleRuntime(
        ability_indexes_by_player_id={
            source_army.player_id: AbilityCatalogIndex.from_records(
                (_once_per_battle_record(source_unit=source_unit),)
            ),
            target_army.player_id: AbilityCatalogIndex.from_records(()),
        },
        armies=(source_army, target_army),
    )
    decisions = DecisionController()
    request = runtime.fight_phase_start_request(
        FightPhaseStartRequestContext(state=state, decisions=decisions)
    )
    assert request is not None
    queued = decisions.request_decision(request)
    result = DecisionResult.for_request(
        result_id="result:once-per-battle:drift",
        request=queued,
        selected_option_id=queued.options[1].option_id,
    )
    decisions.submit_result(result)
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.with_removed_models(
        (source_model.model_instance_id,)
    )

    status = runtime.apply_fight_phase_start_result(
        FightPhaseStartResultContext(
            state=state,
            decisions=decisions,
            request=queued,
            result=result,
        )
    )

    assert type(status) is LifecycleStatus
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert cast(dict[str, JsonValue], status.payload)["invalid_reason"] == (
        "once_per_battle_activation_drift"
    )
    assert not state.persisting_effects
    assert all(
        event.event_type != RULE_FREQUENCY_LIMIT_CONSUMED_EVENT
        for event in decisions.event_log.records
    )


def test_catalog_once_per_battle_runtime_rejects_actor_drift_without_mutation() -> None:
    source_army, target_army = _mustered_once_per_battle_armies()
    source_unit = source_army.units[0]
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=_battlefield_for_units(
            source_army=source_army,
            source_unit=source_unit,
            source_x=10.0,
            target_army=target_army,
            target_unit=target_army.units[0],
            target_x=20.0,
        ),
        active_player_id=source_army.player_id,
        phase=BattlePhase.FIGHT,
    )
    runtime = CatalogOncePerBattleRuntime(
        ability_indexes_by_player_id={
            source_army.player_id: AbilityCatalogIndex.from_records(
                (_once_per_battle_record(source_unit=source_unit),)
            ),
            target_army.player_id: AbilityCatalogIndex.from_records(()),
        },
        armies=(source_army, target_army),
    )
    decisions = DecisionController()
    request = runtime.fight_phase_start_request(
        FightPhaseStartRequestContext(state=state, decisions=decisions)
    )
    assert request is not None
    result = replace(
        DecisionResult.for_request(
            result_id="result:once-per-battle:actor-drift",
            request=request,
            selected_option_id=request.options[1].option_id,
        ),
        actor_id=target_army.player_id,
    )

    status = runtime.apply_fight_phase_start_result(
        FightPhaseStartResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
        )
    )

    assert type(status) is LifecycleStatus
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert cast(dict[str, JsonValue], status.payload)["invalid_reason"] == (
        "once_per_battle_actor_drift"
    )
    assert not state.persisting_effects
    assert all(
        event.event_type != RULE_FREQUENCY_LIMIT_CONSUMED_EVENT
        for event in decisions.event_log.records
    )


def test_catalog_once_per_battle_runtime_targets_attached_rules_unit_for_leader_model() -> None:
    source_army, target_army = _mustered_attached_once_per_battle_armies()
    source_unit = next(
        unit for unit in source_army.units if unit.datasheet_id == "core-character-leader"
    )
    source_rules_unit_id = source_army.attached_units[0].attached_unit_instance_id
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="catalog-once-per-battle-attached",
        armies=(source_army, target_army),
    )
    state = _state_without_battlefield(
        active_player_id=source_army.player_id,
        phase=BattlePhase.FIGHT,
    )
    for army in (source_army, target_army):
        state.record_army_definition(army)
    state.battlefield_state = scenario.battlefield_state
    runtime = CatalogOncePerBattleRuntime(
        ability_indexes_by_player_id={
            source_army.player_id: AbilityCatalogIndex.from_records(
                (_once_per_battle_record(source_unit=source_unit),)
            ),
            target_army.player_id: AbilityCatalogIndex.from_records(()),
        },
        armies=(source_army, target_army),
    )
    decisions = DecisionController()

    request = runtime.fight_phase_start_request(
        FightPhaseStartRequestContext(state=state, decisions=decisions)
    )
    assert request is not None
    payload = cast(dict[str, JsonValue], request.payload)
    assert payload["source_unit_instance_id"] == source_unit.unit_instance_id
    assert payload["source_rules_unit_instance_id"] == source_rules_unit_id
    queued = decisions.request_decision(request)
    result = DecisionResult.for_request(
        result_id="result:once-per-battle:attached-leader",
        request=queued,
        selected_option_id=queued.options[1].option_id,
    )
    decisions.submit_result(result)

    assert (
        runtime.apply_fight_phase_start_result(
            FightPhaseStartResultContext(
                state=state,
                decisions=decisions,
                request=queued,
                result=result,
            )
        )
        is True
    )
    assert len(state.persisting_effects) == 2
    assert all(
        effect.target_unit_instance_ids == (source_rules_unit_id,)
        for effect in state.persisting_effects
    )


def test_catalog_selected_target_runtime_fail_fast_and_empty_paths() -> None:
    source_army, target_army = _mustered_core_armies()
    source_unit = source_army.units[0]
    selection_clause = _fight_start_selection_clause()
    rule_ir = _rule_ir(
        source_id="test:selected-target:fight-runtime-empty-paths",
        clauses=(
            selection_clause,
            _effect_clause(
                clause_id="test:selected-target:selection:fight:empty-paths-effect",
                duration=_duration("phase"),
                effect_kind=RuleEffectKind.REROLL_PERMISSION,
                roll_type="attack_sequence.hit",
            ),
        ),
    )
    record = _ability_record(
        record_id="record:selected-target:fight-runtime-empty-paths",
        rule_ir=rule_ir,
        trigger_kind=TimingTriggerKind.START_PHASE,
        runtime_clause_id=selection_clause.clause_id,
    )
    empty_index = AbilityCatalogIndex.from_records(())

    with pytest.raises(GameLifecycleError, match="missing ability index"):
        CatalogSelectedTargetEffectRuntime(
            ability_indexes_by_player_id={source_army.player_id: empty_index},
            armies=(source_army, target_army),
        )

    empty_runtime = CatalogSelectedTargetEffectRuntime(
        ability_indexes_by_player_id={
            source_army.player_id: empty_index,
            target_army.player_id: empty_index,
        },
        armies=(source_army, target_army),
    )
    assert empty_runtime.fight_phase_start_bindings() == ()
    assert empty_runtime.attack_sequence_completed_bindings() == ()

    runtime = CatalogSelectedTargetEffectRuntime(
        ability_indexes_by_player_id={
            source_army.player_id: AbilityCatalogIndex.from_records((record,)),
            target_army.player_id: empty_index,
        },
        armies=(source_army, target_army),
    )
    no_battlefield_state = _state_without_battlefield(
        active_player_id=source_army.player_id,
        phase=BattlePhase.FIGHT,
    )
    no_battlefield_state.army_definitions = [source_army, target_army]
    assert (
        runtime.fight_phase_start_request(
            FightPhaseStartRequestContext(
                state=no_battlefield_state,
                decisions=DecisionController(),
            )
        )
        is None
    )
    with pytest.raises(GameLifecycleError, match="Fight-start requires context"):
        runtime.apply_fight_phase_start_result(cast(FightPhaseStartResultContext, object()))

    battlefield = _battlefield_for_units(
        source_army=source_army,
        source_unit=source_unit,
        source_x=10.0,
        target_army=target_army,
        target_unit=target_army.units[0],
        target_x=10.4,
    )
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=battlefield,
        active_player_id=source_army.player_id,
        phase=BattlePhase.FIGHT,
    )
    wrong_hook_request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE,
        actor_id=source_army.player_id,
        payload={"hook_id": "other-hook"},
        options=(
            DecisionOption(
                option_id="wrong-hook-option",
                label="Wrong Hook Option",
                payload={"hook_id": "other-hook"},
            ),
        ),
    )
    wrong_hook_result = DecisionResult.for_request(
        result_id="result:selected-target:wrong-hook",
        request=wrong_hook_request,
        selected_option_id="wrong-hook-option",
    )

    assert (
        runtime.apply_fight_phase_start_result(
            FightPhaseStartResultContext(
                state=state,
                decisions=DecisionController(),
                request=wrong_hook_request,
                result=wrong_hook_result,
            )
        )
        is False
    )
    with pytest.raises(GameLifecycleError, match="apply requires decisions"):
        apply_catalog_post_shoot_hit_target_effect_result(
            state=state,
            decisions=cast(DecisionController, object()),
            result=wrong_hook_result,
        )
    with pytest.raises(GameLifecycleError, match="apply requires result"):
        apply_catalog_post_shoot_hit_target_effect_result(
            state=state,
            decisions=DecisionController(),
            result=cast(DecisionResult, object()),
        )


def test_catalog_selected_target_support_validates_payloads_and_status_gates() -> None:
    payload = {
        "id": "payload-id",
        "count": 2,
        "ids": ["target-b", "target-a"],
        "generic_rule_effect_records": [{"source_rule_id": "source-a"}],
        "selected_catalog_target_effect": {
            "option_id": "option-a",
            "target_unit_instance_id": "target-a",
        },
    }
    state = _state_without_battlefield(active_player_id="player-a", phase=BattlePhase.FIGHT)
    status_clause = _effect_clause(
        clause_id="test:selected-target:status-gated",
        duration=_duration("phase"),
        effect_kind=RuleEffectKind.REROLL_PERMISSION,
        roll_type="attack_sequence.hit",
        conditions=(
            _condition(
                RuleConditionKind.TARGET_CONSTRAINT,
                ("relationship", "target_unit_has_status"),
                ("status", "battle_shocked"),
            ),
        ),
    )

    assert payload_object(payload) == payload
    assert payload_string(payload, key="id") == "payload-id"
    assert payload_int(payload, key="count") == 2
    assert payload_string_tuple(payload, key="ids") == ("target-a", "target-b")
    assert payload_effect_records(payload) == ({"source_rule_id": "source-a"},)
    assert selected_payload(payload)["option_id"] == "option-a"
    assert validate_identifier_tuple("ids", ("b", "a")) == ("a", "b")
    assert validate_effect_record_tuple(({"nested": ["value"]},)) == ({"nested": ["value"]},)
    assert active_player_id(state) == "player-a"
    assert battle_phase_kind(BattlePhase.FIGHT) is BattlePhaseKind.FIGHT
    assert battle_phase_kind(BattlePhase.SHOOTING) is BattlePhaseKind.SHOOTING
    assert timing_window_id(BattlePhase.FIGHT) == "fight_phase_start"
    assert timing_window_id(BattlePhase.SHOOTING) == "attack_sequence_completed"
    state.battle_shocked_unit_ids = ["target-a"]
    assert selected_target_status_gate_allows(
        state=state,
        clause=status_clause,
        selected_target_unit_instance_id="target-a",
    )
    state.battle_shocked_unit_ids = []
    assert not selected_target_status_gate_allows(
        state=state,
        clause=status_clause,
        selected_target_unit_instance_id="target-a",
    )

    bad_status_clause = replace(
        status_clause,
        conditions=(
            _condition(
                RuleConditionKind.TARGET_CONSTRAINT,
                ("relationship", "target_unit_has_status"),
                ("status", "poisoned"),
            ),
        ),
    )
    with pytest.raises(GameLifecycleError, match="status is unsupported"):
        selected_target_status_gate_allows(
            state=state,
            clause=bad_status_clause,
            selected_target_unit_instance_id="target-a",
        )
    inactive_state = _state_without_battlefield(
        active_player_id="player-a",
        phase=BattlePhase.FIGHT,
    )
    inactive_state.active_player_id = None
    with pytest.raises(GameLifecycleError, match="requires active_player_id"):
        active_player_id(inactive_state)
    with pytest.raises(GameLifecycleError, match="phase is unsupported"):
        battle_phase_kind(BattlePhase.COMMAND)
    with pytest.raises(GameLifecycleError, match="phase is unsupported"):
        timing_window_id(BattlePhase.COMMAND)
    with pytest.raises(GameLifecycleError, match="must be an object"):
        payload_object(())
    with pytest.raises(GameLifecycleError, match="must be a string"):
        payload_string({"id": 1}, key="id")
    with pytest.raises(GameLifecycleError, match="must be an int"):
        payload_int({"count": True}, key="count")
    with pytest.raises(GameLifecycleError, match="must be a list"):
        payload_string_tuple({"ids": ("a",)}, key="ids")
    with pytest.raises(GameLifecycleError, match="must be strings"):
        payload_string_tuple({"ids": [1]}, key="ids")
    with pytest.raises(GameLifecycleError, match="effect records must be a list"):
        payload_effect_records({"generic_rule_effect_records": ()})
    with pytest.raises(GameLifecycleError, match="effect record must be an object"):
        payload_effect_records({"generic_rule_effect_records": [1]})
    with pytest.raises(GameLifecycleError, match="selected payload must be an object"):
        selected_payload({"selected_catalog_target_effect": ()})
    with pytest.raises(GameLifecycleError, match="effect records must be a tuple"):
        validate_effect_record_tuple([])
    with pytest.raises(GameLifecycleError, match="effect record must be an object"):
        validate_effect_record_tuple((1,))
    with pytest.raises(GameLifecycleError, match="ids must be a tuple"):
        validate_identifier_tuple("ids", ["a"])


def test_catalog_selected_target_support_uses_real_battlefield_target_resolution() -> None:
    source_army, target_army = _mustered_core_armies()
    source_unit = source_army.units[0]
    target_unit = target_army.units[0]
    battlefield = _battlefield_for_units(
        source_army=source_army,
        source_unit=source_unit,
        source_x=10.0,
        target_army=target_army,
        target_unit=target_unit,
        target_x=10.4,
    )
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=battlefield,
        active_player_id=source_army.player_id,
        phase=BattlePhase.FIGHT,
    )
    distance_selection = replace(
        _fight_start_selection_clause(),
        conditions=(
            _condition(
                RuleConditionKind.DISTANCE_PREDICATE,
                ("object_kind", "model"),
                ("object_reference", "this"),
                ("predicate", "within_engagement_range"),
                ("range_kind", "engagement_range"),
            ),
        ),
    )
    source_model_ids = source_unit.own_model_ids()

    assert eligible_selection_target_unit_ids(
        state=state,
        source_player_id=source_army.player_id,
        source_unit_instance_id=source_unit.unit_instance_id,
        source_model_instance_id=None,
        selection_clause=distance_selection,
        explicit_target_unit_ids=None,
    ) == (target_unit.unit_instance_id,)
    assert (
        eligible_selection_target_unit_ids(
            state=state,
            source_player_id=source_army.player_id,
            source_unit_instance_id=source_unit.unit_instance_id,
            source_model_instance_id=None,
            selection_clause=distance_selection,
            explicit_target_unit_ids=("other-target",),
        )
        == ()
    )
    assert (
        selection_source_model_ids(
            selection_clause=distance_selection,
            current_model_instance_ids=source_model_ids,
        )
        == source_model_ids
    )
    assert effect_target_unit_ids(
        state=state,
        source_player_id=source_army.player_id,
        source_unit=source_unit,
        selected_target_unit_instance_id=target_unit.unit_instance_id,
        clause=replace(
            _effect_clause(
                clause_id="test:selected-target:this-unit",
                duration=_duration("phase"),
                effect_kind=RuleEffectKind.MODIFY_CHARACTERISTIC,
                characteristic="attacks",
                delta=1,
            ),
            target=RuleTargetSpec(kind=RuleTargetKind.THIS_UNIT, source_span=_span()),
        ),
    ) == (source_unit.unit_instance_id,)
    assert effect_target_unit_ids(
        state=state,
        source_player_id=source_army.player_id,
        source_unit=source_unit,
        selected_target_unit_instance_id=target_unit.unit_instance_id,
        clause=replace(
            _effect_clause(
                clause_id="test:selected-target:selected-unit",
                duration=_duration("phase"),
                effect_kind=RuleEffectKind.SET_CONTEXTUAL_STATUS,
                status="benefit_of_cover",
                operation="deny",
            ),
            target=RuleTargetSpec(kind=RuleTargetKind.SELECTED_TARGET, source_span=_span()),
        ),
    ) == (target_unit.unit_instance_id,)

    friendly_clause = replace(
        _effect_clause(
            clause_id="test:selected-target:friendly-unit",
            duration=_duration("phase"),
            effect_kind=RuleEffectKind.MODIFY_CHARACTERISTIC,
            characteristic="objective_control",
            delta=1,
            conditions=(
                _condition(
                    RuleConditionKind.KEYWORD_GATE,
                    ("required_keyword", "INFANTRY"),
                ),
            ),
        ),
        target=RuleTargetSpec(
            kind=RuleTargetKind.FRIENDLY_UNIT,
            source_span=_span(),
            parameters=_parameters(("required_keyword_sequence", ("IMPERIUM",))),
        ),
    )

    assert required_keywords_for_clause(friendly_clause) == ("IMPERIUM", "INFANTRY")
    assert (
        effect_target_unit_ids(
            state=state,
            source_player_id=source_army.player_id,
            source_unit=source_unit,
            selected_target_unit_instance_id=target_unit.unit_instance_id,
            clause=friendly_clause,
        )
        == ()
    )
    with pytest.raises(GameLifecycleError, match="numeric range is malformed"):
        any_models_satisfy_distance(
            source_models=(),
            target_models=(),
            parameters={"range_kind": "numeric_range"},
        )


def test_catalog_selected_target_distance_gate_ignores_dead_placements() -> None:
    source_army, target_army = _mustered_core_armies()
    source_unit = source_army.units[0]
    target_unit = target_army.units[0]
    distance_selection = replace(
        _fight_start_selection_clause(),
        conditions=(
            _condition(
                RuleConditionKind.DISTANCE_PREDICATE,
                ("object_kind", "model"),
                ("object_reference", "this"),
                ("predicate", "within_engagement_range"),
                ("range_kind", "engagement_range"),
            ),
        ),
    )

    dead_source_unit = _unit_with_dead_model(source_unit, index=0)
    dead_source_army = _army_with_unit(source_army, dead_source_unit)
    dead_source_state = _state_with_battlefield(
        armies=(dead_source_army, target_army),
        battlefield=_battlefield_for_units_with_model_xs(
            source_army=dead_source_army,
            source_unit=dead_source_unit,
            source_model_xs=(10.0, 30.0, 32.0, 34.0, 36.0),
            target_army=target_army,
            target_unit=target_unit,
            target_model_xs=(10.4, 40.0, 42.0, 44.0, 46.0),
        ),
        active_player_id=dead_source_army.player_id,
        phase=BattlePhase.FIGHT,
    )

    assert (
        eligible_selection_target_unit_ids(
            state=dead_source_state,
            source_player_id=dead_source_army.player_id,
            source_unit_instance_id=dead_source_unit.unit_instance_id,
            source_model_instance_id=None,
            selection_clause=distance_selection,
            explicit_target_unit_ids=None,
        )
        == ()
    )

    dead_target_unit = _unit_with_dead_model(target_unit, index=0)
    dead_target_army = _army_with_unit(target_army, dead_target_unit)
    dead_target_state = _state_with_battlefield(
        armies=(source_army, dead_target_army),
        battlefield=_battlefield_for_units_with_model_xs(
            source_army=source_army,
            source_unit=source_unit,
            source_model_xs=(10.0, 30.0, 32.0, 34.0, 36.0),
            target_army=dead_target_army,
            target_unit=dead_target_unit,
            target_model_xs=(10.4, 40.0, 42.0, 44.0, 46.0),
        ),
        active_player_id=source_army.player_id,
        phase=BattlePhase.FIGHT,
    )

    assert (
        eligible_selection_target_unit_ids(
            state=dead_target_state,
            source_player_id=source_army.player_id,
            source_unit_instance_id=source_unit.unit_instance_id,
            source_model_instance_id=None,
            selection_clause=distance_selection,
            explicit_target_unit_ids=None,
        )
        == ()
    )


def test_catalog_command_point_bundle_registers_source_backed_generic_consumers() -> None:
    source_army, target_army = _mustered_once_per_battle_armies()
    source_unit = source_army.units[0]
    target_unit = target_army.units[0]
    destroyed_record = _command_point_record(
        record_id="record:catalog-cp:destroyed-character",
        raw_text=DESTROYED_CHARACTER_COMMAND_POINT_TEXT,
        source_unit=source_unit,
        trigger_kind=TimingTriggerKind.AFTER_UNIT_DESTROYED,
    )
    leadership_record = _command_point_record(
        record_id="record:catalog-cp:leadership",
        raw_text=LEADERSHIP_COMMAND_POINT_TEXT,
        source_unit=source_unit,
        trigger_kind=TimingTriggerKind.END_PHASE,
    )
    opponent_cost_record = _command_point_record(
        record_id="record:catalog-cp:opponent-cost",
        raw_text=OPPONENT_STRATAGEM_COST_TEXT,
        source_unit=source_unit,
        trigger_kind=TimingTriggerKind.ANY_PHASE,
    )
    own_cost_record = _command_point_record(
        record_id="record:catalog-cp:own-cost",
        raw_text=OWN_STRATAGEM_COST_TEXT,
        source_unit=target_unit,
        trigger_kind=TimingTriggerKind.ANY_PHASE,
    )
    catalog = ArmyCatalog.phase9a_canonical_content_pack()

    bundle = RuntimeContentBundle.from_contributions(
        activation=RuntimeContentActivation.from_armies(
            armies=(source_army, target_army),
            catalog=catalog,
        ),
        armies=(source_army, target_army),
        catalog=catalog,
        contributions=(),
        base_ability_records=(
            destroyed_record,
            leadership_record,
            opponent_cost_record,
            own_cost_record,
        ),
    )

    assert CATALOG_IR_COMMAND_POINT_GAIN_CONSUMER_ID in {
        binding.hook_id for binding in bundle.unit_destroyed_hook_registry.all_bindings()
    }
    assert {
        binding.source_id for binding in bundle.stratagem_cost_modifier_registry.all_bindings()
    } == {opponent_cost_record.definition.source_id, own_cost_record.definition.source_id}
    assert {
        binding.source_id for binding in bundle.stratagem_cost_choice_hook_registry.all_bindings()
    } >= {CATALOG_IR_STRATAGEM_COST_MODIFIER_CONSUMER_ID}
    subscriptions = bundle.event_index.subscriptions_for(TimingTriggerKind.END_PHASE)
    assert any(
        subscription.source_rule_id == leadership_record.definition.source_id
        and subscription.filters
        == {
            "phase": BattlePhaseKind.COMMAND.value,
            "player_id": source_army.player_id,
        }
        for subscription in subscriptions
    )


def test_catalog_command_point_destroyed_character_gain_is_scoped_and_idempotent() -> None:
    source_army, target_army = _mustered_once_per_battle_armies()
    source_unit = source_army.units[0]
    character_target = replace(
        target_army.units[0],
        keywords=tuple(sorted((*target_army.units[0].keywords, "CHARACTER"))),
    )
    target_army = _army_with_unit(target_army, character_target)
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=_battlefield_for_units(
            source_army=source_army,
            source_unit=source_unit,
            source_x=10.0,
            target_army=target_army,
            target_unit=character_target,
            target_x=20.0,
        ),
        active_player_id=source_army.player_id,
        phase=BattlePhase.SHOOTING,
    )
    record = _command_point_record(
        record_id="record:catalog-cp:destroyed-character-runtime",
        raw_text=DESTROYED_CHARACTER_COMMAND_POINT_TEXT,
        source_unit=source_unit,
        trigger_kind=TimingTriggerKind.AFTER_UNIT_DESTROYED,
    )
    runtime = _command_point_runtime(
        armies=(source_army, target_army),
        records_by_player={source_army.player_id: (record,)},
    )
    decisions = DecisionController()
    attacker_model_id = source_unit.own_models[0].model_instance_id
    destroyed_event = decisions.event_log.append(
        "model_destroyed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": BattlePhase.SHOOTING.value,
            "destroying_player_id": source_army.player_id,
            "attacking_model_instance_id": attacker_model_id,
            "target_unit_instance_id": character_target.unit_instance_id,
            "model_instance_id": character_target.own_models[0].model_instance_id,
        },
    )
    destroyed_payload = cast(dict[str, JsonValue], destroyed_event.payload)
    context = UnitDestroyedContext(
        state=state,
        decisions=decisions,
        completed_phase=BattlePhase.SHOOTING,
        model_destroyed_event_id=destroyed_event.event_id,
        model_destroyed_payload=destroyed_payload,
        destroying_player_id=source_army.player_id,
        destroyed_unit_instance_id=character_target.unit_instance_id,
        destroyed_player_id=target_army.player_id,
    )

    runtime.resolve_unit_destroyed(context)
    runtime.resolve_unit_destroyed(context)

    assert state.command_point_total(source_army.player_id) == 1
    gain_events = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == CATALOG_IR_COMMAND_POINT_GAIN_EVENT
    )
    assert len(gain_events) == 1
    payload = cast(dict[str, JsonValue], gain_events[0].payload)
    assert payload["source_record_id"] == record.record_id
    assert payload["source_model_instance_id"] == attacker_model_id
    assert payload["destroyed_unit_instance_id"] == character_target.unit_instance_id


def test_catalog_command_point_leadership_gain_dispatches_at_owner_command_phase_end() -> None:
    source_army, target_army = _mustered_once_per_battle_armies()
    source_unit = _unit_with_leadership(source_army.units[0], leadership=2)
    source_army = _army_with_unit(source_army, source_unit)
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=_battlefield_for_units(
            source_army=source_army,
            source_unit=source_unit,
            source_x=10.0,
            target_army=target_army,
            target_unit=target_army.units[0],
            target_x=20.0,
        ),
        active_player_id=source_army.player_id,
        phase=BattlePhase.COMMAND,
    )
    record = _command_point_record(
        record_id="record:catalog-cp:leadership-runtime",
        raw_text=LEADERSHIP_COMMAND_POINT_TEXT,
        source_unit=source_unit,
        trigger_kind=TimingTriggerKind.END_PHASE,
    )
    runtime = _command_point_runtime(
        armies=(source_army, target_army),
        records_by_player={source_army.player_id: (record,)},
    )
    handler_registry = RuntimeContentEventHandlerRegistry.from_bindings(
        runtime.event_handler_bindings()
    )
    event_index = RuntimeContentEventIndex.from_subscriptions(
        runtime.event_subscriptions(),
        handler_registry=handler_registry,
    )
    decisions = DecisionController()

    results = event_index.dispatch(
        RuntimeContentEvent(
            event_id="runtime-event:catalog-cp:leadership",
            game_id=state.game_id,
            player_id=source_army.player_id,
            battle_round=state.battle_round,
            trigger_kind=TimingTriggerKind.END_PHASE,
            phase=BattlePhaseKind.COMMAND,
            active_player_id=source_army.player_id,
        ),
        state=state,
        decisions=decisions,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=ArmyCatalog.phase9a_canonical_content_pack(),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )

    assert len(results) == 1
    assert state.command_point_total(source_army.player_id) == 1
    resolution_events = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == CATALOG_IR_COMMAND_POINT_LEADERSHIP_TEST_EVENT
    )
    assert len(resolution_events) == 1
    resolution = cast(dict[str, JsonValue], resolution_events[0].payload)
    assert resolution["passed"] is True
    assert resolution["leadership_target"] == 2
    assert resolution["source_record_id"] == record.record_id


@pytest.mark.parametrize(
    ("raw_text", "trigger_kind", "expects_dice_roll"),
    [
        (DIRECT_PHASE_COMMAND_POINT_TEXT, TimingTriggerKind.START_PHASE, False),
        (FIXED_ROLL_COMMAND_POINT_TEXT, TimingTriggerKind.END_PHASE, True),
    ],
)
def test_catalog_command_point_phase_gain_supports_automatic_and_fixed_roll_gates(
    raw_text: str,
    trigger_kind: TimingTriggerKind,
    expects_dice_roll: bool,
) -> None:
    source_army, target_army = _mustered_once_per_battle_armies()
    source_unit = source_army.units[0]
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=_battlefield_for_units(
            source_army=source_army,
            source_unit=source_unit,
            source_x=10.0,
            target_army=target_army,
            target_unit=target_army.units[0],
            target_x=20.0,
        ),
        active_player_id=source_army.player_id,
        phase=BattlePhase.COMMAND,
    )
    record = _command_point_record(
        record_id=f"record:catalog-cp:phase-gain:{trigger_kind.value}",
        raw_text=raw_text,
        source_unit=source_unit,
        trigger_kind=trigger_kind,
    )
    runtime = _command_point_runtime(
        armies=(source_army, target_army),
        records_by_player={source_army.player_id: (record,)},
    )
    handler_registry = RuntimeContentEventHandlerRegistry.from_bindings(
        runtime.event_handler_bindings()
    )
    event_index = RuntimeContentEventIndex.from_subscriptions(
        runtime.event_subscriptions(),
        handler_registry=handler_registry,
    )
    decisions = DecisionController()

    results = event_index.dispatch(
        RuntimeContentEvent(
            event_id=f"runtime-event:catalog-cp:{trigger_kind.value}",
            game_id=state.game_id,
            player_id=source_army.player_id,
            battle_round=state.battle_round,
            trigger_kind=trigger_kind,
            phase=BattlePhaseKind.COMMAND,
            active_player_id=source_army.player_id,
        ),
        state=state,
        decisions=decisions,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=ArmyCatalog.phase9a_canonical_content_pack(),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )

    assert len(results) == 1
    assert state.command_point_total(source_army.player_id) == 1
    assert sum(event.event_type == "dice_rolled" for event in decisions.event_log.records) == int(
        expects_dice_roll
    )
    resolution = next(
        event
        for event in decisions.event_log.records
        if event.event_type == CATALOG_IR_COMMAND_POINT_PHASE_GAIN_EVENT
    )
    payload = cast(dict[str, JsonValue], resolution.payload)
    assert payload["test_kind"] == ("fixed_roll" if expects_dice_roll else "automatic")
    assert payload["passed"] is True


def test_catalog_command_point_phase_gain_records_failure_cap_and_inactive_owner() -> None:
    source_army, target_army = _mustered_once_per_battle_armies()
    source_unit = source_army.units[0]
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=_battlefield_for_units(
            source_army=source_army,
            source_unit=source_unit,
            source_x=10.0,
            target_army=target_army,
            target_unit=target_army.units[0],
            target_x=20.0,
        ),
        active_player_id=source_army.player_id,
        phase=BattlePhase.COMMAND,
    )
    automatic_record = _command_point_record(
        record_id="record:catalog-cp:phase-gain:cap",
        raw_text=DIRECT_PHASE_COMMAND_POINT_TEXT,
        source_unit=source_unit,
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    failed_roll_record = _command_point_record(
        record_id="record:catalog-cp:phase-gain:failed-roll",
        raw_text=("At the end of your Command phase, roll one D6: on a 7+, you gain 1CP."),
        source_unit=source_unit,
        trigger_kind=TimingTriggerKind.END_PHASE,
    )
    runtime = _command_point_runtime(
        armies=(source_army, target_army),
        records_by_player={
            source_army.player_id: (automatic_record, failed_roll_record),
        },
    )
    handler_registry = RuntimeContentEventHandlerRegistry.from_bindings(
        runtime.event_handler_bindings()
    )
    event_index = RuntimeContentEventIndex.from_subscriptions(
        runtime.event_subscriptions(),
        handler_registry=handler_registry,
    )
    decisions = DecisionController()

    def dispatch(
        *, event_id: str, trigger_kind: TimingTriggerKind, active_player_id: str
    ) -> tuple[RuntimeContentEventResult, ...]:
        return event_index.dispatch(
            RuntimeContentEvent(
                event_id=event_id,
                game_id=state.game_id,
                player_id=source_army.player_id,
                battle_round=state.battle_round,
                trigger_kind=trigger_kind,
                phase=BattlePhaseKind.COMMAND,
                active_player_id=active_player_id,
            ),
            state=state,
            decisions=decisions,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            army_catalog=ArmyCatalog.phase9a_canonical_content_pack(),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )

    inactive_results = dispatch(
        event_id="runtime-event:catalog-cp:inactive-owner",
        trigger_kind=TimingTriggerKind.START_PHASE,
        active_player_id=target_army.player_id,
    )
    dispatch(
        event_id="runtime-event:catalog-cp:gain-applied",
        trigger_kind=TimingTriggerKind.START_PHASE,
        active_player_id=source_army.player_id,
    )
    dispatch(
        event_id="runtime-event:catalog-cp:gain-capped",
        trigger_kind=TimingTriggerKind.START_PHASE,
        active_player_id=source_army.player_id,
    )
    dispatch(
        event_id="runtime-event:catalog-cp:roll-failed",
        trigger_kind=TimingTriggerKind.END_PHASE,
        active_player_id=source_army.player_id,
    )

    assert inactive_results[0].replay_payload == {"resolutions": []}
    assert state.command_point_total(source_army.player_id) == 1
    assert any(
        event.event_type == "command_points_gain_capped" for event in decisions.event_log.records
    )
    failed_resolution = next(
        event.payload
        for event in decisions.event_log.records
        if event.event_type == CATALOG_IR_COMMAND_POINT_PHASE_GAIN_EVENT
        and isinstance(event.payload, dict)
        and event.payload.get("runtime_event_id") == "runtime-event:catalog-cp:roll-failed"
    )
    assert failed_resolution["passed"] is False
    assert failed_resolution["command_point_result"] is None


def test_catalog_command_point_cost_choices_modify_only_the_current_stratagem_use() -> None:
    source_army, target_army = _mustered_once_per_battle_armies()
    source_unit = source_army.units[0]
    target_unit = target_army.units[0]
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=_battlefield_for_units(
            source_army=source_army,
            source_unit=source_unit,
            source_x=10.0,
            target_army=target_army,
            target_unit=target_unit,
            target_x=18.0,
        ),
        active_player_id=target_army.player_id,
        phase=BattlePhase.SHOOTING,
    )
    record = _command_point_record(
        record_id="record:catalog-cp:opponent-cost-runtime",
        raw_text=OPPONENT_STRATAGEM_COST_TEXT,
        source_unit=source_unit,
        trigger_kind=TimingTriggerKind.ANY_PHASE,
    )
    second_record = _command_point_record(
        record_id="record:catalog-cp:opponent-cost-runtime-second",
        raw_text=OPPONENT_STRATAGEM_COST_TEXT,
        source_unit=source_unit,
        trigger_kind=TimingTriggerKind.ANY_PHASE,
    )
    runtime = _command_point_runtime(
        armies=(source_army, target_army),
        records_by_player={source_army.player_id: (record, second_record)},
    )
    decisions = DecisionController()
    definition = _test_stratagem_definition(command_point_cost=1)
    eligibility = StratagemEligibilityContext.from_state(
        state=state,
        player_id=target_army.player_id,
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    target_binding = StratagemTargetBinding(
        target_kind=StratagemTargetKind.FRIENDLY_UNIT,
        target_player_id=target_army.player_id,
        target_unit_instance_id=target_unit.unit_instance_id,
    )
    source_request, source_result = _test_stratagem_source_decision(
        actor_id=target_army.player_id,
        suffix="opponent-cost",
    )
    request_context = StratagemCostChoiceRequestContext(
        state=state,
        decisions=decisions,
        source_request=source_request,
        source_result=source_result,
        definition=definition,
        eligibility_context=eligibility,
        target_binding=target_binding,
        effect_selection=None,
    )

    request = runtime.stratagem_cost_choice_request(request_context)
    assert request is not None
    assert request.actor_id == source_army.player_id
    use_option = next(
        option
        for option in request.options
        if isinstance(option.payload, dict) and option.payload.get("use_ability") is True
    )
    result = DecisionResult.for_request(
        result_id="result:catalog-cp:opponent-cost",
        request=request,
        selected_option_id=use_option.option_id,
    )
    result_payload = cast(dict[str, JsonValue], result.payload)
    request_payload = cast(dict[str, JsonValue], request.payload)
    with pytest.raises(GameLifecycleError, match="cost choice actor drift"):
        runtime.apply_stratagem_cost_choice_result(
            StratagemCostChoiceResultContext(
                state=state,
                decisions=decisions,
                request=request,
                result=replace(result, actor_id=target_army.player_id),
                source_request=source_request,
                source_result=source_result,
                definition=definition,
                eligibility_context=eligibility,
                target_binding=target_binding,
                effect_selection=None,
            )
        )
    with pytest.raises(GameLifecycleError, match="cost choice actor drift"):
        runtime.apply_stratagem_cost_choice_result(
            StratagemCostChoiceResultContext(
                state=state,
                decisions=decisions,
                request=replace(request, actor_id=target_army.player_id),
                result=replace(result, actor_id=target_army.player_id),
                source_request=source_request,
                source_result=source_result,
                definition=definition,
                eligibility_context=eligibility,
                target_binding=target_binding,
                effect_selection=None,
            )
        )
    assert not any(
        event.event_type == CATALOG_IR_STRATAGEM_COST_CHOICE_EVENT
        for event in decisions.event_log.records
    )
    assert not runtime.apply_stratagem_cost_choice_result(
        StratagemCostChoiceResultContext(
            state=state,
            decisions=decisions,
            request=replace(
                request,
                payload={**request_payload, "hook_id": "catalog-ir:unrelated-hook"},
            ),
            result=result,
            source_request=source_request,
            source_result=source_result,
            definition=definition,
            eligibility_context=eligibility,
            target_binding=target_binding,
            effect_selection=None,
        )
    )
    with pytest.raises(GameLifecycleError, match="source_clause_id drift"):
        runtime.apply_stratagem_cost_choice_result(
            StratagemCostChoiceResultContext(
                state=state,
                decisions=decisions,
                request=request,
                result=replace(
                    result,
                    payload={**result_payload, "source_clause_id": "drifted-clause"},
                ),
                source_request=source_request,
                source_result=source_result,
                definition=definition,
                eligibility_context=eligibility,
                target_binding=target_binding,
                effect_selection=None,
            )
        )
    assert not any(
        event.event_type == CATALOG_IR_STRATAGEM_COST_CHOICE_EVENT
        for event in decisions.event_log.records
    )
    assert runtime.apply_stratagem_cost_choice_result(
        StratagemCostChoiceResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
            source_request=source_request,
            source_result=source_result,
            definition=definition,
            eligibility_context=eligibility,
            target_binding=target_binding,
            effect_selection=None,
        )
    )
    second_request = runtime.stratagem_cost_choice_request(request_context)
    assert second_request is not None
    assert second_request.payload != request.payload
    decline_option = next(
        option
        for option in second_request.options
        if isinstance(option.payload, dict) and option.payload.get("use_ability") is False
    )
    second_result = DecisionResult.for_request(
        result_id="result:catalog-cp:opponent-cost-second",
        request=second_request,
        selected_option_id=decline_option.option_id,
    )
    assert runtime.apply_stratagem_cost_choice_result(
        StratagemCostChoiceResultContext(
            state=state,
            decisions=decisions,
            request=second_request,
            result=second_result,
            source_request=source_request,
            source_result=source_result,
            definition=definition,
            eligibility_context=eligibility,
            target_binding=target_binding,
            effect_selection=None,
        )
    )
    registry = StratagemCostModifierRegistry.from_bindings(
        runtime.stratagem_cost_modifier_bindings()
    )

    applied_cost = registry.modified_command_point_cost(
        _cost_modifier_context(
            state=state,
            decisions=decisions,
            definition=definition,
            eligibility=eligibility,
            target_binding=target_binding,
            source_request_id=source_request.request_id,
            source_result_id=source_result.result_id,
        )
    )
    unrelated_cost = registry.modified_command_point_cost(
        _cost_modifier_context(
            state=state,
            decisions=decisions,
            definition=definition,
            eligibility=eligibility,
            target_binding=target_binding,
            source_request_id="request:unrelated-stratagem",
            source_result_id="result:unrelated-stratagem",
        )
    )
    no_choice_cost = registry.modified_command_point_cost(
        StratagemCostModifierContext(
            state=state,
            definition=definition,
            eligibility_context=eligibility,
            target_binding=target_binding,
            effect_selection=None,
            base_command_point_cost=definition.command_point_cost,
            current_command_point_cost=definition.command_point_cost,
        )
    )

    assert applied_cost == 2
    assert unrelated_cost == 1
    assert no_choice_cost == 1
    assert runtime.stratagem_cost_choice_request(request_context) is None
    assert (
        sum(
            event.event_type == CATALOG_IR_STRATAGEM_COST_CHOICE_EVENT
            for event in decisions.event_log.records
        )
        == 2
    )


def test_catalog_command_point_own_cost_reduction_is_consumed_by_generic_registry() -> None:
    source_army, target_army = _mustered_core_armies()
    source_unit = source_army.units[0]
    target_unit = target_army.units[0]
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=_battlefield_for_units(
            source_army=source_army,
            source_unit=source_unit,
            source_x=10.0,
            target_army=target_army,
            target_unit=target_unit,
            target_x=20.0,
        ),
        active_player_id=source_army.player_id,
        phase=BattlePhase.SHOOTING,
    )
    record = _command_point_record(
        record_id="record:catalog-cp:own-cost-runtime",
        raw_text=OWN_STRATAGEM_COST_TEXT,
        source_unit=source_unit,
        trigger_kind=TimingTriggerKind.ANY_PHASE,
    )
    runtime = _command_point_runtime(
        armies=(source_army, target_army),
        records_by_player={source_army.player_id: (record,)},
    )
    decisions = DecisionController()
    definition = _test_stratagem_definition(command_point_cost=1)
    eligibility = StratagemEligibilityContext.from_state(
        state=state,
        player_id=source_army.player_id,
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    target_binding = StratagemTargetBinding(
        target_kind=StratagemTargetKind.FRIENDLY_UNIT,
        target_player_id=source_army.player_id,
        target_unit_instance_id=source_unit.unit_instance_id,
    )
    source_request, source_result = _test_stratagem_source_decision(
        actor_id=source_army.player_id,
        suffix="own-cost",
    )
    request_context = StratagemCostChoiceRequestContext(
        state=state,
        decisions=decisions,
        source_request=source_request,
        source_result=source_result,
        definition=definition,
        eligibility_context=eligibility,
        target_binding=target_binding,
        effect_selection=None,
    )
    request = runtime.stratagem_cost_choice_request(request_context)
    assert request is not None
    use_option = next(
        option
        for option in request.options
        if isinstance(option.payload, dict) and option.payload.get("use_ability") is True
    )
    result = DecisionResult.for_request(
        result_id="result:catalog-cp:own-cost",
        request=request,
        selected_option_id=use_option.option_id,
    )
    assert runtime.apply_stratagem_cost_choice_result(
        StratagemCostChoiceResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
            source_request=source_request,
            source_result=source_result,
            definition=definition,
            eligibility_context=eligibility,
            target_binding=target_binding,
            effect_selection=None,
        )
    )

    registry = StratagemCostModifierRegistry.from_bindings(
        runtime.stratagem_cost_modifier_bindings()
    )
    no_choice_cost = registry.modified_command_point_cost(
        StratagemCostModifierContext(
            state=state,
            definition=definition,
            eligibility_context=eligibility,
            target_binding=target_binding,
            effect_selection=None,
            base_command_point_cost=definition.command_point_cost,
            current_command_point_cost=definition.command_point_cost,
        )
    )
    accepted_cost = registry.modified_command_point_cost(
        _cost_modifier_context(
            state=state,
            decisions=decisions,
            definition=definition,
            eligibility=eligibility,
            target_binding=target_binding,
            source_request_id=source_request.request_id,
            source_result_id=source_result.result_id,
        )
    )

    assert no_choice_cost == 1
    assert accepted_cost == 0


def test_catalog_command_point_cost_frequency_is_consumed_from_stratagem_use_record() -> None:
    source_army, target_army = _mustered_once_per_battle_armies()
    source_unit = source_army.units[0]
    target_unit = target_army.units[0]
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=_battlefield_for_units(
            source_army=source_army,
            source_unit=source_unit,
            source_x=10.0,
            target_army=target_army,
            target_unit=target_unit,
            target_x=18.0,
        ),
        active_player_id=target_army.player_id,
        phase=BattlePhase.SHOOTING,
    )
    record = _command_point_record(
        record_id="record:catalog-cp:frequency-consumed",
        raw_text=OPPONENT_STRATAGEM_COST_TEXT,
        source_unit=source_unit,
        trigger_kind=TimingTriggerKind.ANY_PHASE,
    )
    runtime = _command_point_runtime(
        armies=(source_army, target_army),
        records_by_player={source_army.player_id: (record,)},
    )
    modifier_binding = runtime.stratagem_cost_modifier_bindings()[0]
    definition = _test_stratagem_definition(command_point_cost=1)
    eligibility = StratagemEligibilityContext.from_state(
        state=state,
        player_id=target_army.player_id,
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    target_binding = StratagemTargetBinding(
        target_kind=StratagemTargetKind.FRIENDLY_UNIT,
        target_player_id=target_army.player_id,
        target_unit_instance_id=target_unit.unit_instance_id,
    )
    state.record_stratagem_use(
        StratagemUseRecord(
            use_id="stratagem-use:catalog-cp:frequency-consumed",
            player_id=target_army.player_id,
            stratagem_id=definition.stratagem_id,
            source_id=definition.source_id,
            battle_round=state.battle_round,
            phase=BattlePhaseKind.SHOOTING,
            active_player_id=state.active_player_id,
            timing_window_id=None,
            request_id="request:catalog-cp:frequency-consumed:prior",
            result_id="result:catalog-cp:frequency-consumed:prior",
            selected_option_id="option:catalog-cp:frequency-consumed:prior",
            target_binding=target_binding,
            targeted_unit_instance_ids=(target_unit.unit_instance_id,),
            affected_unit_instance_ids=(target_unit.unit_instance_id,),
            command_point_cost=2,
            command_point_transaction_id=None,
            handler_id="record-only:catalog-cp:frequency-consumed",
            command_point_modifier_ids=(modifier_binding.modifier_id,),
            command_point_modifier_source_ids=(modifier_binding.source_id,),
        )
    )
    source_request, source_result = _test_stratagem_source_decision(
        actor_id=target_army.player_id,
        suffix="frequency-consumed",
    )

    assert (
        runtime.stratagem_cost_choice_request(
            StratagemCostChoiceRequestContext(
                state=state,
                decisions=DecisionController(),
                source_request=source_request,
                source_result=source_result,
                definition=definition,
                eligibility_context=eligibility,
                target_binding=target_binding,
                effect_selection=None,
            )
        )
        is None
    )


def test_catalog_command_point_enhancement_cost_source_binds_only_assigned_bearer() -> None:
    source_army, target_army = _mustered_once_per_battle_armies()
    source_unit = source_army.units[0]
    enhancement_id = "catalog-cp-test-enhancement"
    assigned_source_army = replace(
        source_army,
        detachment_selection=replace(
            source_army.detachment_selection,
            enhancement_ids=(enhancement_id,),
        ),
        enhancement_assignments=(
            EnhancementAssignment(
                enhancement_id=enhancement_id,
                target_unit_selection_id=source_unit.unit_instance_id.removeprefix(
                    f"{source_army.army_id}:"
                ),
                source_id="source:catalog-cp-test-enhancement-assignment",
            ),
        ),
    )
    datasheet_record = _command_point_record(
        record_id="record:catalog-cp:enhancement-cost-runtime",
        raw_text=OPPONENT_STRATAGEM_COST_TEXT,
        source_unit=source_unit,
        trigger_kind=TimingTriggerKind.ANY_PHASE,
    )
    enhancement_record = AbilityCatalogRecord(
        record_id=datasheet_record.record_id,
        definition=replace(datasheet_record.definition, ability_id=enhancement_id),
        source_kind=AbilitySourceKind.ENHANCEMENT,
        detachment_id=source_army.detachment_selection.detachment_ids[0],
    )

    assigned_runtime = _command_point_runtime(
        armies=(assigned_source_army, target_army),
        records_by_player={assigned_source_army.player_id: (enhancement_record,)},
    )
    unassigned_runtime = _command_point_runtime(
        armies=(source_army, target_army),
        records_by_player={source_army.player_id: (enhancement_record,)},
    )

    assert len(assigned_runtime.stratagem_cost_modifier_bindings()) == 1
    assert len(assigned_runtime.stratagem_cost_choice_hook_bindings()) == 1
    assert unassigned_runtime.stratagem_cost_modifier_bindings() == ()
    assert unassigned_runtime.stratagem_cost_choice_hook_bindings() == ()


def test_catalog_command_point_runtime_helpers_fail_fast_on_contract_drift() -> None:
    source_army, target_army = _mustered_once_per_battle_armies()
    source_unit = source_army.units[0]
    destroyed_record = _command_point_record(
        record_id="record:catalog-cp:strict-destroyed",
        raw_text=DESTROYED_CHARACTER_COMMAND_POINT_TEXT,
        source_unit=source_unit,
        trigger_kind=TimingTriggerKind.AFTER_UNIT_DESTROYED,
    )
    phase_record = _command_point_record(
        record_id="record:catalog-cp:strict-phase",
        raw_text=DIRECT_PHASE_COMMAND_POINT_TEXT,
        source_unit=source_unit,
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    cost_record = _command_point_record(
        record_id="record:catalog-cp:strict-cost",
        raw_text=OPPONENT_STRATAGEM_COST_TEXT,
        source_unit=source_unit,
        trigger_kind=TimingTriggerKind.ANY_PHASE,
    )
    destroyed_clause = catalog_rule_clauses_from_record(destroyed_record)[1]
    phase_clause = catalog_rule_clauses_from_record(phase_record)[0]
    cost_clause = catalog_rule_clauses_from_record(cost_record)[0]

    with pytest.raises(GameLifecycleError, match="ability indexes must be a mapping"):
        command_point_runtime._validate_ability_indexes(())  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(GameLifecycleError, match="must contain ability indexes"):
        command_point_runtime._validate_ability_indexes(  # pyright: ignore[reportPrivateUsage]
            {source_army.player_id: object()}
        )
    with pytest.raises(GameLifecycleError, match="armies must be a tuple"):
        command_point_runtime._validate_armies([])  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(GameLifecycleError, match="must contain ArmyDefinition"):
        command_point_runtime._validate_armies((object(),))  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(GameLifecycleError, match="payload must be an object"):
        command_point_runtime._payload_object(None, label="test")  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(GameLifecycleError, match="missing source_id"):
        command_point_runtime._payload_identifier({}, key="source_id")  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(GameLifecycleError, match="must be a boolean"):
        command_point_runtime._payload_bool({}, key="accepted")  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(GameLifecycleError, match="must be an integer"):
        command_point_runtime._mapping_int({}, key="delta")  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(GameLifecycleError, match="must be positive"):
        command_point_runtime._mapping_positive_int(  # pyright: ignore[reportPrivateUsage]
            {"delta": 0}, key="delta"
        )

    with pytest.raises(GameLifecycleError, match="player army is unknown"):
        command_point_runtime._army_for_player(  # pyright: ignore[reportPrivateUsage]
            (source_army, target_army), player_id="unknown-player"
        )
    with pytest.raises(GameLifecycleError, match="runtime unit is unknown"):
        command_point_runtime._unit_in_army(  # pyright: ignore[reportPrivateUsage]
            source_army, unit_instance_id="unknown-unit"
        )
    with pytest.raises(GameLifecycleError, match="runtime unit is unknown"):
        command_point_runtime._unit_by_id(  # pyright: ignore[reportPrivateUsage]
            (source_army, target_army), "unknown-unit"
        )
    with pytest.raises(GameLifecycleError, match="runtime model is unknown"):
        command_point_runtime._model_in_unit(  # pyright: ignore[reportPrivateUsage]
            source_unit, model_instance_id="unknown-model"
        )
    with pytest.raises(GameLifecycleError, match="missing Leadership"):
        command_point_runtime._model_leadership(  # pyright: ignore[reportPrivateUsage]
            replace(
                source_unit.own_models[0],
                characteristics=tuple(
                    value
                    for value in source_unit.own_models[0].characteristics
                    if value.characteristic is not Characteristic.LEADERSHIP
                ),
            )
        )

    assert not command_point_runtime._destroyed_keywords_match(  # pyright: ignore[reportPrivateUsage]
        destroyed_clause, destroyed_keywords={"MONSTER"}
    )
    without_keyword_clause = replace(
        destroyed_clause,
        conditions=tuple(
            condition
            for condition in destroyed_clause.conditions
            if condition.kind is not RuleConditionKind.KEYWORD_GATE
        ),
    )
    with pytest.raises(GameLifecycleError, match="missing keyword gate"):
        command_point_runtime._destroyed_keywords_match(  # pyright: ignore[reportPrivateUsage]
            without_keyword_clause, destroyed_keywords={"CHARACTER"}
        )

    assert (
        command_point_runtime._phase_gain_trigger_kind(  # pyright: ignore[reportPrivateUsage]
            phase_clause
        )
        is TimingTriggerKind.START_PHASE
    )
    assert (
        command_point_runtime._phase_gain_dice_gate(  # pyright: ignore[reportPrivateUsage]
            phase_clause
        )
        is None
    )
    with pytest.raises(GameLifecycleError, match="trigger edge is malformed"):
        command_point_runtime._phase_gain_trigger_kind(  # pyright: ignore[reportPrivateUsage]
            replace(
                phase_clause,
                trigger=replace(
                    cast(RuleTrigger, phase_clause.trigger),
                    parameters=(
                        RuleParameter("edge", "middle"),
                        RuleParameter("owner", "active_player"),
                        RuleParameter("phase", "command"),
                    ),
                ),
            )
        )
    with pytest.raises(GameLifecycleError, match="missing its trigger"):
        command_point_runtime._required_trigger(  # pyright: ignore[reportPrivateUsage]
            replace(phase_clause, trigger=None)
        )

    frequency = next(
        condition
        for condition in cost_clause.conditions
        if condition.kind is RuleConditionKind.FREQUENCY_LIMIT
    )
    malformed_frequency_clause = replace(
        cost_clause,
        conditions=tuple(
            replace(condition, parameters=(RuleParameter("scope", 1),))
            if condition is frequency
            else condition
            for condition in cost_clause.conditions
        ),
    )
    with pytest.raises(GameLifecycleError, match="frequency scope is malformed"):
        command_point_runtime._cost_frequency_scope(  # pyright: ignore[reportPrivateUsage]
            malformed_frequency_clause
        )
    without_distance_clause = replace(
        cost_clause,
        conditions=tuple(
            condition
            for condition in cost_clause.conditions
            if condition.kind is not RuleConditionKind.DISTANCE_PREDICATE
        ),
    )
    with pytest.raises(GameLifecycleError, match="range is missing"):
        command_point_runtime._cost_source_range_inches(  # pyright: ignore[reportPrivateUsage]
            without_distance_clause
        )

    with pytest.raises(GameLifecycleError, match="indexes must match army player IDs"):
        CatalogCommandPointRuntime(
            ability_indexes_by_player_id={
                source_army.player_id: AbilityCatalogIndex.from_records(())
            },
            armies=(source_army, target_army),
        )
    runtime = _command_point_runtime(
        armies=(source_army, target_army),
        records_by_player={},
    )
    with pytest.raises(GameLifecycleError, match="unit-destroyed runtime requires context"):
        runtime.resolve_unit_destroyed(cast(Any, object()))
    with pytest.raises(GameLifecycleError, match="cost choice requires context"):
        runtime.stratagem_cost_choice_request(cast(Any, object()))
    with pytest.raises(GameLifecycleError, match="cost choice result requires context"):
        runtime.apply_stratagem_cost_choice_result(cast(Any, object()))


def _command_point_record(
    *,
    record_id: str,
    raw_text: str,
    source_unit: UnitInstance,
    trigger_kind: TimingTriggerKind,
) -> AbilityCatalogRecord:
    source_text = RuleSourceText.from_raw(
        source_id=f"source:{record_id}",
        raw_text=raw_text,
    )
    rule_ir = compile_rule_source_text(
        source_text,
        source_keyword_sequence_parts=SOURCE_KEYWORD_SEQUENCE_PARTS,
    ).rule_ir
    return _ability_record(
        record_id=record_id,
        rule_ir=rule_ir,
        trigger_kind=trigger_kind,
        datasheet_id=source_unit.datasheet_id,
    )


def _command_point_runtime(
    *,
    armies: tuple[ArmyDefinition, ...],
    records_by_player: Mapping[str, tuple[AbilityCatalogRecord, ...]],
) -> CatalogCommandPointRuntime:
    return CatalogCommandPointRuntime(
        ability_indexes_by_player_id={
            army.player_id: AbilityCatalogIndex.from_records(
                records_by_player.get(army.player_id, ())
            )
            for army in armies
        },
        armies=armies,
    )


def _unit_with_leadership(unit: UnitInstance, *, leadership: int) -> UnitInstance:
    return replace(
        unit,
        own_models=tuple(
            replace(
                model,
                characteristics=tuple(
                    CharacteristicValue.from_raw(Characteristic.LEADERSHIP, leadership)
                    if value.characteristic is Characteristic.LEADERSHIP
                    else value
                    for value in model.characteristics
                ),
            )
            for model in unit.own_models
        ),
    )


def _test_stratagem_definition(*, command_point_cost: int) -> StratagemDefinition:
    return StratagemDefinition(
        stratagem_id="catalog-cp-test-stratagem",
        name="Catalog CP Test Stratagem",
        source_id="source:catalog-cp-test-stratagem",
        command_point_cost=command_point_cost,
        category=StratagemCategory.BATTLE_TACTIC,
        when_descriptor="Start of the Shooting phase.",
        target_descriptor="One friendly unit.",
        effect_descriptor="Record-only test effect.",
        restrictions_descriptor="Test Stratagem.",
        timing=StratagemTimingDescriptor(
            trigger_kind=TimingTriggerKind.START_PHASE,
            phase=BattlePhaseKind.SHOOTING,
        ),
    )


def _test_stratagem_source_decision(
    *,
    actor_id: str,
    suffix: str,
) -> tuple[DecisionRequest, DecisionResult]:
    request = DecisionRequest(
        request_id=f"request:catalog-cp:{suffix}",
        decision_type=STRATAGEM_DECISION_TYPE,
        actor_id=actor_id,
        payload={"finite": True},
        options=(
            DecisionOption(
                option_id=f"option:catalog-cp:{suffix}",
                label="Use test Stratagem",
                payload={"submission_kind": STRATAGEM_DECISION_TYPE},
            ),
        ),
    )
    return (
        request,
        DecisionResult.for_request(
            result_id=f"result:catalog-cp:{suffix}",
            request=request,
            selected_option_id=request.options[0].option_id,
        ),
    )


def _cost_modifier_context(
    *,
    state: GameState,
    decisions: DecisionController,
    definition: StratagemDefinition,
    eligibility: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
    source_request_id: str,
    source_result_id: str,
) -> StratagemCostModifierContext:
    return StratagemCostModifierContext(
        state=state,
        definition=definition,
        eligibility_context=eligibility,
        target_binding=target_binding,
        effect_selection=None,
        base_command_point_cost=definition.command_point_cost,
        current_command_point_cost=definition.command_point_cost,
        decisions=decisions,
        source_decision_request_id=source_request_id,
        source_decision_result_id=source_result_id,
    )


def _desperate_escape_record(*, source_unit: UnitInstance) -> AbilityCatalogRecord:
    source_text = RuleSourceText.from_raw(
        source_id="test:chaos-daemons:desperate-escape",
        raw_text=(
            "Each time an enemy unit (excluding Monsters and Vehicles) that is within "
            "Engagement Range of one or more units from your army with this ability is selected "
            "to Fall Back, models in that enemy unit must take Desperate Escape tests. If that "
            "enemy unit is also Battle-shocked, subtract 1 from each of those Desperate Escape "
            "tests."
        ),
    )
    rule_ir = compile_rule_source_text(
        source_text,
        source_keyword_sequence_parts=SOURCE_KEYWORD_SEQUENCE_PARTS,
    ).rule_ir
    return AbilityCatalogRecord(
        record_id="record:chaos-daemons:desperate-escape",
        definition=AbilityDefinition(
            ability_id="ability:chaos-daemons:desperate-escape",
            name="Forced Desperate Escape",
            source_id=source_text.source_id,
            when_descriptor="Enemy selected to Fall Back.",
            effect_descriptor="Force Desperate Escape tests.",
            restrictions_descriptor="Non-Monster non-Vehicle enemy unit.",
            timing=AbilityTimingDescriptor(
                trigger_kind=TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_SELECTED_TO_FALL_BACK
            ),
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
            replay_payload=validate_json_value({"rule_ir": rule_ir.to_payload()}),
        ),
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id=source_unit.datasheet_id,
    )


def _once_per_battle_record(*, source_unit: UnitInstance) -> AbilityCatalogRecord:
    rule_ir = compile_rule_source_text(
        RuleSourceText.from_raw(
            source_id="wahapedia:datasheet-ability:finest-hour",
            raw_text=ONCE_PER_BATTLE_FIGHT_BOOST_TEXT,
        ),
        source_keyword_sequence_parts=SOURCE_KEYWORD_SEQUENCE_PARTS,
    ).rule_ir
    return _ability_record(
        record_id="record:once-per-battle:finest-hour",
        rule_ir=rule_ir,
        trigger_kind=TimingTriggerKind.START_PHASE,
        datasheet_id=source_unit.datasheet_id,
    )


def _fight_start_selection_clause(
    *,
    clause_id: str = "test:selected-target:selection:fight",
) -> RuleClause:
    return RuleClause(
        clause_id=clause_id,
        template_id="phase17c:selected-target-constraint",
        source_span=_span(),
        trigger=RuleTrigger(
            kind=RuleTriggerKind.TIMING_WINDOW,
            source_span=_span(),
            parameters=_parameters(
                ("edge", "start"),
                ("phase", BattlePhase.FIGHT.value),
            ),
        ),
        target=RuleTargetSpec(kind=RuleTargetKind.ENEMY_UNIT, source_span=_span()),
    )


def _post_shoot_hit_selection_clause() -> RuleClause:
    return RuleClause(
        clause_id="test:selected-target:selection:post-shoot",
        template_id="phase17c:selected-target-constraint",
        source_span=_span(),
        trigger=RuleTrigger(
            kind=RuleTriggerKind.TIMING_WINDOW,
            source_span=_span(),
            parameters=_parameters(
                ("timing_window", "just_after_friendly_unit_has_shot"),
                ("target_relationship", "hit_by_those_attacks"),
            ),
        ),
        target=RuleTargetSpec(
            kind=RuleTargetKind.ENEMY_UNIT,
            source_span=_span(),
            parameters=_parameters(("target_relationship", "hit_by_those_attacks")),
        ),
    )


def _effect_clause(
    *,
    clause_id: str,
    duration: RuleDuration | None,
    effect_kind: RuleEffectKind,
    conditions: tuple[RuleCondition, ...] = (),
    **parameters: RuleParameterValue,
) -> RuleClause:
    return RuleClause(
        clause_id=clause_id,
        source_span=_span(),
        conditions=conditions,
        target=RuleTargetSpec(kind=RuleTargetKind.SELECTED_TARGET, source_span=_span()),
        effects=(_effect(effect_kind, *tuple(parameters.items())),),
        duration=duration,
    )


def _effect(
    kind: RuleEffectKind,
    *parameters: tuple[str, RuleParameterValue],
) -> RuleEffectSpec:
    return RuleEffectSpec(
        kind=kind,
        source_span=_span(),
        parameters=_parameters(*parameters),
    )


def _condition(
    kind: RuleConditionKind,
    *parameters: tuple[str, RuleParameterValue],
) -> RuleCondition:
    return RuleCondition(
        kind=kind,
        source_span=_span(),
        parameters=_parameters(*parameters),
    )


def _duration(endpoint: str) -> RuleDuration:
    return RuleDuration(
        kind=RuleDurationKind.UNTIL_TIMING_ENDPOINT,
        source_span=_span(),
        parameters=_parameters(("endpoint", endpoint)),
    )


def _rule_ir(*, source_id: str, clauses: tuple[RuleClause, ...]) -> RuleIR:
    return RuleIR(
        rule_id=f"{source_id}:rule",
        source_id=source_id,
        normalized_text=_span().text,
        parser_version="test-catalog-runtime-consumers",
        clauses=clauses,
    )


def _ability_record(
    *,
    record_id: str,
    rule_ir: RuleIR,
    trigger_kind: TimingTriggerKind,
    runtime_clause_id: str | None = None,
    handler_id: str = GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    datasheet_id: str = "core-intercessor-like-infantry",
) -> AbilityCatalogRecord:
    replay_payload: dict[str, JsonValue] = {"rule_ir": cast(JsonValue, rule_ir.to_payload())}
    if runtime_clause_id is not None:
        replay_payload["runtime_clause_id"] = runtime_clause_id
    return AbilityCatalogRecord(
        record_id=record_id,
        definition=AbilityDefinition(
            ability_id=f"{record_id}:ability",
            name="Selected Target Test",
            source_id=rule_ir.source_id,
            when_descriptor="Selected target timing.",
            effect_descriptor="Selected target effect.",
            restrictions_descriptor="Test-only source-backed RuleIR.",
            timing=AbilityTimingDescriptor(trigger_kind=trigger_kind),
            handler_id=handler_id,
            replay_payload=validate_json_value(replay_payload),
        ),
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id=datasheet_id,
    )


def _parameters(*parameters: tuple[str, RuleParameterValue]) -> tuple[RuleParameter, ...]:
    return parameters_from_pairs(parameters)


def _span() -> TextSpan:
    text = "catalog support test"
    return TextSpan(text=text, start=0, end=len(text))


def _mustered_core_armies() -> tuple[ArmyDefinition, ArmyDefinition]:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return (
        muster_army(
            catalog=catalog,
            request=_muster_request(catalog=catalog, player_id="player-a", army_id="army-alpha"),
        ),
        muster_army(
            catalog=catalog,
            request=_muster_request(catalog=catalog, player_id="player-b", army_id="army-beta"),
        ),
    )


def _mustered_once_per_battle_armies() -> tuple[ArmyDefinition, ArmyDefinition]:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    source_request = replace(
        _muster_request(catalog=catalog, player_id="player-a", army_id="army-alpha"),
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id="army-alpha-character",
                datasheet_id="core-character-leader",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-character-leader",
                        model_count=1,
                    ),
                ),
            ),
        ),
    )
    return (
        muster_army(catalog=catalog, request=source_request),
        muster_army(
            catalog=catalog,
            request=_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
            ),
        ),
    )


def _mustered_attached_once_per_battle_armies() -> tuple[ArmyDefinition, ArmyDefinition]:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    source_request = replace(
        _muster_request(catalog=catalog, player_id="player-a", army_id="army-alpha"),
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id="bodyguard",
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
            UnitMusterSelection(
                unit_selection_id="leader",
                datasheet_id="core-character-leader",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-character-leader",
                        model_count=1,
                    ),
                ),
            ),
        ),
        attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="leader",
                bodyguard_unit_selection_id="bodyguard",
            ),
        ),
    )
    return (
        muster_army(catalog=catalog, request=source_request),
        muster_army(
            catalog=catalog,
            request=_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
            ),
        ),
    )


def _muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id=f"{army_id}-unit",
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
        ),
    )


def _battlefield_for_units(
    *,
    source_army: ArmyDefinition,
    source_unit: UnitInstance,
    source_x: float,
    target_army: ArmyDefinition,
    target_unit: UnitInstance,
    target_x: float,
) -> BattlefieldRuntimeState:
    return _battlefield_for_units_with_model_xs(
        source_army=source_army,
        source_unit=source_unit,
        source_model_xs=_model_xs_for_unit(unit=source_unit, start_x=source_x),
        target_army=target_army,
        target_unit=target_unit,
        target_model_xs=_model_xs_for_unit(unit=target_unit, start_x=target_x),
    )


def _battlefield_for_units_with_model_xs(
    *,
    source_army: ArmyDefinition,
    source_unit: UnitInstance,
    source_model_xs: tuple[float, ...],
    target_army: ArmyDefinition,
    target_unit: UnitInstance,
    target_model_xs: tuple[float, ...],
) -> BattlefieldRuntimeState:
    return BattlefieldRuntimeState(
        battlefield_id="catalog-runtime-consumers-battlefield",
        battlefield_width_inches=60.0,
        battlefield_depth_inches=44.0,
        placed_armies=(
            _placed_army(army=source_army, unit=source_unit, model_xs=source_model_xs),
            _placed_army(army=target_army, unit=target_unit, model_xs=target_model_xs),
        ),
    )


def _model_xs_for_unit(*, unit: UnitInstance, start_x: float) -> tuple[float, ...]:
    return tuple(start_x + (index * 2.0) for index, _model in enumerate(unit.own_models))


def _placed_army(
    *,
    army: ArmyDefinition,
    unit: UnitInstance,
    model_xs: tuple[float, ...],
) -> PlacedArmy:
    if len(model_xs) != len(unit.own_models):
        raise AssertionError("Test battlefield model positions must match unit models.")
    return PlacedArmy(
        army_id=army.army_id,
        player_id=army.player_id,
        unit_placements=(
            UnitPlacement(
                army_id=army.army_id,
                player_id=army.player_id,
                unit_instance_id=unit.unit_instance_id,
                model_placements=tuple(
                    ModelPlacement(
                        army_id=army.army_id,
                        player_id=army.player_id,
                        unit_instance_id=unit.unit_instance_id,
                        model_instance_id=model.model_instance_id,
                        pose=Pose.at(x=model_xs[index], y=10.0),
                    )
                    for index, model in enumerate(unit.own_models)
                ),
            ),
        ),
    )


def _state_with_battlefield(
    *,
    armies: tuple[ArmyDefinition, ...],
    battlefield: BattlefieldRuntimeState,
    active_player_id: str,
    phase: BattlePhase,
) -> GameState:
    state = _state_without_battlefield(active_player_id=active_player_id, phase=phase)
    state.player_ids = tuple(army.player_id for army in armies)
    state.turn_order = tuple(army.player_id for army in armies)
    state.army_definitions = list(armies)
    state.battlefield_state = battlefield
    return state


def _state_without_battlefield(
    *,
    active_player_id: str | None,
    phase: BattlePhase,
) -> GameState:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    phases = tuple(descriptor.battle_phase_sequence.phases)
    return GameState(
        game_id="catalog-runtime-consumers-game",
        ruleset_descriptor_hash=descriptor.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(descriptor.setup_sequence.steps),
        battle_phase_sequence=phases,
        setup_step_index=None,
        battle_phase_index=phases.index(phase),
        battle_round=1,
        active_player_id=active_player_id,
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        tactical_secondary_draw_count=2,
    )


def _army_with_unit(army: ArmyDefinition, unit: UnitInstance) -> ArmyDefinition:
    return replace(army, units=(unit,))


def _unit_with_dead_model(unit: UnitInstance, *, index: int) -> UnitInstance:
    models = list(unit.own_models)
    model = models[index]
    models[index] = replace(model, wounds_remaining=0)
    return replace(unit, own_models=tuple(models))
