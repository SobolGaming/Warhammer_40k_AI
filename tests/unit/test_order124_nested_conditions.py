"""The improved branch never escapes its enclosing source condition."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest
from tests.order124_helpers import (
    KEYWORDS,
    OBJECTIVE,
    SOURCE_ID,
    TARGET,
    declare_nested_shot,
    finish_nested_shot,
    nested_session,
    nested_source,
)

from warhammer40k_core.adapters.access_control import (
    ROLE_POLICY_BY_ROLE,
    PrincipalRole,
    ViewerContext,
)
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.ability_catalog import catalog_ability_records_from_catalog
from warhammer40k_core.engine.catalog_datasheet_rule_runtime import CatalogDatasheetRuleRuntime
from warhammer40k_core.engine.catalog_nested_attack_reroll_support import (
    nested_attack_reroll_clause_is_supported,
)
from warhammer40k_core.engine.catalog_rule_consumption import catalog_rule_ir_hook_ids_for_rule
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.runtime_modifiers import AttackRerollPermissionContext
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.rules.rule_compiler import CompiledRuleSource
from warhammer40k_core.rules.rule_ir import parameter_payload, parameters_from_pairs


def test_selected_source_compiles_with_parent_and_stronger_branch() -> None:
    compiled = nested_source()
    rule = compiled.rule_ir
    assert not rule.diagnostics
    assert rule.source_id == SOURCE_ID
    assert len(rule.clauses) == 1
    clause = rule.clauses[0]
    assert parameter_payload(clause.conditions[0].parameters) == {
        "gate_subject": "attack_target",
        "target_constraint": "closest_eligible",
    }
    assert parameter_payload(clause.effects[0].parameters) == {
        "attack_kind": "ranged",
        "roll_type": "hit",
        "reroll_unmodified_value": 1,
        "full_reroll_if_target_within_opponent_controlled_objective_range": True,
    }
    assert (
        CompiledRuleSource.from_payload(
            compiled.to_payload(), source_keyword_sequence_parts=KEYWORDS
        )
        == compiled
    )
    assert "catalog-ir:passive-hit-reroll" in catalog_rule_ir_hook_ids_for_rule(rule)
    without_parent = replace(rule, clauses=(replace(clause, conditions=()),))
    assert not catalog_rule_ir_hook_ids_for_rule(without_parent)


def _source_context(request: DecisionRequest) -> dict[str, object] | None:
    payload = cast(dict[str, object], request.payload)
    attack = payload.get("attack_context")
    if not isinstance(attack, dict):
        return None
    source = cast(dict[str, object], attack).get("source_payload")
    return cast(dict[str, object], source) if isinstance(source, dict) else None


def _assert_roundtrips(session: LocalGameSession) -> tuple[LocalGameSession, LocalGameSession]:
    payload = json.loads(json.dumps(session.to_persistence_payload()))
    loaded = LocalGameSession.from_persistence_payload(payload)
    fork = session.fork()
    assert loaded.to_persistence_payload() == payload
    assert fork.lifecycle.to_payload() == session.lifecycle.to_payload()
    for viewer in ("player-a", "player-b"):
        assert loaded.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
        assert fork.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
        assert loaded.events_since(
            EventStreamCursor(), viewer_player_id=viewer
        ) == session.events_since(EventStreamCursor(), viewer_player_id=viewer)
    for role in (
        PrincipalRole.DELAYED_SPECTATOR,
        PrincipalRole.ADMINISTRATOR,
        PrincipalRole.REPLAY_VIEWER,
    ):
        context = ViewerContext(
            principal_id=f"order124:{role.value}",
            role=role,
            viewer_player_id=None,
            policy=ROLE_POLICY_BY_ROLE[role],
        )
        assert loaded.view_for_context(viewer=context) == session.view_for_context(viewer=context)
        assert loaded.events_since_for_context(
            EventStreamCursor(), viewer=context
        ) == session.events_since_for_context(EventStreamCursor(), viewer=context)
    replay = ReplayRunner.from_payload(session.replay_artifact(artifact_id="order124")).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay
    return loaded, fork


@pytest.mark.parametrize("attached", [False, True])
@pytest.mark.parametrize("use_reroll", [False, True])
def test_real_nested_upgrade_survives_pending_and_completed_continuations(
    attached: bool, use_reroll: bool
) -> None:
    session = nested_session(attached=attached)
    state = session.lifecycle.state
    assert state is not None
    records = state.objective_control_records
    assert records[-1].phase == "movement"
    assert records[-1].results[0].controlled_by_player_id == "player-b"
    _assert_roundtrips(session)
    request = declare_nested_shot(session)
    assert request.decision_type == "select_dice_reroll"
    assert cast(dict[str, object], request.payload)["current_values"] == [4]
    source = _source_context(request)
    assert source is not None
    assert source["source_rule_id"] == SOURCE_ID
    assert source["nested_conditions"] == {
        "closest_eligible_target_unit_instance_id": TARGET,
        "opponent_controlled_objective_ids": [OBJECTIVE],
        "improved_reroll_applies": True,
    }
    assert "conditional_hit_reroll" not in source
    loaded, fork = _assert_roundtrips(session)
    requests = finish_nested_shot(session, use_reroll=use_reroll)
    assert any(_source_context(row) is not None for row in requests)
    for continuation in (loaded, fork):
        finish_nested_shot(continuation, use_reroll=use_reroll)
        assert continuation.lifecycle.to_payload() == session.lifecycle.to_payload()
        _assert_roundtrips(continuation)
    _assert_roundtrips(session)
    # The native attack path creates one original hit roll per attack and only
    # the accepted source choices create rerolls; permission discovery draws none.
    events = session.lifecycle.decision_controller.event_log.records
    hits = [
        event
        for event in events
        if event.event_type == "dice_rolled"
        and isinstance(event.payload, dict)
        and isinstance(event.payload.get("spec"), dict)
        and cast(dict[str, JsonValue], event.payload["spec"]).get("roll_type")
        == "attack_sequence.hit"
    ]
    assert len(hits) == 6


@pytest.mark.parametrize(
    "mutation", ["no_parent", "no_upgrade", "false_upgrade", "melee", "extra_parent"]
)
def test_incomplete_structured_nested_sources_gain_no_runtime_hook(mutation: str) -> None:
    rule = nested_source().rule_ir
    clause = rule.clauses[0]
    parameters = parameter_payload(clause.effects[0].parameters)
    if mutation == "no_parent":
        clause = replace(clause, conditions=())
    elif mutation == "extra_parent":
        clause = replace(clause, conditions=(*clause.conditions, *clause.conditions))
    else:
        if mutation == "no_upgrade":
            del parameters["full_reroll_if_target_within_opponent_controlled_objective_range"]
        elif mutation == "false_upgrade":
            parameters["full_reroll_if_target_within_opponent_controlled_objective_range"] = False
        else:
            parameters["attack_kind"] = "melee"
        clause = replace(
            clause,
            effects=(
                replace(
                    clause.effects[0], parameters=parameters_from_pairs(tuple(parameters.items()))
                ),
            ),
        )
    assert not nested_attack_reroll_clause_is_supported(clause)
    assert not catalog_rule_ir_hook_ids_for_rule(replace(rule, clauses=(clause,)))


def _runtime_context(
    session: LocalGameSession,
) -> tuple[CatalogDatasheetRuleRuntime, AttackRerollPermissionContext]:
    state = session.lifecycle.state
    assert state is not None
    catalog = session.lifecycle.config.army_catalog
    records = catalog_ability_records_from_catalog(catalog)
    runtime = CatalogDatasheetRuleRuntime(
        {player: AbilityCatalogIndex.from_records(records) for player in state.player_ids},
        tuple(state.army_definitions),
    )
    attacker = state.army_definitions[0].unit_by_id("army-alpha:shooter")
    weapon = next(
        item for item in catalog.wargear if item.wargear_id == "core-bolt-rifle"
    ).weapon_profiles[0]
    return runtime, AttackRerollPermissionContext(
        state=state,
        player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        target_unit_instance_id=TARGET,
        source_phase=BattlePhase.SHOOTING,
        roll_type="attack_sequence.hit",
        timing_window="attack_sequence.hit",
        weapon_profile=weapon,
        shooting_type=ShootingType.NORMAL,
    )


@pytest.mark.parametrize("control", ["friendly", "tied", "uncontrolled"])
def test_real_boundary_control_negatives_keep_only_the_basic_permission(control: str) -> None:
    session = nested_session(control=control)
    runtime, context = _runtime_context(session)
    state = context.state
    ownership = state.objective_control_records[-1].results[0].controlled_by_player_id
    assert ownership == ("player-a" if control == "friendly" else None)
    before = session.lifecycle.to_payload()
    permissions = tuple(
        value
        for binding in runtime.attack_reroll_permission_bindings(
            army_catalog=session.lifecycle.config.army_catalog
        )
        if (value := binding.handler(context)) is not None
    )
    assert len(permissions) == 1
    assert permissions[0].source_payload["conditional_hit_reroll"] == {
        "reroll_unmodified_values": [1]
    }
    assert session.lifecycle.to_payload() == before
    _assert_roundtrips(session)


@pytest.mark.parametrize("mutation", ["phase", "player", "roll", "window", "model", "target"])
def test_unrelated_attack_contexts_cannot_gain_the_nested_source(mutation: str) -> None:
    session = nested_session()
    runtime, context = _runtime_context(session)
    changed = {
        "phase": replace(context, source_phase=BattlePhase.FIGHT),
        "player": replace(context, player_id="player-b"),
        "roll": replace(context, roll_type="attack_sequence.wound"),
        "window": replace(context, timing_window="attack_sequence.wound"),
        "model": replace(context, attacker_model_instance_id=None),
        "target": replace(context, target_unit_instance_id="army-alpha:shooter"),
    }[mutation]
    before = session.lifecycle.to_payload()
    assert not any(
        binding.handler(changed)
        for binding in runtime.attack_reroll_permission_bindings(
            army_catalog=session.lifecycle.config.army_catalog
        )
    )
    assert session.lifecycle.to_payload() == before


@pytest.mark.parametrize("missing", ["weapon", "type"])
def test_nested_source_requires_complete_actual_attack_context(missing: str) -> None:
    session = nested_session()
    runtime, context = _runtime_context(session)
    changed = (
        replace(context, weapon_profile=None)
        if missing == "weapon"
        else replace(context, shooting_type=None)
    )
    binding = next(
        row
        for row in runtime.attack_reroll_permission_bindings(
            army_catalog=session.lifecycle.config.army_catalog
        )
        if row.handler(context) is not None
    )
    before = session.lifecycle.to_payload()
    with pytest.raises(GameLifecycleError, match="actual weapon and shooting type"):
        binding.handler(changed)
    assert session.lifecycle.to_payload() == before


@pytest.mark.parametrize("case", ["equally_closest", "nearer_ineligible"])
def test_shared_target_legality_and_closest_ties_preserve_eligible_targets(case: str) -> None:
    session = (
        nested_session(tied_closest=True)
        if case == "equally_closest"
        else nested_session(control="tied", nearest_target_ineligible=True)
    )
    runtime, context = _runtime_context(session)
    before = session.lifecycle.to_payload()
    for target_id in (
        (TARGET, "army-beta:other") if case == "equally_closest" else ("army-beta:other",)
    ):
        permissions = tuple(
            value
            for binding in runtime.attack_reroll_permission_bindings(
                army_catalog=session.lifecycle.config.army_catalog
            )
            if (value := binding.handler(replace(context, target_unit_instance_id=target_id)))
            is not None
        )
        assert len(permissions) == 1
        nested = cast(dict[str, JsonValue], permissions[0].source_payload["nested_conditions"])
        assert nested["closest_eligible_target_unit_instance_id"] == target_id
    if case == "nearer_ineligible":
        assert not any(
            binding.handler(context)
            for binding in runtime.attack_reroll_permission_bindings(
                army_catalog=session.lifecycle.config.army_catalog
            )
        )
    assert session.lifecycle.to_payload() == before
    _assert_roundtrips(session)


@pytest.mark.parametrize(
    ("improved", "closest", "source_present", "expected"),
    [(False, True, True, "basic"), (True, False, True, "none"), (True, True, False, "none")],
)
def test_real_weaker_branch_and_outer_source_negatives(
    improved: bool, closest: bool, source_present: bool, expected: str
) -> None:
    session = nested_session(
        improved=improved, closest=closest, source_present=source_present, attack_count=12
    )
    declare_nested_shot(session)
    loaded, fork = _assert_roundtrips(session)
    requests = finish_nested_shot(session, use_reroll=False)
    source_requests = tuple(row for row in requests if _source_context(row) is not None)
    if expected == "basic":
        assert source_requests
        for row in source_requests:
            assert cast(dict[str, object], row.payload)["current_values"] == [1]
            source = _source_context(row)
            assert source is not None
            assert source["conditional_hit_reroll"] == {"reroll_unmodified_values": [1]}
            assert source["nested_conditions"] == {
                "closest_eligible_target_unit_instance_id": TARGET,
                "opponent_controlled_objective_ids": [],
                "improved_reroll_applies": False,
            }
    else:
        assert not source_requests
    for continuation in (loaded, fork):
        finish_nested_shot(continuation, use_reroll=False)
        assert continuation.lifecycle.to_payload() == session.lifecycle.to_payload()
    _assert_roundtrips(session)


@pytest.mark.parametrize("attached", [False, True])
@pytest.mark.parametrize("use_reroll", [False, True])
def test_real_advanced_assault_preserves_nested_permission_and_continuations(
    attached: bool,
    use_reroll: bool,
) -> None:
    session = nested_session(advanced=True, attached=attached)
    state = session.lifecycle.state
    assert state is not None
    assert len(state.advanced_unit_states) == 1
    assert state.objective_control_records[-1].results[0].controlled_by_player_id == "player-b"
    _assert_roundtrips(session)
    request = declare_nested_shot(session, shooting_type="assault")
    assert request.decision_type == "select_dice_reroll"
    source = _source_context(request)
    assert source is not None
    assert source["nested_conditions"] == {
        "closest_eligible_target_unit_instance_id": TARGET,
        "opponent_controlled_objective_ids": [OBJECTIVE],
        "improved_reroll_applies": True,
    }
    assert "conditional_hit_reroll" not in source
    loaded, fork = _assert_roundtrips(session)
    requests = finish_nested_shot(session, use_reroll=use_reroll)
    assert any(_source_context(row) is not None for row in requests)
    for continuation in (loaded, fork):
        finish_nested_shot(continuation, use_reroll=use_reroll)
        assert continuation.lifecycle.to_payload() == session.lifecycle.to_payload()
        _assert_roundtrips(continuation)
    _assert_roundtrips(session)
    hits = [
        event
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type == "dice_rolled"
        and isinstance(event.payload, dict)
        and isinstance(event.payload.get("spec"), dict)
        and cast(dict[str, JsonValue], event.payload["spec"]).get("roll_type")
        == "attack_sequence.hit"
    ]
    assert len(hits) == 6
