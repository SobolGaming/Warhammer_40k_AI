"""Conditional seam and shared consumers; in-turn deployment certification stays open."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest
from tests.large_model_setup_helpers import oversized_deployment_case
from tests.order122_helpers import submit_quiet_choice
from tests.order134_helpers import conditional_deployment_session
from tests.unit_keyword_helpers import with_unit_keywords

from warhammer40k_core.adapters.access_control import (
    ROLE_POLICY_BY_ROLE,
    PrincipalRole,
    ViewerContext,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.charge_eligibility import charge_unit_ineligibility_reason
from warhammer40k_core.engine.charge_phase_state import ChargePhaseState
from warhammer40k_core.engine.damage_allocation import DamageKind, apply_damage_to_model
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.effects import EffectExpirationBoundary
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.large_model_deployment_restrictions import (
    deployment_restriction_payload,
    record_conditional_deployment_restriction,
    validate_deployment_restriction_identity,
)
from warhammer40k_core.engine.large_model_restrictions import large_model_activity_reason
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.rules_units import (
    rules_unit_view_by_id,
    rules_unit_views_from_armies,
)
from warhammer40k_core.engine.shooting_eligibility_state import shooting_state_restriction_reason
from warhammer40k_core.engine.unit_splitting import build_split_army


@pytest.mark.parametrize("opponent_turn", [False, True])
@pytest.mark.parametrize("aircraft", [False, True])
def test_constructed_condition_shared_consumers_and_actual_turn_expiry(
    opponent_turn: bool, aircraft: bool
) -> None:
    session = conditional_deployment_session(opponent_turn=opponent_turn)
    state = session.lifecycle.state
    assert state is not None
    if aircraft:
        state.army_definitions[:] = [
            replace(
                army,
                units=tuple(
                    with_unit_keywords(unit, keywords=(*unit.keywords, "AIRCRAFT"))
                    for unit in army.units
                ),
            )
            for army in state.army_definitions
        ]
    view = rules_unit_view_by_id(state=state, unit_instance_id="army-alpha:passengers")
    identities = (view.unit_instance_id, *view.component_unit_instance_ids)
    assert state.active_player_id is not None
    turn_player = state.active_player_id
    for phase in (
        BattlePhase.MOVEMENT,
        BattlePhase.SHOOTING,
        BattlePhase.CHARGE,
        BattlePhase.FIGHT,
    ):
        state.battle_phase_index = state.battle_phase_sequence.index(phase)
        for unit_id in identities:
            for activity in ("normal", "advance", "fall_back", "charge", "ranged_attacks"):
                assert (
                    large_model_activity_reason(state, unit_id, activity)
                    == "large_model_setup_turn_restriction"
                )
            for activity in (
                "remain_stationary",
                "pile_in",
                "consolidate",
                "surge",
                "melee_attacks",
            ):
                assert large_model_activity_reason(state, unit_id, activity) is None
        assert (
            shooting_state_restriction_reason(state=state, rules_unit=view, player_id="player-a")
            == "large_model_setup_turn_restriction"
        )
    assert (
        charge_unit_ineligibility_reason(
            state=state,
            charge_state=ChargePhaseState(
                battle_round=state.battle_round, active_player_id="player-a"
            ),
            ignore_already_selected=False,
            unit_instance_id=view.unit_instance_id,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
        )
        == "large_model_setup_turn_restriction"
    )
    restored = GameState.from_payload(json.loads(json.dumps(state.to_payload())))
    assert restored.to_payload() == state.to_payload()
    other = "player-a" if turn_player == "player-b" else "player-b"
    restored.expire_persisting_effects_at_boundary(
        EffectExpirationBoundary.turn_end(battle_round=state.battle_round, player_id=other)
    )
    assert large_model_activity_reason(restored, view.unit_instance_id, "normal") is not None
    restored.expire_persisting_effects_at_boundary(
        EffectExpirationBoundary.turn_end(battle_round=state.battle_round, player_id=turn_player)
    )
    assert large_model_activity_reason(restored, view.unit_instance_id, "normal") is None
    assert large_model_activity_reason(state, view.unit_instance_id, "normal") is not None


def test_pregame_seam_creates_no_first_turn_effect() -> None:
    state, request, proposal = oversized_deployment_case()
    before = state.to_payload()
    assert (
        record_conditional_deployment_restriction(
            state=state,
            unit_instance_id=request.unit_instance_id,
            qualifying_model_instance_ids=tuple(
                row.model_instance_id for row in proposal.model_placements
            ),
            setup_occasion_id="order134-pregame",
        )
        is None
    )
    assert state.to_payload() == before


@pytest.mark.parametrize(
    "invalid",
    ["unknown-model", "empty-models", "duplicate-models", "blank-occasion", "duplicate-occasion"],
)
def test_conditional_seam_invalid_context_is_atomic(invalid: str) -> None:
    session = conditional_deployment_session()
    state = session.lifecycle.state
    assert state is not None
    view = rules_unit_view_by_id(state=state, unit_instance_id="army-alpha:passengers")
    mid = view.own_models[0].model_instance_id
    models = (
        ("unknown",)
        if invalid == "unknown-model"
        else ()
        if invalid == "empty-models"
        else (mid, mid)
        if invalid == "duplicate-models"
        else (mid,)
    )
    occasion = (
        " "
        if invalid == "blank-occasion"
        else "order134-constructed-condition-1"
        if invalid == "duplicate-occasion"
        else "new"
    )
    before = state.to_payload()
    with pytest.raises(GameLifecycleError):
        record_conditional_deployment_restriction(
            state=state,
            unit_instance_id=view.unit_instance_id,
            qualifying_model_instance_ids=models,
            setup_occasion_id=occasion,
        )
    assert state.to_payload() == before


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_rule_id", "wrong"),
        ("effect_payload", {}),
        (
            "effect_payload",
            {"effect_kind": "large_model_deployment_turn_restriction", "extra": True},
        ),
    ],
)
def test_conditional_effect_envelope_rejects_malformed_restore(
    field: str, value: JsonValue
) -> None:
    state = conditional_deployment_session().lifecycle.state
    assert state is not None
    payload = json.loads(json.dumps(state.to_payload()))
    payload["persisting_effects"][0][field] = value
    with pytest.raises(GameLifecycleError):
        GameState.from_payload(payload)


@pytest.mark.parametrize(
    "invalid", ["unknown-model", "foreign-model", "wrong-unit", "wrong-owner", "wrong-turn-player"]
)
def test_conditional_restore_binds_model_target_and_owner(invalid: str) -> None:
    state = conditional_deployment_session().lifecycle.state
    assert state is not None
    original = state.to_payload()
    payload = json.loads(json.dumps(original))
    effect = payload["persisting_effects"][0]
    if invalid in ("unknown-model", "foreign-model"):
        effect["effect_payload"]["qualifying_model_instance_ids"] = [
            "unknown"
            if invalid == "unknown-model"
            else state.army_definitions[1].units[0].own_models[0].model_instance_id
        ]
    elif invalid == "wrong-unit":
        effect["target_unit_instance_ids"] = ["army-alpha:transport"]
    elif invalid == "wrong-owner":
        effect["owner_player_id"] = "player-b"
    else:
        effect["effect_payload"]["turn_player_id"] = "unknown"
        effect["expiration"]["player_id"] = "unknown"
    with pytest.raises(GameLifecycleError):
        GameState.from_payload(payload)
    assert state.to_payload() == original
    assert GameState.from_payload(json.loads(json.dumps(original))).to_payload() == original


def test_dead_qualifying_model_keeps_valid_conditional_state_and_remaining_unit_lock() -> None:
    state = conditional_deployment_session().lifecycle.state
    assert state is not None
    effect = state.persisting_effects[0]
    row = deployment_restriction_payload(effect)
    assert row is not None
    view = rules_unit_view_by_id(state=state, unit_instance_id="army-alpha:passengers")
    model = next(
        m for m in view.own_models if m.model_instance_id in row.qualifying_model_instance_ids
    )
    apply_damage_to_model(
        state=state,
        target_unit_instance_id=view.unit_instance_id,
        model_instance_id=model.model_instance_id,
        damage=model.current_wounds,
        damage_kind=DamageKind.NORMAL,
    )
    restored = GameState.from_payload(json.loads(json.dumps(state.to_payload())))
    assert restored.to_payload() == state.to_payload()
    assert large_model_activity_reason(restored, "army-alpha:passengers", "normal") is not None


def test_constructed_split_inventory_retains_conditional_source_model_membership() -> None:
    # Pure inventory control: no in-turn split or deployment permission is claimed.
    state = conditional_deployment_session().lifecycle.state
    assert state is not None
    effect = state.persisting_effects[0]
    row = deployment_restriction_payload(effect)
    assert row is not None
    view = rules_unit_view_by_id(state=state, unit_instance_id="army-alpha:passengers")
    split = build_split_army(
        army=state.army_definitions[0],
        unit_instance_id=view.unit_instance_id,
        first_model_ids=tuple(sorted(m.model_instance_id for m in view.own_models)[::2]),
        request_id="order134-constructed-split",
        source_id="order134:inventory-control",
        specified_strengths=None,
    )
    state.army_definitions[0] = split
    validate_deployment_restriction_identity(state=state, effect=effect, row=row)
    for successor in rules_unit_views_from_armies(armies=(split,)):
        if successor.split_record is not None:
            assert (
                large_model_activity_reason(state, successor.unit_instance_id, "normal") is not None
            )


def test_conditional_checkpoint_facade_restore_fork_views_events_replay_continuation() -> None:
    session = conditional_deployment_session()
    state = session.lifecycle.state
    assert state is not None
    start_round, start_player = state.battle_round, state.active_player_id
    status = session.advance_until_decision_or_terminal()
    assert status.decision_request is not None
    request = status.decision_request
    unit = rules_unit_view_by_id(state=state, unit_instance_id="army-alpha:passengers")
    selected = next(
        option
        for option in request.options
        if isinstance(option.payload, dict)
        and option.payload.get("unit_instance_id") == unit.unit_instance_id
    )
    status = session.submit_option(
        request_id=request.request_id, option_id=selected.option_id, result_id="order134-select"
    )
    assert status.decision_request is not None
    request = status.decision_request
    assert {option.option_id for option in request.options} == {"remain_stationary"}
    before = session.lifecycle.to_payload()
    with pytest.raises(DecisionError, match="finite action space"):
        session.submit_option(
            request_id=request.request_id,
            option_id="normal_move",
            result_id="order134-invalid",
        )
    assert session.lifecycle.to_payload() == before
    saved = json.loads(json.dumps(session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(saved)
    fork = session.fork()
    assert restored.lifecycle.to_payload() == fork.lifecycle.to_payload() == before
    for player in state.player_ids:
        assert restored.view(viewer_player_id=player) == session.view(viewer_player_id=player)
    for role in PrincipalRole:
        viewer = ViewerContext(
            principal_id=f"order134:{role.value}",
            role=role,
            viewer_player_id=(
                "player-a" if role in (PrincipalRole.PLAYER, PrincipalRole.COACH) else None
            ),
            policy=ROLE_POLICY_BY_ROLE[role],
        )
        assert restored.view_for_context(viewer=viewer) == session.view_for_context(viewer=viewer)
    # Replay starts from the explicit constructed conditional checkpoint, not a claimed deployment.
    for index in range(100):
        status = restored.advance_until_decision_or_terminal()
        continued_request = status.decision_request
        assert continued_request is not None
        submit_quiet_choice(restored, continued_request, result_id=f"order134-continue-{index}")
        current = restored.lifecycle.state
        assert current is not None
        if (current.battle_round, current.active_player_id) != (start_round, start_player):
            break
    else:
        raise AssertionError("Conditional checkpoint did not continue to the next turn.")
    assert not any(deployment_restriction_payload(effect) for effect in current.persisting_effects)
    assert session.lifecycle.to_payload() == before
    assert restored.lifecycle.decision_controller.event_log.to_payload()
    replay = restored.replay_artifact(artifact_id="order134-conditional-checkpoint")
    assert ReplayRunner.from_payload(replay).run().status is ReplayRunStatus.REPRODUCED
