"""Real shared attack hosts for the optional Lethal Hits invariant."""

from __future__ import annotations

from dataclasses import replace

from tests.phase13b_shooting_declaration_helpers import (
    _canonical_catalog,
    _compact_intercessor_catalog,
    _compact_shooting_lifecycle,
)
from tests.phase15c_fight_order_helpers import fight_lifecycle
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.weapon_profiles import AbilityDescriptor, AttackProfile, WeaponKeyword
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.geometry.pose import Pose


def lethal_session(
    phase: BattlePhase,
    *,
    devastating: bool = False,
    sustained: int = 1,
    target_keywords: tuple[str, ...] = (),
    torrent: bool = False,
) -> LocalGameSession:
    catalog = _compact_intercessor_catalog(_canonical_catalog())
    keywords = [WeaponKeyword.LETHAL_HITS]
    abilities = [AbilityDescriptor.lethal_hits(target_keywords=target_keywords)]
    if devastating:
        keywords.append(WeaponKeyword.DEVASTATING_WOUNDS)
        abilities.append(AbilityDescriptor.devastating_wounds())
    if sustained:
        keywords.append(WeaponKeyword.SUSTAINED_HITS)
        abilities.append(AbilityDescriptor.sustained_hits(sustained))
    if torrent:
        keywords.append(WeaponKeyword.TORRENT)
    catalog = replace(
        catalog,
        wargear=tuple(
            replace(
                row,
                weapon_profiles=tuple(
                    replace(
                        weapon,
                        keywords=tuple(keywords),
                        abilities=tuple(abilities),
                        attack_profile=AttackProfile.fixed(18),
                        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 1),
                    )
                    for weapon in row.weapon_profiles
                ),
            )
            for row in catalog.wargear
        ),
    )
    if phase is BattlePhase.SHOOTING:
        lifecycle, _ = _compact_shooting_lifecycle(catalog=catalog, game_id="order44-shooting")
    else:
        lifecycle, _ = fight_lifecycle(
            alpha_unit_ids=("intercessor-1",),
            enemy_unit_ids=("enemy",),
            origins={"intercessor-1": Pose.at(10, 10), "enemy": Pose.at(12, 10)},
            game_id="order44-fight",
            model_count=1,
            catalog=catalog,
            datasheet_id="core-character-leader",
            model_profile_id="core-character-leader",
            fights_first_unit_keys=("intercessor-1",),
        )
    return LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle.to_payload()))


def attack_steps(session: LocalGameSession, step: str) -> list[dict[str, JsonValue]]:
    return [
        event.payload
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type == "attack_sequence_step"
        and isinstance(event.payload, dict)
        and event.payload.get("step") == step
    ]


def attack_completed(session: LocalGameSession) -> bool:
    return any(
        event.event_type == "attack_sequence_completed"
        for event in session.lifecycle.decision_controller.event_log.records
    )


def reach_lethal_choice(session: LocalGameSession) -> DecisionRequest:
    for _ in range(100):
        request = pending_request(session)
        if request.decision_type == "select_lethal_hit_wound":
            return request
        assert not attack_completed(session), "Attack completed without the Lethal Hits choice."
        _submit_lethal_fixture_request(session, request)
    raise AssertionError("Did not reach a Lethal Hits choice.")


def complete_attack(session: LocalGameSession, *, choice: str = "auto-wound") -> None:
    for _ in range(150):
        if attack_completed(session):
            return
        request = pending_request(session)
        if request.decision_type == "select_lethal_hit_wound":
            status = session.submit_option(
                request_id=request.request_id,
                result_id=f"{request.request_id}:fixture-choice",
                option_id=choice,
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status
        else:
            _submit_lethal_fixture_request(session, request)
    raise AssertionError("Attack did not complete.")


def lethal_wound_checkpoint(*, phase: BattlePhase) -> LocalGameSession:
    """An accepted decline paused before its wound's Command Re-roll choice."""
    from warhammer40k_core.engine.command_points import CommandPointSourceKind

    session = lethal_session(phase)
    state = session.lifecycle.state
    assert state is not None
    state.gain_command_points(
        player_id="player-a",
        amount=1,
        source_id="r44-fixture",
        source_kind=CommandPointSourceKind.OTHER,
    )
    request = reach_lethal_choice(session)
    status = session.submit_option(
        request_id=request.request_id, result_id="r44:decline", option_id="roll-to-wound"
    )
    assert isinstance(status.payload, dict)
    assert status.payload["phase_body_status"] == "attack_wound_command_reroll_pending", status
    assert status.decision_request is not None
    assert status.decision_request.decision_type == "use_stratagem"
    return session


def _submit_lethal_fixture_request(session: LocalGameSession, request: DecisionRequest) -> None:
    from warhammer40k_core.engine.stratagems import stratagem_decline_payload

    if request.decision_type == "submit_stratagem_target_proposal":
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id=f"{request.request_id}:fixture-choice",
            payload=stratagem_decline_payload(),
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status
    else:
        submit_fixture_request(session, request)
