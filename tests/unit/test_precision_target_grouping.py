"""P04G: inapplicable PRECISION cannot split otherwise identical physical attacks."""

import json
from dataclasses import replace
from typing import Any, cast

import pytest
from tests.precision_grouping_helpers import (
    assert_precision_scene_persistence_and_completion,
    offered_group_request,
    precision_melee_scene,
    precision_shooting_scene,
)
from tests.precision_replacement_helpers import precision_replacement_scene
from tests.psychic_modifier_helpers import submit_fixture_request

from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.attack_sequence import GatheredAttackGroup
from warhammer40k_core.engine.attack_sequence_selection import target_has_character_for_attack_group
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id


@pytest.mark.parametrize("precision_first", [True, False])
def test_non_character_target_gathers_both_physical_precision_orders(
    precision_first: bool,
) -> None:
    scene = precision_shooting_scene(precision_first=precision_first, pause_at_first_hit=True)
    request = offered_group_request(scene.session)
    assert len(request.options) == 1, [option.payload for option in request.options]
    body = cast(dict[str, JsonValue], request.options[0].payload)
    group = cast(dict[str, JsonValue], body["gathered_group"])
    contributions = cast(list[dict[str, JsonValue]], group["contributions"])
    assert group["target_unit_instance_id"] == scene.target_id
    assert group["pool_indices"] == [0, 1]
    assert group["target_has_character"] is False
    assert group["total_attacks"] == 4
    assert tuple(item["weapon_instance_id"] for item in contributions) == scene.physical_weapon_ids
    assert (scene.precision_weapon_id == scene.physical_weapon_ids[0]) is precision_first
    state = scene.session.lifecycle.state
    assert state is not None
    assert state.shooting_phase_state is not None
    sequence = state.shooting_phase_state.attack_sequence
    assert sequence is not None
    assert sequence.current_gathered_group is not None
    assert sequence.current_gathered_group.target_has_character is False
    # The synthetic execution carrier preserves the first physical source profile.
    # Its otherwise inert PRECISION must not affect choices against this target.
    assert (WeaponKeyword.PRECISION in sequence.current_pool().weapon_profile.keywords) is (
        precision_first
    )
    assert tuple(pool.weapon_instance_id for pool in sequence.attack_pools) == (
        scene.physical_weapon_ids
    )
    assert_precision_scene_persistence_and_completion(scene)


@pytest.mark.parametrize("precision_first", [True, False])
def test_character_target_preserves_distinct_precision_groups(precision_first: bool) -> None:
    scene = precision_shooting_scene(precision_first=precision_first, character_target=True)
    request = offered_group_request(scene.session)
    assert len(request.options) == 2
    groups = [
        cast(dict[str, JsonValue], cast(dict[str, JsonValue], item.payload)["gathered_group"])
        for item in request.options
    ]
    assert all(group["target_has_character"] is True for group in groups)
    assert {tuple(cast(list[int], group["pool_indices"])) for group in groups} == {(0,), (1,)}
    assert_precision_scene_persistence_and_completion(scene, allow_precision=True)


def test_mixed_precision_random_defence_history_restores_and_replays() -> None:
    scene = precision_shooting_scene(precision_first=True, random_defence=True)
    assert len(offered_group_request(scene.session).options) == 1
    before = scene.session.lifecycle.decision_controller
    assert any(
        record.request.decision_type == "select_attack_weapon_group" for record in before.records
    )
    assert any(
        event.event_type == "random_profile_values_evaluated" for event in before.event_log.records
    )
    assert_precision_scene_persistence_and_completion(scene)
    history = scene.session.lifecycle.decision_controller.event_log.records
    assert any("random_profile" in event.event_type for event in history)


@pytest.mark.parametrize("character_target", [False, True])
def test_selected_duplicate_precision_source_follows_target_applicability(
    character_target: bool,
) -> None:
    scene = precision_shooting_scene(
        precision_first=True, duplicate_precision=True, character_target=character_target
    )
    accepted = next(
        event
        for event in scene.session.lifecycle.decision_controller.event_log.records
        if event.event_type == "shooting_declaration_accepted"
    )
    pools = cast(
        list[dict[str, JsonValue]], cast(dict[str, JsonValue], accepted.payload)["attack_pools"]
    )
    assert sum(bool(pool["selected_weapon_ability_ids"]) for pool in pools) == 1
    assert len(offered_group_request(scene.session).options) == (2 if character_target else 1)
    assert any(
        pool["weapon_selection_context"] for pool in pools if pool["selected_weapon_ability_ids"]
    )
    assert_precision_scene_persistence_and_completion(scene, allow_precision=character_target)


@pytest.mark.parametrize("precision_first", [True, False])
def test_legal_extra_attacks_share_target_aware_grouping(precision_first: bool) -> None:
    scene = precision_melee_scene(precision_first=precision_first)
    request = offered_group_request(scene.session)
    assert len(request.options) == 2  # One primary and the identical Extra Attacks pair.
    groups = [
        cast(dict[str, JsonValue], cast(dict[str, JsonValue], item.payload)["gathered_group"])
        for item in request.options
    ]
    group = next(item for item in groups if len(cast(list[int], item["pool_indices"])) == 2)
    contributions = cast(list[dict[str, JsonValue]], group["contributions"])
    assert group["target_has_character"] is False
    assert tuple(item["weapon_instance_id"] for item in contributions) == scene.physical_weapon_ids
    assert (scene.precision_weapon_id == scene.physical_weapon_ids[0]) is precision_first
    selected = next(
        item
        for item in request.options
        if cast(dict[str, JsonValue], item.payload)["gathered_group"] == group
    )
    scene.session.submit_option(
        request_id=request.request_id,
        option_id=selected.option_id,
        result_id="order103-select-mixed-extra-group",
    )
    assert_precision_scene_persistence_and_completion(scene)


@pytest.mark.parametrize("replacement_character", [False, True])
def test_actual_casualties_retarget_unresolved_precision_groups(
    replacement_character: bool,
) -> None:
    scene = precision_replacement_scene(replacement_character=replacement_character)
    decisions = scene.session.lifecycle.decision_controller
    requests = [record.request for record in decisions.records]
    pending = scene.session.advance_until_decision_or_terminal().decision_request
    if pending is not None:
        requests.append(pending)
    request = next(
        request
        for request in reversed(requests)
        if request.decision_type == "select_attack_weapon_group"
        and cast(
            dict[str, JsonValue],
            cast(dict[str, JsonValue], request.options[0].payload)["gathered_group"],
        )["target_unit_instance_id"]
        == scene.target_id
    )
    assert len(request.options) == (2 if replacement_character else 1)
    groups = [
        cast(dict[str, JsonValue], cast(dict[str, JsonValue], option.payload)["gathered_group"])
        for option in request.options
    ]
    assert all(group["target_has_character"] is replacement_character for group in groups)
    physical = {
        cast(str, item["weapon_instance_id"])
        for group in groups
        for item in cast(list[dict[str, JsonValue]], group["contributions"])
    }
    assert physical == set(scene.physical_weapon_ids)
    assert_precision_scene_persistence_and_completion(scene, allow_precision=replacement_character)


def test_group_context_is_required_strict_and_pending_mutation_fails_atomically() -> None:
    scene = precision_shooting_scene(precision_first=True, character_target=True)
    request = offered_group_request(scene.session)
    payload = cast(dict[str, JsonValue], json.loads(json.dumps(request.options[0].payload)))
    group_payload = cast(Any, payload["gathered_group"])
    group = GatheredAttackGroup.from_payload(group_payload)
    for invalid in (None, 0, 1, "false"):
        with pytest.raises(GameLifecycleError, match="bool"):
            replace(group, target_has_character=cast(Any, invalid))
    missing = dict(group_payload)
    del missing["target_has_character"]
    with pytest.raises(KeyError, match="target_has_character"):
        GatheredAttackGroup.from_payload(cast(Any, missing))
    group_payload["target_has_character"] = False
    before = scene.session.lifecycle.to_payload()
    status = scene.session.lifecycle.submit_decision(
        DecisionResult(
            result_id="order103-invalid-context",
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id=request.options[0].option_id,
            payload=payload,
        )
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert scene.session.lifecycle.to_payload() == before


def test_non_precision_selected_source_identity_remains_distinct() -> None:
    scene = precision_shooting_scene(precision_first=True, duplicate_lethal=True)
    request = offered_group_request(scene.session)
    assert len(request.options) == 2
    tokens = [
        cast(
            list[str],
            cast(
                dict[str, JsonValue],
                cast(
                    dict[str, JsonValue],
                    cast(dict[str, JsonValue], option.payload)["gathered_group"],
                )["signature"],
            )["weapon_rule_tokens"],
        )
        for option in request.options
    ]
    selected = [
        {token for token in row if token.startswith("selected-weapon-ability:")} for row in tokens
    ]
    assert all(len(row) == 1 for row in selected)
    assert selected[0] != selected[1]
    assert_precision_scene_persistence_and_completion(scene)


def test_attached_character_allocation_and_casualty_preserve_recorded_group_context() -> None:
    scene = precision_shooting_scene(
        precision_first=True, character_target=True, attached_target=True, random_defence=True
    )
    request = offered_group_request(scene.session)
    assert len(request.options) == 2
    precision_option = next(
        option
        for option in request.options
        if any(
            item["weapon_instance_id"] == scene.precision_weapon_id
            for item in cast(
                list[dict[str, JsonValue]],
                cast(
                    dict[str, JsonValue],
                    cast(dict[str, JsonValue], option.payload)["gathered_group"],
                )["contributions"],
            )
        )
    )
    scene.session.submit_option(
        request_id=request.request_id,
        option_id=precision_option.option_id,
        result_id="order103-attached-select-precision",
    )
    allocation_request = scene.session.advance_until_decision_or_terminal().decision_request
    assert allocation_request is not None
    request = allocation_request
    assert request.decision_type == "select_precision_allocation"
    state = scene.session.lifecycle.state
    assert state is not None
    characters = tuple(
        model
        for model in rules_unit_view_by_id(state=state, unit_instance_id=scene.target_id).own_models
        if model.is_alive and "CHARACTER" in model.keywords
    )
    assert len(characters) == 1
    character_id = characters[0].model_instance_id
    option = next(
        option
        for option in request.options
        if character_id
        in cast(list[str], cast(dict[str, JsonValue], option.payload)["selected_model_ids"])
    )
    scene.session.submit_option(
        request_id=request.request_id,
        option_id=option.option_id,
        result_id="order103-attached-allocate-character",
    )
    for _ in range(20):
        state = scene.session.lifecycle.state
        assert state is not None
        if not target_has_character_for_attack_group(
            state=state, target_unit_instance_id=scene.target_id
        ):
            break
        pending = scene.session.advance_until_decision_or_terminal().decision_request
        assert pending is not None
        submit_fixture_request(scene.session, pending)
    else:
        raise AssertionError(
            "Real Precision attacks did not destroy the selected attached Character."
        )
    decisions = scene.session.lifecycle.decision_controller
    selected = next(
        record
        for record in decisions.records
        if record.result.result_id == "order103-attached-select-precision"
    )
    recorded = cast(
        dict[str, JsonValue], cast(dict[str, JsonValue], selected.result.payload)["gathered_group"]
    )
    assert recorded["target_has_character"] is True
    assert any(
        event.event_type == "random_profile_values_evaluated"
        for event in decisions.event_log.records
    )
    assert_precision_scene_persistence_and_completion(scene, allow_precision=True)
