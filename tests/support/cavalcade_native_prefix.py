"""Frozen native admission prefix; no adaptive movement or attack search."""

from typing import Literal, TypedDict

from tests.movement_submission_helpers import straight_line_witness_for_unit

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.weapon_profiles import WeaponProfilePayload
from warhammer40k_core.engine.decision_request import DecisionRequestPayload
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalPayload,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.shooting_targets import ShootingTargetCandidatePayload
from warhammer40k_core.engine.stratagems import stratagem_decline_payload
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose

SCREEN_ID = "cavalcade-a:nurglings"
THREAT_ID = "cavalcade-b:bloodcrushers-1"
RANGED_ID = "cavalcade-a:lord-of-change-1"
SHADOW_LORD_SOURCE_ID = "gw-11e-chaos-daemons-datasheet-ir-2026-27:datasheet:000001148:10"


def complete_native_prefix(
    session: LocalGameSession,
    *,
    recipe: Literal[
        "ranged-sidestep", "screen-sidestep", "blocked-screen", "blocked-ranged"
    ] = "ranged-sidestep",
) -> None:
    """Reach first A Shooting, retaining all 78 models and real rule choices."""
    state = session.lifecycle.state
    assert state is not None
    assert state.battle_round == 1
    assert state.active_player_id == "player-a"
    assert state.current_battle_phase is BattlePhase.COMMAND
    order = (
        SCREEN_ID,
        RANGED_ID,
        *(
            u.unit_instance_id
            for u in state.army_definitions[0].units
            if u.unit_instance_id not in (SCREEN_ID, RANGED_ID)
        ),
    )
    index = 0
    for n in range(40):
        state = session.lifecycle.state
        assert state is not None
        request = session.lifecycle.pending_decision_request()
        assert request is not None
        if state.current_battle_phase is BattlePhase.SHOOTING:
            assert index == 9
            return
        actor = request.actor_id
        assert actor is not None
        public = session.view(viewer_player_id=actor)["pending_decision"]
        assert public is not None
        family = request.decision_type
        proposal = None
        if family == "select_faction_rule_battle_round_option":
            choice = next(
                o["option_id"]
                for o in public["options"]
                if isinstance(o["payload"], dict)
                and o["payload"]["selected_shadow_form_source_id"] == SHADOW_LORD_SOURCE_ID
            )
        elif family == "select_movement_unit":
            choice = order[index]
            index += 1
        elif family == "select_movement_action":
            move = order[index - 1] == RANGED_ID or (
                recipe == "blocked-screen" and order[index - 1] == SCREEN_ID
            )
            choice = "normal_move" if move else "remain_stationary"
        elif family == "submit_movement_proposal":
            req = MovementProposalRequest.from_decision_request_payload(public["payload"])
            assert req.unit_instance_id in (SCREEN_ID, RANGED_ID)
            proposal = validate_json_value(
                MovementProposalPayload(
                    proposal_request_id=req.request_id,
                    proposal_kind=req.proposal_kind,
                    unit_instance_id=req.unit_instance_id,
                    movement_phase_action="normal_move",
                    movement_mode="normal",
                    witness=native_prefix_witness(
                        session, unit_id=req.unit_instance_id, recipe=recipe
                    ),
                ).to_payload()
            )
            choice = ""
        elif family == "resolve_reaction_window":
            choice = "decline"
        elif family == "use_stratagem":
            choice = "decline_stratagem_window"
        elif family == "submit_stratagem_target_proposal":
            proposal = stratagem_decline_payload()
            choice = ""
        else:
            raise AssertionError(f"Unenumerated native prefix decision: {family}")
        if proposal is None:
            status = session.submit_viewer_option(
                viewer=ViewerContext.for_player(actor),
                request_id=public["request_id"],
                option_id=choice,
                result_id=f"native-prefix-{n:03}",
            )
        else:
            status = session.submit_viewer_parameterized_payload(
                viewer=ViewerContext.for_player(actor),
                request_id=public["request_id"],
                payload=proposal,
                result_id=f"native-prefix-{n:03}",
            )
        assert status.status_kind not in (
            LifecycleStatusKind.INVALID,
            LifecycleStatusKind.UNSUPPORTED,
        ), status
        session.advance_until_decision_or_terminal()
    raise AssertionError("Native prefix exceeded frozen decision bound.")


def native_prefix_witness(session: LocalGameSession, *, unit_id: str, recipe: str) -> PathWitness:
    if recipe != "ranged-sidestep":
        assert recipe in ("blocked-screen", "blocked-ranged")
        return straight_line_witness_for_unit(session.lifecycle, unit_instance_id=unit_id, dy=-1)
    assert unit_id == RANGED_ID
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    placements = state.battlefield_state.unit_placement_by_id(unit_id).model_placements
    assert len(placements) == 1
    model = placements[0]
    start = model.pose
    corner = Pose.at(
        start.position.x + 4,
        start.position.y,
        start.position.z,
        facing_degrees=start.facing.degrees,
    )
    end = Pose.at(
        start.position.x + 4,
        start.position.y - 1,
        start.position.z,
        facing_degrees=start.facing.degrees,
    )
    return PathWitness.for_paths(((model.model_instance_id, (start, corner, end)),))


class NativeRangedAudit(TypedDict):
    equipped_ranged_profiles: list[WeaponProfilePayload]
    monster: bool
    can_select_to_shoot: bool
    has_legal_declaration_against_B: bool
    B_candidates: list[ShootingTargetCandidatePayload]
    independent_visibility_status: str
    independent_visibility_reason: str
    pending_request: DecisionRequestPayload


def native_ranged_audit(session: LocalGameSession) -> NativeRangedAudit:
    """Query real E/B geometry and offered profile legality without spending RNG."""
    from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
    from warhammer40k_core.engine.phases.shooting_eligibility import (
        shooting_unit_can_select_to_shoot,
        shooting_unit_has_legal_declaration_against_targets,
    )
    from warhammer40k_core.engine.shooting_targets import (
        shooting_target_candidate_for_model,
    )
    from warhammer40k_core.engine.shooting_terrain_visibility import (
        shooting_terrain_areas_for_state,
    )

    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    unit = next(
        u for a in state.army_definitions for u in a.units if u.unit_instance_id == RANGED_ID
    )
    config = session.lifecycle.config
    scenario = battlefield_scenario_for_state(state=state)
    terrain = state.battlefield_state.terrain_features
    areas = shooting_terrain_areas_for_state(state)
    model = unit.own_models[0]
    profiles = tuple(
        profile
        for gear in config.army_catalog.wargear
        if gear.wargear_id in model.wargear_ids
        for profile in gear.weapon_profiles
        if profile.range_profile.distance_inches is not None
    )
    candidates = tuple(
        shooting_target_candidate_for_model(
            scenario=scenario,
            ruleset_descriptor=config.ruleset_descriptor,
            attacker_unit=unit,
            attacker_model_instance_id=model.model_instance_id,
            weapon_profile=profile,
            target_unit_id=THREAT_ID,
            terrain_features=terrain,
            terrain_areas=areas,
        )
        for profile in profiles
    )
    assert all(
        candidate.violation_code is not None and candidate.violation_code.value == "out_of_range"
        for candidate in candidates
    ), "Native prefix audit requires its declared range-excluded horizon."
    pending = session.lifecycle.pending_decision_request()
    assert pending is not None
    return {
        "equipped_ranged_profiles": [p.to_payload() for p in profiles],
        "monster": "MONSTER" in unit.keywords,
        "can_select_to_shoot": shooting_unit_can_select_to_shoot(
            state=state, unit=unit, army_catalog=config.army_catalog, player_id="player-a"
        ),
        "has_legal_declaration_against_B": shooting_unit_has_legal_declaration_against_targets(
            state=state,
            unit=unit,
            ruleset_descriptor=config.ruleset_descriptor,
            army_catalog=config.army_catalog,
            player_id="player-a",
            target_unit_ids=(THREAT_ID,),
        ),
        "B_candidates": [c.to_payload() for c in candidates],
        "independent_visibility_status": "not_evaluated",
        "independent_visibility_reason": "All equipped ranged profiles are excluded by range.",
        "pending_request": pending.to_payload(),
    }
