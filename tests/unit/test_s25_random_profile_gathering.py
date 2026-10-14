"""Admitted random profiles gather while real occurrences retain independent dice."""

import json
from typing import cast

import pytest
from tests.epic_challenge_helpers import epic_checkpoint, submit_all_melee
from tests.order128_helpers import assert_checkpoint
from tests.phase13b_shooting_declaration_helpers import proposal_from_request
from tests.psychic_modifier_helpers import submit_fixture_request
from tests.s25_native_profile_helpers import native_profile_request
from tests.s25_random_melee_gathering_helpers import random_ws_melee_request

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.stratagems import stratagem_decline_payload


@pytest.mark.parametrize("player", ["player-a", "player-b"])
@pytest.mark.parametrize(
    "mode", ["random-skill", "random-strength", "random-ap", "random-toughness", "random-damage"]
)
def test_native_random_profiles_group_without_early_or_shared_occurrence_rolls(
    player: str,
    mode: str,
) -> None:
    session, request = native_profile_request(player=player, mode=mode)
    target = "army-beta:scalar" if player == "player-a" else "army-alpha:scalar"
    proposal = proposal_from_request(request=request, target_unit_id=target).to_payload()
    offered = cast(
        dict[str, JsonValue], cast(dict[str, JsonValue], request.payload)["proposal_request"]
    )
    weapons = cast(list[dict[str, JsonValue]], offered["available_weapons"])
    first = proposal["declarations"][0]
    matching = [w for w in weapons if w["weapon_profile_id"] == first["weapon_profile_id"]]
    proposal["declarations"] = [
        {
            **first,
            "attacker_model_instance_id": cast(str, w["model_instance_id"]),
            "weapon_instance_id": cast(str, w["weapon_instance_id"]),
        }
        for w in matching[:2]
    ]
    physical_ids = {row["weapon_instance_id"] for row in proposal["declarations"]}
    assert len(physical_ids) == 2
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="s25-random:declaration",
        payload=validate_json_value(proposal),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    state = session.lifecycle.state
    assert state is not None
    assert state.shooting_phase_state is not None
    sequence = state.shooting_phase_state.attack_sequence
    assert sequence is not None
    assert sequence.current_gathered_group is not None
    group = sequence.current_gathered_group
    assert group.pool_indices == (0, 1)
    assert group.total_attacks == 4
    assert not any(snapshot.conservative_boundaries for snapshot in group.native_snapshots)
    assert_checkpoint(session)
    before = session.to_persistence_payload()
    pending = session.advance_until_decision_or_terminal().decision_request
    assert pending is not None
    with pytest.raises(DecisionError, match="finite action space"):
        session.submit_option(
            request_id=pending.request_id,
            option_id="s25-random:invalid",
            result_id="s25-random:invalid",
        )
    assert session.to_persistence_payload() == before
    restored = LocalGameSession.from_persistence_payload(json.loads(json.dumps(before)))
    fork = session.fork()
    for _ in range(100):
        requests = tuple(
            s.advance_until_decision_or_terminal().decision_request for s in (restored, fork)
        )
        assert requests[0] is not None
        assert requests[1] is not None
        assert requests[0].to_payload() == requests[1].to_payload()
        for current, current_request in zip((restored, fork), requests, strict=True):
            assert current_request is not None
            submit_fixture_request(current, current_request)
        if any(
            e.event_type == "attack_sequence_completed"
            for e in restored.lifecycle.decision_controller.event_log.records
        ):
            break
    else:
        raise AssertionError("Random profile native continuation did not complete.")
    assert restored.to_persistence_payload() == fork.to_persistence_payload()

    assert session.to_persistence_payload() == before
    assert_checkpoint(restored)
    events = restored.lifecycle.decision_controller.event_log.records
    stages: dict[str, list[int]] = {"hit": [], "wound": [], "save": []}
    for index, event in enumerate(events):
        if event.event_type != "dice_rolled" or not isinstance(event.payload, dict):
            continue
        spec = cast(dict[str, JsonValue], event.payload["spec"])
        roll_type = cast(str, spec["roll_type"])
        if roll_type in {"attack_sequence.hit", "attack_sequence.wound"}:
            stages[roll_type.removeprefix("attack_sequence.")].append(index)
        elif roll_type.startswith("attack_sequence.save."):
            stages["save"].append(index)
    assert len(stages["hit"]) == 4
    assert stages["wound"]
    assert max(stages["hit"]) < min(stages["wound"])
    if stages["save"]:
        assert max(stages["wound"]) < min(stages["save"])
    evaluations = [
        e.payload
        for e in events
        if e.event_type == "random_weapon_profile_evaluated" and isinstance(e.payload, dict)
    ]
    if mode in {"random-skill", "random-strength", "random-ap"}:
        assert evaluations
        assert len({cast(str, row["scope_id"]) for row in evaluations}) == len(evaluations)
        if mode == "random-skill":
            assert len(evaluations) == 4
            assert {cast(str, row["weapon_instance_id"]) for row in evaluations} == physical_ids
        for row in evaluations:
            assert row["weapon_instance_id"] in physical_ids
            assert str(row["scope_id"]).startswith(str(row["attack_context_id"]))
    if mode == "random-toughness":
        history_rows = [
            e.payload
            for e in events
            if e.event_type == "random_profile_values_evaluated" and isinstance(e.payload, dict)
        ]
        # Grouped Wound re-entry restores an earlier physical evaluation and
        # journals that transition with reused=True; it does not roll again.
        model_rows = [
            row
            for row in history_rows
            if any(
                not entry["reused"] for entry in cast(list[dict[str, JsonValue]], row["entries"])
            )
        ]
        assert len(model_rows) == len(stages["wound"])
        assert len({cast(str, row["scope_id"]) for row in model_rows}) == len(model_rows)
        wound_contexts = {
            cast(str, e.payload["attack_context_id"]): index
            for index, e in enumerate(events)
            if e.event_type == "attack_sequence_step"
            and isinstance(e.payload, dict)
            and e.payload.get("step") == "wound"
        }
        assert len(wound_contexts) == len(stages["wound"])
        assert {cast(str, row["scope_id"]) for row in model_rows} == set(wound_contexts)
        original_entries: dict[str, dict[str, JsonValue]] = {}
        for row in model_rows:
            entries = cast(list[dict[str, JsonValue]], row["entries"])
            assert len(entries) == 5
            assert len({cast(str, entry["model_instance_id"]) for entry in entries}) == 5
            assert all(entry["reused"] is False for entry in entries)
            for entry in entries:
                profile = cast(dict[str, JsonValue], entry["profile_value"])
                identity = cast(str, profile["evaluation_id"])
                assert identity not in original_entries
                original_entries[identity] = entry
        observed_fresh: set[str] = set()
        for row in history_rows:
            entries = cast(list[dict[str, JsonValue]], row["entries"])
            assert len(entries) == 5
            assert len({cast(str, entry["model_instance_id"]) for entry in entries}) == 5
            assert row["unit_instance_id"] == target
            assert all(type(entry["reused"]) is bool for entry in entries)
            assert len({cast(bool, entry["reused"]) for entry in entries}) == 1
            for entry in entries:
                profile = cast(dict[str, JsonValue], entry["profile_value"])
                identity = cast(str, profile["evaluation_id"])
                assert identity == (
                    f"{row['scope_id']}:{target}:{entry['model_instance_id']}:toughness"
                )
                if entry["reused"]:
                    assert identity in observed_fresh
                else:
                    assert identity not in observed_fresh
                    observed_fresh.add(identity)
                assert {key: value for key, value in entry.items() if key != "reused"} == {
                    key: value
                    for key, value in original_entries[identity].items()
                    if key != "reused"
                }
        actual_rolls = [
            (index, e.payload)
            for index, e in enumerate(events)
            if e.event_type == "dice_rolled"
            and isinstance(e.payload, dict)
            and str(cast(dict[str, JsonValue], e.payload["spec"])["roll_type"]).startswith(
                "random_characteristic.toughness.per_model."
            )
        ]
        assert len(actual_rolls) == 5 * len(stages["wound"])
        assert min(index for index, _ in actual_rolls) > max(stages["hit"])
        assert max(index for index, _ in actual_rolls) < min(stages["wound"])
        expected_rolls: list[JsonValue] = []
        expected_witnesses: list[dict[str, JsonValue]] = []
        for entry in original_entries.values():
            roll = cast(dict[str, JsonValue], entry["roll"])
            expected_witnesses.append(roll)
            roll_state = cast(dict[str, JsonValue], roll["roll_state"])
            expected_rolls.append(roll_state["original_result"])
        assert len(
            {cast(str, cast(dict[str, JsonValue], row)["roll_id"]) for row in expected_rolls}
        ) == len(expected_rolls)
        assert sorted(json.dumps(row, sort_keys=True) for _, row in actual_rolls) == sorted(
            json.dumps(row, sort_keys=True) for row in expected_rolls
        )
        witnesses = [
            e.payload
            for e in events
            if e.event_type == "random_characteristic_rolled"
            and isinstance(e.payload, dict)
            and e.payload.get("characteristic") == "toughness"
        ]
        assert len(witnesses) == len(expected_witnesses)
        assert len({cast(str, row["scope_id"]) for row in witnesses}) == len(witnesses)
        assert sorted(json.dumps(row, sort_keys=True) for row in witnesses) == sorted(
            json.dumps(row, sort_keys=True) for row in expected_witnesses
        )
    if mode == "random-damage":
        damage_rolls = [
            (index, e.payload)
            for index, e in enumerate(events)
            if e.event_type == "dice_rolled"
            and isinstance(e.payload, dict)
            and cast(str, cast(dict[str, JsonValue], e.payload["spec"])["roll_type"]).startswith(
                "random_characteristic.damage.per_attack."
            )
        ]
        assert damage_rolls, "The declared AP -6 control must actually roll random Damage."
        assert len(
            {
                cast(str, cast(dict[str, JsonValue], row["spec"])["roll_type"])
                for _, row in damage_rolls
            }
        ) == len(damage_rolls)
        allocations = [
            index
            for index, e in enumerate(events)
            if e.event_type == "attack_sequence_step"
            and isinstance(e.payload, dict)
            and e.payload.get("step") == "allocate"
        ]
        assert allocations
        assert min(allocations) < min(index for index, _ in damage_rolls)
        assert max(stages["wound"]) < min(index for index, _ in damage_rolls)
    # Continue the recovered native game beyond completion on both copies.
    for current in (restored, fork):
        next_request = current.advance_until_decision_or_terminal().decision_request
        assert next_request is not None
        if next_request.decision_type == "submit_stratagem_target_proposal":
            status = current.submit_parameterized_payload(
                request_id=next_request.request_id,
                payload=stratagem_decline_payload(),
                result_id=next_request.request_id + ":s25-native-continuation",
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
        else:
            submit_fixture_request(current, next_request)
    assert restored.to_persistence_payload() == fork.to_persistence_payload()


@pytest.mark.parametrize("player", ["player-a", "player-b"])
def test_predeclared_random_ws_preserves_physical_melee_occurrences(player: str) -> None:
    session, request = random_ws_melee_request(player)
    submit_all_melee(session, request)
    state = session.lifecycle.state
    assert state is not None
    assert state.fight_phase_state is not None
    sequence = state.fight_phase_state.attack_sequence
    assert sequence is not None
    group = sequence.current_gathered_group
    assert group is not None
    assert len(group.pool_indices) == 5
    assert group.total_attacks == 10
    physical_ids = {row.weapon_instance_id for row in group.contributions}
    assert len(physical_ids) == 5
    epic_checkpoint(session)
    for _ in range(160):
        if any(
            e.event_type == "attack_sequence_completed"
            for e in session.lifecycle.decision_controller.event_log.records
        ):
            break
        pending = session.advance_until_decision_or_terminal().decision_request
        assert pending is not None
        submit_fixture_request(session, pending)
    else:
        raise AssertionError("Random WS native attacks did not complete.")
    epic_checkpoint(session)
    events = session.lifecycle.decision_controller.event_log.records
    rows = [
        e.payload
        for e in events
        if e.event_type == "random_weapon_profile_evaluated" and isinstance(e.payload, dict)
    ]
    assert len(rows) == 10
    assert len({cast(str, row["scope_id"]) for row in rows}) == 10
    assert {cast(str, row["weapon_instance_id"]) for row in rows} == physical_ids
    stages: dict[str, list[int]] = {"hit": [], "wound": []}
    for index, event in enumerate(events):
        if event.event_type == "dice_rolled" and isinstance(event.payload, dict):
            spec = cast(dict[str, JsonValue], event.payload["spec"])
            for name in stages:
                if spec.get("roll_type") == "attack_sequence." + name:
                    stages[name].append(index)
    assert len(stages["hit"]) == 10
    assert stages["wound"]
    assert max(stages["hit"]) < min(stages["wound"])
