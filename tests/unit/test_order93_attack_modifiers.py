from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest
from tests.generic_modifier_helpers import generic_effect
from tests.order93_modifier_helpers import modifier_session
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.core.random_profile_values import RandomProfileValue
from warhammer40k_core.core.weapon_profiles import AttackProfile, WeaponKeyword, WeaponProfile
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.effects import EffectExpiration
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner


def _record_effect(
    session: LocalGameSession,
    *,
    phase: BattlePhase,
    identity: str,
    unit_id: str,
    kind: str,
    parameters: dict[str, JsonValue],
    model_id: str | None = None,
) -> None:
    state = session.lifecycle.state
    assert state is not None
    owner = "player-a" if unit_id.startswith("army-alpha:") else "player-b"
    effect = generic_effect(
        effect_id=identity,
        owner_player_id=owner,
        target_unit_instance_ids=(unit_id,),
        target_kind="this_unit" if model_id is None else "this_model",
        source_model_instance_id=model_id,
        effect_kind=kind,
        parameters=parameters,
    )
    payload = cast(dict[str, JsonValue], effect.effect_payload)
    context = cast(dict[str, JsonValue], payload["context"])
    state.record_persisting_effect(
        replace(
            effect,
            started_phase=phase,
            effect_payload={**payload, "context": {**context, "phase": phase.value}},
            expiration=EffectExpiration.end_phase(
                battle_round=1, phase=phase, player_id="player-a"
            ),
        )
    )


def _attack_session(phase: BattlePhase, *, random_strength: bool) -> LocalGameSession:
    def transform(profile: WeaponProfile) -> WeaponProfile:
        strength = (
            RandomProfileValue(
                Characteristic.STRENGTH, DiceExpression(1, 3, 4), "source:strength-dice"
            )
            if random_strength
            else CharacteristicValue.from_raw(Characteristic.STRENGTH, 6)
        )
        return replace(
            profile,
            attack_profile=AttackProfile.fixed(2),
            source_ids=tuple(sorted({*profile.source_ids, "source:strength-dice"})),
            strength=strength,
            keywords=(WeaponKeyword.TORRENT,),
        )

    session = modifier_session(phase, weapon_profile_transform=transform)
    for characteristic, unit in (
        ("strength", "army-alpha:intercessor-1"),
        ("toughness", "army-beta:enemy"),
    ):
        for suffix, delta in (("bonus", 2), ("penalty", -2)):
            _record_effect(
                session,
                phase=phase,
                identity=f"{characteristic}:{suffix}",
                unit_id=unit,
                kind="modify_characteristic",
                parameters={"characteristic": characteristic, "delta": delta},
            )
    for suffix, delta in (("bonus", 2), ("penalty", -2)):
        _record_effect(
            session,
            phase=phase,
            identity=f"wound:{suffix}",
            unit_id="army-alpha:intercessor-1",
            kind="modify_dice_roll",
            parameters={"roll_type": "wound", "delta": delta, "attack_role": "attacker"},
        )
    return LocalGameSession(lifecycle=GameLifecycle.from_payload(session.lifecycle.to_payload()))


def _source_choice(
    session: LocalGameSession, request: DecisionRequest, *, ignore_positive: bool = False
) -> None:
    payload = cast(dict[str, JsonValue], request.payload)
    rows = cast(list[dict[str, JsonValue]], payload["modifiers"])
    decided = cast(list[str], payload["decided_modifier_ids"])
    operation = cast(dict[str, JsonValue], rows[len(decided)]["operation"])
    ignore = (
        cast(int, operation["operand"]) > 0
        if ignore_positive
        else cast(int, operation["operand"]) < 0
    )
    prefix = "ignore:" if ignore else "keep:"
    option = next((item for item in request.options if item.option_id.startswith(prefix)), None)
    option_id = (
        option.option_id
        if option is not None
        else ("ignore-remaining" if ignore else "keep-remaining")
    )
    status = session.submit_option(
        request_id=request.request_id, result_id=f"{request.request_id}:subset", option_id=option_id
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status


def _wound_events(session: LocalGameSession) -> list[dict[str, JsonValue]]:
    return [
        event.payload
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type == "attack_sequence_step"
        and isinstance(event.payload, dict)
        and event.payload.get("step") == "wound"
    ]


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
@pytest.mark.parametrize("random_strength", [False, True])
def test_strength_toughness_wound_subsets_restore_replay_and_repeat(
    phase: BattlePhase,
    random_strength: bool,
) -> None:
    session = _attack_session(phase, random_strength=random_strength)
    occurrences: dict[str, set[str]] = {}
    restored_kinds: set[str] = set()
    for _ in range(100):
        request = pending_request(session)
        if request.decision_type == "select_modifier_ignores":
            payload = cast(dict[str, JsonValue], request.payload)
            subject = cast(dict[str, JsonValue], payload["subject"])
            kind = cast(str, subject["kind"])
            if kind in {"strength_characteristic", "toughness_characteristic", "wound_roll"}:
                assert request.actor_id == (
                    "player-b" if kind == "toughness_characteristic" else "player-a"
                )
                occurrences.setdefault(kind, set()).add(cast(str, payload["occurrence_id"]))
                rows = cast(list[dict[str, JsonValue]], payload["modifiers"])
                assert sorted(
                    cast(int, cast(dict[str, JsonValue], item["operation"])["operand"])
                    for item in rows
                ) == [-2, 2]
                if kind not in restored_kinds:
                    assert (
                        GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload()
                        == session.lifecycle.to_payload()
                    )
                    restored_kinds.add(kind)
                _source_choice(session, request)
            else:
                status = session.submit_option(
                    request_id=request.request_id,
                    result_id=f"{request.request_id}:keep",
                    option_id="keep-remaining",
                )
                assert status.status_kind is not LifecycleStatusKind.INVALID, status
        else:
            submit_fixture_request(session, request)
        if len(_wound_events(session)) == 2:
            break
    else:
        raise AssertionError("Both attacks must consume separate Strength/Toughness/Wound choices.")
    assert {kind: len(ids) for kind, ids in occurrences.items()} == {
        "strength_characteristic": 2,
        "toughness_characteristic": 2,
        "wound_roll": 2,
    }
    for event in _wound_events(session):
        wound = cast(dict[str, JsonValue], event["payload"])
        assert wound["strength"] in {7, 8, 9} if random_strength else wound["strength"] == 8
        assert wound["toughness"] == 6
        assert wound["modifier"] == 2
        assert wound["capped_modifier"] == 1
    assert (
        GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload()
        == session.lifecycle.to_payload()
    )
    assert (
        ReplayRunner.from_payload(
            session.replay_artifact(artifact_id=f"attack-subsets-{phase.value}-{random_strength}")
        )
        .run()
        .reproduced_exactly
    )


def test_toughness_choices_preserve_model_sources_before_attached_bodyguard_maximum() -> None:
    from tests.phase13b_shooting_declaration_helpers import (
        _attached_formation_for_player,
        _canonical_catalog,
        _compact_intercessor_catalog,
        _proposal_from_request,
        _shooting_lifecycle,
    )

    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.list_validation import AttachmentDeclaration
    from warhammer40k_core.geometry.pose import Pose

    catalog = _compact_intercessor_catalog(_canonical_catalog())
    catalog = replace(
        catalog,
        wargear=tuple(
            replace(
                wargear,
                weapon_profiles=tuple(
                    replace(
                        profile,
                        attack_profile=AttackProfile.fixed(1),
                        keywords=(WeaponKeyword.TORRENT,),
                        abilities=(),
                    )
                    for profile in wargear.weapon_profiles
                ),
            )
            for wargear in catalog.wargear
        ),
    )
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        alpha_unit_specs=(
            ("intercessor-1", "core-intercessor-like-infantry", "core-intercessor-like", 1),
        ),
        enemy_unit_specs=(
            ("bodyguard-unit", "core-intercessor-like-infantry", "core-intercessor-like", 2),
            ("leader-unit", "core-character-leader", "core-character-leader", 1),
        ),
        enemy_attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="leader-unit", bodyguard_unit_selection_id="bodyguard-unit"
            ),
        ),
        enemy_pose=Pose.at(30, 35),
        catalog=catalog,
        game_id="order93-bodyguard-toughness",
    )
    state = lifecycle.state
    assert state is not None
    formation = _attached_formation_for_player(state=state, player_id="player-b")
    target_id = formation.attached_unit_instance_id
    session = LocalGameSession(lifecycle=lifecycle)
    _record_effect(
        session,
        phase=BattlePhase.SHOOTING,
        identity="defender-permission",
        unit_id=target_id,
        kind="grant_ability",
        parameters={"ability": "modifier_ignore_permission", "selection": "any_or_all"},
    )
    first, second = units["bodyguard-unit"].own_models
    leader = units["leader-unit"].own_models[0]
    for identity, model, delta in (
        ("first-model", first, 8),
        ("second-model", second, 3),
        ("leader-model", leader, 20),
    ):
        _record_effect(
            session,
            phase=BattlePhase.SHOOTING,
            identity=identity,
            unit_id=target_id,
            model_id=model.model_instance_id,
            kind="modify_characteristic",
            parameters={"characteristic": "toughness", "delta": delta},
        )
    session = LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle.to_payload()))
    observed: dict[str, list[str]] = {}
    for _ in range(35):
        request = pending_request(session)
        if request.decision_type == "submit_shooting_declaration":
            proposal = _proposal_from_request(request=request, target_unit_id=target_id)
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"{request.request_id}:shoot-attached",
                payload=validate_json_value(proposal.to_payload()),
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status
        elif request.decision_type == "select_modifier_ignores":
            payload = cast(dict[str, JsonValue], request.payload)
            subject = cast(dict[str, JsonValue], payload["subject"])
            assert subject["kind"] == "toughness_characteristic"
            model_id = cast(str, subject["model_instance_id"])
            assert request.actor_id == "player-b"
            operations = cast(list[dict[str, JsonValue]], payload["modifiers"])
            observed[model_id] = [
                cast(str, cast(dict[str, JsonValue], row["operation"])["modifier_id"])
                for row in operations
            ]
            assert (
                GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload()
                == session.lifecycle.to_payload()
            )
            status = session.submit_option(
                request_id=request.request_id,
                result_id=f"{request.request_id}:model-choice",
                option_id="ignore-remaining"
                if model_id == first.model_instance_id
                else "keep-remaining",
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status
        else:
            submit_fixture_request(session, request)
        if _wound_events(session):
            break
    assert observed == {
        first.model_instance_id: ["first-model"],
        second.model_instance_id: ["second-model"],
    }
    wound = cast(dict[str, JsonValue], _wound_events(session)[0]["payload"])
    assert wound["toughness"] == 7
    assert (
        GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload()
        == session.lifecycle.to_payload()
    )
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="bodyguard-model-subsets"))
        .run()
        .reproduced_exactly
    )


def test_wound_rerolls_reuse_choices_and_generated_hits_have_new_occurrences() -> None:
    from warhammer40k_core.core.weapon_profiles import AbilityDescriptor

    def transform(profile: WeaponProfile) -> WeaponProfile:
        return replace(
            profile,
            attack_profile=AttackProfile.fixed(2),
            strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 6),
            keywords=(WeaponKeyword.SUSTAINED_HITS,),
            abilities=(AbilityDescriptor.sustained_hits(1),),
        )

    session = modifier_session(weapon_profile_transform=transform)
    _record_effect(
        session,
        phase=BattlePhase.SHOOTING,
        identity="critical-hit-threshold",
        unit_id="army-alpha:intercessor-1",
        kind="set_contextual_status",
        parameters={
            "status": "critical_hit_threshold",
            "critical_threshold": 2,
            "roll_type": "hit",
            "attack_role": "attacker",
        },
    )
    for characteristic in ("strength",):
        for suffix, delta in (("bonus", 2), ("penalty", -2)):
            _record_effect(
                session,
                phase=BattlePhase.SHOOTING,
                identity=f"{characteristic}:{suffix}",
                unit_id="army-alpha:intercessor-1",
                kind="modify_characteristic",
                parameters={"characteristic": characteristic, "delta": delta},
            )
    for suffix, delta in (("bonus", 2), ("penalty", -2)):
        _record_effect(
            session,
            phase=BattlePhase.SHOOTING,
            identity=f"wound:{suffix}",
            unit_id="army-alpha:intercessor-1",
            kind="modify_dice_roll",
            parameters={"roll_type": "wound", "delta": delta, "attack_role": "attacker"},
        )
    _record_effect(
        session,
        phase=BattlePhase.SHOOTING,
        identity="wound-reroll",
        unit_id="army-alpha:intercessor-1",
        kind="reroll_permission",
        parameters={"roll_type": "wound", "attack_role": "attacker"},
    )
    session = LocalGameSession(lifecycle=GameLifecycle.from_payload(session.lifecycle.to_payload()))
    rerolls: set[str] = set()
    counts: dict[str, int] = {}
    for _ in range(220):
        request = pending_request(session)
        if request.decision_type == "select_modifier_ignores":
            payload = cast(dict[str, JsonValue], request.payload)
            subject = cast(dict[str, JsonValue], payload["subject"])
            if subject["kind"] in {"strength_characteristic", "wound_roll"}:
                occurrence = cast(str, payload["occurrence_id"])
                counts[occurrence] = counts.get(occurrence, 0) + 1
                assert counts[occurrence] <= 2, (
                    "A reroll must not re-request accepted source choices."
                )
                _source_choice(session, request)
            else:
                session.submit_option(
                    request_id=request.request_id,
                    result_id=f"{request.request_id}:keep",
                    option_id="keep-remaining",
                )
        elif (
            request.decision_type == "select_dice_reroll"
            and isinstance(request.payload, dict)
            and request.payload.get("roll_type") == "attack_sequence.wound"
        ):
            context = cast(dict[str, JsonValue], request.payload["attack_context"])
            occurrence = cast(str, context["attack_context_id"])
            assert counts[f"{occurrence}:strength"] == 2
            assert counts[f"{occurrence}:wound-roll"] == 2
            if not rerolls:
                assert (
                    GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload()
                    == session.lifecycle.to_payload()
                )
            rerolls.add(occurrence)
            selected = next(option for option in request.options if option.option_id != "decline")
            status = session.submit_option(
                request_id=request.request_id,
                result_id=f"{request.request_id}:reroll",
                option_id=selected.option_id,
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status
        else:
            submit_fixture_request(session, request)
        generated = [
            event
            for event in _wound_events(session)
            if "generated-hit" in cast(str, event["attack_context_id"])
        ]
        if generated and rerolls:
            break
    else:
        raise AssertionError("Expected a generated hit and a source-backed Wound reroll.")
    for event in _wound_events(session):
        wound = cast(dict[str, JsonValue], event["payload"])
        assert wound["strength"] == 8
        assert wound["modifier"] == 2
        assert wound["capped_modifier"] == 1
        roll = cast(dict[str, JsonValue], wound["roll_state"])
        assert cast(list[JsonValue], roll["rerolls"])
    assert (
        GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload()
        == session.lifecycle.to_payload()
    )
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="generated-rerolled-subsets"))
        .run()
        .reproduced_exactly
    )
