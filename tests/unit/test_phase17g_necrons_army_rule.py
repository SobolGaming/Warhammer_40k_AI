from __future__ import annotations

# pyright: reportPrivateUsage=false
import json
from collections.abc import Callable
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
    muster_army,
)
from warhammer40k_core.engine.battlefield_state import BattlefieldRuntimeState, ModelPlacement
from warhammer40k_core.engine.command_phase_start_hooks import (
    CommandPhaseStartRequestContext,
    CommandPhaseStartResultContext,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.necrons import army_rule
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.healing import SELECT_HEALING_MODEL_DECISION_TYPE
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    AttachmentDeclaration,
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import (
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_by_id
from warhammer40k_core.engine.setup_completion import SetupCompletionGate
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack

NECRON_UNIT_1_ID = "army-alpha:necron-warriors-1"
NECRON_UNIT_2_ID = "army-alpha:necron-warriors-2"


def test_lifecycle_reanimation_heals_wounded_unit_then_requests_next_activation() -> None:
    lifecycle = _battle_ready_lifecycle(alpha_unit_ids=("necron-warriors-1", "necron-warriors-2"))
    state = _require_state(lifecycle)
    unit = _unit_by_id(state, NECRON_UNIT_1_ID)
    wounded = unit.own_models[0]
    _set_model_wounds(
        state,
        model_instance_id=wounded.model_instance_id,
        wounds_remaining=wounded.starting_wounds - 1,
    )

    status = lifecycle.advance_until_decision_or_terminal()

    request = _require_request(status.decision_request)
    assert request.actor_id == "player-a"
    assert {option.option_id for option in request.options} == {
        f"necrons:reanimation_protocols:{NECRON_UNIT_1_ID}",
        f"necrons:reanimation_protocols:{NECRON_UNIT_2_ID}",
    }
    follow_up_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-necrons-heal-unit-1",
            request=request,
            selected_option_id=f"necrons:reanimation_protocols:{NECRON_UNIT_1_ID}",
        )
    )

    assert (
        _model_by_id(state, wounded.model_instance_id).wounds_remaining == wounded.starting_wounds
    )
    assert follow_up_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    follow_up_request = _require_request(follow_up_status.decision_request)
    assert {option.option_id for option in follow_up_request.options} == {
        f"necrons:reanimation_protocols:{NECRON_UNIT_2_ID}"
    }
    assert _reanimation_healing_effect_targets(lifecycle) == (NECRON_UNIT_1_ID,)


def test_reanimation_revive_choice_uses_necron_player_and_json_safe_records() -> None:
    lifecycle = _battle_ready_lifecycle(alpha_unit_ids=("necron-warriors-1",))
    state = _require_state(lifecycle)
    unit = _unit_by_id(state, NECRON_UNIT_1_ID)
    removed_placements = tuple(
        _remove_model(state, model_instance_id=model.model_instance_id)
        for model in unit.own_models[:2]
    )
    removed_model_ids = tuple(placement.model_instance_id for placement in removed_placements)

    status = lifecycle.advance_until_decision_or_terminal()
    request = _require_request(status.decision_request)
    lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-necrons-revive-unit-1",
            request=request,
            selected_option_id=f"necrons:reanimation_protocols:{NECRON_UNIT_1_ID}",
        )
    )

    healing_request = _require_request(lifecycle.decision_controller.queue.peek_next())
    assert healing_request.decision_type == SELECT_HEALING_MODEL_DECISION_TYPE
    assert healing_request.actor_id == "player-a"
    assert _healing_option_model_ids(healing_request) == removed_model_ids
    selected_model_id = removed_model_ids[0]
    lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-necrons-revive-model-result",
            request=healing_request,
            selected_option_id=_option_for_model(healing_request, selected_model_id).option_id,
        )
    )

    assert state.battlefield_state is not None
    assert selected_model_id in state.battlefield_state.placed_model_ids()
    assert selected_model_id not in state.battlefield_state.removed_model_ids
    assert _model_by_id(state, selected_model_id).wounds_remaining >= 1
    assert "<" not in json.dumps(lifecycle.decision_controller.to_payload(), sort_keys=True)


def test_reanimation_uses_attached_rules_unit_identity() -> None:
    lifecycle = _battle_ready_lifecycle(attached_alpha=True)
    state = _require_state(lifecycle)
    formation = state.army_definitions[0].attached_units[0]
    bodyguard = _unit_by_id(state, formation.bodyguard_unit_instance_id)
    for model in bodyguard.own_models[:2]:
        _remove_model(state, model_instance_id=model.model_instance_id)

    status = lifecycle.advance_until_decision_or_terminal()

    request = _require_request(status.decision_request)
    assert len(request.options) == 1
    option_payload = cast(dict[str, JsonValue], request.options[0].payload)
    assert option_payload["rules_unit_instance_id"] == formation.attached_unit_instance_id
    component_ids = cast(list[JsonValue], option_payload["component_unit_instance_ids"])
    assert tuple(component_ids) == (
        formation.bodyguard_unit_instance_id,
        *formation.leader_unit_instance_ids,
        *formation.support_unit_instance_ids,
    )
    follow_up_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-necrons-attached-result",
            request=request,
            selected_option_id=(
                f"necrons:reanimation_protocols:{formation.attached_unit_instance_id}"
            ),
        )
    )

    healing_request = _require_request(follow_up_status.decision_request)
    assert healing_request.decision_type == SELECT_HEALING_MODEL_DECISION_TYPE
    healing_payload = cast(dict[str, JsonValue], healing_request.payload)
    healing_effect = cast(dict[str, JsonValue], healing_payload["effect"])
    assert healing_effect["target_unit_instance_id"] == formation.attached_unit_instance_id


def test_reanimation_stale_rules_unit_rejects_before_queue_pop() -> None:
    lifecycle = _battle_ready_lifecycle(alpha_unit_ids=("necron-warriors-1",))
    state = _require_state(lifecycle)
    unit = _unit_by_id(state, NECRON_UNIT_1_ID)
    request = _require_request(lifecycle.advance_until_decision_or_terminal().decision_request)
    for model in unit.own_models:
        _remove_model(state, model_instance_id=model.model_instance_id)

    status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-necrons-stale-result",
            request=request,
            selected_option_id=f"necrons:reanimation_protocols:{NECRON_UNIT_1_ID}",
        )
    )

    assert status.status_kind is LifecycleStatusKind.INVALID
    invalid_payload = cast(dict[str, JsonValue], status.payload)
    assert invalid_payload["invalid_reason"] == "rules_unit_destroyed"
    assert lifecycle.decision_controller.queue.pending_requests == (request,)
    assert lifecycle.decision_controller.records == ()


def test_reanimation_request_returns_none_for_non_necrons_army() -> None:
    lifecycle = _battle_ready_lifecycle(necrons_alpha=False)

    assert army_rule.reanimation_protocols_request(_command_request_context(lifecycle)) is None


def test_reanimation_request_filters_non_necrons_and_destroyed_rules_units() -> None:
    lifecycle = _battle_ready_lifecycle(
        alpha_unit_ids=("necron-warriors-1", "necron-warriors-2", "necron-warriors-3")
    )
    state = _require_state(lifecycle)
    _update_unit(
        state,
        unit_instance_id=NECRON_UNIT_2_ID,
        update=lambda unit: replace(unit, faction_keywords=()),
    )
    destroyed_unit = _unit_by_id(state, "army-alpha:necron-warriors-3")
    for model in destroyed_unit.own_models:
        _remove_model(state, model_instance_id=model.model_instance_id)

    request = _require_request(
        army_rule.reanimation_protocols_request(_command_request_context(lifecycle))
    )

    assert {option.option_id for option in request.options} == {
        f"necrons:reanimation_protocols:{NECRON_UNIT_1_ID}"
    }


def test_reanimation_result_validation_rejects_drifted_payloads() -> None:
    lifecycle = _battle_ready_lifecycle(alpha_unit_ids=("necron-warriors-1",))
    request = _require_request(
        army_rule.reanimation_protocols_request(_command_request_context(lifecycle))
    )

    with pytest.raises(GameLifecycleError, match="requires request context"):
        army_rule.reanimation_protocols_request(cast(CommandPhaseStartRequestContext, object()))
    with pytest.raises(GameLifecycleError, match="requires result context"):
        army_rule.apply_reanimation_protocols_result(cast(CommandPhaseStartResultContext, object()))

    wrong_type_request = DecisionRequest(
        request_id="phase17g-necrons-wrong-type",
        decision_type="other_decision",
        actor_id="player-a",
        payload={"hook_id": army_rule.HOOK_ID},
        options=(
            DecisionOption(
                option_id="ignored",
                label="Ignored",
                payload={},
            ),
        ),
    )
    wrong_type_result = DecisionResult(
        result_id="phase17g-necrons-wrong-type-result",
        request_id=wrong_type_request.request_id,
        decision_type=wrong_type_request.decision_type,
        actor_id="player-a",
        selected_option_id="ignored",
        payload={},
    )
    assert not army_rule.apply_reanimation_protocols_result(
        _command_result_context(
            lifecycle,
            request=wrong_type_request,
            result=wrong_type_result,
        )
    )

    wrong_hook_request = replace(request, payload={"hook_id": "other-hook"})
    assert not army_rule.apply_reanimation_protocols_result(
        _command_result_context(
            lifecycle,
            request=wrong_hook_request,
            result=DecisionResult.for_request(
                result_id="phase17g-necrons-wrong-request-hook",
                request=wrong_hook_request,
                selected_option_id=f"necrons:reanimation_protocols:{NECRON_UNIT_1_ID}",
            ),
        )
    )

    missing_actor_request = replace(request, actor_id=None)
    with pytest.raises(GameLifecycleError, match="requires an actor"):
        army_rule.apply_reanimation_protocols_result(
            _command_result_context(
                lifecycle,
                request=missing_actor_request,
                result=DecisionResult.for_request(
                    result_id="phase17g-necrons-missing-actor",
                    request=missing_actor_request,
                    selected_option_id=f"necrons:reanimation_protocols:{NECRON_UNIT_1_ID}",
                ),
            )
        )

    inactive_actor_request = replace(request, actor_id="player-b")
    with pytest.raises(GameLifecycleError, match="must be the active player"):
        army_rule.apply_reanimation_protocols_result(
            _command_result_context(
                lifecycle,
                request=inactive_actor_request,
                result=DecisionResult.for_request(
                    result_id="phase17g-necrons-inactive-actor",
                    request=inactive_actor_request,
                    selected_option_id=f"necrons:reanimation_protocols:{NECRON_UNIT_1_ID}",
                ),
            )
        )

    non_necrons_lifecycle = _battle_ready_lifecycle(necrons_alpha=False)
    with pytest.raises(GameLifecycleError, match="does not own Necrons"):
        army_rule.apply_reanimation_protocols_result(
            _command_result_context(
                non_necrons_lifecycle,
                request=request,
                result=DecisionResult.for_request(
                    result_id="phase17g-necrons-non-necrons-actor",
                    request=request,
                    selected_option_id=f"necrons:reanimation_protocols:{NECRON_UNIT_1_ID}",
                ),
            )
        )

    with pytest.raises(GameLifecycleError, match="hook_id drift"):
        army_rule.apply_reanimation_protocols_result(
            _command_result_context(
                lifecycle,
                request=_request_with_first_option_payload(
                    request,
                    {"hook_id": "other-hook"},
                ),
                result=DecisionResult.for_request(
                    result_id="phase17g-necrons-result-hook-drift",
                    request=_request_with_first_option_payload(
                        request,
                        {"hook_id": "other-hook"},
                    ),
                    selected_option_id=f"necrons:reanimation_protocols:{NECRON_UNIT_1_ID}",
                ),
            )
        )

    player_drift_request = _request_with_first_option_payload(
        request,
        _first_option_payload_with(request, key="player_id", value="player-b"),
    )
    with pytest.raises(GameLifecycleError, match="player drift"):
        army_rule.apply_reanimation_protocols_result(
            _command_result_context(
                lifecycle,
                request=player_drift_request,
                result=DecisionResult.for_request(
                    result_id="phase17g-necrons-player-drift",
                    request=player_drift_request,
                    selected_option_id=f"necrons:reanimation_protocols:{NECRON_UNIT_1_ID}",
                ),
            )
        )

    option_drift_request = replace(
        request,
        options=(
            replace(
                request.options[0],
                option_id="necrons:reanimation_protocols:wrong-rules-unit",
            ),
        ),
    )
    with pytest.raises(GameLifecycleError, match="option_id drift"):
        army_rule.apply_reanimation_protocols_result(
            _command_result_context(
                lifecycle,
                request=option_drift_request,
                result=DecisionResult.for_request(
                    result_id="phase17g-necrons-option-drift",
                    request=option_drift_request,
                    selected_option_id="necrons:reanimation_protocols:wrong-rules-unit",
                ),
            )
        )

    stale_lifecycle = _battle_ready_lifecycle(alpha_unit_ids=("necron-warriors-1",))
    stale_state = _require_state(stale_lifecycle)
    stale_request = _require_request(
        army_rule.reanimation_protocols_request(_command_request_context(stale_lifecycle))
    )
    stale_unit = _unit_by_id(stale_state, NECRON_UNIT_1_ID)
    for model in stale_unit.own_models:
        _remove_model(stale_state, model_instance_id=model.model_instance_id)
    with pytest.raises(GameLifecycleError, match="no longer eligible"):
        army_rule.apply_reanimation_protocols_result(
            _command_result_context(
                stale_lifecycle,
                request=stale_request,
                result=DecisionResult.for_request(
                    result_id="phase17g-necrons-stale-direct",
                    request=stale_request,
                    selected_option_id=f"necrons:reanimation_protocols:{NECRON_UNIT_1_ID}",
                ),
            )
        )


def test_reanimation_fail_fast_guards_and_revival_geometry_edges() -> None:
    lifecycle = _battle_ready_lifecycle(alpha_unit_ids=("necron-warriors-1",))
    state = _require_state(lifecycle)
    army = state.army_definition_for_player("player-a")
    if army is None:
        raise AssertionError("player-a army is required")
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=NECRON_UNIT_1_ID)
    current_phase = state.current_battle_phase
    if current_phase is None:
        raise AssertionError("current_battle_phase is required")

    with pytest.raises(GameLifecycleError, match="lookup requires GameState"):
        army_rule._eligible_reanimation_rules_units(cast(GameState, object()), army=army)
    with pytest.raises(GameLifecycleError, match="lookup requires ArmyDefinition"):
        army_rule._eligible_reanimation_rules_units(
            state,
            army=cast(ArmyDefinition, object()),
        )
    with pytest.raises(GameLifecycleError, match="owner drift"):
        army_rule._eligible_reanimation_rules_units(
            state,
            army=replace(army, player_id="player-b"),
        )
    with pytest.raises(GameLifecycleError, match="event records must be EventRecord"):
        army_rule._resolved_reanimation_rules_unit_ids(
            records=cast(tuple[EventRecord, ...], (object(),)),
            state=state,
            player_id="player-a",
        )
    with pytest.raises(GameLifecycleError, match="healing event missing effect"):
        army_rule._resolved_reanimation_rules_unit_ids(
            records=(
                EventRecord(
                    event_id="phase17g-necrons-missing-effect",
                    event_type="healing_resolved",
                    payload={},
                ),
            ),
            state=state,
            player_id="player-a",
        )
    assert army_rule._resolved_reanimation_rules_unit_ids(
        records=(
            EventRecord(
                event_id="phase17g-necrons-other-hook",
                event_type="healing_resolved",
                payload={"effect": {"source_context": {"hook_id": "other-hook"}}},
            ),
            EventRecord(
                event_id="phase17g-necrons-resolved",
                event_type=army_rule.REANIMATION_RESOLVED_EVENT,
                payload={
                    "hook_id": army_rule.HOOK_ID,
                    "player_id": "player-a",
                    "battle_round": state.battle_round,
                    "phase": current_phase.value,
                    "rules_unit_instance_id": NECRON_UNIT_1_ID,
                },
            ),
        ),
        state=state,
        player_id="player-a",
    ) == {NECRON_UNIT_1_ID}

    with pytest.raises(GameLifecycleError, match="rolling requires decisions"):
        army_rule._roll_reanimation_d3(
            state=state,
            decisions=cast(DecisionController, object()),
            rules_unit=rules_unit,
        )

    model = _unit_by_id(state, NECRON_UNIT_1_ID).own_models[0]
    _remove_model(state, model_instance_id=model.model_instance_id)
    removed_rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=NECRON_UNIT_1_ID)
    if state.battlefield_state is None:
        raise AssertionError("battlefield_state is required")
    state.battlefield_state = state.battlefield_state.without_unit_placement(NECRON_UNIT_1_ID)
    with pytest.raises(GameLifecycleError, match="requires placed anchors"):
        army_rule._revival_placements_for_rules_unit(
            state=state,
            army=army,
            rules_unit=removed_rules_unit,
        )

    geometry_state = _require_state(_battle_ready_lifecycle())
    battlefield = geometry_state.battlefield_state
    if battlefield is None:
        raise AssertionError("battlefield_state is required")
    anchor_model_id = _unit_by_id(geometry_state, NECRON_UNIT_1_ID).own_models[0].model_instance_id
    anchor = battlefield.model_placement_by_id(anchor_model_id)
    bounded_pose = army_rule._candidate_revival_pose(
        battlefield=replace(battlefield, battlefield_width_inches=anchor.pose.position.x),
        anchor=anchor,
        index=0,
    )
    assert bounded_pose.position.x < anchor.pose.position.x
    with pytest.raises(GameLifecycleError, match="could not derive revival placement"):
        army_rule._candidate_revival_pose(
            battlefield=replace(
                battlefield,
                battlefield_width_inches=0.1,
                battlefield_depth_inches=0.1,
            ),
            anchor=replace(anchor, pose=Pose.at(0.0, 0.0, 0.0)),
            index=0,
        )

    keyword_lifecycle = _battle_ready_lifecycle(necrons_alpha=False)
    keyword_state = _require_state(keyword_lifecycle)
    _update_unit(
        keyword_state,
        unit_instance_id=NECRON_UNIT_1_ID,
        update=_unit_with_necrons_keyword,
    )
    assert army_rule._necrons_army_for_player(keyword_state, player_id="player-a") is not None
    with pytest.raises(GameLifecycleError, match="army lookup requires GameState"):
        army_rule._necrons_army_for_player(cast(GameState, object()), player_id="player-a")
    keyword_state.player_ids = ("player-a", "player-b", "player-c")
    assert army_rule._necrons_army_for_player(keyword_state, player_id="player-c") is None

    with pytest.raises(GameLifecycleError, match="keyword lookup requires rules unit"):
        army_rule._rules_unit_has_necrons_keyword(cast(RulesUnitView, object()))
    with pytest.raises(GameLifecycleError, match="keyword lookup requires UnitInstance"):
        army_rule._unit_has_necrons_keyword(cast(UnitInstance, object()))
    with pytest.raises(GameLifecycleError, match="label requires rules unit"):
        army_rule._rules_unit_label(cast(RulesUnitView, object()))
    state.player_ids = ("player-a", "player-b", "player-c")
    with pytest.raises(GameLifecycleError, match="requires one opposing player"):
        army_rule._opposing_player_id(state=state, player_id="player-a")

    state.battlefield_state = None
    with pytest.raises(GameLifecycleError, match="requires battlefield_state"):
        army_rule._battlefield_state(state)
    state.battlefield_state = cast(BattlefieldRuntimeState, object())
    with pytest.raises(GameLifecycleError, match="battlefield_state is invalid"):
        army_rule._battlefield_state(state)

    with pytest.raises(GameLifecycleError, match="event payload must be an object"):
        army_rule._event_payload_object(
            EventRecord(
                event_id="phase17g-necrons-scalar-event",
                event_type="scalar",
                payload="not-an-object",
            )
        )
    with pytest.raises(GameLifecycleError, match="payload must be an object"):
        army_rule._payload_object("not-an-object")
    with pytest.raises(GameLifecycleError, match="missing required key"):
        army_rule._payload_string({}, key="missing")
    with pytest.raises(GameLifecycleError, match="must be a string"):
        army_rule._validate_identifier("field", object())
    with pytest.raises(GameLifecycleError, match="must not be empty"):
        army_rule._validate_identifier("field", " ")


def _battle_ready_lifecycle(
    *,
    alpha_unit_ids: tuple[str, ...] = ("necron-warriors-1",),
    attached_alpha: bool = False,
    necrons_alpha: bool = True,
) -> GameLifecycle:
    config = _config(alpha_unit_ids=alpha_unit_ids, attached_alpha=attached_alpha)
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    state = _require_state(lifecycle)
    for army in _mustered_armies(config):
        state.record_army_definition(
            _as_necrons(army) if necrons_alpha and army.player_id == "player-a" else army
        )
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase17g-necrons-battlefield",
        armies=tuple(state.army_definitions),
    )
    state.record_battlefield_state(scenario.battlefield_state)
    state.record_secondary_mission_choice(_fixed_secondary_choice(player_id="player-a"))
    state.record_secondary_mission_choice(_fixed_secondary_choice(player_id="player-b"))
    _complete_setup_through_gate(state=state, config=config)
    _runtime_content_bundle(lifecycle)
    assert state.stage is GameLifecycleStage.BATTLE
    return lifecycle


def _config(
    *,
    alpha_unit_ids: tuple[str, ...],
    attached_alpha: bool,
) -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    alpha_request = (
        _attached_alpha_army_muster_request(catalog=catalog)
        if attached_alpha
        else _army_muster_request(
            catalog=catalog,
            player_id="player-a",
            army_id="army-alpha",
            unit_selection_ids=alpha_unit_ids,
        )
    )
    return GameConfig(
        game_id="phase17g-necrons-lifecycle-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
            descriptor_version="core-v2-phase17g-necrons-test",
        ),
        army_catalog=catalog,
        army_muster_requests=(
            alpha_request,
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=("enemy-unit",),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down"),
        mission_setup=_mission_setup(),
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_ids: tuple[str, ...],
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
        force_disposition_id="purge-the-foe",
        unit_selections=tuple(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            )
            for unit_selection_id in unit_selection_ids
        ),
    )


def _attached_alpha_army_muster_request(*, catalog: ArmyCatalog) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id="army-alpha",
        player_id="player-a",
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        force_disposition_id="purge-the-foe",
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id="bodyguard-unit",
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
            UnitMusterSelection(
                unit_selection_id="leader-unit",
                datasheet_id="core-character-leader",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-character-leader",
                        model_count=1,
                    ),
                ),
            ),
            UnitMusterSelection(
                unit_selection_id="support-unit",
                datasheet_id="core-character-support",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-character-support",
                        model_count=1,
                    ),
                ),
            ),
        ),
        attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="leader-unit",
                bodyguard_unit_selection_id="bodyguard-unit",
            ),
            AttachmentDeclaration(
                source_unit_selection_id="support-unit",
                bodyguard_unit_selection_id="bodyguard-unit",
            ),
        ),
    )


def _mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )


def _as_necrons(army: ArmyDefinition) -> ArmyDefinition:
    return replace(
        army,
        detachment_selection=replace(
            army.detachment_selection,
            faction_id=army_rule.NECRONS_FACTION_ID,
        ),
        units=tuple(_unit_with_necrons_keyword(unit) for unit in army.units),
    )


def _unit_with_necrons_keyword(unit: UnitInstance) -> UnitInstance:
    return replace(
        unit,
        faction_keywords=tuple(sorted({*unit.faction_keywords, "Necrons"})),
    )


def _complete_setup_through_gate(*, state: GameState, config: GameConfig) -> None:
    final_setup_step = state.setup_sequence[-1]
    while state.current_setup_step is not final_setup_step:
        state.complete_current_setup_step()
    SetupCompletionGate().complete_setup_and_enter_battle(
        state=state,
        decisions=DecisionController(),
        config=config,
    )


def test_reanimation_phase_start_engagement_ignores_destroyed_enemy_placements() -> None:
    lifecycle = _battle_ready_lifecycle()
    state = _require_state(lifecycle)
    necron_unit = _unit_by_id(state, NECRON_UNIT_1_ID)
    enemy_unit_id = "army-beta:enemy-unit"
    enemy_unit = _unit_by_id(state, enemy_unit_id)
    necron_poses = (
        Pose.at(x=10.0, y=20.0),
        *tuple(Pose.at(x=30.0 + index, y=30.0) for index in range(1, 5)),
    )
    enemy_poses = (
        Pose.at(x=10.5, y=20.0),
        *tuple(Pose.at(x=50.0 + index, y=50.0) for index in range(1, 5)),
    )
    _place_unit_model_poses(state, unit_id=necron_unit.unit_instance_id, poses=necron_poses)
    _place_unit_model_poses(state, unit_id=enemy_unit_id, poses=enemy_poses)
    _set_model_wounds(
        state,
        model_instance_id=enemy_unit.own_models[0].model_instance_id,
        wounds_remaining=0,
    )
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=NECRON_UNIT_1_ID)

    assert (
        army_rule._phase_start_enemy_engagement_model_ids(state=state, rules_unit=rules_unit) == ()
    )


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )


def _fixed_secondary_choice(*, player_id: str) -> SecondaryMissionChoice:
    return SecondaryMissionChoice(
        player_id=player_id,
        mode=SecondaryMissionMode.FIXED,
        fixed_mission_ids=("assassination", "bring_it_down"),
    )


def _require_state(lifecycle: GameLifecycle) -> GameState:
    if lifecycle.state is None:
        raise AssertionError("lifecycle state is required")
    return lifecycle.state


def _require_request(request: DecisionRequest | None) -> DecisionRequest:
    if request is None:
        raise AssertionError("decision request is required")
    return request


def _runtime_content_bundle(lifecycle: GameLifecycle) -> RuntimeContentBundle:
    require_runtime_content_bundle = cast(
        Callable[[], RuntimeContentBundle],
        object.__getattribute__(lifecycle, "_require_runtime_content_bundle"),
    )
    return require_runtime_content_bundle()


def _command_request_context(lifecycle: GameLifecycle) -> CommandPhaseStartRequestContext:
    return CommandPhaseStartRequestContext(
        state=_require_state(lifecycle),
        decisions=lifecycle.decision_controller,
        active_player_id="player-a",
    )


def _command_result_context(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    result: DecisionResult,
) -> CommandPhaseStartResultContext:
    return CommandPhaseStartResultContext(
        state=_require_state(lifecycle),
        decisions=lifecycle.decision_controller,
        request=request,
        result=result,
        active_player_id="player-a",
    )


def _request_with_first_option_payload(
    request: DecisionRequest,
    payload: dict[str, JsonValue],
) -> DecisionRequest:
    return replace(
        request,
        options=(replace(request.options[0], payload=payload),),
    )


def _first_option_payload_with(
    request: DecisionRequest,
    *,
    key: str,
    value: JsonValue,
) -> dict[str, JsonValue]:
    payload = dict(cast(dict[str, JsonValue], request.options[0].payload))
    payload[key] = value
    return payload


def _remove_model(state: GameState, *, model_instance_id: str) -> ModelPlacement:
    if state.battlefield_state is None:
        raise AssertionError("battlefield_state is required")
    placement = state.battlefield_state.model_placement_by_id(model_instance_id)
    _set_model_wounds(state, model_instance_id=model_instance_id, wounds_remaining=0)
    state.battlefield_state = state.battlefield_state.with_removed_models((model_instance_id,))
    return placement


def _update_unit(
    state: GameState,
    *,
    unit_instance_id: str,
    update: Callable[[UnitInstance], UnitInstance],
) -> None:
    updated_armies: list[ArmyDefinition] = []
    did_update = False
    for army in state.army_definitions:
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            if unit.unit_instance_id == unit_instance_id:
                updated_units.append(update(unit))
                did_update = True
                continue
            updated_units.append(unit)
        updated_armies.append(replace(army, units=tuple(updated_units)))
    if not did_update:
        raise AssertionError(f"missing unit {unit_instance_id}")
    state.army_definitions = updated_armies


def _set_model_wounds(
    state: GameState,
    *,
    model_instance_id: str,
    wounds_remaining: int,
) -> None:
    updated_armies: list[ArmyDefinition] = []
    did_update = False
    for army in state.army_definitions:
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            updated_models: list[ModelInstance] = []
            for model in unit.own_models:
                if model.model_instance_id != model_instance_id:
                    updated_models.append(model)
                    continue
                updated_models.append(replace(model, wounds_remaining=wounds_remaining))
                did_update = True
            updated_units.append(replace(unit, own_models=tuple(updated_models)))
        updated_armies.append(replace(army, units=tuple(updated_units)))
    if not did_update:
        raise AssertionError(f"missing model {model_instance_id}")
    state.army_definitions = updated_armies


def _place_unit_model_poses(
    state: GameState,
    *,
    unit_id: str,
    poses: tuple[Pose, ...],
) -> None:
    if state.battlefield_state is None:
        raise AssertionError("battlefield_state is required")
    unit_placement = state.battlefield_state.unit_placement_by_id(unit_id)
    if len(poses) != len(unit_placement.model_placements):
        raise AssertionError("pose fixture must match placed model count")
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        unit_placement.with_model_placements(
            tuple(
                placement.with_pose(pose)
                for placement, pose in zip(unit_placement.model_placements, poses, strict=True)
            )
        )
    )


def _unit_by_id(state: GameState, unit_instance_id: str) -> UnitInstance:
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == unit_instance_id:
                return unit
    raise AssertionError(f"missing unit {unit_instance_id}")


def _model_by_id(state: GameState, model_instance_id: str) -> ModelInstance:
    for army in state.army_definitions:
        for unit in army.units:
            for model in unit.own_models:
                if model.model_instance_id == model_instance_id:
                    return model
    raise AssertionError(f"missing model {model_instance_id}")


def _healing_option_model_ids(request: DecisionRequest) -> tuple[str, ...]:
    return tuple(
        sorted(
            _payload_string(cast(dict[str, JsonValue], option.payload), key="model_instance_id")
            for option in request.options
        )
    )


def _option_for_model(request: DecisionRequest, model_instance_id: str) -> DecisionOption:
    for option in request.options:
        payload = cast(dict[str, JsonValue], option.payload)
        if payload["model_instance_id"] == model_instance_id:
            return option
    raise AssertionError(f"missing option for model {model_instance_id}")


def _reanimation_healing_effect_targets(lifecycle: GameLifecycle) -> tuple[str, ...]:
    targets: list[str] = []
    for record in lifecycle.decision_controller.event_log.records:
        if record.event_type != "healing_resolved":
            continue
        payload = cast(dict[str, JsonValue], record.payload)
        effect = cast(dict[str, JsonValue], payload["effect"])
        source_context = cast(dict[str, JsonValue], effect["source_context"])
        if source_context["hook_id"] == army_rule.HOOK_ID:
            targets.append(_payload_string(effect, key="target_unit_instance_id"))
    return tuple(targets)


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    value = payload[key]
    if type(value) is not str:
        raise AssertionError(f"{key} must be a string")
    return value
