from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine import (
    catalog_tracked_target_runtime as catalog_tracked_target_runtime_module,
)
from warhammer40k_core.engine import tracked_targets as tracked_targets_module
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilitySourceKind,
    AbilityTimingDescriptor,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battle_round_hooks import BattleRoundStartRequestContext
from warhammer40k_core.engine.catalog_rule_consumption import catalog_rule_clauses_from_record
from warhammer40k_core.engine.catalog_tracked_target_runtime import CatalogTrackedTargetRuntime
from warhammer40k_core.engine.command_points import initial_command_point_ledgers
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import EventLog, JsonValue, canonical_json
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.scoring import initial_victory_point_ledgers
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.tracked_targets import (
    SELECT_TRACKED_TARGET_DECISION_TYPE,
    TrackedTargetOwnerScope,
    TrackedTargetRecord,
    TrackedTargetRole,
    apply_select_tracked_target_decision,
    build_select_tracked_target_request,
    invalid_select_tracked_target_status,
    tracked_target_reroll_permission_context_for_unit,
)
from warhammer40k_core.engine.unit_destroyed_hooks import UnitDestroyedContext
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.source_data import RuleSourceText

PREY_TARGET_TEXT = (
    "At the start of the first battle round, select one enemy unit to be this model's "
    "prey. Each time a model in this model's unit makes a melee attack that targets "
    "its prey, you can re-roll the Wound roll. Each time this model's prey is "
    "destroyed, select one new enemy unit to be this model's prey."
)


def test_tracked_target_initial_selection_request_payload_is_json_safe() -> None:
    state = _battle_state_with_scenario(beta_unit_count=2)
    record = _tracked_target_catalog_record(trigger_kind=TimingTriggerKind.START_BATTLE_ROUND)
    runtime = CatalogTrackedTargetRuntime(
        ability_indexes_by_player_id={
            "player-a": AbilityCatalogIndex.from_records((record,)),
            "player-b": AbilityCatalogIndex.from_records(()),
        },
        armies=tuple(state.army_definitions),
    )
    decisions = DecisionController()

    bindings = runtime.battle_round_start_bindings()
    request = runtime.battle_round_start_request(
        BattleRoundStartRequestContext(state=state, decisions=decisions)
    )

    assert len(bindings) == 1
    assert request is not None
    assert request.decision_type == SELECT_TRACKED_TARGET_DECISION_TYPE
    canonical_json(request.payload)
    assert [option.option_id for option in request.options] == sorted(
        unit.unit_instance_id for unit in state.army_definitions[1].units
    )
    assert isinstance(request.payload, dict)
    assert request.payload["submission_kind"] == SELECT_TRACKED_TARGET_DECISION_TYPE
    assert request.payload["source_rule_id"] == record.definition.source_id
    assert request.payload["supported_roll_types"] == ["attack_sequence.wound"]


def test_tracked_target_runtime_empty_indexes_have_no_hooks() -> None:
    state = _battle_state_with_scenario()
    runtime = CatalogTrackedTargetRuntime(
        ability_indexes_by_player_id={
            "player-a": AbilityCatalogIndex.from_records(()),
            "player-b": AbilityCatalogIndex.from_records(()),
        },
        armies=tuple(state.army_definitions),
    )

    assert runtime.battle_round_start_bindings() == ()
    assert runtime.unit_destroyed_bindings() == ()


def test_tracked_target_runtime_fail_fast_and_empty_selection_paths() -> None:
    state = _battle_state_with_scenario()
    record = _tracked_target_catalog_record(trigger_kind=TimingTriggerKind.START_BATTLE_ROUND)
    decisions = DecisionController()
    runtime_missing_index = CatalogTrackedTargetRuntime(
        ability_indexes_by_player_id={"player-b": AbilityCatalogIndex.from_records(())},
        armies=tuple(state.army_definitions),
    )

    with pytest.raises(GameLifecycleError, match="missing player ability index"):
        runtime_missing_index.battle_round_start_request(
            BattleRoundStartRequestContext(state=state, decisions=decisions)
        )

    source_unit = state.army_definitions[0].units[0]
    source_model_id = source_unit.own_models[0].model_instance_id
    assert state.battlefield_state is not None
    no_source_models_state = _battle_state_with_scenario()
    assert no_source_models_state.battlefield_state is not None
    no_source_models_state.battlefield_state = (
        no_source_models_state.battlefield_state.with_removed_models(source_unit.own_model_ids())
    )
    runtime = CatalogTrackedTargetRuntime(
        ability_indexes_by_player_id={
            "player-a": AbilityCatalogIndex.from_records((record,)),
            "player-b": AbilityCatalogIndex.from_records(()),
        },
        armies=tuple(no_source_models_state.army_definitions),
    )
    assert (
        runtime.battle_round_start_request(
            BattleRoundStartRequestContext(state=no_source_models_state, decisions=decisions)
        )
        is None
    )

    active_state = _battle_state_with_scenario()
    active_source_unit = active_state.army_definitions[0].units[0]
    active_target_unit = active_state.army_definitions[1].units[0]
    _record_selection(
        state=active_state,
        source_unit_instance_id=active_source_unit.unit_instance_id,
        source_model_instance_id=active_source_unit.own_models[0].model_instance_id,
        target_unit_instance_id=active_target_unit.unit_instance_id,
        owner_scope=TrackedTargetOwnerScope.THIS_MODEL,
    )
    assert (
        build_select_tracked_target_request(
            state=active_state,
            actor_player_id="player-a",
            source_rule_id="rule:this_model",
            source_ability_id="ability:prey",
            source_clause_id="clause:select",
            source_effect_index=0,
            source_unit_instance_id=active_source_unit.unit_instance_id,
            source_model_instance_id=active_source_unit.own_models[0].model_instance_id,
            owner_scope=TrackedTargetOwnerScope.THIS_MODEL,
            role=TrackedTargetRole.PREY,
            supported_roll_types=("attack_sequence.wound",),
            target_allegiance="enemy",
            target_scope="enemy_unit",
            replacement=False,
        )
        is None
    )

    no_targets_state = _battle_state_with_scenario()
    beta = no_targets_state.army_definitions[1].units[0]
    assert no_targets_state.battlefield_state is not None
    no_targets_state.battlefield_state = no_targets_state.battlefield_state.with_removed_models(
        beta.own_model_ids()
    )
    assert (
        build_select_tracked_target_request(
            state=no_targets_state,
            actor_player_id="player-a",
            source_rule_id="rule:prey",
            source_ability_id="ability:prey",
            source_clause_id="clause:select",
            source_effect_index=0,
            source_unit_instance_id=source_unit.unit_instance_id,
            source_model_instance_id=source_model_id,
            owner_scope=TrackedTargetOwnerScope.THIS_MODEL,
            role=TrackedTargetRole.PREY,
            supported_roll_types=("attack_sequence.wound",),
            target_allegiance="enemy",
            target_scope="enemy_unit",
            replacement=False,
        )
        is None
    )

    with pytest.raises(GameLifecycleError, match="allegiance and target_scope drift"):
        build_select_tracked_target_request(
            state=state,
            actor_player_id="player-a",
            source_rule_id="rule:prey",
            source_ability_id="ability:prey",
            source_clause_id="clause:select",
            source_effect_index=0,
            source_unit_instance_id=source_unit.unit_instance_id,
            source_model_instance_id=source_model_id,
            owner_scope=TrackedTargetOwnerScope.THIS_MODEL,
            role=TrackedTargetRole.PREY,
            supported_roll_types=("attack_sequence.wound",),
            target_allegiance="enemy",
            target_scope="friendly_unit",
            replacement=False,
        )
    with pytest.raises(GameLifecycleError, match="replacement must be a bool"):
        build_select_tracked_target_request(
            state=state,
            actor_player_id="player-a",
            source_rule_id="rule:prey",
            source_ability_id="ability:prey",
            source_clause_id="clause:select",
            source_effect_index=0,
            source_unit_instance_id=source_unit.unit_instance_id,
            source_model_instance_id=source_model_id,
            owner_scope=TrackedTargetOwnerScope.THIS_MODEL,
            role=TrackedTargetRole.PREY,
            supported_roll_types=("attack_sequence.wound",),
            target_allegiance="enemy",
            target_scope="enemy_unit",
            replacement=cast(bool, "yes"),
        )


def test_tracked_target_selection_records_active_target_and_round_trips() -> None:
    state = _battle_state_with_scenario()
    source_unit = state.army_definitions[0].units[0]
    source_model_id = source_unit.own_models[0].model_instance_id
    target_unit_id = state.army_definitions[1].units[0].unit_instance_id

    request = build_select_tracked_target_request(
        state=state,
        actor_player_id="player-a",
        source_rule_id="rule:prey",
        source_ability_id="ability:prey",
        source_clause_id="clause:select",
        source_effect_index=0,
        source_unit_instance_id=source_unit.unit_instance_id,
        source_model_instance_id=source_model_id,
        owner_scope=TrackedTargetOwnerScope.THIS_MODEL,
        role=TrackedTargetRole.PREY,
        supported_roll_types=("attack_sequence.wound",),
        target_allegiance="enemy",
        target_scope="enemy_unit",
        replacement=False,
    )

    assert request is not None
    assert request.decision_type == SELECT_TRACKED_TARGET_DECISION_TYPE
    canonical_json(request.payload)
    result = DecisionResult.for_request(
        result_id="result:prey",
        request=request,
        selected_option_id=target_unit_id,
    )
    record = apply_select_tracked_target_decision(
        state=state,
        request=request,
        result=result,
        decisions_event_log=EventLog(),
    )

    assert record.target_unit_instance_id == target_unit_id
    assert (
        state.active_tracked_target_for(
            source_rule_id="rule:prey",
            source_unit_instance_id=source_unit.unit_instance_id,
            source_model_instance_id=source_model_id,
            owner_scope=TrackedTargetOwnerScope.THIS_MODEL,
            role=TrackedTargetRole.PREY,
        )
        == record
    )
    assert TrackedTargetRecord.from_payload(record.to_payload()) == record


def test_tracked_target_selection_rejects_non_option_before_mutation() -> None:
    state = _battle_state_with_scenario()
    source_unit = state.army_definitions[0].units[0]
    source_model_id = source_unit.own_models[0].model_instance_id
    request = build_select_tracked_target_request(
        state=state,
        actor_player_id="player-a",
        source_rule_id="rule:prey",
        source_ability_id="ability:prey",
        source_clause_id="clause:select",
        source_effect_index=0,
        source_unit_instance_id=source_unit.unit_instance_id,
        source_model_instance_id=source_model_id,
        owner_scope=TrackedTargetOwnerScope.THIS_MODEL,
        role=TrackedTargetRole.PREY,
        supported_roll_types=("attack_sequence.wound",),
        target_allegiance="enemy",
        target_scope="enemy_unit",
        replacement=False,
    )
    assert request is not None
    result = DecisionResult(
        result_id="result:bad",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id="unit:not-an-option",
        payload=request.options[0].payload,
    )

    status = invalid_select_tracked_target_status(
        state=state,
        request=request,
        result=result,
    )

    assert status is not None
    assert state.tracked_target_records == []


def test_tracked_target_invalid_status_accepts_valid_and_rejects_stale_targets() -> None:
    state = _battle_state_with_scenario()
    source_unit = state.army_definitions[0].units[0]
    source_model_id = source_unit.own_models[0].model_instance_id
    target_unit = state.army_definitions[1].units[0]
    request = build_select_tracked_target_request(
        state=state,
        actor_player_id="player-a",
        source_rule_id="rule:prey",
        source_ability_id="ability:prey",
        source_clause_id="clause:select",
        source_effect_index=0,
        source_unit_instance_id=source_unit.unit_instance_id,
        source_model_instance_id=source_model_id,
        owner_scope=TrackedTargetOwnerScope.THIS_MODEL,
        role=TrackedTargetRole.PREY,
        supported_roll_types=("attack_sequence.wound",),
        target_allegiance="enemy",
        target_scope="enemy_unit",
        replacement=False,
    )
    assert request is not None
    result = DecisionResult.for_request(
        result_id="result:valid",
        request=request,
        selected_option_id=target_unit.unit_instance_id,
    )

    assert invalid_select_tracked_target_status(state=state, request=request, result=result) is None

    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.with_removed_models(
        target_unit.own_model_ids()
    )
    status = invalid_select_tracked_target_status(state=state, request=request, result=result)

    assert status is not None
    status_payload = cast(dict[str, JsonValue], status.payload)
    assert status_payload["invalid_reason"] == "selected_target_no_longer_legal"


def test_tracked_target_reroll_requires_active_target_and_matching_model_scope() -> None:
    state = _battle_state_with_scenario()
    source_unit = state.army_definitions[0].units[0]
    source_model_id = source_unit.own_models[0].model_instance_id
    other_model_id = source_unit.own_models[1].model_instance_id
    target_unit_id = state.army_definitions[1].units[0].unit_instance_id
    _record_selection(
        state=state,
        source_unit_instance_id=source_unit.unit_instance_id,
        source_model_instance_id=source_model_id,
        target_unit_instance_id=target_unit_id,
        owner_scope=TrackedTargetOwnerScope.THIS_MODEL,
    )

    assert (
        tracked_target_reroll_permission_context_for_unit(
            state=state,
            player_id="player-a",
            unit_instance_id=source_unit.unit_instance_id,
            model_instance_id=source_model_id,
            roll_type="attack_sequence.wound",
            timing_window="attack_sequence.wound",
            target_unit_instance_id=target_unit_id,
        )
        is not None
    )
    assert (
        tracked_target_reroll_permission_context_for_unit(
            state=state,
            player_id="player-a",
            unit_instance_id=source_unit.unit_instance_id,
            model_instance_id=other_model_id,
            roll_type="attack_sequence.wound",
            timing_window="attack_sequence.wound",
            target_unit_instance_id=target_unit_id,
        )
        is None
    )
    assert (
        tracked_target_reroll_permission_context_for_unit(
            state=state,
            player_id="player-a",
            unit_instance_id=source_unit.unit_instance_id,
            model_instance_id=source_model_id,
            roll_type="attack_sequence.wound",
            timing_window="attack_sequence.wound",
            target_unit_instance_id=source_unit.unit_instance_id,
        )
        is None
    )


def test_tracked_target_unit_scope_applies_to_other_models_in_unit() -> None:
    state = _battle_state_with_scenario()
    source_unit = state.army_definitions[0].units[0]
    other_model_id = source_unit.own_models[1].model_instance_id
    target_unit_id = state.army_definitions[1].units[0].unit_instance_id
    _record_selection(
        state=state,
        source_unit_instance_id=source_unit.unit_instance_id,
        source_model_instance_id=None,
        target_unit_instance_id=target_unit_id,
        owner_scope=TrackedTargetOwnerScope.THIS_UNIT,
    )

    context = tracked_target_reroll_permission_context_for_unit(
        state=state,
        player_id="player-a",
        unit_instance_id=source_unit.unit_instance_id,
        model_instance_id=other_model_id,
        roll_type="attack_sequence.wound",
        timing_window="attack_sequence.wound",
        target_unit_instance_id=target_unit_id,
    )

    assert context is not None
    assert context.source_payload["owner_scope"] == "this_unit"


def test_tracked_target_quarry_reroll_applies_to_hit_and_wound_rolls() -> None:
    state = _battle_state_with_scenario()
    source_unit = state.army_definitions[0].units[0]
    source_model_id = source_unit.own_models[0].model_instance_id
    target_unit_id = state.army_definitions[1].units[0].unit_instance_id
    state.record_tracked_target(
        TrackedTargetRecord(
            record_id="record:quarry",
            source_rule_id="rule:quarry",
            source_ability_id="ability:quarry",
            source_clause_id="clause:select",
            source_effect_index=0,
            owner_player_id="player-a",
            source_unit_instance_id=source_unit.unit_instance_id,
            source_model_instance_id=source_model_id,
            owner_scope=TrackedTargetOwnerScope.THIS_MODEL,
            role=TrackedTargetRole.QUARRY,
            supported_roll_types=("attack_sequence.hit", "attack_sequence.wound"),
            target_unit_instance_id=target_unit_id,
            target_allegiance="enemy",
            target_lifecycle="until_destroyed",
            selected_battle_round=1,
            selection_request_id="request:quarry",
            selection_result_id="result:quarry",
            active=True,
        )
    )

    hit_context = tracked_target_reroll_permission_context_for_unit(
        state=state,
        player_id="player-a",
        unit_instance_id=source_unit.unit_instance_id,
        model_instance_id=source_model_id,
        roll_type="attack_sequence.hit",
        timing_window="attack_sequence.hit",
        target_unit_instance_id=target_unit_id,
    )
    wound_context = tracked_target_reroll_permission_context_for_unit(
        state=state,
        player_id="player-a",
        unit_instance_id=source_unit.unit_instance_id,
        model_instance_id=source_model_id,
        roll_type="attack_sequence.wound",
        timing_window="attack_sequence.wound",
        target_unit_instance_id=target_unit_id,
    )

    assert hit_context is not None
    assert wound_context is not None


def test_tracked_target_supported_roll_types_drive_rerolls_not_role_label() -> None:
    state = _battle_state_with_scenario()
    source_unit = state.army_definitions[0].units[0]
    source_model_id = source_unit.own_models[0].model_instance_id
    target_unit_id = state.army_definitions[1].units[0].unit_instance_id
    state.record_tracked_target(
        TrackedTargetRecord(
            record_id="record:quarry-wound-only",
            source_rule_id="rule:quarry",
            source_ability_id="ability:quarry",
            source_clause_id="clause:select",
            source_effect_index=0,
            owner_player_id="player-a",
            source_unit_instance_id=source_unit.unit_instance_id,
            source_model_instance_id=source_model_id,
            owner_scope=TrackedTargetOwnerScope.THIS_MODEL,
            role=TrackedTargetRole.QUARRY,
            supported_roll_types=("attack_sequence.wound",),
            target_unit_instance_id=target_unit_id,
            target_allegiance="enemy",
            target_lifecycle="until_destroyed",
            selected_battle_round=1,
            selection_request_id="request:quarry-wound-only",
            selection_result_id="result:quarry-wound-only",
            active=True,
        )
    )

    assert (
        tracked_target_reroll_permission_context_for_unit(
            state=state,
            player_id="player-a",
            unit_instance_id=source_unit.unit_instance_id,
            model_instance_id=source_model_id,
            roll_type="attack_sequence.hit",
            timing_window="attack_sequence.hit",
            target_unit_instance_id=target_unit_id,
        )
        is None
    )
    assert (
        tracked_target_reroll_permission_context_for_unit(
            state=state,
            player_id="player-a",
            unit_instance_id=source_unit.unit_instance_id,
            model_instance_id=source_model_id,
            roll_type="attack_sequence.wound",
            timing_window="attack_sequence.wound",
            target_unit_instance_id=target_unit_id,
        )
        is not None
    )


def test_tracked_target_reroll_rejects_duplicate_internal_permissions() -> None:
    state = _battle_state_with_scenario()
    source_unit = state.army_definitions[0].units[0]
    source_model_id = source_unit.own_models[0].model_instance_id
    target_unit_id = state.army_definitions[1].units[0].unit_instance_id
    _record_selection(
        state=state,
        source_unit_instance_id=source_unit.unit_instance_id,
        source_model_instance_id=source_model_id,
        target_unit_instance_id=target_unit_id,
        owner_scope=TrackedTargetOwnerScope.THIS_MODEL,
    )
    state.tracked_target_records.append(
        replace(state.tracked_target_records[0], record_id="record:duplicate")
    )

    with pytest.raises(GameLifecycleError, match="Multiple tracked-target reroll permissions"):
        tracked_target_reroll_permission_context_for_unit(
            state=state,
            player_id="player-a",
            unit_instance_id=source_unit.unit_instance_id,
            model_instance_id=source_model_id,
            roll_type="attack_sequence.wound",
            timing_window="attack_sequence.wound",
            target_unit_instance_id=target_unit_id,
        )


def test_tracked_target_defensive_validation_rejects_malformed_records_and_payloads() -> None:
    with pytest.raises(GameLifecycleError, match="require source model"):
        TrackedTargetRecord(
            record_id="record:bad-model-scope",
            source_rule_id="rule:bad",
            source_ability_id="ability:bad",
            source_clause_id="clause:bad",
            source_effect_index=0,
            owner_player_id="player-a",
            source_unit_instance_id="unit-a",
            source_model_instance_id=None,
            owner_scope=TrackedTargetOwnerScope.THIS_MODEL,
            role=TrackedTargetRole.PREY,
            supported_roll_types=("attack_sequence.wound",),
            target_unit_instance_id="unit-b",
            target_allegiance="enemy",
            target_lifecycle="until_destroyed",
            selected_battle_round=1,
            selection_request_id="request:bad",
            selection_result_id="result:bad",
            active=True,
        )
    with pytest.raises(GameLifecycleError, match="must not store source model"):
        TrackedTargetRecord(
            record_id="record:bad-unit-scope",
            source_rule_id="rule:bad",
            source_ability_id="ability:bad",
            source_clause_id="clause:bad",
            source_effect_index=0,
            owner_player_id="player-a",
            source_unit_instance_id="unit-a",
            source_model_instance_id="model-a",
            owner_scope=TrackedTargetOwnerScope.THIS_UNIT,
            role=TrackedTargetRole.PREY,
            supported_roll_types=("attack_sequence.wound",),
            target_unit_instance_id="unit-b",
            target_allegiance="enemy",
            target_lifecycle="until_destroyed",
            selected_battle_round=1,
            selection_request_id="request:bad",
            selection_result_id="result:bad",
            active=True,
        )
    malformed_calls = (
        lambda: tracked_targets_module._payload_object([]),  # pyright: ignore[reportPrivateUsage]
        lambda: tracked_targets_module._payload_string(  # pyright: ignore[reportPrivateUsage]
            {},
            key="source_rule_id",
        ),
        lambda: tracked_targets_module._payload_optional_string(  # pyright: ignore[reportPrivateUsage]
            {},
            key="source_model_instance_id",
        ),
        lambda: tracked_targets_module._payload_int(  # pyright: ignore[reportPrivateUsage]
            {},
            key="source_effect_index",
        ),
        lambda: tracked_targets_module._payload_bool(  # pyright: ignore[reportPrivateUsage]
            {"replacement": "yes"},
            key="replacement",
        ),
        lambda: tracked_targets_module._payload_identifier_list(  # pyright: ignore[reportPrivateUsage]
            {"legal_target_unit_ids": "unit-b"},
            key="legal_target_unit_ids",
        ),
        lambda: tracked_targets_module._validate_supported_roll_types(  # pyright: ignore[reportPrivateUsage]
            cast(tuple[object, ...], [])
        ),
        lambda: tracked_targets_module._validate_supported_roll_types(  # pyright: ignore[reportPrivateUsage]
            ()
        ),
        lambda: tracked_targets_module._validate_supported_roll_types(  # pyright: ignore[reportPrivateUsage]
            ("attack_sequence.hit", "attack_sequence.hit")
        ),
        lambda: tracked_targets_module._role_from_token(1),  # pyright: ignore[reportPrivateUsage]
        lambda: tracked_targets_module._role_from_token(  # pyright: ignore[reportPrivateUsage]
            "unsupported"
        ),
        lambda: tracked_targets_module._owner_scope_from_token(  # pyright: ignore[reportPrivateUsage]
            1
        ),
        lambda: tracked_targets_module._owner_scope_from_token(  # pyright: ignore[reportPrivateUsage]
            "unsupported"
        ),
        lambda: tracked_targets_module._validate_supported_token(  # pyright: ignore[reportPrivateUsage]
            "target_allegiance",
            "neutral",
            supported=("enemy",),
        ),
        lambda: tracked_targets_module._validate_identifier(  # pyright: ignore[reportPrivateUsage]
            "record_id",
            1,
        ),
        lambda: tracked_targets_module._validate_identifier(  # pyright: ignore[reportPrivateUsage]
            "record_id",
            "",
        ),
        lambda: tracked_targets_module._validate_non_negative_int(  # pyright: ignore[reportPrivateUsage]
            "source_effect_index",
            -1,
        ),
        lambda: tracked_targets_module._validate_positive_int(  # pyright: ignore[reportPrivateUsage]
            "selected_battle_round",
            0,
        ),
    )

    for malformed_call in malformed_calls:
        with pytest.raises(GameLifecycleError):
            malformed_call()


def test_tracked_target_runtime_reselection_defensive_paths() -> None:
    state = _battle_state_with_scenario(beta_unit_count=2)
    source_unit = state.army_definitions[0].units[0]
    destroyed_target = state.army_definitions[1].units[0]
    expired = TrackedTargetRecord(
        record_id="tracked:expired",
        source_rule_id="rule:tracked-target",
        source_ability_id="ability:tracked-target",
        source_clause_id="tracked:initial-clause",
        source_effect_index=0,
        owner_player_id="player-a",
        source_unit_instance_id=source_unit.unit_instance_id,
        source_model_instance_id=source_unit.own_models[0].model_instance_id,
        owner_scope=TrackedTargetOwnerScope.THIS_MODEL,
        role=TrackedTargetRole.PREY,
        supported_roll_types=("attack_sequence.wound",),
        target_unit_instance_id=destroyed_target.unit_instance_id,
        target_allegiance="enemy",
        target_lifecycle="until_destroyed",
        selected_battle_round=1,
        selection_request_id="request:initial",
        selection_result_id="result:initial",
        active=False,
    )
    current_phase = state.current_battle_phase
    assert current_phase is not None
    context = UnitDestroyedContext(
        state=state,
        decisions=DecisionController(),
        completed_phase=current_phase,
        model_destroyed_event_id="event:destroyed-target",
        model_destroyed_payload={
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": current_phase.value,
            "destroying_player_id": "player-a",
            "target_unit_instance_id": destroyed_target.unit_instance_id,
            "model_instance_id": destroyed_target.own_models[0].model_instance_id,
        },
        destroying_player_id="player-a",
        destroyed_unit_instance_id=destroyed_target.unit_instance_id,
        destroyed_player_id="player-b",
    )

    with pytest.raises(GameLifecycleError, match="missing player ability index"):
        catalog_tracked_target_runtime_module._tracked_target_reselection_request(  # pyright: ignore[reportPrivateUsage]
            ability_indexes_by_player_id={},
            armies=tuple(state.army_definitions),
            context=context,
            expired_record=expired,
        )

    no_source_models_state = _battle_state_with_scenario(beta_unit_count=2)
    assert no_source_models_state.battlefield_state is not None
    no_source_models_state.battlefield_state = (
        no_source_models_state.battlefield_state.with_removed_models(source_unit.own_model_ids())
    )
    no_source_context = replace(context, state=no_source_models_state)
    assert (
        catalog_tracked_target_runtime_module._tracked_target_reselection_request(  # pyright: ignore[reportPrivateUsage]
            ability_indexes_by_player_id={
                "player-a": AbilityCatalogIndex.from_records((_tracked_target_catalog_record(),))
            },
            armies=tuple(no_source_models_state.army_definitions),
            context=no_source_context,
            expired_record=expired,
        )
        is None
    )

    owner_drift_expired = replace(
        expired, record_id="tracked:owner-drift", owner_player_id="player-b"
    )
    with pytest.raises(GameLifecycleError, match="owner drift"):
        catalog_tracked_target_runtime_module._tracked_target_reselection_request(  # pyright: ignore[reportPrivateUsage]
            ability_indexes_by_player_id={"player-b": AbilityCatalogIndex.from_records(())},
            armies=tuple(state.army_definitions),
            context=context,
            expired_record=owner_drift_expired,
        )

    record = _tracked_target_catalog_record()
    clause = catalog_rule_clauses_from_record(record)[0]
    with pytest.raises(GameLifecycleError, match="source unit drift"):
        catalog_tracked_target_runtime_module._reselection_request_for_clause(  # pyright: ignore[reportPrivateUsage]
            context=context,
            expired_record=replace(expired, source_unit_instance_id="unit:other"),
            record=record,
            clause=clause,
            unit=source_unit,
        )
    assert (
        catalog_tracked_target_runtime_module._reselection_request_for_clause(  # pyright: ignore[reportPrivateUsage]
            context=context,
            expired_record=replace(expired, role=TrackedTargetRole.QUARRY),
            record=record,
            clause=clause,
            unit=source_unit,
        )
        is None
    )
    with pytest.raises(GameLifecycleError, match="could not find source unit"):
        catalog_tracked_target_runtime_module._army_and_unit_for_unit_id(  # pyright: ignore[reportPrivateUsage]
            armies=tuple(state.army_definitions),
            unit_instance_id="unit:missing",
        )


def test_tracked_target_destroyed_target_expires_and_requests_reselection() -> None:
    state = _battle_state_with_scenario(beta_unit_count=2)
    source_unit = state.army_definitions[0].units[0]
    source_model_id = source_unit.own_models[0].model_instance_id
    destroyed_target = state.army_definitions[1].units[0]
    replacement_target = state.army_definitions[1].units[1]
    record = _tracked_target_catalog_record()
    state.record_tracked_target(
        TrackedTargetRecord(
            record_id="tracked:active",
            source_rule_id=record.definition.source_id,
            source_ability_id=record.definition.ability_id,
            source_clause_id="tracked:initial-clause",
            source_effect_index=0,
            owner_player_id="player-a",
            source_unit_instance_id=source_unit.unit_instance_id,
            source_model_instance_id=source_model_id,
            owner_scope=TrackedTargetOwnerScope.THIS_MODEL,
            role=TrackedTargetRole.PREY,
            supported_roll_types=("attack_sequence.wound",),
            target_unit_instance_id=destroyed_target.unit_instance_id,
            target_allegiance="enemy",
            target_lifecycle="until_destroyed",
            selected_battle_round=1,
            selection_request_id="request:initial",
            selection_result_id="result:initial",
            active=True,
        )
    )
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.with_removed_models(
        destroyed_target.own_model_ids()
    )
    decisions = DecisionController()
    runtime = CatalogTrackedTargetRuntime(
        ability_indexes_by_player_id={
            "player-a": AbilityCatalogIndex.from_records((record,)),
        },
        armies=tuple(state.army_definitions),
    )
    current_phase = state.current_battle_phase
    assert current_phase is not None

    runtime.unit_destroyed_handler(
        UnitDestroyedContext(
            state=state,
            decisions=decisions,
            completed_phase=current_phase,
            model_destroyed_event_id="event:destroyed-target",
            model_destroyed_payload={
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "phase": current_phase.value,
                "destroying_player_id": "player-a",
                "target_unit_instance_id": destroyed_target.unit_instance_id,
                "model_instance_id": destroyed_target.own_models[0].model_instance_id,
            },
            destroying_player_id="player-a",
            destroyed_unit_instance_id=destroyed_target.unit_instance_id,
            destroyed_player_id="player-b",
        )
    )

    expired_record = state.tracked_target_records[0]
    assert not expired_record.active
    request = decisions.queue.pending_requests[0]
    assert request.decision_type == SELECT_TRACKED_TARGET_DECISION_TYPE
    assert request.options[0].option_id == replacement_target.unit_instance_id
    assert isinstance(request.payload, dict)
    request_payload = request.payload
    assert request_payload["replacement"] is True
    result = DecisionResult.for_request(
        result_id="result:replacement",
        request=request,
        selected_option_id=replacement_target.unit_instance_id,
    )
    replacement = apply_select_tracked_target_decision(
        state=state,
        request=request,
        result=result,
        decisions_event_log=decisions.event_log,
    )

    assert replacement.active
    assert replacement.target_unit_instance_id == replacement_target.unit_instance_id


def _record_selection(
    *,
    state: GameState,
    source_unit_instance_id: str,
    source_model_instance_id: str | None,
    target_unit_instance_id: str,
    owner_scope: TrackedTargetOwnerScope,
) -> None:
    state.record_tracked_target(
        TrackedTargetRecord(
            record_id=f"record:{owner_scope.value}",
            source_rule_id=f"rule:{owner_scope.value}",
            source_ability_id="ability:prey",
            source_clause_id="clause:select",
            source_effect_index=0,
            owner_player_id="player-a",
            source_unit_instance_id=source_unit_instance_id,
            source_model_instance_id=source_model_instance_id,
            owner_scope=owner_scope,
            role=TrackedTargetRole.PREY,
            supported_roll_types=("attack_sequence.wound",),
            target_unit_instance_id=target_unit_instance_id,
            target_allegiance="enemy",
            target_lifecycle="until_destroyed",
            selected_battle_round=1,
            selection_request_id=f"request:{owner_scope.value}",
            selection_result_id=f"result:{owner_scope.value}",
            active=True,
        )
    )


def _battle_state_with_scenario(*, beta_unit_count: int = 1) -> GameState:
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="tracked-target-battlefield",
        armies=_mustered_armies(beta_unit_count=beta_unit_count),
    )
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    state = GameState(
        game_id="tracked-target-game",
        ruleset_descriptor_hash=descriptor.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(descriptor.setup_sequence.steps),
        battle_phase_sequence=tuple(descriptor.battle_phase_sequence.phases),
        setup_step_index=None,
        battle_phase_index=0,
        battle_round=1,
        active_player_id="player-a",
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        tactical_secondary_draw_count=2,
        command_point_ledgers=initial_command_point_ledgers(("player-a", "player-b")),
        victory_point_ledgers=initial_victory_point_ledgers(("player-a", "player-b")),
    )
    for army in scenario.armies:
        state.record_army_definition(army)
    state.battlefield_state = scenario.battlefield_state
    return state


def _mustered_armies(*, beta_unit_count: int = 1) -> tuple[ArmyDefinition, ...]:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return (
        muster_army(
            catalog=catalog,
            request=_muster_request(catalog=catalog, player_id="player-a", army_id="army-alpha"),
        ),
        muster_army(
            catalog=catalog,
            request=_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_count=beta_unit_count,
            ),
        ),
    )


def _muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_count: int = 1,
) -> ArmyMusterRequest:
    if unit_count < 1:
        raise AssertionError("unit_count must be positive")
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
        unit_selections=tuple(
            UnitMusterSelection(
                unit_selection_id=(
                    f"{army_id}-unit" if unit_count == 1 else f"{army_id}-unit-{index}"
                ),
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            )
            for index in range(1, unit_count + 1)
        ),
    )


def _tracked_target_catalog_record(
    *,
    trigger_kind: TimingTriggerKind = TimingTriggerKind.AFTER_UNIT_DESTROYED,
) -> AbilityCatalogRecord:
    source = RuleSourceText.from_raw(
        source_id="rule:tracked-target",
        raw_text=PREY_TARGET_TEXT,
    )
    rule_ir = compile_rule_source_text(source).rule_ir
    return AbilityCatalogRecord(
        record_id="record:tracked-target",
        definition=AbilityDefinition(
            ability_id="ability:tracked-target",
            name="Tracked Target",
            source_id=source.source_id,
            when_descriptor="Battle-round start and tracked target destroyed.",
            effect_descriptor="Select prey and reselect when destroyed.",
            restrictions_descriptor="Enemy unit target.",
            timing=AbilityTimingDescriptor(trigger_kind=trigger_kind),
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
            replay_payload=cast(JsonValue, {"rule_ir": rule_ir.to_payload()}),
        ),
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id="core-intercessor-like-infantry",
    )
