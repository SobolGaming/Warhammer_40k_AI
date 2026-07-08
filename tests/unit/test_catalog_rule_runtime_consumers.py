from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind, RulesetDescriptor
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilitySourceKind,
    AbilityTimingDescriptor,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    ModelPlacement,
    PlacedArmy,
    UnitPlacement,
)
from warhammer40k_core.engine.catalog_desperate_escape import (
    CATALOG_FORCED_DESPERATE_ESCAPE_SOURCE_KIND,
    catalog_forced_desperate_escape_sources_for_unit,
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
from warhammer40k_core.engine.fight_phase_start_hooks import (
    SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE,
    FightPhaseStartRequestContext,
    FightPhaseStartResultContext,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
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
        datasheet_id="core-intercessor-like-infantry",
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
    return BattlefieldRuntimeState(
        battlefield_id="catalog-runtime-consumers-battlefield",
        battlefield_width_inches=60.0,
        battlefield_depth_inches=44.0,
        placed_armies=(
            _placed_army(army=source_army, unit=source_unit, x=source_x),
            _placed_army(army=target_army, unit=target_unit, x=target_x),
        ),
    )


def _placed_army(*, army: ArmyDefinition, unit: UnitInstance, x: float) -> PlacedArmy:
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
                        pose=Pose.at(x=x + (index * 2.0), y=10.0),
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
