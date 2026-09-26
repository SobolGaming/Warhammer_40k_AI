"""P02G: an absent Strength is one only when interacting, never a mutable profile."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest
from tests.absent_strength_helpers import strength_session
from tests.lethal_hits_helpers import attack_completed, attack_steps, complete_attack
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import (
    Characteristic,
    CharacteristicError,
    CharacteristicValue,
)
from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.core.modifiers import (
    ModifierError,
    ModifierOperation,
    ModifierTerm,
    resolve_characteristic_value,
)
from warhammer40k_core.core.random_profile_values import RandomProfileValue
from warhammer40k_core.core.weapon_profiles import (
    WeaponProfile,
    WeaponProfileError,
    WeaponProfilePayload,
)
from warhammer40k_core.engine.attack_sequence import wound_roll_target_number
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.profile_modifiers import profile_with_delta
from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner, ReplayRunStatus


def _profile(value: CharacteristicValue | RandomProfileValue) -> WeaponProfile:
    original = ArmyCatalog.phase9a_canonical_content_pack().wargear[0].weapon_profiles[0]
    return replace(original, strength=value)


@pytest.mark.parametrize("replacement", [False, True])
def test_absent_strength_query_preserves_descriptor_and_wound_thresholds(replacement: bool) -> None:
    value = (
        CharacteristicValue.replacement_dash(Characteristic.STRENGTH)
        if replacement
        else CharacteristicValue.source_dash(Characteristic.STRENGTH)
    )
    profile = _profile(value)
    payload = profile.to_payload()
    assert profile.strength_for_interaction() == 1
    assert profile.to_payload() == payload
    assert profile.strength.final == 0
    assert profile.strength.is_dash
    restored = WeaponProfile.from_payload(
        cast(WeaponProfilePayload, json.loads(json.dumps(payload)))
    )
    assert restored.strength_for_interaction() == 1
    assert [
        wound_roll_target_number(strength=restored.strength_for_interaction(), toughness=t)
        for t in (1, 2, 10)
    ] == [4, 6, 6]


def test_absent_strength_cannot_be_modified_after_query() -> None:
    profile = _profile(CharacteristicValue.source_dash(Characteristic.STRENGTH))
    assert profile.strength_for_interaction() == 1
    assert isinstance(profile.strength, CharacteristicValue)
    for operation in (ModifierOperation.ADD, ModifierOperation.SET):
        modifier = ModifierTerm(operation, 3).bind(
            modifier_id="test", source_id="test", characteristic=Characteristic.STRENGTH
        )
        with pytest.raises(ModifierError, match="dash"):
            resolve_characteristic_value(profile.strength, (modifier,))
    with pytest.raises(GameLifecycleError, match="dash"):
        profile_with_delta(profile.strength, 1, source_id="test")


def test_strength_query_keeps_numeric_and_random_authority_fail_closed() -> None:
    assert (
        _profile(
            CharacteristicValue.from_raw(Characteristic.STRENGTH, 8)
        ).strength_for_interaction()
        == 8
    )
    random = RandomProfileValue(Characteristic.STRENGTH, DiceExpression(1, 6), "fixture:strength")
    with pytest.raises(CharacteristicError, match="unresolved"):
        _profile(random).strength_for_interaction()
    evaluated = random.evaluate(raw=3, evaluation_id="test:roll", target_id="test:weapon")
    assert _profile(evaluated).strength_for_interaction() == 3
    with pytest.raises(WeaponProfileError, match="positive"):
        _profile(
            CharacteristicValue.from_raw(Characteristic.STRENGTH, 0)
        ).strength_for_interaction()


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
@pytest.mark.parametrize("strength", [None, 2])
def test_strength_interactions_through_attack_hosts_restore_and_replay(
    phase: BattlePhase, strength: int | None
) -> None:
    session = strength_session(phase, strength=strength)
    pending_request(session)
    initial = session.lifecycle.to_payload()
    complete_attack(session)
    wounds = attack_steps(session, "wound")
    assert wounds
    for wound in wounds:
        value = cast(dict[str, JsonValue], wound["payload"])
        assert value["strength"] == (1 if strength is None else strength)
        assert value["toughness"] == 1
        assert value["target_number"] == (4 if strength is None else 2)
        assert value["modifier"] == (0 if strength is None else -1)
    rerolls = [
        event
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type == "weapon_ability_reroll_resolved"
    ]
    assert rerolls
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    assert restored.to_persistence_payload() == checkpoint
    for viewer in ("player-a", "player-b"):
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
        assert restored.events_since(
            EventStreamCursor(), viewer_player_id=viewer
        ) == session.events_since(EventStreamCursor(), viewer_player_id=viewer)
    artifact = ReplayArtifact.capture(
        artifact_id="order88", initial_lifecycle_payload=initial, final_lifecycle=session.lifecycle
    )
    replay = ReplayRunner.from_payload(artifact.to_payload()).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
def test_absent_strength_resumes_a_pending_wound_reroll_without_profile_mutation(
    phase: BattlePhase,
) -> None:
    session = strength_session(phase, command_reroll=True, twin_linked=False)
    pending_request(session)
    initial = session.lifecycle.to_payload()
    for _ in range(30):
        request = pending_request(session)
        if request.decision_type == "use_stratagem":
            break
        assert not attack_completed(session)
        if request.decision_type == "submit_stratagem_target_proposal":
            from warhammer40k_core.engine.stratagems import stratagem_decline_payload

            session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"{request.request_id}:fixture-choice",
                payload=stratagem_decline_payload(),
            )
        else:
            submit_fixture_request(session, request)
    else:
        pytest.fail("No wound Command Re-roll opportunity.")
    payload = cast(dict[str, JsonValue], request.payload)
    context = cast(dict[str, JsonValue], payload["stratagem_context"])
    trigger = cast(dict[str, JsonValue], context["trigger_payload"])
    assert trigger["roll_type"] == "attack_sequence.wound"
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    assert restored.to_persistence_payload() == checkpoint
    option = next(
        option for option in request.options if option.option_id.startswith("use-stratagem:")
    )
    for current in (session, restored):
        current.submit_option(
            request_id=request.request_id, option_id=option.option_id, result_id="order88:reroll"
        )
        complete_attack(current)
    assert restored.to_persistence_payload() == session.to_persistence_payload()
    assert all(
        cast(dict[str, JsonValue], row["payload"])["strength"] == 1
        for row in attack_steps(session, "wound")
    )
    artifact = ReplayArtifact.capture(
        artifact_id="order88-reroll",
        initial_lifecycle_payload=initial,
        final_lifecycle=session.lifecycle,
    )
    replay = ReplayRunner.from_payload(artifact.to_payload()).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
@pytest.mark.parametrize("strength", [None, 1])
def test_strength_interpretation_adds_no_random_profile_rolls(
    phase: BattlePhase, strength: int | None
) -> None:
    session = strength_session(phase, strength=strength, twin_linked=False)
    complete_attack(session)
    wounds = attack_steps(session, "wound")
    assert len(wounds) == 12
    for wound in wounds:
        payload = cast(dict[str, JsonValue], wound["payload"])
        roll = cast(dict[str, JsonValue], payload["roll_state"])
        assert payload["strength"] == 1
        assert len(cast(list[JsonValue], roll["current_values"])) == 1
        assert roll["rerolls"] == []
    assert not any(
        event.event_type in {"random_weapon_profile_evaluated", "random_profile_values_evaluated"}
        for event in session.lifecycle.decision_controller.event_log.records
    )
