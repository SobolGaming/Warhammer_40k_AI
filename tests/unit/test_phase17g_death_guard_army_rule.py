from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from typing import cast

import pytest
from tests.unit.test_phase11c_command_phase import (
    _battle_state_with_center_objective_positions,  # pyright: ignore[reportPrivateUsage]
    _default_unit_selection,  # pyright: ignore[reportPrivateUsage]
    _remove_first_models,  # pyright: ignore[reportPrivateUsage]
    _unit_by_id,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.datasheet import DatasheetDefinition, DatasheetKeywordSet
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
)
from warhammer40k_core.engine.attack_sequence import (
    _target_unit_toughness,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.battle_formation_hooks import (
    SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE,
    BattleFormationHookBinding,
    BattleFormationHookRegistry,
    BattleFormationRequestContext,
    BattleFormationResultContext,
)
from warhammer40k_core.engine.battle_shock import (
    BattleShockTestReason,
    collect_battle_shock_test_requests,
)
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.death_guard import (
    army_rule,
)
from warhammer40k_core.engine.faction_rule_states import FactionRuleState
from warhammer40k_core.engine.game_state import GameConfig, GameState, GameStatePayload
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    LifecycleStatus,
    LifecycleStatusKind,
    SetupStep,
)
from warhammer40k_core.engine.saves import SaveKind, save_options_for_model
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack

DEATH_GUARD_TEST_DATASHEET_ID = "phase17g-death-guard-plague-marine"
DEATH_GUARD_UNIT_ID = "army-alpha:intercessor-unit-1"
ENEMY_UNIT_ID = "army-beta:intercessor-unit-3"


def test_lifecycle_requests_death_guard_plague_selection_and_records_state() -> None:
    lifecycle = GameLifecycle()
    lifecycle.start(_death_guard_config())
    status = _advance_through_secondary_choices(lifecycle)
    request = status.decision_request
    assert request is not None
    assert request.decision_type == SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE
    assert request.actor_id == "player-a"
    assert (
        army_rule.HOOK_ID
        in _runtime_content_bundle(lifecycle).to_summary_payload()["battle_formation_hook_ids"]
    )

    selected = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-death-guard-select-skullsquirm",
            request=request,
            selected_option_id=(
                f"death_guard:nurgles_gift:{army_rule.NurglesGiftPlague.SKULLSQUIRM_BLIGHT.value}"
            ),
        )
    )

    assert selected.decision_request is not None
    assert selected.decision_request.decision_type != SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE
    assert lifecycle.state is not None
    states = lifecycle.state.faction_rule_states_for_player(
        player_id="player-a",
        state_kind=army_rule.NURGLES_GIFT_STATE_KIND,
    )
    assert len(states) == 1
    assert states[0].source_rule_id == army_rule.SOURCE_RULE_ID
    assert (
        army_rule.selected_plague_for_player(
            lifecycle.state,
            player_id="player-a",
        )
        is army_rule.NurglesGiftPlague.SKULLSQUIRM_BLIGHT
    )
    restored = GameState.from_payload(
        cast(GameStatePayload, json.loads(json.dumps(lifecycle.state.to_payload())))
    )
    assert restored.to_payload() == lifecycle.state.to_payload()


def test_lifecycle_rejects_death_guard_plague_selection_drift_before_mutation() -> None:
    lifecycle = GameLifecycle()
    lifecycle.start(_death_guard_config())
    status = _advance_through_secondary_choices(lifecycle)
    request = status.decision_request
    assert request is not None
    option_id = f"death_guard:nurgles_gift:{army_rule.NurglesGiftPlague.SKULLSQUIRM_BLIGHT.value}"
    option = request.option_by_id(option_id)

    actor_drift = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase17g-death-guard-wrong-actor",
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id="player-b",
            selected_option_id=option.option_id,
            payload=option.payload,
        )
    )

    assert actor_drift.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(actor_drift.payload, dict)
    assert actor_drift.payload["invalid_reason"] == "invalid_faction_rule_setup_option_result"
    assert actor_drift.payload["field"] == "actor_id"
    assert lifecycle.decision_controller.queue.peek_next() == request
    assert lifecycle.state is not None
    assert (
        lifecycle.state.faction_rule_states_for_player(
            player_id="player-a",
            state_kind=army_rule.NURGLES_GIFT_STATE_KIND,
        )
        == ()
    )

    drifted_payload = dict(cast(dict[str, object], option.payload))
    drifted_payload["plague_id"] = army_rule.NurglesGiftPlague.RATTLEJOINT_AGUE.value
    payload_drift = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase17g-death-guard-payload-drift",
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id=option.option_id,
            payload=validate_json_value(drifted_payload),
        )
    )

    assert payload_drift.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(payload_drift.payload, dict)
    assert payload_drift.payload["invalid_reason"] == "invalid_faction_rule_setup_option_result"
    assert payload_drift.payload["field"] == "payload"
    assert lifecycle.decision_controller.queue.peek_next() == request
    assert (
        lifecycle.state.faction_rule_states_for_player(
            player_id="player-a",
            state_kind=army_rule.NURGLES_GIFT_STATE_KIND,
        )
        == ()
    )


def test_battle_formation_hook_registry_enforces_single_request_and_handler() -> None:
    config = _death_guard_config()
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    status = _advance_through_secondary_choices(lifecycle)
    request = status.decision_request
    assert request is not None
    assert lifecycle.state is not None
    request_context = BattleFormationRequestContext(
        state=lifecycle.state,
        decisions=lifecycle.decision_controller,
        config=config,
    )

    registry = BattleFormationHookRegistry.from_bindings(
        (
            BattleFormationHookBinding(
                hook_id="phase17g:test-hook-a",
                source_id="phase17g:test-source-a",
                request_handler=lambda context: _test_battle_formation_request(
                    context=context,
                    hook_id="phase17g:test-hook-a",
                ),
            ),
            BattleFormationHookBinding(
                hook_id="phase17g:test-hook-b",
                source_id="phase17g:test-source-b",
                request_handler=lambda context: _test_battle_formation_request(
                    context=context,
                    hook_id="phase17g:test-hook-b",
                ),
            ),
        )
    )

    with pytest.raises(GameLifecycleError, match="multiple simultaneous requests"):
        registry.next_request_for(request_context)

    result = DecisionResult.for_request(
        result_id="phase17g-battle-formation-hook-result",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    result_context = BattleFormationResultContext(
        state=lifecycle.state,
        decisions=lifecycle.decision_controller,
        config=config,
        request=request,
        result=result,
    )
    assert (
        BattleFormationHookRegistry.from_bindings(
            (
                BattleFormationHookBinding(
                    hook_id="phase17g:false-handler",
                    source_id="phase17g:false-source",
                    result_handler=lambda context: False,
                ),
            )
        ).apply_result(result_context)
        is False
    )

    multiple_handlers = BattleFormationHookRegistry.from_bindings(
        (
            BattleFormationHookBinding(
                hook_id="phase17g:true-handler-a",
                source_id="phase17g:true-source-a",
                result_handler=lambda context: True,
            ),
            BattleFormationHookBinding(
                hook_id="phase17g:true-handler-b",
                source_id="phase17g:true-source-b",
                result_handler=lambda context: True,
            ),
        )
    )
    with pytest.raises(GameLifecycleError, match="handled by multiple hooks"):
        multiple_handlers.apply_result(result_context)


def test_battle_formation_hook_registry_rejects_invalid_shapes() -> None:
    config = _death_guard_config()
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    status = _advance_through_secondary_choices(lifecycle)
    request = status.decision_request
    assert request is not None
    assert lifecycle.state is not None
    request_context = BattleFormationRequestContext(
        state=lifecycle.state,
        decisions=lifecycle.decision_controller,
        config=config,
    )
    result_context = BattleFormationResultContext(
        state=lifecycle.state,
        decisions=lifecycle.decision_controller,
        config=config,
        request=request,
        result=DecisionResult.for_request(
            result_id="phase17g-invalid-shape-result",
            request=request,
            selected_option_id=request.options[0].option_id,
        ),
    )

    with pytest.raises(GameLifecycleError, match="requires a handler"):
        BattleFormationHookBinding(hook_id="phase17g:no-handler", source_id="phase17g:source")
    with pytest.raises(GameLifecycleError, match="hook_id must be a string"):
        BattleFormationHookBinding(
            hook_id=cast(str, object()),
            source_id="phase17g:source",
            request_handler=lambda context: None,
        )
    with pytest.raises(GameLifecycleError, match="source_id must not be empty"):
        BattleFormationHookBinding(
            hook_id="phase17g:empty-source",
            source_id=" ",
            request_handler=lambda context: None,
        )
    with pytest.raises(GameLifecycleError, match="request_handler must be callable"):
        BattleFormationHookBinding(
            hook_id="phase17g:bad-request-handler",
            source_id="phase17g:source",
            request_handler=cast(
                Callable[[BattleFormationRequestContext], DecisionRequest | None],
                object(),
            ),
        )
    with pytest.raises(GameLifecycleError, match="result_handler must be callable"):
        BattleFormationHookBinding(
            hook_id="phase17g:bad-result-handler",
            source_id="phase17g:source",
            result_handler=cast(Callable[[BattleFormationResultContext], bool], object()),
        )
    with pytest.raises(GameLifecycleError, match="bindings must be a tuple"):
        BattleFormationHookRegistry(bindings=cast(tuple[BattleFormationHookBinding, ...], object()))
    with pytest.raises(GameLifecycleError, match="must contain BattleFormationHookBinding"):
        BattleFormationHookRegistry(bindings=(cast(BattleFormationHookBinding, object()),))
    with pytest.raises(GameLifecycleError, match="hook IDs must be unique"):
        BattleFormationHookRegistry.from_bindings(
            (
                BattleFormationHookBinding(
                    hook_id="phase17g:duplicate",
                    source_id="phase17g:source-a",
                    request_handler=lambda context: None,
                ),
                BattleFormationHookBinding(
                    hook_id="phase17g:duplicate",
                    source_id="phase17g:source-b",
                    request_handler=lambda context: None,
                ),
            )
        )

    with pytest.raises(GameLifecycleError, match="request hooks require a context"):
        BattleFormationHookRegistry.empty().next_request_for(
            cast(BattleFormationRequestContext, object())
        )
    assert (
        BattleFormationHookRegistry.from_bindings(
            (
                BattleFormationHookBinding(
                    hook_id="phase17g:none-request",
                    source_id="phase17g:source",
                    request_handler=lambda context: None,
                ),
            )
        ).next_request_for(request_context)
        is None
    )
    with pytest.raises(GameLifecycleError, match="DecisionRequest or None"):
        BattleFormationHookRegistry.from_bindings(
            (
                BattleFormationHookBinding(
                    hook_id="phase17g:bad-request",
                    source_id="phase17g:source",
                    request_handler=_bad_battle_formation_request_handler,
                ),
            )
        ).next_request_for(request_context)

    with pytest.raises(GameLifecycleError, match="result hooks require a context"):
        BattleFormationHookRegistry.empty().apply_result(
            cast(BattleFormationResultContext, object())
        )
    with pytest.raises(GameLifecycleError, match="handlers must return bool"):
        BattleFormationHookRegistry.from_bindings(
            (
                BattleFormationHookBinding(
                    hook_id="phase17g:bad-result",
                    source_id="phase17g:source",
                    result_handler=_bad_battle_formation_result_handler,
                ),
            )
        ).apply_result(result_context)


def test_faction_rule_state_validation_rejects_invalid_and_duplicate_records() -> None:
    state = _death_guard_battle_state(army_rule.NurglesGiftPlague.SKULLSQUIRM_BLIGHT)
    stored = state.faction_rule_states_for_player(
        player_id="player-a",
        state_kind=army_rule.NURGLES_GIFT_STATE_KIND,
    )[0]

    with pytest.raises(GameLifecycleError, match="must be FactionRuleState"):
        state.record_faction_rule_state(cast(FactionRuleState, object()))
    with pytest.raises(GameLifecycleError, match="already exists"):
        state.record_faction_rule_state(stored)
    with pytest.raises(GameLifecycleError, match="player_id"):
        state.faction_rule_states_for_player(player_id="missing-player")
    with pytest.raises(GameLifecycleError, match="setup_step"):
        FactionRuleState.from_payload(
            {
                "state_id": "phase17g-invalid-step",
                "player_id": "player-a",
                "faction_id": army_rule.DEATH_GUARD_FACTION_ID,
                "source_rule_id": army_rule.SOURCE_RULE_ID,
                "state_kind": army_rule.NURGLES_GIFT_STATE_KIND,
                "setup_step": "not-a-step",
                "request_id": "phase17g-request",
                "result_id": "phase17g-result",
                "payload": {},
            }
        )


def test_contagion_range_caps_after_modifiers_per_11th_update() -> None:
    assert army_rule.contagion_range_inches(battle_round=1) == 3.0
    assert army_rule.contagion_range_inches(battle_round=2) == 6.0
    assert army_rule.contagion_range_inches(battle_round=3) == 9.0
    assert army_rule.contagion_range_inches(battle_round=3, modifier_inches=6.0) == 12.0


def test_nurgles_gift_requires_live_placed_death_guard_model_in_contagion_range() -> None:
    state = _death_guard_battle_state(army_rule.NurglesGiftPlague.SKULLSQUIRM_BLIGHT)

    assert army_rule.afflicting_death_guard_player_ids(
        state,
        target_unit_instance_id=ENEMY_UNIT_ID,
    ) == ("player-a",)

    _remove_first_models(state, unit_instance_id=DEATH_GUARD_UNIT_ID, count=1)

    assert (
        army_rule.afflicting_death_guard_player_ids(
            state,
            target_unit_instance_id=ENEMY_UNIT_ID,
        )
        == ()
    )


def test_nurgles_gift_afflicted_units_have_minus_one_toughness() -> None:
    state = _death_guard_battle_state(army_rule.NurglesGiftPlague.RATTLEJOINT_AGUE)

    assert _target_unit_toughness(state=state, target_unit_instance_id=ENEMY_UNIT_ID) == 3
    assert (
        army_rule.nurgles_gift_modified_toughness(
            state=state,
            target_unit_instance_id=ENEMY_UNIT_ID,
            base_toughness=4,
        )
        == 3
    )


def test_skullsquirm_blight_only_modifies_afflicted_melee_hit_rolls() -> None:
    state = _death_guard_battle_state(army_rule.NurglesGiftPlague.SKULLSQUIRM_BLIGHT)
    enemy_model_id = _unit_by_id(state, ENEMY_UNIT_ID).own_models[0].model_instance_id

    assert (
        army_rule.nurgles_gift_hit_roll_modifier(
            state=state,
            attacker_model_instance_id=enemy_model_id,
            source_phase=BattlePhase.FIGHT,
        )
        == -1
    )
    assert (
        army_rule.nurgles_gift_hit_roll_modifier(
            state=state,
            attacker_model_instance_id=enemy_model_id,
            source_phase=BattlePhase.SHOOTING,
        )
        == 0
    )


def test_rattlejoint_ague_worsens_afflicted_armour_save_option() -> None:
    state = _death_guard_battle_state(army_rule.NurglesGiftPlague.RATTLEJOINT_AGUE)
    enemy_model = _unit_by_id(state, ENEMY_UNIT_ID).own_models[0]
    base_options = save_options_for_model(model=enemy_model, armor_penetration=0)

    modified = army_rule.nurgles_gift_modified_save_options(
        state=state,
        target_unit_instance_id=ENEMY_UNIT_ID,
        save_options=base_options,
    )

    base_armour = next(option for option in base_options if option.save_kind is SaveKind.ARMOUR)
    modified_armour = next(option for option in modified if option.save_kind is SaveKind.ARMOUR)
    assert modified_armour.characteristic_target_number == (
        base_armour.characteristic_target_number + 1
    )
    assert modified_armour.target_number == base_armour.target_number + 1
    assert army_rule.SOURCE_RULE_ID in modified_armour.source_rule_ids


def test_scabrous_soulrot_worsens_afflicted_move_leadership_and_oc() -> None:
    state = _death_guard_battle_state(army_rule.NurglesGiftPlague.SCABROUS_SOULROT)
    enemy_unit = _unit_by_id(state, ENEMY_UNIT_ID)
    enemy_model = enemy_unit.own_models[0]

    assert (
        army_rule.nurgles_gift_modified_movement_inches(
            state=state,
            unit_instance_id=ENEMY_UNIT_ID,
            base_movement_inches=6.0,
        )
        == 5.0
    )
    assert (
        army_rule.nurgles_gift_modified_objective_control(
            state=state,
            unit_instance_id=ENEMY_UNIT_ID,
            base_objective_control=2,
        )
        == 1
    )
    assert (
        army_rule.nurgles_gift_modified_objective_control(
            state=state,
            unit_instance_id=ENEMY_UNIT_ID,
            base_objective_control=1,
        )
        == 1
    )

    _remove_first_models(state, unit_instance_id=ENEMY_UNIT_ID, count=3)
    assert state.battlefield_state is not None
    enemy_army = state.army_definition_for_player("player-b")
    assert enemy_army is not None
    requests = collect_battle_shock_test_requests(
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id="player-b",
        army=enemy_army,
        battlefield_state=state.battlefield_state,
        starting_strength_records=tuple(state.starting_strength_records),
        state=state,
        ability_index=AbilityCatalogIndex.from_records(()),
    )

    assert len(requests) == 1
    assert requests[0].reason is BattleShockTestReason.BELOW_HALF_STRENGTH
    assert requests[0].leadership_target == (
        enemy_model.characteristic(Characteristic.LEADERSHIP).final + 1
    )


def _death_guard_battle_state(plague: army_rule.NurglesGiftPlague) -> GameState:
    state = _battle_state_with_center_objective_positions(
        player_a_offsets=((0.0, 0.0),),
        player_b_offsets=((2.0, -3.0), (2.0, -1.5), (2.0, 0.0), (2.0, 1.5), (2.0, 3.0)),
    )
    _mark_player_as_death_guard(state, player_id="player-a")
    _record_plague_selection(state, player_id="player-a", plague=plague)
    return state


def _mark_player_as_death_guard(state: GameState, *, player_id: str) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        if army.player_id != player_id:
            updated_armies.append(army)
            continue
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            updated_units.append(replace(unit, faction_keywords=("Death Guard",)))
        updated_armies.append(
            replace(
                army,
                detachment_selection=replace(
                    army.detachment_selection,
                    faction_id=army_rule.DEATH_GUARD_FACTION_ID,
                ),
                units=tuple(updated_units),
            )
        )
    state.army_definitions = updated_armies


def _record_plague_selection(
    state: GameState,
    *,
    player_id: str,
    plague: army_rule.NurglesGiftPlague,
) -> None:
    state.record_faction_rule_state(
        FactionRuleState(
            state_id=f"{army_rule.HOOK_ID}:{player_id}:plague-selection",
            player_id=player_id,
            faction_id=army_rule.DEATH_GUARD_FACTION_ID,
            source_rule_id=army_rule.SOURCE_RULE_ID,
            state_kind=army_rule.NURGLES_GIFT_STATE_KIND,
            setup_step=SetupStep.DECLARE_BATTLE_FORMATIONS,
            request_id="phase17g-death-guard-test-request",
            result_id=f"phase17g-death-guard-test-result:{plague.value}",
            payload={
                "plague_id": plague.value,
                "hook_id": army_rule.HOOK_ID,
            },
        )
    )


def _test_battle_formation_request(
    *,
    context: BattleFormationRequestContext,
    hook_id: str,
) -> DecisionRequest:
    return DecisionRequest(
        request_id=context.state.next_decision_request_id(),
        decision_type=SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE,
        actor_id="player-a",
        payload={
            "hook_id": hook_id,
            "setup_step": SetupStep.DECLARE_BATTLE_FORMATIONS.value,
        },
        options=(
            DecisionOption(
                option_id=f"{hook_id}:option",
                label=hook_id,
                payload={"hook_id": hook_id},
            ),
        ),
    )


def _bad_battle_formation_request_handler(
    context: BattleFormationRequestContext,
) -> DecisionRequest | None:
    assert type(context) is BattleFormationRequestContext
    return cast(DecisionRequest, object())


def _bad_battle_formation_result_handler(context: BattleFormationResultContext) -> bool:
    assert type(context) is BattleFormationResultContext
    return cast(bool, "yes")


def _advance_through_secondary_choices(lifecycle: GameLifecycle) -> LifecycleStatus:
    status = lifecycle.advance_until_decision_or_terminal()
    for result_id in (
        "phase17g-death-guard-secondary-player-a",
        "phase17g-death-guard-secondary-player-b",
    ):
        request = status.decision_request
        assert request is not None
        status = lifecycle.submit_decision(
            DecisionResult.for_request(
                result_id=result_id,
                request=request,
                selected_option_id="fixed:assassination:bring_it_down",
            )
        )
    return status


def _death_guard_config() -> GameConfig:
    catalog = _death_guard_catalog()
    return GameConfig(
        game_id="phase17g-death-guard-lifecycle-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
            descriptor_version="core-v2-phase17g-death-guard-test",
        ),
        army_catalog=catalog,
        army_muster_requests=(
            ArmyMusterRequest(
                army_id="army-alpha",
                player_id="player-a",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id=army_rule.DEATH_GUARD_FACTION_ID,
                    detachment_ids=("plague-company",),
                ),
                unit_selections=(
                    UnitMusterSelection(
                        unit_selection_id="plague-marine",
                        datasheet_id=DEATH_GUARD_TEST_DATASHEET_ID,
                        model_profile_selections=(
                            ModelProfileSelection(
                                model_profile_id="core-intercessor-like",
                                model_count=5,
                            ),
                        ),
                    ),
                ),
            ),
            ArmyMusterRequest(
                army_id="army-beta",
                player_id="player-b",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id="core-marine-force",
                    detachment_ids=("core-combined-arms",),
                ),
                unit_selections=(_default_unit_selection("enemy-unit"),),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down"),
        mission_setup=MissionSetup.from_mission_pack(
            mission_pack=chapter_approved_2026_27_mission_pack(),
            mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
            terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
            attacker_player_id="player-a",
            defender_player_id="player-b",
        ),
    )


def _death_guard_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    death_guard_datasheet = _death_guard_datasheet(base_datasheet)
    return replace(
        base_catalog,
        datasheets=(*base_catalog.datasheets, death_guard_datasheet),
        factions=(
            *base_catalog.factions,
            FactionDefinition(
                faction_id=army_rule.DEATH_GUARD_FACTION_ID,
                name="Death Guard",
                faction_keywords=("Death Guard",),
                source_ids=("gw-11e-faction-detachments-2026-27:faction:death-guard",),
            ),
        ),
        detachments=(
            *base_catalog.detachments,
            DetachmentDefinition(
                detachment_id="plague-company",
                name="Plague Company",
                faction_id=army_rule.DEATH_GUARD_FACTION_ID,
                detachment_point_cost=1,
                unit_datasheet_ids=(DEATH_GUARD_TEST_DATASHEET_ID,),
                force_disposition_ids=("phase17g-force",),
                source_ids=(
                    "gw-11e-faction-detachments-2026-27:detachment:death-guard:plague-company",
                ),
            ),
        ),
    )


def _death_guard_datasheet(base_datasheet: DatasheetDefinition) -> DatasheetDefinition:
    return replace(
        base_datasheet,
        datasheet_id=DEATH_GUARD_TEST_DATASHEET_ID,
        name="Plague Marine",
        keywords=DatasheetKeywordSet(
            keywords=("Infantry", "Battleline"),
            faction_keywords=("Death Guard",),
        ),
        attachment_eligibilities=(),
        source_ids=("phase17g:test:death-guard:plague-marine",),
    )


def _runtime_content_bundle(lifecycle: GameLifecycle) -> RuntimeContentBundle:
    require_runtime_content_bundle = cast(
        Callable[[], RuntimeContentBundle],
        object.__getattribute__(lifecycle, "_require_runtime_content_bundle"),
    )
    return require_runtime_content_bundle()
