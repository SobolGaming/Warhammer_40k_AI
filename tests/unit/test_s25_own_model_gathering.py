"""A supported clause declared before native startup remains owned by each bearer."""

from collections import Counter
from typing import cast

import pytest
from tests.order128_helpers import assert_checkpoint
from tests.phase13b_shooting_declaration_helpers import proposal_from_request
from tests.psychic_modifier_helpers import submit_fixture_request
from tests.s25_native_profile_helpers import native_profile_request

from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id


@pytest.mark.parametrize("player", ["player-a", "player-b"])
@pytest.mark.parametrize(
    "mode",
    [
        "uniform-own-hit",
        "own-ignore",
        "obscuring-cover",
        "activated-own-reroll",
        "attached-own-ignore",
        "activated-own-ignore",
        "activated-own-strength",
        "activated-own-strength-pair",
        "obscuring-cover-ignored",
        "activated-own-skill",
        "activated-own-random-skill",
    ],
)
def test_normal_uniform_own_model_clauses_gather_without_sharing_source_ownership(
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
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="s25-own-model:declaration",
        payload=validate_json_value(proposal),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    state = session.lifecycle.state
    assert state is not None
    assert state.shooting_phase_state is not None
    sequence = state.shooting_phase_state.attack_sequence
    assert sequence is not None
    group = sequence.current_gathered_group
    assert group is not None
    assert group.pool_indices == (0, 1)
    assert group.total_attacks == 4
    assert len({snapshot.source_proof_json for snapshot in group.native_snapshots}) == 2
    assert len({snapshot.rules_json for snapshot in group.native_snapshots}) == 1
    assert_checkpoint(session)
    for _ in range(100):
        if any(
            e.event_type == "attack_sequence_completed"
            for e in session.lifecycle.decision_controller.event_log.records
        ):
            break
        pending = session.advance_until_decision_or_terminal().decision_request
        assert pending is not None
        if (
            mode in {"own-ignore", "attached-own-ignore"}
            and pending.decision_type == "select_modifier_ignores"
        ):
            option = next(o for o in pending.options if o.option_id == "ignore-remaining")
            status = session.submit_option(
                request_id=pending.request_id,
                option_id=option.option_id,
                result_id=pending.request_id + ":s25-own-ignore",
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
        elif mode == "activated-own-reroll" and pending.decision_type == "select_dice_reroll":
            option = next(o for o in pending.options if o.option_id.startswith("reroll:"))
            status = session.submit_option(
                request_id=pending.request_id,
                option_id=option.option_id,
                result_id=pending.request_id + ":s25-own-reroll",
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
        else:
            submit_fixture_request(session, pending)
    else:
        raise AssertionError("Uniform own-model native continuation did not complete.")
    assert_checkpoint(session)
    events = session.lifecycle.decision_controller.event_log.records
    if mode.startswith("activated-own-"):
        activations = [
            e.payload
            for e in events
            if e.event_type == "catalog_any_phase_once_per_battle_ability_activated"
            and isinstance(e.payload, dict)
        ]
        assert len(activations) == 2
        assert {cast(str, row["source_model_instance_id"]) for row in activations} == {
            contribution.attacker_model_instance_id for contribution in group.contributions
        }
        if mode == "activated-own-reroll":
            assert any(e.event_type == "dice_reroll_resolved" for e in events)
    if mode in {"obscuring-cover", "obscuring-cover-ignored"}:
        assert len(state.stratagem_use_records) == 1
        assert state.stratagem_use_records[0].stratagem_id == "smokescreen"
    if mode in {"own-ignore", "attached-own-ignore"}:
        choices = [
            record
            for record in session.lifecycle.decision_controller.records
            if record.request.decision_type == "select_modifier_ignores"
        ]
        assert len(choices) == 4
        expected = Counter(
            (row["attacker_model_instance_id"], row["weapon_profile_id"])
            for row in proposal["declarations"]
            for _ in range(2)
        )
        actual: Counter[tuple[JsonValue, JsonValue]] = Counter()
        ignored_by_bearer: dict[str, set[str]] = {}
        attacker = rules_unit_view_by_id(
            state=state, unit_instance_id=sequence.attacking_unit_instance_id
        )
        for choice in choices:
            payload = cast(dict[str, JsonValue], choice.request.payload)
            subject = cast(dict[str, JsonValue], payload["subject"])
            model_id = cast(str, subject["model_instance_id"])
            assert choice.request.actor_id == player
            assert subject["unit_instance_id"] == attacker.component_unit_id_for_model(model_id)
            assert subject["kind"] == "hit_roll"
            actual[(subject["model_instance_id"], subject["weapon_profile_id"])] += 1
            permissions = cast(list[dict[str, JsonValue]], payload["permissions"])
            assert len(permissions) == 1
            context = cast(dict[str, JsonValue], permissions[0]["source_context"])
            assert context["source_unit_instance_id"] == attacker.component_unit_id_for_model(
                model_id
            )
            assert context["source_model_instance_id"] == model_id
            assert context["eligible_source_model_ids"] == [model_id]
            operations = cast(list[dict[str, JsonValue]], payload["modifiers"])
            identifiers = [
                cast(dict[str, JsonValue], row["operation"])["modifier_id"] for row in operations
            ]
            assert len(identifiers) == 1
            result = cast(dict[str, JsonValue], choice.result.payload)
            assert choice.result.selected_option_id == "ignore-remaining"
            assert result["ignored_modifier_ids"] == identifiers
            ignored_by_bearer.setdefault(model_id, set()).add(cast(str, identifiers[0]))
        assert actual == expected
        assert len(ignored_by_bearer) == 2
        first_ids, second_ids = ignored_by_bearer.values()
        assert first_ids.isdisjoint(second_ids)
    if mode == "activated-own-random-skill":
        evaluations = [
            e.payload
            for e in events
            if e.event_type == "random_weapon_profile_evaluated" and isinstance(e.payload, dict)
        ]
        assert len(evaluations) == 4
        assert len({cast(str, row["scope_id"]) for row in evaluations}) == 4
        assert {cast(str, row["weapon_instance_id"]) for row in evaluations} == {
            contribution.weapon_instance_id for contribution in group.contributions
        }
    hits = [
        e.payload
        for e in events
        if e.event_type == "attack_sequence_step"
        and isinstance(e.payload, dict)
        and e.payload.get("step") == "hit"
    ]
    assert len(hits) == 4
    for hit in hits:
        result = cast(dict[str, JsonValue], hit["payload"])
        assert result["modifier"] == (1 if mode == "uniform-own-hit" else 0)
    stages: dict[str, list[int]] = {"hit": [], "wound": []}
    for index, event in enumerate(events):
        if event.event_type == "dice_rolled" and isinstance(event.payload, dict):
            spec = cast(dict[str, JsonValue], event.payload["spec"])
            for name in stages:
                if spec.get("roll_type") == "attack_sequence." + name:
                    stages[name].append(index)
    assert len(stages["hit"]) == 4
    assert stages["wound"]
    assert max(stages["hit"]) < min(stages["wound"])
