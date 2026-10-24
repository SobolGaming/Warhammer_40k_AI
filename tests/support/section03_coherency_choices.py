"""Small real-unit kernels at the native Fight-end cleanup boundary."""

from collections.abc import Iterator
from dataclasses import replace
from time import perf_counter

import pytest
from tests.phase17n_step6g_secondary_certification_helpers import seed_completed_fight_phase
from tests.support.section02_fixtures import CHAOS_SPAWN, LORD_EXULTANT, Section02Definitions
from tests.support.section03_fixtures import native_state, placement
from tests.support.section03_session import movement_session

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.phases.command import CommandPhaseHandler
from warhammer40k_core.engine.phases.fight import FightPhaseHandler
from warhammer40k_core.engine.phases.movement_handler import MovementPhaseHandler
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)


@pytest.fixture(scope="session")
def section03_cleanup_mission() -> Iterator[MissionSetup]:
    start = perf_counter()
    mission = MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-disruption-vs-reconnaissance-layout-2",
        terrain_layout_id="disruption-vs-reconnaissance-layout-2",
        attacker_player_id="owner",
        defender_player_id="opponent",
        attacker_force_disposition_id="disruption",
        defender_force_disposition_id="reconnaissance",
    )
    before = mission.to_payload()
    print(
        f"Section03 cleanup mission preparation: {perf_counter() - start:.6f}s; "
        "source-complete layout"
    )
    yield mission
    assert mission.to_payload() == before


def cleanup_session(
    definitions: Section02Definitions,
    mission: MissionSetup,
    *,
    turn_player: str = "owner",
    unit: UnitInstance | None = None,
    poses: tuple[Pose, ...] | None = None,
    leader_pose: Pose | None = None,
) -> LocalGameSession:
    from tests.phase11c_command_phase_helpers import secondary_choice
    from tests.phase17n_secondary_mission_helpers import seed_resolved_secondary_mission_selections

    from warhammer40k_core.engine.game_state import SecondaryMissionMode

    unit = unit or definitions.unit(CHAOS_SPAWN)
    enemy = definitions.unit(LORD_EXULTANT, identity="enemy", army_id="enemy")
    state = native_state(
        definitions,
        unit,
        poses or (Pose.at(10, 10), Pose.at(20, 10)),
        enemy=enemy,
        enemy_poses=(Pose.at(50, 35),),
    )
    leader: UnitInstance | None = None
    if leader_pose is not None:
        leader = definitions.unit(LORD_EXULTANT, identity="leader")
        state.army_definitions[:] = [
            replace(army, units=(*army.units, leader)) if army.player_id == "owner" else army
            for army in state.army_definitions
        ]
        assert state.battlefield_state is not None
        state.replace_battlefield_state(
            replace(
                state.battlefield_state,
                placed_armies=tuple(
                    replace(
                        army,
                        unit_placements=(*army.unit_placements, placement(leader, (leader_pose,))),
                    )
                    if army.player_id == "owner"
                    else army
                    for army in state.battlefield_state.placed_armies
                ),
            )
        )
    state.active_player_id = turn_player
    state.mission_setup = mission
    state.ruleset_descriptor_hash = state.runtime_ruleset_descriptor().descriptor_hash
    state.army_definitions[:] = [
        replace(
            army,
            force_disposition_id=mission.primary_mission_assignment_for_player(
                army.player_id
            ).force_disposition_id,
        )
        for army in state.army_definitions
    ]
    state.army_definitions.sort(key=lambda army: army.army_id)
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        replace(
            state.battlefield_state,
            battlefield_width_inches=mission.battlefield_width_inches,
            battlefield_depth_inches=mission.battlefield_depth_inches,
            terrain_features=mission.terrain_features,
        )
    )
    # Selected native sheets omit army detachment definitions. Supply only the
    # retained source roster metadata needed by ordinary muster reconstruction;
    # this kernel does not install named faction or detachment rule providers.
    from warhammer40k_core.core.detachment import DetachmentDefinition
    from warhammer40k_core.engine.list_validation import DetachmentSelection
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        faction_detachments_2026_27,
    )

    source_detachments = tuple(
        row
        for row in faction_detachments_2026_27.detachment_rows()
        if row.faction_id == "emperors-children"
        and row.detachment_id in {"frenzied-host", "mercurial-host"}
    )
    catalog = replace(
        definitions.package.army_catalog,
        detachments=tuple(
            DetachmentDefinition(
                detachment_id=row.detachment_id,
                canonical_detachment_id=row.detachment_id,
                name=row.name,
                faction_id="EC",
                detachment_point_cost=row.detachment_point_cost,
                force_disposition_ids=(row.force_disposition_id,),
                source_ids=(row.source_id,),
            )
            for row in source_detachments
        ),
    )
    state.army_definitions[:] = [
        replace(
            army,
            detachment_selection=DetachmentSelection(
                "EC",
                (
                    next(
                        row.detachment_id
                        for row in source_detachments
                        if row.force_disposition_id == army.force_disposition_id
                    ),
                ),
            ),
        )
        for army in state.army_definitions
    ]
    config = replace(
        movement_session(definitions, state).lifecycle.config,
        mission_setup=mission,
        army_catalog=catalog,
    )
    if leader is not None:
        from warhammer40k_core.engine.list_validation import AttachmentDeclaration

        config = replace(
            config,
            army_muster_requests=tuple(
                replace(
                    request,
                    attachment_declarations=(
                        AttachmentDeclaration(
                            source_unit_selection_id=leader.unit_instance_id.split(":", 1)[1],
                            bodyguard_unit_selection_id=unit.unit_instance_id.split(":", 1)[1],
                        ),
                    ),
                )
                if request.player_id == "owner"
                else request
                for request in config.army_muster_requests
            ),
        )
    from warhammer40k_core.engine.army_mustering import muster_army
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.phase import GameLifecycleStage

    battlefield = state.battlefield_state
    state = GameState.from_config(config)
    for request in config.army_muster_requests:
        state.record_army_definition(
            muster_army(catalog=catalog, request=request, model_geometries=config.model_geometries)
        )
    state.record_battlefield_state(battlefield)
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_round = 1
    state.active_player_id = turn_player
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    for player in state.player_ids:
        state.record_secondary_mission_choice(
            secondary_choice(player_id=player, mode=SecondaryMissionMode.FIXED)
        )
        seed_resolved_secondary_mission_selections(state, player_id=player)
    seed_completed_fight_phase(state)
    fight = FightPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor, army_catalog=config.army_catalog
    )
    command = CommandPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor, army_catalog=config.army_catalog
    )
    movement = MovementPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor, army_catalog=config.army_catalog
    )
    return LocalGameSession(
        GameLifecycle(
            state=state,
            _config=config,
            _fight_phase_handler=fight,
            _command_phase_handler=command,
            _movement_phase_handler=movement,
            _battle_round_flow=BattleRoundFlow(
                phase_handlers={
                    BattlePhase.FIGHT: fight,
                    BattlePhase.COMMAND: command,
                    BattlePhase.MOVEMENT: movement,
                },
                ruleset_descriptor=config.ruleset_descriptor,
                army_catalog=config.army_catalog,
            ),
        )
    )


def reach_cleanup(session: LocalGameSession) -> DecisionRequest:
    for index in range(20):
        pending = session.lifecycle.pending_decision_request()
        if pending is not None and pending.decision_type == "select_coherency_casualty":
            return pending
        if pending is None:
            status = session.advance_until_decision_or_terminal()
        else:
            assert pending.decision_type == "use_stratagem", pending.decision_type
            decline = next(o for o in pending.options if o.option_id == "decline")
            status = session.submit_option(
                request_id=pending.request_id,
                result_id=f"decline-{index}",
                option_id=decline.option_id,
            )
        assert status.status_kind not in {
            LifecycleStatusKind.INVALID,
            LifecycleStatusKind.UNSUPPORTED,
        }
    raise AssertionError("Native turn-end cleanup was not reached")


def casualty_checkpoint(
    definitions: Section02Definitions, mission: MissionSetup, *, turn_player: str = "owner"
) -> LocalGameSession:
    """Native five-model unit split by a real recorded mortal-wound casualty."""
    from tests.phase11c_command_phase_helpers import destroy_models_with_recorded_mortal_wounds
    from tests.setup_completion_helpers import (
        ensure_army_mustered_events_for_fixture,
        record_current_battlefield_placements_for_fixture,
        record_primary_turn_start_evidence_for_fixture,
    )
    from tests.support.section02_fixtures import INFRACTORS

    unit = definitions.unit(INFRACTORS)
    session = cleanup_session(
        definitions,
        mission,
        turn_player=turn_player,
        unit=unit,
        poses=tuple(Pose.at(x, 10) for x in (10, 12, 14, 16, 18)),
    )
    state = session.lifecycle.state
    assert state is not None
    decisions = session.lifecycle.decision_controller
    ensure_army_mustered_events_for_fixture(state, decisions=decisions)
    record_current_battlefield_placements_for_fixture(state, decisions=decisions)
    record_primary_turn_start_evidence_for_fixture(state, decisions=decisions)
    destroy_models_with_recorded_mortal_wounds(
        state=state,
        decisions=decisions,
        unit_instance_id=unit.unit_instance_id,
        model_instance_ids=(unit.own_model_ids()[3],),
        application_id="sf03-bridge",
        destroying_player_id="opponent",
    )
    restored = LocalGameSession(GameLifecycle.from_payload(session.lifecycle.to_payload()))
    object.__setattr__(
        restored, "_initial_replay_lifecycle_payload", restored.lifecycle.to_payload()
    )
    return restored
