from dataclasses import replace
from typing import cast

import pytest

from tests.phase13b_shooting_declaration_helpers import (
    _catalog_with_replaced_bolt_profiles,
    _compact_shooting_lifecycle,
    _grant_command_reroll_cp,
)
from tests.support.section02_fixtures import CHAOS_SPAWN, LORD_EXULTANT, Section02Definitions
from tests.support.section04_fixtures import (
    body,
    choose,
    combat_session,
    combat_state,
    declare_shooting,
    finish_attacks,
    pending,
    shooting_payload,
    shooting_request,
    weapon_rows,
)
from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import CharacteristicValue
from warhammer40k_core.core.count_profiles import AttackProfile, DamageProfile
from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.engine.attack_completion_authority import completed_attack_sequence
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.model_attack_history import model_has_attacked_this_phase
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner
from warhammer40k_core.engine.stratagems import DECLINE_STRATAGEM_WINDOW_OPTION_ID


@pytest.mark.parametrize("weapons", [1, 2])
def test_native_shooting_selection_declaration_and_completed_participation(
    section04_definitions: Section02Definitions, section04_mission: MissionSetup, weapons: int
) -> None:
    d = section04_definitions
    unit = d.unit(LORD_EXULTANT)
    session = combat_session(d, combat_state(d, unit), section04_mission)
    request = shooting_request(session, unit.unit_instance_id)
    assert request.decision_type == "submit_shooting_declaration"
    state = session.lifecycle.state
    assert state is not None
    assert state.shooting_phase_state is not None
    assert unit.unit_instance_id in state.shooting_phase_state.selected_unit_ids
    before = session.lifecycle.decision_controller.event_log.records
    assert not any(e.event_type == "attack_sequence_step" for e in before)
    rows = weapon_rows(request)[:weapons]
    declare_shooting(session, request, rows, ["enemy:target"] * weapons)
    finish_attacks(session)
    events = session.lifecycle.decision_controller.event_log.records
    completed = next(e for e in events if e.event_type == "attack_sequence_completed")
    sequence = completed_attack_sequence(
        event_records=events,
        sequence_id=cast(str, cast(dict[str, JsonValue], completed.payload)["sequence_id"]),
    )
    assert sequence.is_complete
    assert len(sequence.attack_pools) == weapons
    assert {p.weapon_instance_id for p in sequence.attack_pools} == {
        cast(str, r["weapon_instance_id"]) for r in rows
    }
    assert all(p.target_unit_instance_id == "enemy:target" for p in sequence.attack_pools)
    for pool in sequence.attack_pools:
        assert pool.weapon_profile == d.weapon(pool.wargear_id)
        assert pool.attacks == pool.weapon_profile.attack_profile.fixed_attacks
        assert model_has_attacked_this_phase(
            event_records=events,
            model_instance_id=pool.attacker_model_instance_id,
            battle_round=1,
            active_player_id="owner",
            phase="shooting",
        )
    steps = [i for i, e in enumerate(events) if e.event_type == "attack_sequence_step"]
    assert steps
    assert max(steps) < events.index(completed)
    assert state.shooting_phase_state is not None
    assert unit.unit_instance_id in state.shooting_phase_state.shot_unit_ids
    assert session.events_since(EventStreamCursor(), viewer_player_id="owner")
    assert session.events_since(EventStreamCursor(), viewer_player_id="opponent")


@pytest.mark.parametrize(("distance", "select_weapons"), [(8, False), (8, True), (40, False)])
def test_declining_legal_targets_completes_selection_without_shot(
    section04_definitions: Section02Definitions,
    section04_mission: MissionSetup,
    select_weapons: bool,
    distance: int,
) -> None:
    d = section04_definitions
    unit = d.unit(LORD_EXULTANT)
    session = combat_session(d, combat_state(d, unit, distance=distance), section04_mission)
    request = shooting_request(session, unit.unit_instance_id)
    if distance == 8:
        rows = weapon_rows(request)[:2] if select_weapons else []
        declare_shooting(session, request, rows, [None] * len(rows))
    else:
        assert request.decision_type == "select_shooting_unit"
    state = session.lifecycle.state
    assert state is not None
    assert state.shooting_phase_state is not None
    assert unit.unit_instance_id in state.shooting_phase_state.selected_unit_ids
    assert unit.unit_instance_id not in state.shooting_phase_state.shot_unit_ids
    events = session.lifecycle.decision_controller.event_log.records
    assert not any(e.event_type == "attack_sequence_step" for e in events)
    assert any(
        e.event_type
        == (
            "shooting_declaration_accepted"
            if distance == 8
            else "shooting_without_attacks_completed"
        )
        for e in events
    )
    assert pending(session).decision_type == "select_shooting_unit"


def test_faq02_native_weaponless_shooter_resolves_type_without_attacks(
    section04_definitions: Section02Definitions, section04_mission: MissionSetup
) -> None:
    d = section04_definitions
    unit = d.unit(CHAOS_SPAWN)
    session = combat_session(d, combat_state(d, unit), section04_mission)
    choose(session, pending(session), unit.unit_instance_id)
    request = pending(session)
    assert request.decision_type == "select_shooting_type"
    choose(session, request, "normal")
    state = session.lifecycle.state
    assert state is not None
    assert state.shooting_phase_state is not None
    assert unit.unit_instance_id in state.shooting_phase_state.selected_unit_ids
    assert unit.unit_instance_id not in state.shooting_phase_state.shot_unit_ids
    events = session.lifecycle.decision_controller.event_log.records
    assert any(e.event_type == "shooting_without_attacks_completed" for e in events)
    assert not any(
        e.event_type in {"shooting_declaration_accepted", "attack_sequence_step"} for e in events
    )


@pytest.mark.parametrize("alternate", [False, True])
def test_one_physical_weapon_cannot_commit_both_profiles_then_legal_retry(
    section04_definitions: Section02Definitions, section04_mission: MissionSetup, alternate: bool
) -> None:
    d = section04_definitions
    unit = d.unit(LORD_EXULTANT)
    session = combat_session(d, combat_state(d, unit), section04_mission)
    request = shooting_request(session, unit.unit_instance_id)
    rows = [r for r in weapon_rows(request) if r["wargear_id"] == f"{LORD_EXULTANT}:plasma-pistol"]
    assert len(rows) == 2
    assert rows[0]["weapon_instance_id"] == rows[1]["weapon_instance_id"]
    before = session.lifecycle.to_payload()
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="duplicate",
        payload=shooting_payload(request, rows, ["enemy:target"] * 2),
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    assert pending(session) == request
    declare_shooting(session, request, [rows[int(alternate)]], ["enemy:target"])
    accepted = next(
        e
        for e in session.lifecycle.decision_controller.event_log.records
        if e.event_type == "shooting_declaration_accepted"
    )
    pools = cast(
        list[dict[str, JsonValue]], cast(dict[str, JsonValue], accepted.payload)["attack_pools"]
    )
    assert len(pools) == 1
    assert pools[0]["weapon_profile_id"] == rows[int(alternate)]["weapon_profile_id"]
    assert pools[0]["weapon_instance_id"] == rows[0]["weapon_instance_id"]


@pytest.mark.parametrize("reroll", [False, True])
def test_shooting_damage_window_stays_fresh_after_previous_attack_casualty(reroll: bool) -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    rifle = next(g for g in catalog.wargear if g.wargear_id == "core-bolt-rifle").weapon_profiles[0]
    profile = replace(
        rifle,
        attack_profile=AttackProfile.fixed(12),
        damage_profile=DamageProfile.dice(DiceExpression(1, 6, 2)),
        armor_penetration=CharacteristicValue.from_raw(rifle.armor_penetration.characteristic, -5),
        strength=CharacteristicValue.from_raw(rifle.strength.characteristic, 12),
    )
    lifecycle, units = _compact_shooting_lifecycle(
        enemy_model_count=2,
        game_id="review724-shoot",
        catalog=_catalog_with_replaced_bolt_profiles((profile,)),
    )
    state = lifecycle.state
    assert state is not None
    _grant_command_reroll_cp(state, player_id="player-a")
    lifecycle = GameLifecycle.from_payload(lifecycle.to_payload())
    session = LocalGameSession(lifecycle)
    session.advance_until_decision_or_terminal()
    request = shooting_request(session, units["intercessor-1"].unit_instance_id)
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="review724-shot",
        payload=shooting_payload(
            request, weapon_rows(request)[:1], [units["enemy"].unit_instance_id]
        ),
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION, status
    for step in range(100):
        request = pending(session)
        records = lifecycle.decision_controller.event_log.records
        if "opportunity_window" in body(request) and any(
            event.event_type == "model_destroyed" for event in records
        ):
            break
        option = next(
            (
                o.option_id
                for o in request.options
                if o.option_id in {DECLINE_STRATAGEM_WINDOW_OPTION_ID, "keep", "decline"}
            ),
            request.options[0].option_id,
        )
        status = session.submit_option(
            request_id=request.request_id, option_id=option, result_id=f"review-shoot-{step}"
        )
        assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION, status
    else:
        raise AssertionError("Shooting did not reach the post-casualty damage window.")

    assert request.actor_id == "player-a"
    assert request.decision_type == "use_stratagem"
    window = cast(dict[str, JsonValue], body(request)["opportunity_window"])
    metadata = cast(dict[str, JsonValue], window["metadata"])
    roll_type = cast(str, metadata["roll_type"])
    assert roll_type.endswith(":attack-005:damage")
    attack_context = roll_type.removeprefix("random_characteristic.damage.per_attack.")
    attack_context = attack_context.removesuffix(":damage")
    casualty = next(e for e in records if e.event_type == "model_destroyed")
    casualty_id = cast(dict[str, JsonValue], casualty.payload)["model_instance_id"]
    assert casualty_id in {model.model_instance_id for model in units["enemy"].own_models}
    observed = records[records.index(casualty) + 1]
    assert observed.event_type == "rule_trigger_observed"
    trigger_id = cast(dict[str, JsonValue], observed.payload)["trigger_id"]

    checkpoint = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    assert restored.to_persistence_payload() == checkpoint
    viewer = ViewerContext.for_player(request.actor_id)
    view = restored.view_for_context(viewer=viewer)["pending_decision"]
    assert view is not None
    assert view == session.view_for_context(viewer=viewer)["pending_decision"]
    option = next(
        o["option_id"]
        for o in view["options"]
        if (o["option_id"] != DECLINE_STRATAGEM_WINDOW_OPTION_ID) == reroll
    )
    with pytest.raises(GameLifecycleError, match="does not own the pending decision"):
        restored.submit_viewer_option(
            viewer=ViewerContext.for_player("player-b"),
            request_id=view["request_id"],
            option_id=option,
            result_id="wrong-shooter",
        )
    assert restored.to_persistence_payload() == checkpoint
    status = restored.submit_viewer_option(
        viewer=viewer,
        request_id=view["request_id"],
        option_id=option,
        result_id="post-casualty-shooting-answer",
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION, status
    assert window["sequence_number"] == len(records) - 1
    assert [e.event_type for e in records[-3:]] == [
        "primary_battlefield_departure_recorded",
        "model_destruction_occurrence_recorded",
        "decision_requested",
    ]
    assert records[-2].payload == {"trigger_id": trigger_id}
    assert not any(
        e.event_type == "rule_trigger_released" for e in records[records.index(observed) :]
    )

    events = restored.lifecycle.decision_controller.event_log.records
    assert (
        sum(
            e.event_type == "model_destroyed"
            and isinstance(e.payload, dict)
            and e.payload["model_instance_id"] == casualty_id
            for e in events
        )
        == 1
    )
    assert [e.event_type for e in events if e.payload == {"trigger_id": trigger_id}] == [
        "model_destruction_occurrence_recorded",
        "rule_trigger_released",
        "rule_trigger_completed",
    ]
    assert (
        sum(
            e.event_type == "attack_sequence_step"
            and isinstance(e.payload, dict)
            and e.payload.get("step") == "damage"
            and e.payload.get("attack_context_id") == attack_context
            for e in events
        )
        == 1
    )
    assert sum(e.event_type == "command_reroll_resolved" for e in events) == reroll
    restored_state = restored.lifecycle.state
    assert restored_state is not None
    assert (
        sum(
            record.command_point_cost
            for record in restored_state.stratagem_use_records
            if record.stratagem_id == "command-reroll" and record.player_id == "player-a"
        )
        == reroll
    )
    replay = ReplayRunner.from_payload(
        restored.replay_artifact(artifact_id="shooting-after-casualty")
    ).run()
    assert replay.reproduced_exactly, replay
