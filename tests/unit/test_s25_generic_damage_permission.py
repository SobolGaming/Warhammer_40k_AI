"""Real random Damage retains selected generic permissions without binding inventory."""

from typing import TYPE_CHECKING, cast

import pytest
from tests.order128_helpers import assert_checkpoint
from tests.phase13b_shooting_declaration_helpers import proposal_from_request
from tests.psychic_modifier_helpers import submit_fixture_request
from tests.s25_generic_damage_permission_helpers import declared_shared_damage_permission
from tests.s25_native_profile_helpers import native_profile_request

from warhammer40k_core.engine.catalog_modifier_ignore import (
    ModifierIgnoreKind,
    modifier_ignore_sources_for_gathering,
)
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.modifier_permission_context import ModifierPermissionAttackContext
from warhammer40k_core.engine.native_attack_gathering import (
    _current_applicable_rules,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

if TYPE_CHECKING:
    from warhammer40k_core.engine.catalog_modifier_ignore_sources import (
        ModifierIgnoreSourceTemplate,
    )


@pytest.mark.parametrize("player", ["player-a", "player-b"])
@pytest.mark.parametrize("qualified_roll", [False, True])
def test_native_generic_damage_permission_retains_actual_consumer_dependencies(
    player: str, qualified_roll: bool
) -> None:
    mode = "shared-unit-qualified-damage" if qualified_roll else "shared-unit-damage"
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
            "attacker_model_instance_id": cast(str, weapon["model_instance_id"]),
            "weapon_instance_id": cast(str, weapon["weapon_instance_id"]),
        }
        for weapon in matching[:2]
    ]
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="s25-generic-damage:declaration",
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
    assert len({s.rules_json for s in group.native_snapshots}) == 1
    assert len({s.raw_signature_json for s in group.native_snapshots}) == 2
    assert len({s.source_proof_json for s in group.native_snapshots}) == 2
    descriptor = declared_shared_damage_permission(chooser=False, qualified_roll=qualified_roll)
    bundle = session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    registry = bundle.runtime_modifier_registry
    assert not registry.damage_roll_modifier_bindings
    source_rows: list[ModifierIgnoreSourceTemplate] = []
    for pool in sequence.attack_pools:
        assert pool.weapon_profile.damage_profile.dice_expression is not None
        sources = modifier_ignore_sources_for_gathering(
            state=state,
            ability_index=registry.modifier_permission_index(player),
            unit_instance_id=sequence.attacking_unit_instance_id,
            kind=ModifierIgnoreKind.DAMAGE_ROLL,
            model_instance_id=pool.attacker_model_instance_id,
            weapon_profile_id=pool.weapon_profile_id,
            attack_context=ModifierPermissionAttackContext(
                sequence.attacking_unit_instance_id,
                pool.attacker_model_instance_id,
                pool.target_unit_instance_id,
                "attacker",
                sequence.source_phase,
                pool.weapon_profile,
                None,
                None,
            ),
        )
        assert len(sources.persisted_source_templates) == 1
        row = sources.persisted_source_templates[0]
        source = cast(dict[str, JsonValue], row.raw_payload["source"])
        persisted = cast(dict[str, JsonValue], row.raw_payload["persisting_effect"])
        assert source["source_id"] == descriptor.source_id
        assert source["target_kind"] == "this_unit"
        assert source["source_model_instance_id"] != pool.attacker_model_instance_id
        assert persisted["owner_player_id"] == player
        assert persisted == validate_json_value(
            next(
                e.to_payload()
                for e in state.persisting_effects
                if e.effect_id == persisted["effect_id"]
            )
        )
        target_view = rules_unit_view_by_id(state=state, unit_instance_id=target)
        comparison, raw = _current_applicable_rules(
            state=state,
            registry=registry,
            sequence=sequence,
            pool=pool,
            target_has_character="CHARACTER" in target_view.keywords,
        )
        assert comparison["persisted_attacker_ignore_sources"] == [row.comparison_payload]
        assert raw["persisted_attacker_ignore_sources"] == [row.raw_payload]
        assert not any(
            r["source_id"] == descriptor.source_id
            for r in cast(
                list[dict[str, JsonValue]], raw["unused_ignore_grants_excluded_from_comparison"]
            )
        )
        assert any(
            r["source_id"] == descriptor.source_id and r["effect_index"] == 0
            for r in cast(list[dict[str, JsonValue]], comparison["generic_applicable_sources"])
        )
        source_rows.append(row)
    assert source_rows[0].comparison_payload == source_rows[1].comparison_payload
    assert source_rows[0].raw_payload != source_rows[1].raw_payload
    declared_effects = [
        e.to_payload() for e in state.persisting_effects if e.source_rule_id == descriptor.source_id
    ]
    assert len(declared_effects) == 2
    pending = session.advance_until_decision_or_terminal().decision_request
    assert pending is not None
    before = session.to_persistence_payload()
    with pytest.raises(DecisionError, match="finite action space"):
        session.submit_option(
            request_id=pending.request_id,
            option_id="s25-generic-damage-invalid",
            result_id="s25-generic-damage-invalid",
        )
    assert session.to_persistence_payload() == before
    assert_checkpoint(session)
    for _ in range(120):
        if any(
            e.event_type == "attack_sequence_completed"
            for e in session.lifecycle.decision_controller.event_log.records
        ):
            break
        pending = session.advance_until_decision_or_terminal().decision_request
        assert pending is not None
        submit_fixture_request(session, pending)
    else:
        raise AssertionError("Normal generic Damage permission did not complete.")
    assert_checkpoint(session)
    completed_state = session.lifecycle.state
    assert completed_state is not None
    assert [
        e.to_payload()
        for e in completed_state.persisting_effects
        if e.source_rule_id == descriptor.source_id
    ] == declared_effects
    choices = [
        r.request
        for r in session.lifecycle.decision_controller.records
        if r.request.decision_type == "select_modifier_ignores"
    ]
    assert choices
    physical_subjects = {
        (p.attacker_model_instance_id, p.weapon_profile_id) for p in sequence.attack_pools
    }
    contexts: set[str] = set()
    for choice in choices:
        assert choice.actor_id == player
        payload = cast(dict[str, JsonValue], choice.payload)
        subject = cast(dict[str, JsonValue], payload["subject"])
        assert subject["kind"] == ModifierIgnoreKind.DAMAGE_ROLL.value
        assert (subject["model_instance_id"], subject["weapon_profile_id"]) in physical_subjects
        operations = cast(list[dict[str, JsonValue]], payload["modifiers"])
        assert len(operations) == 1
        operation = cast(dict[str, JsonValue], operations[0]["operation"])
        assert operation["source_id"] == descriptor.source_id
        assert operation["operand"] == 1
        permissions = cast(list[dict[str, JsonValue]], payload["permissions"])
        assert len(permissions) == 1
        permission = permissions[0]
        assert permission["source_id"] == descriptor.source_id
        assert permission["modifier_kinds"] == ["damage_roll"]
        context = cast(dict[str, JsonValue], permission["source_context"])
        assert context["subject_model_instance_id"] == subject["model_instance_id"]
        assert (
            context["source_model_instance_id"]
            == cast(dict[str, JsonValue], source_rows[0].raw_payload["source"])[
                "source_model_instance_id"
            ]
        )
        assert context["persisting_effect"] == source_rows[0].raw_payload["persisting_effect"]
        continuation = cast(dict[str, JsonValue], payload["source_context"])
        assert (
            continuation["allocated_model_instance_id"]
            in sequence.attack_pools[0].target_in_range_model_ids
        )
        contexts.add(cast(str, continuation["attack_context_id"]))
    events = session.lifecycle.decision_controller.event_log.records
    dice_types: set[str] = set()
    for event in events:
        if event.event_type == "dice_rolled" and isinstance(event.payload, dict):
            spec = cast(dict[str, JsonValue], event.payload["spec"])
            roll_type = spec.get("roll_type")
            if isinstance(roll_type, str) and roll_type.startswith(
                "random_characteristic.damage.per_attack."
            ):
                assert spec["actor_id"] == player
                assert event.payload["source"] == "rng"
                dice_types.add(roll_type)
    assert dice_types == {
        "random_characteristic.damage.per_attack." + c + ":damage" for c in contexts
    }
    selected = [e.payload for e in events if e.event_type == "catalog_shadow_form_selected"]
    assert len(selected) == 1
    assert (
        cast(dict[str, JsonValue], selected[0])["selected_shadow_form_source_id"]
        == descriptor.source_id
    )
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
