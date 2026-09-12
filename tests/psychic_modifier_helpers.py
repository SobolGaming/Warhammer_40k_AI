from __future__ import annotations

from dataclasses import replace
from typing import cast

from tests.generic_modifier_helpers import generic_effect
from tests.phase13b_shooting_declaration_helpers import (
    _canonical_catalog,
    _catalog_with_stealth_datasheet,
    _compact_intercessor_catalog,
    _compact_shooting_lifecycle,
    _proposal_from_request,
)
from tests.phase15c_fight_order_helpers import fight_lifecycle
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.weapon_profiles import AttackProfile, WeaponKeyword
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.effects import EffectExpiration
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_resolution import MeleeDeclarationProposalRequest
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.geometry.pose import Pose


def psychic_session(phase: BattlePhase, *, native_stealth: bool = False) -> LocalGameSession:
    catalog = _compact_intercessor_catalog(
        _catalog_with_stealth_datasheet() if native_stealth else _canonical_catalog()
    )
    catalog = replace(
        catalog,
        wargear=tuple(
            replace(
                wargear,
                weapon_profiles=tuple(
                    replace(
                        profile,
                        keywords=(WeaponKeyword.PSYCHIC,),
                        abilities=(),
                        attack_profile=AttackProfile.fixed(1),
                    )
                    for profile in wargear.weapon_profiles
                ),
            )
            for wargear in catalog.wargear
        ),
    )
    if phase is BattlePhase.SHOOTING:
        lifecycle, units = _compact_shooting_lifecycle(catalog=catalog, game_id="psychic-sources")
        attacker = units["intercessor-1"]
    else:
        lifecycle, units = fight_lifecycle(
            alpha_unit_ids=("intercessor-1",),
            enemy_unit_ids=("enemy",),
            origins={"intercessor-1": Pose.at(10, 10), "enemy": Pose.at(12, 10)},
            game_id="psychic-sources-fight",
            model_count=1,
            catalog=catalog,
            datasheet_id="core-character-leader",
            model_profile_id="core-character-leader",
            fights_first_unit_keys=("intercessor-1",),
        )
        attacker = units["intercessor-1"]
    state = lifecycle.state
    assert state is not None
    target = units["enemy"]
    for name, kind, delta in (
        ("a-hit", "hit", 2),
        ("b-hit", "hit", -2),
        ("c-skill", "skill", -1),
        ("d-skill", "skill", 1),
    ):
        affected = target if kind == "hit" and delta < 0 else attacker
        parameters: dict[str, JsonValue] = {"delta": delta}
        parameters.update(
            {"roll_type": "hit"}
            if kind == "hit"
            else {
                "characteristic": "ballistic_skill"
                if phase is BattlePhase.SHOOTING
                else "weapon_skill"
            }
        )
        effect = generic_effect(
            effect_id=name,
            owner_player_id="player-b" if affected is target else "player-a",
            target_unit_instance_ids=(affected.unit_instance_id,),
            target_kind="this_unit",
            effect_kind="modify_dice_roll" if kind == "hit" else "modify_characteristic",
            parameters=parameters,
        )
        payload = cast(dict[str, JsonValue], effect.effect_payload)
        context = cast(dict[str, JsonValue], payload["context"])
        payload = {**payload, "context": {**context, "phase": phase.value}}
        state.record_persisting_effect(
            replace(
                effect,
                started_phase=phase,
                effect_payload=payload,
                expiration=EffectExpiration.end_phase(
                    battle_round=1, phase=phase, player_id="player-a"
                ),
            )
        )
    return LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle.to_payload()))


def pending_request(session: LocalGameSession) -> DecisionRequest:
    status = session.advance_until_decision_or_terminal()
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION, status
    assert status.decision_request is not None
    return status.decision_request


def complete_psychic_attack(session: LocalGameSession) -> None:
    request = reach_psychic_request(session)
    status = session.submit_option(
        request_id=request.request_id,
        result_id=f"{request.request_id}:keep-all",
        option_id="keep-all-modifiers",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    for _ in range(15):
        if any(
            event.event_type == "attack_sequence_step"
            and isinstance(event.payload, dict)
            and event.payload.get("step") == "hit"
            for event in session.lifecycle.decision_controller.event_log.records
        ):
            return
        request = pending_request(session)
        option = next(
            (
                option
                for option in request.options
                if "decline" in option.option_id or "keep" in option.option_id
            ),
            request.options[0],
        )
        status = session.submit_option(
            request_id=request.request_id,
            result_id=f"{request.request_id}:resolve",
            option_id=option.option_id,
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID
    raise AssertionError("Psychic attack did not record its hit.")


def reach_psychic_request(session: LocalGameSession) -> DecisionRequest:
    for _ in range(25):
        request = pending_request(session)
        if request.decision_type == "select_psychic_attack_modifier_ignores":
            return request
        submit_fixture_request(session, request)
    raise AssertionError("Did not reach the Psychic modifier choice.")


def submit_fixture_request(session: LocalGameSession, request: DecisionRequest) -> None:
    result_id = f"{request.request_id}:fixture-choice"
    if request.decision_type == "submit_shooting_declaration":
        proposal = _proposal_from_request(request=request, target_unit_id="army-beta:enemy")
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id=result_id,
            payload=validate_json_value(proposal.to_payload()),
        )
    elif request.decision_type == "submit_melee_declaration":
        melee = MeleeDeclarationProposalRequest.from_decision_request(request)
        weapon = cast(dict[str, JsonValue], melee.available_weapons[0])
        targets = cast(list[str], weapon["engaged_target_unit_instance_ids"])
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id=result_id,
            payload={
                "proposal_request_id": melee.request_id,
                "proposal_kind": melee.proposal_kind,
                "player_id": melee.actor_id,
                "battle_round": melee.battle_round,
                "unit_instance_id": melee.unit_instance_id,
                "source_decision_request_id": melee.source_decision_request_id,
                "source_decision_result_id": melee.source_decision_result_id,
                "declarations": [
                    {
                        "attacker_model_instance_id": weapon["model_instance_id"],
                        "wargear_id": weapon["wargear_id"],
                        "weapon_profile_id": weapon["weapon_profile_id"],
                        "target_allocations": [{"target_unit_instance_id": targets[0]}],
                    }
                ],
            },
        )
    elif request.decision_type == "submit_movement_proposal":
        move = MovementProposalRequest.from_decision_request_payload(request.payload)
        context = cast(dict[str, JsonValue], move.context)
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id=result_id,
            payload={
                "proposal_request_id": move.request_id,
                "proposal_kind": move.proposal_kind.value,
                "unit_instance_id": move.unit_instance_id,
                "movement_phase_action": move.movement_phase_action,
                "movement_mode": context["movement_mode"],
            },
        )
    else:
        assert request.options, request.decision_type
        status = session.submit_option(
            request_id=request.request_id,
            result_id=result_id,
            option_id=request.options[0].option_id,
        )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
