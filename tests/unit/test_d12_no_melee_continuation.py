"""D12's normal no-usable-melee continuation without changing original branches."""

from __future__ import annotations

import pytest
from tests.epic_challenge_helpers import (
    epic_checkpoint,
    epic_proposal,
    epic_request,
    epic_scene,
    epic_unit_from_state,
    finish_epic_fight,
    submit_all_melee,
    submit_epic,
)
from tests.fight_completion_helpers import submit_completion_request
from tests.psychic_modifier_helpers import pending_request

from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_resolution import MeleeDeclarationProposalRequest
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind


def _empty_melee_payload(melee: MeleeDeclarationProposalRequest) -> dict[str, JsonValue]:
    return {
        "proposal_request_id": melee.request_id,
        "proposal_kind": melee.proposal_kind,
        "player_id": melee.actor_id,
        "battle_round": melee.battle_round,
        "unit_instance_id": melee.unit_instance_id,
        "source_decision_request_id": melee.source_decision_request_id,
        "source_decision_result_id": melee.source_decision_result_id,
        "declarations": [],
    }


def _melee_rows(melee: MeleeDeclarationProposalRequest) -> tuple[dict[str, JsonValue], ...]:
    rows: list[dict[str, JsonValue]] = []
    for row in melee.available_weapons:
        assert isinstance(row, dict)
        rows.append(row)
    return tuple(rows)


@pytest.mark.parametrize("player", ["player-a", "player-b"])
def test_d12_dead_leader_support_no_usable_melee_completes_and_replays(player: str) -> None:
    # This public scene reaches casualties through real Charge/Precision attacks.
    session = epic_scene(player=player, support=True, dead="leader")
    request = epic_request(session, player=player)
    state = session.lifecycle.state
    assert state is not None
    unit = epic_unit_from_state(state, player=player)
    dead = next(model for model in unit.own_models if not model.is_alive)
    support = next(model for model in unit.alive_models() if "CHARACTER" in model.keywords)
    assert unit.unit_instance_id.startswith("attached-unit:")
    assert ":support:" in support.model_instance_id
    before = session.to_persistence_payload()
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id=request.request_id + ":dead-invalid",
        payload=validate_json_value(
            {"proposal": epic_proposal(request, model_id=dead.model_instance_id).to_payload()}
        ),
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.to_persistence_payload() == before
    cp = state.command_point_total(player)
    submit_epic(session, request, epic_proposal(request, model_id=support.model_instance_id))
    assert state.command_point_total(player) == cp - 1
    grant = state.persisting_effects[-1]
    grant_payload = grant.effect_payload
    assert isinstance(grant_payload, dict)
    assert grant_payload["effect_kind"] == "epic_challenge_precision"
    assert grant_payload["model_instance_id"] == support.model_instance_id
    epic_checkpoint(session)

    declaration_request = pending_request(session)
    assert declaration_request.decision_type == "submit_melee_declaration"
    melee = MeleeDeclarationProposalRequest.from_decision_request(declaration_request)
    assert len(melee.available_weapons) == 1
    row = _melee_rows(melee)[0]
    assert row["model_instance_id"] == support.model_instance_id
    assert row["engaged_target_unit_instance_ids"] == []
    assert melee.target_unit_instance_ids
    empty = _empty_melee_payload(melee)
    forced = dict(empty)
    forced["declarations"] = [
        {
            "attacker_model_instance_id": row["model_instance_id"],
            "weapon_instance_id": row["weapon_instance_id"],
            "wargear_id": row["wargear_id"],
            "weapon_profile_id": row["weapon_profile_id"],
            "target_allocations": [{"target_unit_instance_id": melee.target_unit_instance_ids[0]}],
        }
    ]
    before = session.to_persistence_payload()
    status = session.submit_parameterized_payload(
        request_id=declaration_request.request_id,
        result_id=declaration_request.request_id + ":nonengaged-invalid",
        payload=forced,
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.to_persistence_payload() == before
    assert pending_request(session) == declaration_request

    event_start = len(session.lifecycle.decision_controller.event_log.records)
    record_count = len(session.lifecycle.to_payload()["decisions"]["records"])
    status = session.submit_parameterized_payload(
        request_id=declaration_request.request_id,
        result_id=declaration_request.request_id + ":legal-empty-retry",
        payload=empty,
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert len(session.lifecycle.to_payload()["decisions"]["records"]) == record_count + 1
    added = session.lifecycle.decision_controller.event_log.records[event_start:]
    assert any(event.event_type == "melee_declaration_not_available" for event in added)
    assert any(event.event_type == "fight_activation_completed" for event in added)
    assert not any(
        event.event_type in {"melee_declaration_accepted", "unit_has_fought"}
        or "dice" in event.event_type
        for event in added
    )
    assert not any(
        isinstance(event.payload, dict)
        and event.payload.get("unit_instance_id") == unit.unit_instance_id
        and event.event_type == "counter_offensive_requested"
        for event in added
    )
    restored, fork = epic_checkpoint(session)
    for clone in (session, restored, fork):
        for _ in range(60):
            clone_state = clone.lifecycle.state
            assert clone_state is not None
            if clone_state.current_battle_phase is not BattlePhase.FIGHT:
                assert grant.effect_id not in {
                    effect.effect_id for effect in clone_state.persisting_effects
                }
                break
            next_request = pending_request(clone)
            if next_request.decision_type == "submit_melee_declaration":
                submit_all_melee(clone, next_request)
            else:
                submit_completion_request(clone)
        else:
            raise AssertionError(
                "No-melee completion did not continue through native Fight expiry."
            )
        epic_checkpoint(clone)
    assert (
        restored.to_persistence_payload()
        == fork.to_persistence_payload()
        == session.to_persistence_payload()
    )


@pytest.mark.parametrize("player", ["player-a", "player-b"])
def test_d12_armed_attached_melee_empty_rejects_atomically_and_retries(player: str) -> None:
    session = epic_scene(player=player, support=True, armed_bodyguard=True)
    request = epic_request(session, player=player)
    state = session.lifecycle.state
    assert state is not None
    unit = epic_unit_from_state(state, player=player)
    chosen = next(model for model in unit.alive_models() if "CHARACTER" in model.keywords)
    submit_epic(session, request, epic_proposal(request, model_id=chosen.model_instance_id))
    declaration_request = pending_request(session)
    assert declaration_request.decision_type == "submit_melee_declaration"
    melee = MeleeDeclarationProposalRequest.from_decision_request(declaration_request)
    assert any(row["engaged_target_unit_instance_ids"] for row in _melee_rows(melee))
    before = session.to_persistence_payload()
    status = session.submit_parameterized_payload(
        request_id=declaration_request.request_id,
        result_id=declaration_request.request_id + ":mandatory-empty-invalid",
        payload=_empty_melee_payload(melee),
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.to_persistence_payload() == before
    assert pending_request(session) == declaration_request
    submit_all_melee(session, declaration_request)
    finish_epic_fight(session, unit_id=unit.unit_instance_id)
    epic_checkpoint(session)
