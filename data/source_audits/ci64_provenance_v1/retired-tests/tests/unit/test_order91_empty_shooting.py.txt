"""Order 91: unit/type selection does not assert that any attacks were made."""

from __future__ import annotations

import json

import pytest
from tests.empty_shooting_helpers import SHOOTER, empty_shooting_session

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.activity_restrictions import has_activity_restriction
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id


@pytest.mark.parametrize("no_weapons", [False, True])
@pytest.mark.parametrize("attached", [False, True])
def test_empty_selection_resolves_type_without_shot_history(
    no_weapons: bool, attached: bool
) -> None:
    session = empty_shooting_session(no_weapons=no_weapons, attached=attached, spare=True)
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    assert request.decision_type == "select_shooting_unit"
    state = session.lifecycle.state
    assert state is not None
    unit = rules_unit_view_by_id(state=state, unit_instance_id=SHOOTER)
    assert unit.unit_instance_id in {option.option_id for option in request.options}
    status = session.submit_option(
        request_id=request.request_id, option_id=unit.unit_instance_id, result_id="order91:unit"
    )
    request = status.decision_request
    assert request is not None
    assert request.decision_type == "select_shooting_type"
    option = next(
        option
        for option in request.options
        if isinstance(option.payload, dict) and option.payload["shooting_type"] == "normal"
    )
    status = session.submit_option(
        request_id=request.request_id, option_id=option.option_id, result_id="order91:type"
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    events = session.lifecycle.decision_controller.event_log.records
    assert any(event.event_type == "shooting_without_attacks_completed" for event in events)
    assert not any(
        event.event_type
        in {
            "shooting_declaration_accepted",
            "attack_sequence_completed",
            "attack_sequence_models_attacked",
            "unit_hidden_status_lost_after_shooting",
        }
        for event in events
    )
    assert not state.ranged_attack_history_records
    assert not state.one_shot_weapon_use_records
    # Empty completion may already have advanced out of the phase; the event
    # records the restriction before the ordinary phase-end expiration.
    if state.shooting_phase_state is not None:
        assert unit.unit_instance_id not in state.shooting_phase_state.shot_unit_ids
    assert state.current_battle_phase is not None
    if state.current_battle_phase.value == "shooting":
        assert has_activity_restriction(state=state, rules_unit=unit, activity="completed_shooting")
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    clone = LocalGameSession.from_persistence_payload(checkpoint)
    assert clone.to_persistence_payload() == checkpoint
    for player in state.player_ids:
        assert clone.view(viewer_player_id=player) == session.view(viewer_player_id=player)
        assert clone.events_since(
            EventStreamCursor(), viewer_player_id=player
        ) == session.events_since(EventStreamCursor(), viewer_player_id=player)
    replay = ReplayRunner.from_payload(session.replay_artifact(artifact_id="order91-empty")).run()
    assert replay.status is ReplayRunStatus.REPRODUCED


@pytest.mark.parametrize("kind", ["normal", "assault", "indirect", "close_quarters"])
def test_empty_type_applies_action_lock_then_expires(kind: str) -> None:
    from warhammer40k_core.core.weapon_profiles import WeaponKeyword
    from warhammer40k_core.engine.effects import EffectExpirationBoundary
    from warhammer40k_core.engine.mission_action_eligibility import (
        MISSION_ACTION_UNIT_ALREADY_SHOT,
        mission_action_unit_ineligibility_reason,
    )
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

    session = empty_shooting_session(
        spare=True,
        advanced=kind == "assault",
        no_weapons=kind == "close_quarters",
        vehicle=kind == "close_quarters",
        engaged=kind == "close_quarters",
        keywords=(WeaponKeyword.ASSAULT,)
        if kind == "assault"
        else (WeaponKeyword.INDIRECT_FIRE,)
        if kind == "indirect"
        else (),
    )
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    request = session.submit_option(
        request_id=request.request_id, option_id=SHOOTER, result_id="order91:select"
    ).decision_request
    assert request is not None
    assert kind in {option.option_id for option in request.options}
    session.submit_option(request_id=request.request_id, option_id=kind, result_id="order91:type")
    state = session.lifecycle.state
    assert state is not None
    assert state.current_battle_phase is BattlePhase.SHOOTING
    unit = rules_unit_view_by_id(state=state, unit_instance_id=SHOOTER)
    assert has_activity_restriction(state=state, rules_unit=unit, activity="completed_shooting")
    if kind in {"normal", "indirect"}:
        assert (
            mission_action_unit_ineligibility_reason(
                state=state,
                player_id="player-a",
                unit_instance_id=SHOOTER,
                runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            )
            == MISSION_ACTION_UNIT_ALREADY_SHOT
        )
    assert state.shooting_phase_state is not None
    assert not state.shooting_phase_state.shot_unit_ids
    assert SHOOTER in state.shooting_phase_state.selected_unit_ids
    assert session.fork().lifecycle.to_payload() == session.lifecycle.to_payload()
    state.expire_persisting_effects_at_boundary(
        EffectExpirationBoundary.phase_end(
            battle_round=1, player_id="player-b", phase=BattlePhase.SHOOTING
        )
    )
    assert has_activity_restriction(state=state, rules_unit=unit, activity="completed_shooting")
    state.expire_persisting_effects_at_boundary(
        EffectExpirationBoundary.phase_end(
            battle_round=1, player_id="player-a", phase=BattlePhase.SHOOTING
        )
    )
    assert not has_activity_restriction(state=state, rules_unit=unit, activity="completed_shooting")


@pytest.mark.parametrize(
    "field",
    [
        "unit_instance_id",
        "battle_round",
        "active_player_id",
        "phase",
        "shooting_type",
        "omit",
        "effect",
        "shot",
        "selected",
    ],
)
def test_empty_completion_restore_rejects_forged_or_missing_authority(field: str) -> None:
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError

    session = empty_shooting_session(no_weapons=True, spare=True)
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    request = session.submit_option(
        request_id=request.request_id, option_id=SHOOTER, result_id="order91:select"
    ).decision_request
    assert request is not None
    session.submit_option(
        request_id=request.request_id, option_id="normal", result_id="order91:type"
    )
    payload = json.loads(json.dumps(session.lifecycle.to_payload()))
    events = payload["decisions"]["event_log"]
    completion = next(
        row for row in events if row["event_type"] == "shooting_without_attacks_completed"
    )
    if field == "omit":
        completion["event_type"] = "omitted_completion"
    elif field == "shot":
        payload["state"]["shooting_phase_state"]["shot_unit_ids"] = [SHOOTER]
    elif field == "selected":
        payload["state"]["shooting_phase_state"]["selected_unit_ids"] = []
    elif field == "effect":
        payload["state"]["persisting_effects"] = []
    else:
        completion["payload"][field] = {
            "unit_instance_id": "army-alpha:spare",
            "battle_round": 2,
            "active_player_id": "player-b",
            "phase": "charge",
            "shooting_type": "indirect",
        }[field]
    with pytest.raises(GameLifecycleError):
        GameLifecycle.from_payload(payload)


def test_empty_selection_keeps_other_units_and_phase_completion_available() -> None:
    session = empty_shooting_session(no_weapons=True, spare=True)
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    request = session.submit_option(
        request_id=request.request_id, option_id=SHOOTER, result_id="selected"
    ).decision_request
    assert request is not None
    request = session.submit_option(
        request_id=request.request_id, option_id="normal", result_id="typed"
    ).decision_request
    assert request is not None
    assert {option.option_id for option in request.options} == {
        "army-alpha:spare",
        "complete_shooting_phase",
    }
    session.submit_option(
        request_id=request.request_id, option_id="complete_shooting_phase", result_id="done"
    )
    state = session.lifecycle.state
    assert state is not None
    assert not state.ranged_attack_history_records
    assert not any(
        has_activity_restriction(
            state=state,
            rules_unit=rules_unit_view_by_id(state=state, unit_instance_id=unit),
            activity="completed_shooting",
        )
        for unit in (SHOOTER, "army-alpha:spare")
    )
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="skip-rest")).run().status
        is ReplayRunStatus.REPRODUCED
    )


def test_no_attack_transport_restricts_all_cargo_and_rejects_type_cargo_drift() -> None:
    from dataclasses import replace

    from tests.phase13b_shooting_declaration_helpers import _shooting_lifecycle

    from warhammer40k_core.engine.firing_deck_restrictions import firing_deck_restriction_payload
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError
    from warhammer40k_core.geometry.pose import Pose

    lifecycle, _ = _shooting_lifecycle(
        alpha_unit_ids=("cargo", "transport-1", "spare"),
        alpha_datasheets={"transport-1": ("core-transport", "core-transport", 1)},
        embarked_unit_ids=("cargo",),
        enemy_pose=Pose.at(80, 35),
    )
    session = LocalGameSession(GameLifecycle.from_payload(lifecycle.to_payload()))
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    request = session.submit_option(
        request_id=request.request_id,
        option_id="army-alpha:transport-1",
        result_id="empty-transport",
    ).decision_request
    assert request is not None
    clone = session.fork()
    state = clone.lifecycle.state
    assert state is not None
    state.transport_cargo_states[0] = replace(
        state.transport_cargo_states[0], embarked_unit_instance_ids=()
    )
    before = clone.lifecycle.to_payload()
    status = clone.submit_option(
        request_id=request.request_id, option_id="normal", result_id="drifted-type"
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert "shooting_type_cargo_drift" in json.dumps(status.payload)
    assert clone.lifecycle.to_payload() == before
    with pytest.raises(GameLifecycleError, match="cargo snapshot drifted"):
        GameLifecycle.from_payload(before)
    session.submit_option(
        request_id=request.request_id, option_id="normal", result_id="transport-type"
    )
    state = session.lifecycle.state
    assert state is not None
    effect = next(
        effect for effect in state.persisting_effects if firing_deck_restriction_payload(effect)
    )
    assert effect.target_unit_instance_ids == ("army-alpha:cargo",)
    assert not state.ranged_attack_history_records
    assert session.fork().lifecycle.to_payload() == session.lifecycle.to_payload()
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="cargo-empty")).run().status
        is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.parametrize("kind", ["normal", "assault", "close_quarters", "indirect"])
def test_spent_one_shot_weapon_still_permits_unit_type_selection(kind: str) -> None:
    from warhammer40k_core.core.weapon_profiles import WeaponKeyword
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.weapon_instances import (
        equipped_weapon_profile_instances_for_model,
    )

    keyword = {
        "normal": (),
        "assault": (WeaponKeyword.ASSAULT,),
        "close_quarters": (WeaponKeyword.CLOSE_QUARTERS,),
        "indirect": (WeaponKeyword.INDIRECT_FIRE,),
    }[kind]
    session = empty_shooting_session(
        reachable=True,
        spare=True,
        advanced=kind == "assault",
        engaged=kind == "close_quarters",
        keywords=(WeaponKeyword.ONE_SHOT, *keyword),
    )
    state, config = session.lifecycle.state, session.lifecycle.config
    assert state is not None
    assert config is not None
    unit = rules_unit_view_by_id(state=state, unit_instance_id=SHOOTER)
    for model in unit.own_models:
        for weapon in equipped_weapon_profile_instances_for_model(
            model=model, army_catalog=config.army_catalog
        ):
            if weapon.weapon_profile.range_profile.distance_inches is not None:
                state.record_one_shot_weapon_selected(
                    weapon_instance_id=weapon.weapon_instance_id,
                    model_instance_id=model.model_instance_id,
                    wargear_id=weapon.wargear_id,
                    weapon_profile_id=weapon.weapon_profile.profile_id,
                    source_phase=BattlePhase.SHOOTING,
                    selection_id="fixture-earlier-one-shot",
                )
    used = tuple(state.one_shot_weapon_use_records)
    # The canonical fixture starts with weapons spent in an earlier use.
    session = LocalGameSession(session.lifecycle)
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    request = session.submit_option(
        request_id=request.request_id, option_id=SHOOTER, result_id="spent-unit"
    ).decision_request
    assert request is not None
    session.submit_option(request_id=request.request_id, option_id=kind, result_id="spent-type")
    assert tuple(state.one_shot_weapon_use_records) == used
    assert not state.ranged_attack_history_records
    assert any(
        e.event_type == "shooting_without_attacks_completed"
        for e in session.lifecycle.decision_controller.event_log.records
    )


def test_destroyed_only_indirect_bearer_does_not_authorize_indirect_selection() -> None:
    from dataclasses import replace

    from tests.phase13b_shooting_declaration_helpers import (
        _replace_unit_instance_in_state,
        _shooting_lifecycle,
    )

    from warhammer40k_core.core.weapon_profiles import WeaponKeyword
    from warhammer40k_core.engine.phases.shooting_eligibility import (
        _legal_shooting_types_for_rules_unit,
    )
    from warhammer40k_core.engine.shooting_types import ShootingType

    config = empty_shooting_session(keywords=(WeaponKeyword.INDIRECT_FIRE,)).lifecycle.config
    assert config is not None
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("shooter",),
        catalog=config.army_catalog,
        alpha_unit_specs=(
            ("shooter", "core-intercessor-like-infantry", "core-intercessor-like", 2),
        ),
    )
    state = lifecycle.state
    assert state is not None
    physical = units["shooter"]
    dead_model, survivor = physical.own_models
    _replace_unit_instance_in_state(
        state=state,
        replacement=replace(
            physical,
            own_models=(replace(dead_model, wounds_remaining=0), replace(survivor, wargear_ids=())),
        ),
    )
    assert state.battlefield_state is not None
    dead = dead_model.model_instance_id
    state.replace_battlefield_state(state.battlefield_state.with_removed_models((dead,)))
    unit = rules_unit_view_by_id(state=state, unit_instance_id=SHOOTER)
    types = _legal_shooting_types_for_rules_unit(
        state=state,
        rules_unit=unit,
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
    )
    assert types == (ShootingType.NORMAL,)


def test_live_indirect_keyword_grant_authorizes_type_without_native_indirect() -> None:
    from warhammer40k_core.core.weapon_profiles import WeaponKeyword
    from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.phases.shooting_eligibility import (
        _legal_shooting_types_for_rules_unit,
    )
    from warhammer40k_core.engine.shooting_types import ShootingType

    session = empty_shooting_session()
    state, config = session.lifecycle.state, session.lifecycle.config
    assert state is not None
    assert config is not None
    state.record_persisting_effect(
        PersistingEffect(
            effect_id="fixture-indirect-grant",
            source_rule_id="fixture-indirect-source",
            owner_player_id="player-a",
            target_unit_instance_ids=(SHOOTER,),
            started_battle_round=1,
            started_phase=BattlePhase.SHOOTING,
            expiration=EffectExpiration.end_phase(
                battle_round=1, player_id="player-a", phase=BattlePhase.SHOOTING
            ),
            effect_payload={
                "effect_kind": "ranged_weapon_keyword_grant",
                "granted_weapon_keywords": [WeaponKeyword.INDIRECT_FIRE.value],
            },
        )
    )
    types = _legal_shooting_types_for_rules_unit(
        state=state,
        rules_unit=rules_unit_view_by_id(state=state, unit_instance_id=SHOOTER),
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
    )
    assert types == (ShootingType.NORMAL, ShootingType.INDIRECT)
