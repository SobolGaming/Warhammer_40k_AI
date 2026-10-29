"""Public native declarations execute the same Core ability owners as kernels."""

import json
from typing import cast

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section04_fixtures import (
    combat_session,
    combat_state,
    declare_shooting,
    finish_attacks,
    shooting_request,
    weapon_rows,
)
from tests.support.section09_fixtures import movement_mission
from tests.support.section24_fixtures import BODY, LORD, bolt, profile_grant, with_profile
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.core.weapon_profiles import AbilityDescriptor, WeaponKeyword
from warhammer40k_core.engine.attack_completion_authority import completed_attack_sequence
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import LifecycleStatusKind


@pytest.mark.parametrize("near", [False, True])
@pytest.mark.parametrize("blast", [False, True])
def test_declared_native_weapon_gathers_snapshot_blast_rapid_and_melta(
    section24_definitions: Section02Definitions, near: bool, blast: bool
) -> None:
    p = profile_grant(
        bolt(section24_definitions), WeaponKeyword.RAPID_FIRE, AbilityDescriptor.rapid_fire(1)
    )
    p = profile_grant(p, WeaponKeyword.MELTA, AbilityDescriptor.melta(2))
    if blast:
        p = profile_grant(p, WeaponKeyword.BLAST, AbilityDescriptor.blast(2))
    d = with_profile(section24_definitions, p)
    own = d.unit(LORD)
    target = d.unit(BODY, army_id="enemy", identity="target")
    state = combat_state(d, own, target=target, distance=5 if near else 10)
    session = combat_session(d, state, movement_mission())
    request = shooting_request(session, own.unit_instance_id)
    row = next(r for r in weapon_rows(request) if r["weapon_profile_id"] == p.profile_id)
    before = session.lifecycle.to_payload()
    invalid = session.submit_parameterized_payload(
        request_id=request.request_id, result_id="s24:malformed", payload={}
    )
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    declare_shooting(session, request, [row], [target.unit_instance_id])
    events = session.lifecycle.decision_controller.event_log.records
    accepted = next(e for e in events if e.event_type == "shooting_declaration_accepted")
    body = cast(dict[str, JsonValue], accepted.payload)
    pools = cast(list[dict[str, JsonValue]], body["attack_pools"])
    assert len(pools) == 1
    assert pools[0]["weapon_instance_id"] == row["weapon_instance_id"]
    assert pools[0]["attacks"] == 1 + int(near) + (
        2 * (len(target.own_models) // 5) if blast else 0
    )
    ids = cast(list[str], pools[0]["targeting_rule_ids"])
    assert ("weapon-ability:melta:2" in ids) is near
    finish_attacks(session)
    events = session.lifecycle.decision_controller.event_log.records
    done = next(e for e in events if e.event_type == "attack_sequence_completed")
    identity = cast(dict[str, JsonValue], done.payload)["sequence_id"]
    assert isinstance(identity, str)
    sequence = completed_attack_sequence(event_records=events, sequence_id=identity)
    assert sequence.is_complete
    assert sequence.attack_pools[0].attacks == pools[0]["attacks"]
    for viewer in state.player_ids:
        projection = session.view(viewer_player_id=viewer)
        assert json.loads(json.dumps(projection)) == projection
        assert session.events_since(EventStreamCursor(), viewer_player_id=viewer)["events"]


def test_overwatch_filters_borrowed_weapons_rejects_atomic_retry_and_fires_carrier(
    section24_definitions: Section02Definitions,
) -> None:
    from tests.support.s24_firing_deck import (
        CARRIER,
        borrowed_rows,
        declaration_payload,
        reach_declaration,
        request_body,
        scene,
    )
    from warhammer40k_core.engine.firing_deck_restrictions import firing_deck_restriction_payload
    from warhammer40k_core.engine.game_state import GameState

    session = scene(section24_definitions)
    request = reach_declaration(session)
    state = session.lifecycle.state
    assert state is not None
    assert state.current_battle_phase is not None
    assert state.current_battle_phase.value == "movement"
    assert state.active_player_id == "opponent"
    assert state.out_of_phase_shooting_state is not None
    assert state.out_of_phase_shooting_state.selected_unit_instance_id == CARRIER
    assert len(state.stratagem_use_records) == 1
    assert state.stratagem_use_records[0].stratagem_id == "fire-overwatch"
    rows = weapon_rows(request)
    assert rows
    assert all("firing_deck_source_unit_instance_id" not in row for row in rows)
    for viewer in state.player_ids:
        projected = session.view(viewer_player_id=viewer)["pending_decision"]
        assert projected is not None
        assert json.loads(json.dumps(projected)) == projected
        assert "firing_deck_source_unit_instance_id" not in json.dumps(projected)
    assert request_body(request)["firing_deck_embarked_unit_instance_ids"] == []
    before = session.lifecycle.to_payload()
    # A schema-valid forged physical cargo weapon reaches the owning rules validator.
    forbidden = declaration_payload(request, borrowed_rows(session)[:1], borrowed=True)
    for selection_only in (False, True):
        payload = dict(forbidden)
        if selection_only:
            payload = declaration_payload(request, rows[:1], borrowed=False)
            payload["firing_deck_selection"] = forbidden["firing_deck_selection"]
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id=f"s24:forbidden:{selection_only}",
            payload=payload,
        )
        assert status.status_kind is LifecycleStatusKind.INVALID
        assert "firing_deck_out_of_phase" in json.dumps(status.payload)
        assert session.lifecycle.to_payload() == before
        assert session.lifecycle.decision_controller.queue.pending_requests == (request,)
    # This native boundary kernel has no roster/setup replay claim. Round-trip
    # its pending authoritative state; full-start session restore is a separate
    # retained native probe, avoiding an invented roster for these selected sheets.
    assert GameState.from_payload(state.to_payload()).to_payload() == state.to_payload()
    restored = session
    status = restored.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="s24:own-overwatch",
        payload=declaration_payload(request, rows[:1], borrowed=False),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    finish_attacks(restored)
    state = restored.lifecycle.state
    assert state is not None
    assert state.out_of_phase_shooting_state is None
    assert not any(firing_deck_restriction_payload(e) for e in state.persisting_effects)
    accepted = [
        e
        for e in restored.lifecycle.decision_controller.event_log.records
        if e.event_type == "out_of_phase_shooting_declaration_accepted"
    ]
    assert len(accepted) == 1
    weapon_id = rows[0]["weapon_instance_id"]
    assert isinstance(weapon_id, str)
    assert weapon_id in json.dumps(accepted[0].payload)
    assert state.command_point_total("owner") == 1
    assert "s24:forbidden" not in json.dumps(
        [r.to_payload() for r in restored.lifecycle.decision_controller.records]
    )


def test_own_shooting_firing_deck_preserves_capacity_physical_identity_and_completion(
    section24_definitions: Section02Definitions,
) -> None:
    from tests.support.s24_firing_deck import (
        CARGO,
        declaration_payload,
        reach_declaration,
        scene,
    )
    from warhammer40k_core.engine.firing_deck_restrictions import firing_deck_restriction_payload

    session = scene(section24_definitions, own_phase=True)
    request = reach_declaration(session, own_phase=True)
    rows = [r for r in weapon_rows(request) if "firing_deck_source_unit_instance_id" in r]
    by_model = {str(r["firing_deck_source_model_instance_id"]): r for r in rows}
    assert len(by_model) > 2
    chosen = list(by_model.values())
    before = session.lifecycle.to_payload()
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="s24:over-capacity",
        payload=declaration_payload(request, chosen[:3], borrowed=True),
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    assert session.lifecycle.decision_controller.queue.pending_requests == (request,)
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="s24:own-firing-deck",
        payload=declaration_payload(request, chosen[:2], borrowed=True),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    state = session.lifecycle.state
    assert state is not None
    assert not state.one_shot_weapon_use_records
    effects = [e for e in state.persisting_effects if firing_deck_restriction_payload(e)]
    assert len(effects) == 1
    assert effects[0].target_unit_instance_ids == (CARGO,)
    accepted = next(
        e
        for e in session.lifecycle.decision_controller.event_log.records
        if e.event_type == "shooting_declaration_accepted"
    )
    pools = cast(dict[str, JsonValue], accepted.payload)["attack_pools"]
    assert isinstance(pools, list)
    assert len(pools) == 2
    assert {cast(str, cast(dict[str, JsonValue], p)["weapon_instance_id"]) for p in pools} == {
        cast(str, r["weapon_instance_id"]) for r in chosen[:2]
    }
    finish_attacks(session)


@pytest.mark.parametrize(
    ("phase", "active", "reaction", "expected"),
    [
        ("shooting", "owner", False, True),
        ("shooting", "opponent", False, False),
        ("movement", "owner", False, False),
        ("shooting", "owner", True, False),
    ],
)
def test_firing_deck_shared_inventory_obeys_owner_phase_and_reaction_boundary(
    section24_definitions: Section02Definitions,
    phase: str,
    active: str,
    reaction: bool,
    expected: bool,
) -> None:
    from tests.support.s24_firing_deck import CARRIER, scene
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.phases.shooting_firing_deck import (
        _available_firing_deck_weapons,
        firing_deck_cargo_snapshot,
    )
    from warhammer40k_core.engine.phases.shooting_model import OutOfPhaseShootingState

    session = scene(section24_definitions, own_phase=True)
    state = session.lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase(phase))
    state.active_player_id = active
    if reaction:
        state.out_of_phase_shooting_state = OutOfPhaseShootingState(
            battle_round=state.battle_round,
            player_id="owner",
            parent_phase=BattlePhase.SHOOTING,
            source_rule_id="constructed:s24:reaction",
            source_decision_request_id="s24:source",
            source_decision_result_id="s24:result",
            source_context={},
            selected_unit_instance_id=CARRIER,
        )
    before = state.to_payload()
    army = state.army_definition_for_player("owner")
    assert army is not None
    borrowed = _available_firing_deck_weapons(
        state=state,
        transport_unit=army.unit_by_id(CARRIER),
        army_catalog=session.lifecycle.config.army_catalog,
    )
    assert bool(borrowed) is expected
    assert (
        bool(
            firing_deck_cargo_snapshot(
                state=state,
                unit_instance_id=CARRIER,
                army_catalog=session.lifecycle.config.army_catalog,
            )
        )
        is expected
    )
    assert state.to_payload() == before


def test_firing_deck_excludes_one_shot_cargo_without_spending_its_physical_weapon(
    section24_definitions: Section02Definitions,
) -> None:
    from tests.support.s24_firing_deck import CARRIER, borrowed_rows, reach_declaration, scene
    from tests.support.section24_fixtures import profile_grant, with_profile
    from warhammer40k_core.core.weapon_profiles import WeaponProfile, WeaponProfilePayload

    premise = scene(section24_definitions, own_phase=True)
    physical = borrowed_rows(premise)[0]
    profile = WeaponProfile.from_payload(cast(WeaponProfilePayload, physical["weapon_profile"]))
    # Explicit One Shot grant on the unchanged native physical cargo equipment.
    d = with_profile(section24_definitions, profile_grant(profile, WeaponKeyword.ONE_SHOT))
    session = scene(d, own_phase=True)
    request = reach_declaration(session, own_phase=True)
    rows = weapon_rows(request)
    assert rows
    assert all("firing_deck_source_unit_instance_id" not in r for r in rows)
    state = session.lifecycle.state
    assert state is not None
    assert not state.one_shot_weapon_use_records
    assert state.one_shot_weapon_available(
        weapon_instance_id=str(physical["weapon_instance_id"]),
        model_instance_id=str(physical["firing_deck_source_model_instance_id"]),
        wargear_id=str(physical["wargear_id"]),
        weapon_profile_id=profile.profile_id,
    )
    assert state.shooting_phase_state is not None
    assert CARRIER in state.shooting_phase_state.selected_unit_ids
