from __future__ import annotations

import json
import math
from typing import cast

import pytest
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
    muster_army,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    ModelPlacement,
    PlacedArmy,
    UnitPlacement,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalPayload,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.movement import (
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    MovementPhaseActionKind,
)
from warhammer40k_core.engine.triggered_movement import (
    DECLINE_TRIGGERED_MOVEMENT_OPTION_ID,
    SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27 as faction_detachment_source,
)

_RANGERS_DATASHEET_ID = "000000592"
_RANGERS_MODEL_PROFILE_ID = "000000592:rangers"
_CORE_ENEMY_DATASHEET_ID = "core-intercessor-like-infantry"
_CORE_ENEMY_MODEL_PROFILE_ID = "core-intercessor-like"
_AELDARI_FACTION_ID = "aeldari"
_AELDARI_DETACHMENT_ID = "path-of-the-outcast"
_CORE_FACTION_ID = "core-marine-force"
_CORE_DETACHMENT_ID = "core-combined-arms"


@pytest.fixture(scope="module")
def rangers_facade_catalog() -> ArmyCatalog:
    return _rangers_facade_catalog()


@pytest.mark.integration
def test_generated_rangers_path_of_the_outcast_moves_through_local_session_facade(
    rangers_facade_catalog: ArmyCatalog,
) -> None:
    session, units = _rangers_movement_session(
        catalog=rangers_facade_catalog,
        game_id="aeldari-rangers-facade-single",
        ranger_selection_ids=("rangers",),
        enemy_selection_ids=("enemy",),
        origins={
            "army-a:rangers": Pose.at(12.0, 10.0),
            "army-b:enemy": Pose.at(18.0, 10.0),
        },
    )
    rangers = units["army-a:rangers"]
    enemy = units["army-b:enemy"]
    starting_placement = _unit_placement(session, rangers.unit_instance_id)

    status = session.advance_until_decision_or_terminal()
    status = _submit_normal_move(
        session,
        status=status,
        unit_instance_id=enemy.unit_instance_id,
        result_id_prefix="rangers-facade-enemy-move",
        dx=0.5,
    )
    triggered_request = _assert_triggered_request(
        status,
        unit_instance_id=rangers.unit_instance_id,
    )
    source_event_id = _trigger_source_event_id(triggered_request)

    proposal_status = session.submit_option(
        request_id=triggered_request.request_id,
        option_id=f"triggered:{rangers.unit_instance_id}",
        result_id="rangers-facade-select-rangers",
    )
    proposal_request = _request(proposal_status, MOVEMENT_PROPOSAL_DECISION_TYPE)
    parsed_proposal = MovementProposalRequest.from_decision_request_payload(
        proposal_request.payload
    )
    assert parsed_proposal.unit_instance_id == rangers.unit_instance_id
    assert parsed_proposal.proposal_kind.value == "surge_move"
    assert parsed_proposal.movement_phase_action == "surge_move"
    source_rule_id = _proposal_descriptor(parsed_proposal)["source_rule_id"]
    assert type(source_rule_id) is str
    assert source_rule_id.endswith("Datasheets_abilities:000000592:4")

    witness = _shift_witness(starting_placement, dx=0.25)
    assert PathWitness.from_payload(witness.to_payload()) == witness
    _submit_movement_proposal(
        session,
        status=proposal_status,
        result_id="rangers-facade-submit-path-witness",
        witness=witness,
    )

    moved_placement = _unit_placement(session, rangers.unit_instance_id)
    _assert_shifted(starting_placement, moved_placement, dx=0.25)
    trigger_events = tuple(
        record
        for record in session.lifecycle.decision_controller.event_log.records
        if record.event_type == "movement_end_surge_triggered"
    )
    assert len(trigger_events) == 1
    assert _json_object(trigger_events[0].payload)["trigger_event_id"] == source_event_id
    assert any(
        record.event_type == "triggered_movement_resolved"
        for record in session.lifecycle.decision_controller.event_log.records
    )

    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(session.lifecycle.to_payload(), sort_keys=True)),
    )
    restored = GameLifecycle.from_payload(payload)

    assert restored.to_payload() == payload
    restored_battlefield = _state(restored).battlefield_state
    assert restored_battlefield is not None
    restored_placement = restored_battlefield.unit_placement_by_id(rangers.unit_instance_id)
    assert restored_placement == moved_placement


@pytest.mark.integration
def test_generated_rangers_cannot_repeat_normal_move_reactions_in_one_phase(
    rangers_facade_catalog: ArmyCatalog,
) -> None:
    session, units = _rangers_movement_session(
        catalog=rangers_facade_catalog,
        game_id="aeldari-rangers-facade-repeat",
        ranger_selection_ids=("rangers-alpha", "rangers-beta"),
        enemy_selection_ids=("enemy-one", "enemy-two"),
        origins={
            "army-a:rangers-alpha": Pose.at(12.0, 8.0),
            "army-a:rangers-beta": Pose.at(12.0, 18.0),
            "army-b:enemy-one": Pose.at(17.0, 13.0),
            "army-b:enemy-two": Pose.at(20.5, 13.0),
        },
    )
    alpha = units["army-a:rangers-alpha"]
    beta = units["army-a:rangers-beta"]
    enemy_one = units["army-b:enemy-one"]
    enemy_two = units["army-b:enemy-two"]
    alpha_start = _unit_placement(session, alpha.unit_instance_id)
    beta_start = _unit_placement(session, beta.unit_instance_id)

    status = session.advance_until_decision_or_terminal()
    status = _submit_normal_move(
        session,
        status=status,
        unit_instance_id=enemy_one.unit_instance_id,
        result_id_prefix="rangers-repeat-enemy-one",
        dx=0.25,
    )
    alpha_first_request = _assert_triggered_request(
        status,
        unit_instance_id=alpha.unit_instance_id,
    )
    first_enemy_event_id = _trigger_source_event_id(alpha_first_request)
    status = _submit_triggered_move(
        session,
        status=status,
        unit_instance_id=alpha.unit_instance_id,
        result_id_prefix="rangers-repeat-alpha-first",
        dx=-0.25,
    )

    beta_first_request = _assert_triggered_request(
        status,
        unit_instance_id=beta.unit_instance_id,
    )
    assert _trigger_source_event_id(beta_first_request) == first_enemy_event_id
    status = _submit_triggered_move(
        session,
        status=status,
        unit_instance_id=beta.unit_instance_id,
        result_id_prefix="rangers-repeat-beta-first",
        dx=-0.25,
    )
    _assert_shifted(
        alpha_start,
        _unit_placement(session, alpha.unit_instance_id),
        dx=-0.25,
    )
    _assert_shifted(
        beta_start,
        _unit_placement(session, beta.unit_instance_id),
        dx=-0.25,
    )

    status = _submit_normal_move(
        session,
        status=status,
        unit_instance_id=enemy_two.unit_instance_id,
        result_id_prefix="rangers-repeat-enemy-two",
        dx=0.25,
    )
    second_request = _request(
        status,
        SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE,
    )
    assert second_request.actor_id == "player-a"
    assert {option.option_id for option in second_request.options} == {
        DECLINE_TRIGGERED_MOVEMENT_OPTION_ID
    }
    second_enemy_event_id = _trigger_source_event_id(second_request)
    assert second_enemy_event_id != first_enemy_event_id
    session.submit_option(
        request_id=second_request.request_id,
        option_id=DECLINE_TRIGGERED_MOVEMENT_OPTION_ID,
        result_id="rangers-repeat-decline-second-window",
    )
    _assert_shifted(
        alpha_start,
        _unit_placement(session, alpha.unit_instance_id),
        dx=-0.25,
    )
    _assert_shifted(
        beta_start,
        _unit_placement(session, beta.unit_instance_id),
        dx=-0.25,
    )

    alpha_applied_events = tuple(
        record
        for record in session.lifecycle.decision_controller.event_log.records
        if record.event_type == "triggered_movement_resolved"
        and _json_object(record.payload).get("unit_instance_id") == alpha.unit_instance_id
    )
    assert len(alpha_applied_events) == 1


def _rangers_facade_catalog() -> ArmyCatalog:
    generated_catalog = _ability_support_catalog_package().army_catalog
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    rangers = generated_catalog.datasheet_by_id(_RANGERS_DATASHEET_ID)
    linked_wargear_ids = {
        wargear_id
        for option in rangers.wargear_options
        for wargear_id in (*option.default_wargear_ids, *option.allowed_wargear_ids)
    }
    ranger_wargear = tuple(
        wargear for wargear in generated_catalog.wargear if wargear.wargear_id in linked_wargear_ids
    )
    faction_row = next(
        row
        for row in faction_detachment_source.faction_rows()
        if row.faction_id == _AELDARI_FACTION_ID
    )
    detachment_row = next(
        row
        for row in faction_detachment_source.detachment_rows()
        if row.faction_id == _AELDARI_FACTION_ID and row.detachment_id == _AELDARI_DETACHMENT_ID
    )
    aeldari = FactionDefinition(
        faction_id=faction_row.faction_id,
        name=faction_row.name,
        faction_keywords=tuple(
            sorted({*faction_row.faction_keywords, *rangers.keywords.faction_keywords})
        ),
        source_ids=faction_row.source_ids,
    )
    path_of_the_outcast = DetachmentDefinition(
        detachment_id=detachment_row.detachment_id,
        name=detachment_row.name,
        faction_id=detachment_row.faction_id,
        detachment_point_cost=detachment_row.detachment_point_cost,
        unit_datasheet_ids=(_RANGERS_DATASHEET_ID,),
        force_disposition_ids=(detachment_row.force_disposition_id,),
        source_ids=detachment_row.source_ids,
    )
    return ArmyCatalog(
        catalog_id="aeldari-rangers-facade",
        ruleset_id=base_catalog.ruleset_id,
        source_package_id="data-package:core-v2:aeldari-rangers-facade:phase17k-generated",
        datasheets=(*base_catalog.datasheets, rangers),
        wargear=(*base_catalog.wargear, *ranger_wargear),
        factions=(*base_catalog.factions, aeldari),
        army_rules=base_catalog.army_rules,
        detachments=(*base_catalog.detachments, path_of_the_outcast),
        enhancements=base_catalog.enhancements,
        stratagems=base_catalog.stratagems,
        source_ids=(
            generated_catalog.source_package_id,
            faction_detachment_source.SOURCE_PACKAGE_ID,
        ),
    )


def _rangers_movement_session(
    *,
    catalog: ArmyCatalog,
    game_id: str,
    ranger_selection_ids: tuple[str, ...],
    enemy_selection_ids: tuple[str, ...],
    origins: dict[str, Pose],
) -> tuple[LocalGameSession, dict[str, UnitInstance]]:
    config = GameConfig(
        game_id=game_id,
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-aeldari-rangers-facade-test"
        ),
        army_catalog=catalog,
        army_muster_requests=(
            _rangers_muster_request(
                catalog=catalog,
                selection_ids=ranger_selection_ids,
            ),
            _enemy_muster_request(
                catalog=catalog,
                selection_ids=enemy_selection_ids,
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
    armies = tuple(
        muster_army(catalog=catalog, request=request) for request in config.army_muster_requests
    )
    units = {unit.unit_instance_id: unit for army in armies for unit in army.units}
    if set(origins) != set(units):
        raise AssertionError("Rangers facade origins must cover every generated unit.")
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    state.record_battlefield_state(_battlefield_state(armies=armies, origins=origins))
    for player_id in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player_id=player_id,
                mode=SecondaryMissionMode.FIXED,
                fixed_mission_ids=("assassination", "bring_it_down"),
            )
        )
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    state.battle_round = 1
    state.active_player_id = "player-b"
    lifecycle_payload = cast(
        GameLifecyclePayload,
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": GameLifecycle().decision_controller.to_payload(),
            "reaction_queue": {"frames": []},
        },
    )
    return LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle_payload)), units


def _rangers_muster_request(
    *,
    catalog: ArmyCatalog,
    selection_ids: tuple[str, ...],
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id="army-a",
        player_id="player-a",
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=_AELDARI_FACTION_ID,
            detachment_ids=(_AELDARI_DETACHMENT_ID,),
        ),
        force_disposition_id="reconnaissance",
        unit_selections=tuple(
            UnitMusterSelection(
                unit_selection_id=selection_id,
                datasheet_id=_RANGERS_DATASHEET_ID,
                model_profile_selections=(ModelProfileSelection(_RANGERS_MODEL_PROFILE_ID, 5),),
            )
            for selection_id in selection_ids
        ),
    )


def _enemy_muster_request(
    *,
    catalog: ArmyCatalog,
    selection_ids: tuple[str, ...],
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id="army-b",
        player_id="player-b",
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=_CORE_FACTION_ID,
            detachment_ids=(_CORE_DETACHMENT_ID,),
        ),
        force_disposition_id="purge-the-foe",
        unit_selections=tuple(
            UnitMusterSelection(
                unit_selection_id=selection_id,
                datasheet_id=_CORE_ENEMY_DATASHEET_ID,
                model_profile_selections=(ModelProfileSelection(_CORE_ENEMY_MODEL_PROFILE_ID, 5),),
            )
            for selection_id in selection_ids
        ),
    )


def _battlefield_state(
    *,
    armies: tuple[ArmyDefinition, ...],
    origins: dict[str, Pose],
) -> BattlefieldRuntimeState:
    return BattlefieldRuntimeState(
        battlefield_id="aeldari-rangers-facade-battlefield",
        battlefield_width_inches=60.0,
        battlefield_depth_inches=44.0,
        placed_armies=tuple(
            PlacedArmy(
                army_id=army.army_id,
                player_id=army.player_id,
                unit_placements=tuple(
                    _placement_at(
                        army=army,
                        unit=unit,
                        origin=origins[unit.unit_instance_id],
                    )
                    for unit in army.units
                ),
            )
            for army in armies
        ),
    )


def _placement_at(
    *,
    army: ArmyDefinition,
    unit: UnitInstance,
    origin: Pose,
) -> UnitPlacement:
    poses = tuple(
        Pose.at(
            origin.position.x + ((index % 2) * 1.4),
            origin.position.y + ((index // 2) * 1.4),
            origin.position.z,
            facing_degrees=origin.facing.degrees,
        )
        for index in range(len(unit.own_models))
    )
    return UnitPlacement(
        army_id=army.army_id,
        player_id=army.player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id=army.army_id,
                player_id=army.player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=pose,
            )
            for model, pose in zip(unit.own_models, poses, strict=True)
        ),
    )


def _submit_normal_move(
    session: LocalGameSession,
    *,
    status: LifecycleStatus,
    unit_instance_id: str,
    result_id_prefix: str,
    dx: float,
) -> LifecycleStatus:
    unit_request = _request(status, SELECT_MOVEMENT_UNIT_DECISION_TYPE)
    action_status = session.submit_option(
        request_id=unit_request.request_id,
        option_id=unit_instance_id,
        result_id=f"{result_id_prefix}-select-unit",
    )
    action_request = _request(action_status, SELECT_MOVEMENT_ACTION_DECISION_TYPE)
    proposal_status = session.submit_option(
        request_id=action_request.request_id,
        option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
        result_id=f"{result_id_prefix}-select-normal-move",
    )
    return _submit_movement_proposal(
        session,
        status=proposal_status,
        result_id=f"{result_id_prefix}-submit-path-witness",
        witness=_shift_witness(_unit_placement(session, unit_instance_id), dx=dx),
    )


def _submit_triggered_move(
    session: LocalGameSession,
    *,
    status: LifecycleStatus,
    unit_instance_id: str,
    result_id_prefix: str,
    dx: float,
) -> LifecycleStatus:
    request = _assert_triggered_request(status, unit_instance_id=unit_instance_id)
    proposal_status = session.submit_option(
        request_id=request.request_id,
        option_id=f"triggered:{unit_instance_id}",
        result_id=f"{result_id_prefix}-select-unit",
    )
    return _submit_movement_proposal(
        session,
        status=proposal_status,
        result_id=f"{result_id_prefix}-submit-path-witness",
        witness=_shift_witness(_unit_placement(session, unit_instance_id), dx=dx),
    )


def _submit_movement_proposal(
    session: LocalGameSession,
    *,
    status: LifecycleStatus,
    result_id: str,
    witness: PathWitness,
) -> LifecycleStatus:
    request = _request(status, MOVEMENT_PROPOSAL_DECISION_TYPE)
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    if proposal.movement_phase_action is None:
        raise AssertionError("Movement proposal request must identify its action.")
    movement_mode = proposal.context.get("movement_mode") if proposal.context is not None else None
    if movement_mode is not None and type(movement_mode) is not str:
        raise AssertionError("Movement proposal context mode must be a string.")
    return session.submit_parameterized_payload(
        request_id=request.request_id,
        payload=validate_json_value(
            MovementProposalPayload(
                proposal_request_id=proposal.request_id,
                proposal_kind=proposal.proposal_kind,
                unit_instance_id=proposal.unit_instance_id,
                movement_phase_action=proposal.movement_phase_action,
                movement_mode=movement_mode,
                witness=witness,
            ).to_payload()
        ),
        result_id=result_id,
    )


def _assert_triggered_request(
    status: LifecycleStatus,
    *,
    unit_instance_id: str,
) -> DecisionRequest:
    request = _request(status, SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE)
    assert request.actor_id == "player-a"
    assert {option.option_id for option in request.options} == {
        DECLINE_TRIGGERED_MOVEMENT_OPTION_ID,
        f"triggered:{unit_instance_id}",
    }
    return request


def _trigger_source_event_id(request: DecisionRequest) -> str:
    descriptor = _json_object(_json_object(request.payload)["descriptor"])
    trigger_timing = _json_object(descriptor["trigger_timing"])
    source_event_id = trigger_timing["source_event_id"]
    assert type(source_event_id) is str
    return source_event_id


def _proposal_descriptor(proposal: MovementProposalRequest) -> dict[str, JsonValue]:
    if proposal.context is None:
        raise AssertionError("Triggered movement proposal must include context.")
    return _json_object(proposal.context["descriptor"])


def _request(status: LifecycleStatus, decision_type: str) -> DecisionRequest:
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    assert status.decision_request.decision_type == decision_type
    return status.decision_request


def _unit_placement(session: LocalGameSession, unit_instance_id: str) -> UnitPlacement:
    state = _state(session.lifecycle)
    assert state.battlefield_state is not None
    return state.battlefield_state.unit_placement_by_id(unit_instance_id)


def _state(lifecycle: GameLifecycle) -> GameState:
    assert lifecycle.state is not None
    return lifecycle.state


def _shift_witness(placement: UnitPlacement, *, dx: float) -> PathWitness:
    return PathWitness.for_paths(
        tuple(
            (
                model.model_instance_id,
                (
                    model.pose,
                    Pose.at(
                        model.pose.position.x + (dx / 2.0),
                        model.pose.position.y,
                        model.pose.position.z,
                        facing_degrees=model.pose.facing.degrees,
                    ),
                    Pose.at(
                        model.pose.position.x + dx,
                        model.pose.position.y,
                        model.pose.position.z,
                        facing_degrees=model.pose.facing.degrees,
                    ),
                ),
            )
            for model in placement.model_placements
        )
    )


def _assert_shifted(before: UnitPlacement, after: UnitPlacement, *, dx: float) -> None:
    assert tuple(model.model_instance_id for model in before.model_placements) == tuple(
        model.model_instance_id for model in after.model_placements
    )
    for start, end in zip(before.model_placements, after.model_placements, strict=True):
        assert math.isclose(end.pose.position.x, start.pose.position.x + dx)
        assert math.isclose(end.pose.position.y, start.pose.position.y)
        assert math.isclose(end.pose.position.z, start.pose.position.z)


def _json_object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value
