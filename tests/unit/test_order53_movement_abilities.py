from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest
from tests.phase15a_charge_test_support import (
    _charge_lifecycle,
    _compact_test_unit_poses,
    _decision_request,
    _state,
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.engine.movement_legality import MovementCapabilitySet
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.geometry.pose import Pose


def _walker_catalog() -> ArmyCatalog:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return replace(
        catalog,
        datasheets=tuple(
            replace(
                sheet,
                keywords=replace(
                    sheet.keywords, keywords=("VEHICLE", "WALKER", "SUPER_HEAVY_WALKER")
                ),
            )
            if sheet.datasheet_id == "core-intercessor-like-infantry"
            else sheet
            for sheet in catalog.datasheets
        ),
    )


@pytest.mark.parametrize(
    "mode", [MovementMode.NORMAL, MovementMode.ADVANCE, MovementMode.FALL_BACK]
)
def test_source_linked_movement_ability_grants_only_its_transit_permissions(
    mode: MovementMode,
) -> None:
    capability = MovementCapabilitySet.from_keywords(
        ("VEHICLE", "SUPER_HEAVY_WALKER"),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        movement_mode=mode,
    )
    assert capability.can_move_through_friendly_models
    assert capability.can_move_through_enemy_models
    assert capability.friendly_model_transit_blocker_keywords == ("TITANIC",)
    assert capability.enemy_model_transit_blocker_keywords == ("TITANIC",)
    assert not capability.can_transit_enemy_engagement_range
    assert not capability.ignores_vertical_distance


@pytest.mark.parametrize("action", ["normal_move", "advance"])
def test_all_model_keyword_choice_precedes_move_and_advance_roll(action: str) -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("mover",),
        catalog=_walker_catalog(),
        game_id="order53-choice",
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(30, 20), model_count=5),
    )
    state = _state(lifecycle)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    session = LocalGameSession(lifecycle=lifecycle)
    request = _decision_request(session.advance_until_decision_or_terminal())
    request = _decision_request(
        session.submit_option(
            request_id=request.request_id,
            option_id=units["mover"].unit_instance_id,
            result_id="select-unit",
        )
    )
    choices = tuple(
        option
        for option in request.options
        if isinstance(option.payload, dict)
        and option.payload.get("movement_phase_action") == action
    )
    assert len(choices) == 2
    assert not any(
        event.event_type == "advance_roll_resolved"
        for event in lifecycle.decision_controller.event_log.records
    )
    assert {
        cast(bool, option.payload["move_keyword_choice"]["selected"])
        for option in choices
        if isinstance(option.payload, dict)
        and isinstance(option.payload["move_keyword_choice"], dict)
    } == {False, True}


@pytest.mark.parametrize("selected", [False, True])
@pytest.mark.parametrize("action", ["normal_move", "advance", "fall_back"])
@pytest.mark.parametrize("seed", range(4))
def test_move_keyword_completion_is_once_per_move_and_replays(
    selected: bool,
    action: str,
    seed: int,
) -> None:
    import json
    from typing import cast

    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
    from warhammer40k_core.engine.movement_proposals import (
        MovementProposalPayload,
        MovementProposalRequest,
    )
    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
    from warhammer40k_core.geometry.pathing import PathWitness

    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("mover", "observer"),
        catalog=_walker_catalog(),
        game_id=f"order53-completion-{seed}",
        enemy_model_poses=_compact_test_unit_poses(
            origin=Pose.at(10, 23) if action == "fall_back" else Pose.at(30, 20),
            model_count=5,
        ),
    )
    state = _state(lifecycle)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    session = LocalGameSession(lifecycle=lifecycle)
    request = _decision_request(session.advance_until_decision_or_terminal())
    actions = _decision_request(
        session.submit_option(
            request_id=request.request_id,
            option_id=units["mover"].unit_instance_id,
            result_id="unit",
        )
    )
    option_id = ("fall_back:ordered_retreat" if action == "fall_back" else action) + (
        ":move_keywords" if selected else ""
    )
    request = _decision_request(
        session.submit_option(
            request_id=actions.request_id,
            option_id=option_id,
            result_id="action",
        )
    )
    checkpoint = cast(GameLifecyclePayload, json.loads(json.dumps(lifecycle.to_payload())))
    assert GameLifecycle.from_payload(checkpoint).to_payload() == checkpoint
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    assert state.battlefield_state is not None
    placement = state.battlefield_state.unit_placement_by_id(units["mover"].unit_instance_id)
    witness = PathWitness.for_straight_line_endpoints(
        tuple(
            (
                model.model_instance_id,
                model.pose,
                Pose.at(model.pose.position.x, model.pose.position.y - 2),
            )
            for model in placement.model_placements
        )
    )
    submission = MovementProposalPayload(
        proposal_request_id=request.request_id,
        proposal_kind=proposal.proposal_kind,
        unit_instance_id=proposal.unit_instance_id,
        movement_phase_action=action,
        movement_mode="normal" if action == "normal_move" else action,
        fall_back_mode="ordered_retreat" if action == "fall_back" else None,
        witness=witness,
    )
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="path",
        payload=validate_json_value(submission.to_payload()),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    events = lifecycle.decision_controller.event_log.records
    rolls = tuple(event for event in events if event.event_type == "move_keyword_roll_resolved")
    assert len(rolls) == int(selected)
    if selected:
        from warhammer40k_core.core.dice import DiceRollState, DiceRollStatePayload

        payload = rolls[0].payload
        assert isinstance(payload, dict)
        roll = DiceRollState.from_payload(cast(DiceRollStatePayload, payload["roll_state"]))
        assert (units["mover"].unit_instance_id in state.battle_shocked_unit_ids) == (
            roll.current_total == 1
        )
        assert not any(event.event_type == "battle_shock_test_resolved" for event in events)
        from warhammer40k_core.adapters.event_stream import EventStreamCursor

        for viewer in ("player-a", "player-b"):
            delta = session.events_since(EventStreamCursor(), viewer_player_id=viewer)
            public = [
                event
                for event in delta["events"]
                if event["event_type"] == "move_keyword_roll_resolved"
            ]
            assert len(public) == 1
            assert public[0]["payload"] == payload
            json.dumps(delta, allow_nan=False)
    assert all("MOBILE" not in model.keywords for model in units["mover"].own_models)
    checkpoint = cast(GameLifecyclePayload, json.loads(json.dumps(lifecycle.to_payload())))
    assert GameLifecycle.from_payload(checkpoint).to_payload() == checkpoint
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="move-keywords")).run().status
        is ReplayRunStatus.REPRODUCED
    )
    if selected and action == "normal_move" and seed == 0:
        from warhammer40k_core.engine.phase import GameLifecycleError

        for field, value in (
            ("event_type", "removed-roll"),
            ("participant_id", "changed"),
            ("source_rule_id", "changed"),
            ("player_id", "player-b"),
            ("state_update", "changed"),
        ):
            changed = json.loads(json.dumps(checkpoint))
            events_payload = changed["decisions"]["event_log"]
            row = next(
                item
                for item in events_payload
                if item["event_type"] == "move_keyword_roll_resolved"
            )
            if field == "event_type":
                row[field] = value
            else:
                row["payload"][field] = value
            with pytest.raises(GameLifecycleError):
                GameLifecycle.from_payload(changed)


@pytest.mark.parametrize(
    ("height", "selected", "vertical", "endpoint", "accepted"),
    [
        (4, False, False, False, True),
        (4.001, False, False, False, False),
        (7, True, False, False, True),
        (4, False, True, False, False),
        (7, True, True, False, False),
        (4, False, False, True, False),
        (7, True, False, True, False),
    ],
)
def test_horizontal_terrain_sections_mobile_and_endpoints(
    height: float, selected: bool, vertical: bool, endpoint: bool, accepted: bool
) -> None:
    from warhammer40k_core.engine.battlefield_state import ModelDisplacementKind
    from warhammer40k_core.engine.movement_legality import MovementLegalityContext
    from warhammer40k_core.geometry.base import CircularBase
    from warhammer40k_core.geometry.pathing import PathWitness, TerrainPathLegalityContext
    from warhammer40k_core.geometry.terrain import (
        TerrainFeatureDefinition,
        TerrainFeatureKind,
        TerrainWallDefinition,
    )
    from warhammer40k_core.geometry.terrain_classification import TerrainAreaClassification
    from warhammer40k_core.geometry.volume import Model, ModelVolume

    mover = Model(
        model_id="walker",
        pose=Pose.at(1, 1),
        base=CircularBase(radius=0.5),
        volume=ModelVolume(height=2),
    )
    from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry

    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=3,
        center_y_inches=5,
        width_inches=4,
        depth_inches=14,
        display_template_id="test:order53",
    )
    feature = TerrainFeatureDefinition(
        footprint_center_x_inches=3,
        footprint_center_y_inches=5,
        footprint_width_inches=4,
        footprint_depth_inches=14,
        rules_footprint_polygon=display.footprint_polygon,
        display_geometry=display,
        feature_id="mixed-height",
        feature_kind=TerrainFeatureKind.BATTLEFIELD_DEBRIS_AND_STATUARY,
        classification=TerrainAreaClassification.DENSE,
        walls=(
            TerrainWallDefinition(
                wall_id="crossed",
                bottom_z_inches=0,
                center_x_inches=3,
                center_y_inches=1,
                width_inches=1,
                depth_inches=2,
                height_inches=height,
            ),
            TerrainWallDefinition(
                wall_id="tall-section",
                bottom_z_inches=0,
                center_x_inches=3,
                center_y_inches=10,
                width_inches=1,
                depth_inches=2,
                height_inches=10,
            ),
        ),
    )
    context = MovementLegalityContext.from_keywords(
        keywords=("VEHICLE", "SUPER_HEAVY_WALKER") + (("MOBILE",) if selected else ()),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        movement_mode=MovementMode.NORMAL,
        movement_phase_action="normal_move",
        displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
    ).to_terrain_path_legality_context(
        moving_model=mover,
        witness=PathWitness.for_paths(
            (
                (
                    mover.model_id,
                    (
                        mover.pose,
                        Pose.at(3, 1, 1 if vertical else 0),
                        Pose.at(3 if endpoint else 5, 1),
                    ),
                ),
            )
        ),
        terrain=(),
        terrain_features=(feature,),
        contact_footprint_available=True,
        sample_interval_inches=0.5,
    )
    assert context.validate().is_valid is accepted
    assert TerrainPathLegalityContext.from_payload(context.to_payload()) == context


@pytest.mark.parametrize(
    "mode",
    [MovementMode.CHARGE, MovementMode.PILE_IN, MovementMode.CONSOLIDATE],
)
def test_other_moves_do_not_inherit_walker_permissions(mode: MovementMode) -> None:
    capability = MovementCapabilitySet.from_keywords(
        ("VEHICLE", "SUPER_HEAVY_WALKER"),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        movement_mode=mode,
    )
    assert capability.horizontal_terrain_transit_height_inches is None
    assert not capability.can_move_through_enemy_models


@pytest.mark.parametrize("selected", [False, True])
@pytest.mark.parametrize("reroll", [None, "decline", "reroll:0"])
@pytest.mark.parametrize(
    "mode", [MovementMode.NORMAL, MovementMode.ADVANCE, MovementMode.FALL_BACK]
)
def test_reactive_move_retains_choice_across_rejection_restore_and_replay(
    selected: bool,
    reroll: str | None,
    mode: MovementMode,
) -> None:
    import json
    from typing import cast

    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
    from warhammer40k_core.engine.movement_proposals import (
        MovementProposalPayload,
        MovementProposalRequest,
    )
    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.engine.reaction_windows import ReactionWindow, ReactionWindowKind
    from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
    from warhammer40k_core.engine.triggered_movement import (
        TriggeredMovementDescriptor,
        TriggeredMovementEligibleUnit,
        TriggeredMovementKind,
    )
    from warhammer40k_core.engine.triggered_movement_selection import (
        triggered_movement_unit_selection_request,
    )
    from warhammer40k_core.geometry.pathing import PathWitness

    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("mover", "observer"),
        catalog=_walker_catalog(),
        game_id="order53-reactive",
        enemy_model_poses=_compact_test_unit_poses(
            origin=Pose.at(10, 23) if mode is MovementMode.FALL_BACK else Pose.at(30, 20),
            model_count=5,
        ),
    )
    state = _state(lifecycle)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    unit_id = units["mover"].unit_instance_id
    descriptor = TriggeredMovementDescriptor(
        movement_kind=TriggeredMovementKind.TRIGGERED,
        source_rule_id="test:movement-reaction",
        trigger_timing=ReactionWindow(
            phase=BattlePhase.MOVEMENT,
            window_kind=ReactionWindowKind.RULE_TRIGGER,
            source_step=None,
            source_event_id=None,
        ),
        max_distance_inches=4,
        movement_mode=mode,
        allow_within_engagement_range=mode is MovementMode.FALL_BACK,
    )
    eligible = TriggeredMovementEligibleUnit(
        unit_instance_id=unit_id,
        hook_id="test:normal-move",
        source_id=descriptor.source_rule_id,
    )
    if reroll is not None:
        from warhammer40k_core.core.dice import (
            DiceExpression,
            DiceRollSpec,
            RerollComponentSelectionPolicy,
            RerollPermission,
        )
        from warhammer40k_core.engine.dice import DiceRollManager

        roll = DiceRollManager(
            state.game_id, event_log=lifecycle.decision_controller.event_log
        ).roll(
            DiceRollSpec(
                expression=DiceExpression(quantity=1, sides=6),
                reason="Source distance",
                roll_type="reactive.distance",
                actor_id="player-a",
            )
        )
        descriptor = replace(descriptor, max_distance_inches=float(roll.current_total))
        eligible = replace(
            eligible,
            distance_roll_state=roll,
            distance_reroll_permission=RerollPermission(
                source_id=descriptor.source_rule_id,
                timing_window="after_distance_roll",
                owning_player_id="player-a",
                eligible_roll_type="reactive.distance",
                component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
            ),
        )
    request = triggered_movement_unit_selection_request(
        state=state,
        player_id="player-a",
        descriptor=descriptor,
        eligible_units=(eligible,),
    )
    lifecycle.decision_controller.request_decision(request)
    session = LocalGameSession(lifecycle=lifecycle)
    request = _decision_request(session.advance_until_decision_or_terminal())
    request = _decision_request(
        session.submit_option(
            request_id=request.request_id,
            option_id=f"triggered:{unit_id}" + (":move_keywords" if selected else ""),
            result_id="reactive-choice",
        )
    )
    assert state.battlefield_state is not None
    placement = state.battlefield_state.unit_placement_by_id(unit_id)
    if reroll is not None:
        checkpoint = cast(GameLifecyclePayload, json.loads(json.dumps(lifecycle.to_payload())))
        assert GameLifecycle.from_payload(checkpoint).to_payload() == checkpoint
        request = _decision_request(
            session.submit_option(
                request_id=request.request_id,
                result_id="distance-reroll",
                option_id=reroll,
            )
        )
    for distance in (10, 1):
        proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
        assert proposal.context is not None
        choice = proposal.context["move_keyword_choice"]
        assert isinstance(choice, dict)
        assert choice["selected"] is selected
        checkpoint = cast(GameLifecyclePayload, json.loads(json.dumps(lifecycle.to_payload())))
        assert GameLifecycle.from_payload(checkpoint).to_payload() == checkpoint
        before = state.battlefield_state
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id=f"path-{distance}",
            payload=validate_json_value(
                MovementProposalPayload(
                    proposal_request_id=request.request_id,
                    proposal_kind=proposal.proposal_kind,
                    unit_instance_id=unit_id,
                    movement_phase_action=cast(str, proposal.movement_phase_action),
                    witness=PathWitness.for_straight_line_endpoints(
                        tuple(
                            (
                                m.model_instance_id,
                                m.pose,
                                Pose.at(m.pose.position.x, m.pose.position.y - distance),
                            )
                            for m in placement.model_placements
                        )
                    ),
                ).to_payload()
            ),
        )
        if distance == 10:
            assert status.status_kind is LifecycleStatusKind.INVALID
            assert state.battlefield_state == before
            assert not any(
                e.event_type == "move_keyword_roll_resolved"
                for e in lifecycle.decision_controller.event_log.records
            )
            request = lifecycle.decision_controller.queue.pending_requests[0]
        else:
            assert status.status_kind is not LifecycleStatusKind.INVALID
            assert status.decision_request is not None
            assert status.decision_request.request_id != request.request_id
    completed = [
        event
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == "triggered_movement_resolved"
    ]
    assert len(completed) == 1
    moved = state.battlefield_state.unit_placement_by_id(unit_id)
    assert tuple(model.pose for model in moved.model_placements) == tuple(
        Pose.at(model.pose.position.x, model.pose.position.y - 1)
        for model in placement.model_placements
    )
    assert sum(
        e.event_type == "move_keyword_roll_resolved"
        for e in lifecycle.decision_controller.event_log.records
    ) == int(selected)
    checkpoint = cast(GameLifecyclePayload, json.loads(json.dumps(lifecycle.to_payload())))
    assert GameLifecycle.from_payload(checkpoint).to_payload() == checkpoint
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="reactive")).run().status
        is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.parametrize("native_descriptor", [False, True])
def test_attached_rules_unit_has_one_all_model_choice(native_descriptor: bool) -> None:
    from tests.phase15a_charge_declaration_helpers import charge_lifecycle

    from warhammer40k_core.core.datasheet import (
        CatalogAbilitySourceKind,
        CatalogAbilitySupport,
        DatasheetAbilityDescriptor,
    )
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        core_super_heavy_walker_2026_09 as source,
    )

    catalog = _walker_catalog()
    if native_descriptor:
        catalog = replace(
            catalog,
            datasheets=tuple(
                replace(
                    sheet,
                    keywords=replace(sheet.keywords, keywords=("VEHICLE", "WALKER")),
                    abilities=(
                        *sheet.abilities,
                        DatasheetAbilityDescriptor(
                            ability_id=source.movement_abilities()[0].ability_ids[0],
                            name="Arbitrary display name",
                            source_id=source.MOVEMENT_ABILITY_SOURCE_ID,
                            support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
                            source_kind=CatalogAbilitySourceKind.CORE,
                            effect_description="Source-bound descriptor",
                        ),
                    ),
                )
                if sheet.datasheet_id == "core-intercessor-like-infantry"
                else sheet
                for sheet in catalog.datasheets
            ),
        )
    lifecycle, _ = charge_lifecycle(
        alpha_unit_ids=("mover", "leader", "observer"),
        alpha_attached_unit_ids=("mover", "leader"),
        alpha_origins={"mover": Pose.at(10, 20), "leader": Pose.at(10, 21.8)},
        catalog=catalog,
        game_id="order53-attached",
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(30, 20), model_count=5),
    )
    state = _state(lifecycle)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    view = rules_unit_view_by_id(state=state, unit_instance_id="army-alpha:mover")
    session = LocalGameSession(lifecycle=lifecycle)
    request = _decision_request(session.advance_until_decision_or_terminal())
    request = _decision_request(
        session.submit_option(
            request_id=request.request_id, option_id=view.unit_instance_id, result_id="unit"
        )
    )
    selected = next(
        option for option in request.options if option.option_id == "normal_move:move_keywords"
    )
    assert isinstance(selected.payload, dict)
    choice = selected.payload["move_keyword_choice"]
    assert isinstance(choice, dict)
    assert choice["model_instance_ids"] == sorted(m.model_instance_id for m in view.alive_models())
    assert isinstance(choice["model_instance_ids"], list)
    assert len(choice["model_instance_ids"]) == 6
    for player in ("player-a", "player-b"):
        projection = session.view(viewer_player_id=player)
        assert projection["pending_decision"] is not None


@pytest.mark.parametrize(
    "mutation", ["selected", "source", "members", "unit", "missing", "source_record"]
)
def test_changed_move_choice_fails_before_queue_pop_and_on_restore(mutation: str) -> None:
    from copy import deepcopy
    from typing import cast

    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.movement_proposals import (
        MovementProposalPayload,
        MovementProposalRequest,
    )
    from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatusKind
    from warhammer40k_core.geometry.pathing import PathWitness

    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("mover", "observer"),
        catalog=_walker_catalog(),
        game_id="order53-tamper",
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(30, 20), model_count=5),
    )
    state = _state(lifecycle)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    session = LocalGameSession(lifecycle=lifecycle)
    request = _decision_request(session.advance_until_decision_or_terminal())
    request = _decision_request(
        session.submit_option(
            request_id=request.request_id,
            option_id=units["mover"].unit_instance_id,
            result_id="unit",
        )
    )
    request = _decision_request(
        session.submit_option(
            request_id=request.request_id, option_id="normal_move:move_keywords", result_id="action"
        )
    )
    assert isinstance(request.payload, dict)
    raw_proposal = request.payload["proposal_request"]
    assert isinstance(raw_proposal, dict)
    context = raw_proposal["context"]
    assert isinstance(context, dict)
    choice = context["move_keyword_choice"]
    assert isinstance(choice, dict)
    if mutation == "selected":
        choice.update(selected=False, keywords=[])
    elif mutation == "source":
        choice["source_rule_id"] = "unknown-source"
    elif mutation == "members":
        choice["model_instance_ids"] = [units["mover"].own_models[0].model_instance_id]
    elif mutation == "unit":
        raw_proposal["unit_instance_id"] = units["observer"].unit_instance_id
    else:
        del context["move_keyword_choice"]
        if mutation == "source_record":
            raw_proposal["source_decision_request_id"] = "invented"
            raw_proposal["source_decision_result_id"] = "invented"
    with pytest.raises(GameLifecycleError):
        GameLifecycle.from_payload(deepcopy(lifecycle.to_payload()))
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    assert state.battlefield_state is not None
    placement = state.battlefield_state.unit_placement_by_id(units["mover"].unit_instance_id)
    before = deepcopy(lifecycle.to_payload())
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="bad",
        payload=validate_json_value(
            MovementProposalPayload(
                proposal_request_id=request.request_id,
                proposal_kind=proposal.proposal_kind,
                unit_instance_id=proposal.unit_instance_id,
                movement_phase_action=cast(str, proposal.movement_phase_action),
                movement_mode="normal",
                witness=PathWitness.for_straight_line_endpoints(
                    tuple(
                        (
                            m.model_instance_id,
                            m.pose,
                            Pose.at(m.pose.position.x, m.pose.position.y - 2),
                        )
                        for m in placement.model_placements
                    )
                ),
            ).to_payload()
        ),
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert lifecycle.to_payload() == before


def test_surge_cannot_use_movement_ability_even_with_normal_geometry_mode() -> None:
    from warhammer40k_core.engine.battlefield_state import ModelDisplacementKind
    from warhammer40k_core.engine.movement_legality import MovementLegalityContext

    context = MovementLegalityContext.from_keywords(
        keywords=("VEHICLE", "SUPER_HEAVY_WALKER"),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        movement_mode=MovementMode.NORMAL,
        movement_phase_action=None,
        displacement_kind=ModelDisplacementKind.SURGE_MOVE,
    )
    assert context.capabilities.horizontal_terrain_transit_height_inches is None
    assert not context.capabilities.can_move_through_enemy_models


@pytest.mark.parametrize("titanic", [False, True])
def test_witnessed_normal_move_crosses_friendly_vehicle_but_not_titanic(titanic: bool) -> None:
    from tests.unit_keyword_helpers import with_unit_keywords

    from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
    from warhammer40k_core.engine.phases.movement_resolvers import resolve_normal_move
    from warhammer40k_core.geometry.pathing import PathWitness

    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("mover", "blocker"),
        catalog=_walker_catalog(),
        game_id="order53-transit",
        alpha_origins={"mover": Pose.at(10, 20), "blocker": Pose.at(10, 22)},
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(30, 20), model_count=5),
    )
    state = _state(lifecycle)
    state.army_definitions = [
        replace(
            army,
            units=tuple(
                with_unit_keywords(
                    unit, keywords=("VEHICLE", "MONSTER") + (("TITANIC",) if titanic else ())
                )
                if unit.unit_instance_id == units["blocker"].unit_instance_id
                else unit
                for unit in army.units
            ),
        )
        for army in state.army_definitions
    ]
    scenario = battlefield_scenario_for_state(state=state)
    placement = scenario.battlefield_state.unit_placement_by_id(units["mover"].unit_instance_id)
    result = resolve_normal_move(
        scenario=scenario,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=placement,
        state=state,
        path_witness=PathWitness.for_straight_line_endpoints(
            tuple(
                (m.model_instance_id, m.pose, Pose.at(m.pose.position.x, m.pose.position.y + 4))
                for m in placement.model_placements
            )
        ),
    )
    assert result.is_valid is not titanic


@pytest.mark.parametrize("selected", [False, True])
@pytest.mark.parametrize(
    "mode", [MovementMode.NORMAL, MovementMode.ADVANCE, MovementMode.FALL_BACK]
)
def test_finite_reactive_paths_offer_and_complete_the_same_keyword_choice(
    selected: bool, mode: MovementMode
) -> None:
    import json

    from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
    from warhammer40k_core.engine.reaction_windows import ReactionWindow, ReactionWindowKind
    from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
    from warhammer40k_core.engine.triggered_movement import (
        TriggeredMovementDescriptor,
        TriggeredMovementHandler,
        TriggeredMovementKind,
    )
    from warhammer40k_core.geometry.pathing import PathWitness

    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("mover", "observer"),
        catalog=_walker_catalog(),
        game_id="order53-finite",
        enemy_model_poses=_compact_test_unit_poses(
            origin=Pose.at(10, 23) if mode is MovementMode.FALL_BACK else Pose.at(30, 20),
            model_count=5,
        ),
    )
    state = _state(lifecycle)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    assert state.battlefield_state is not None
    placement = state.battlefield_state.unit_placement_by_id(units["mover"].unit_instance_id)
    request = TriggeredMovementHandler(
        ruleset_descriptor=state.runtime_ruleset_descriptor()
    ).request_from_state(
        state=state,
        decisions=lifecycle.decision_controller,
        unit_instance_id=placement.unit_instance_id,
        descriptor=TriggeredMovementDescriptor(
            movement_kind=TriggeredMovementKind.TRIGGERED,
            source_rule_id="test:finite-move",
            trigger_timing=ReactionWindow(
                phase=BattlePhase.MOVEMENT,
                window_kind=ReactionWindowKind.RULE_TRIGGER,
                source_step=None,
                source_event_id=None,
            ),
            max_distance_inches=3,
            movement_mode=mode,
            allow_within_engagement_range=mode is MovementMode.FALL_BACK,
        ),
        candidate_witnesses=(
            PathWitness.for_straight_line_endpoints(
                tuple(
                    (m.model_instance_id, m.pose, Pose.at(m.pose.position.x, m.pose.position.y - 2))
                    for m in placement.model_placements
                )
            ),
        ),
    )
    lifecycle.decision_controller.request_decision(request)
    session = LocalGameSession(lifecycle=lifecycle)
    session.advance_until_decision_or_terminal()
    option = next(
        option
        for option in request.options
        if isinstance(option.payload, dict)
        and isinstance(choice := option.payload.get("move_keyword_choice"), dict)
        and choice["selected"] is selected
    )
    assert ("MOBILE" in option.label) is selected
    session.submit_option(
        request_id=request.request_id, option_id=option.option_id, result_id="finite-path"
    )
    assert sum(
        event.event_type == "move_keyword_roll_resolved"
        for event in lifecycle.decision_controller.event_log.records
    ) == int(selected)
    checkpoint = cast(GameLifecyclePayload, json.loads(json.dumps(lifecycle.to_payload())))
    assert GameLifecycle.from_payload(checkpoint).to_payload() == checkpoint
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="finite")).run().status
        is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.parametrize("titanic", [False, True])
def test_fall_back_enemy_vehicle_transit_preserves_titanic_exclusion(titanic: bool) -> None:
    from tests.unit_keyword_helpers import with_unit_keywords

    from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
    from warhammer40k_core.engine.phases.movement_model import FallBackModeKind
    from warhammer40k_core.engine.phases.movement_resolvers import resolve_fall_back_move
    from warhammer40k_core.geometry.pathing import PathWitness

    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("mover",),
        catalog=_walker_catalog(),
        game_id="order53-enemy-transit",
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(10, 22), model_count=5),
    )
    state = _state(lifecycle)
    state.army_definitions = [
        replace(
            army,
            units=tuple(
                with_unit_keywords(
                    unit, keywords=("VEHICLE", "MONSTER") + (("TITANIC",) if titanic else ())
                )
                if army.player_id == "player-b"
                else unit
                for unit in army.units
            ),
        )
        for army in state.army_definitions
    ]
    scenario = battlefield_scenario_for_state(state=state)
    placement = scenario.battlefield_state.unit_placement_by_id(units["mover"].unit_instance_id)
    result = resolve_fall_back_move(
        scenario=scenario,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=placement,
        state=state,
        fall_back_mode=FallBackModeKind.DESPERATE_ESCAPE,
        path_witness=PathWitness.for_straight_line_endpoints(
            tuple(
                (m.model_instance_id, m.pose, Pose.at(m.pose.position.x, m.pose.position.y + 6))
                for m in placement.model_placements
            )
        ),
    )
    assert result.is_valid is not titanic


@pytest.mark.parametrize(
    ("mode", "surge"),
    [
        (MovementMode.CHARGE, False),
        (MovementMode.PILE_IN, False),
        (MovementMode.CONSOLIDATE, False),
        (MovementMode.NORMAL, True),
    ],
)
def test_reactive_resolver_rejects_keyword_grants_outside_source_modes(
    mode: MovementMode, surge: bool
) -> None:
    from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
    from warhammer40k_core.engine.move_ability_choices import keyword_choice_context
    from warhammer40k_core.engine.phase import GameLifecycleError
    from warhammer40k_core.engine.reaction_windows import ReactionWindow, ReactionWindowKind
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
    from warhammer40k_core.engine.triggered_movement import (
        TriggeredMovementDescriptor,
        TriggeredMovementKind,
    )
    from warhammer40k_core.engine.triggered_movement_resolution import resolve_triggered_movement
    from warhammer40k_core.geometry.pathing import PathWitness
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        core_super_heavy_walker_2026_09 as source,
    )

    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("mover",),
        catalog=_walker_catalog(),
        game_id="order53-reactive-exclusions",
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(30, 20), model_count=5),
    )
    state = _state(lifecycle)
    scenario = battlefield_scenario_for_state(state=state)
    placement = scenario.battlefield_state.unit_placement_by_id(units["mover"].unit_instance_id)
    descriptor = TriggeredMovementDescriptor(
        movement_kind=TriggeredMovementKind.SURGE if surge else TriggeredMovementKind.TRIGGERED,
        movement_mode=mode,
        source_rule_id="test:excluded-move",
        trigger_timing=ReactionWindow(
            phase=BattlePhase.CHARGE,
            window_kind=ReactionWindowKind.RULE_TRIGGER,
            source_step=None,
            source_event_id=None,
        ),
        max_distance_inches=4,
    )
    with pytest.raises(GameLifecycleError, match="descriptor's allowed move"):
        resolve_triggered_movement(
            scenario=scenario,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            unit_placement=placement,
            descriptor=descriptor,
            path_witness=PathWitness.for_straight_line_endpoints(
                tuple(
                    (m.model_instance_id, m.pose, Pose.at(m.pose.position.x, m.pose.position.y - 1))
                    for m in placement.model_placements
                )
            ),
            battle_round=state.battle_round,
            move_keyword_choice=keyword_choice_context(
                descriptor=source.movement_abilities()[0],
                unit=rules_unit_view_by_id(
                    state=state, unit_instance_id=placement.unit_instance_id
                ),
                selected=True,
            ),
            surge_target_unit_instance_id=units["enemy"].unit_instance_id if surge else None,
        )
