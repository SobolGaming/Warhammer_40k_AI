"""Selected Core Command-abilities timing through the real catalog and facade."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest
from tests.core_clause_evidence_helpers import assert_persistence_viewers_replay
from tests.phase11c_command_phase_helpers import (
    complete_setup_through_gate,
    mustered_armies,
    secondary_choice,
)
from tests.psychic_modifier_helpers import pending_request
from tests.support.ability_presence_fixtures import ability_presence_fixture, compiled_ability_rule

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    CatalogJsonObject,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.engine.catalog_rule_consumption import catalog_rule_ir_consumers_for_rule
from warhammer40k_core.engine.command_abilities import command_abilities_window
from warhammer40k_core.engine.damage_allocation import DamageKind, apply_damage_to_model
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.game_state import GameState, SecondaryMissionMode
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.engine.sequencing import SEQUENCING_DECISION_TYPE
from warhammer40k_core.engine.stratagems import stratagem_decline_payload
from warhammer40k_core.rules.rule_ir import RuleParameter


def _session(
    *texts: str, damaged_bodyguard: bool = False, source_lost: bool = False
) -> LocalGameSession:
    config, _, _ = ability_presence_fixture(embarked=False)
    descriptors: list[DatasheetAbilityDescriptor] = []
    for index, text in enumerate(texts):
        rule = compiled_ability_rule(text, source_id=f"test:order121:source:{index}")
        assert not rule.diagnostics
        assert all(clause.is_supported for clause in rule.clauses)
        descriptors.append(
            DatasheetAbilityDescriptor(
                ability_id=f"order121-ability-{index}",
                name=f"Command timing fixture {index}",
                source_id=rule.source_id,
                support=CatalogAbilitySupport.GENERIC_RULE_IR,
                source_kind=CatalogAbilitySourceKind.DATASHEET,
                effect_description=text,
                rule_ir_payload=cast(CatalogJsonObject, rule.to_payload()),
            )
        )
    config = replace(
        config,
        army_catalog=replace(
            config.army_catalog,
            datasheets=tuple(
                replace(sheet, abilities=(*sheet.abilities, *descriptors))
                if sheet.datasheet_id == "core-character-leader"
                else sheet
                for sheet in config.army_catalog.datasheets
            ),
        ),
    )
    state = GameState.from_config(config)
    from warhammer40k_core.engine.decision_controller import DecisionController

    decisions = DecisionController()
    for army in mustered_armies(config):
        state.record_army_definition(army)
    state.record_battlefield_state(
        create_deterministic_battlefield_scenario(
            battlefield_id="order121-battlefield", armies=tuple(state.army_definitions)
        ).battlefield_state
    )
    for unit in state.army_definitions[0].units:
        if (damaged_bodyguard and unit.unit_instance_id == "army-alpha:passengers") or (
            source_lost and unit.unit_instance_id == "army-alpha:leader"
        ):
            for model in unit.own_models[:3]:
                apply_damage_to_model(
                    state=state,
                    target_unit_instance_id=unit.unit_instance_id,
                    model_instance_id=model.model_instance_id,
                    damage=model.current_wounds,
                    damage_kind=DamageKind.NORMAL,
                )
    for player in state.player_ids:
        state.record_secondary_mission_choice(
            secondary_choice(player_id=player, mode=SecondaryMissionMode.FIXED)
        )
    complete_setup_through_gate(state=state, decisions=decisions, config=config)
    return LocalGameSession(
        GameLifecycle.from_payload(
            cast(
                GameLifecyclePayload,
                {
                    "config": config.to_payload(),
                    "state": state.to_payload(),
                    "decisions": decisions.to_payload(),
                    "reaction_queue": ReactionQueue().to_payload(),
                    "parameterized_movement_proposals": True,
                },
            )
        )
    )


def _events(session: LocalGameSession, kind: str) -> list[EventRecord]:
    return [
        event
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type == kind
    ]


@pytest.mark.parametrize(
    "timing",
    [
        "In your Command phase",
        "At the start of your Command phase",
        "At the end of your Command phase",
    ],
)
def test_command_gain_executes_in_its_distinct_source_window(timing: str) -> None:
    text = f"{timing}, roll one D6: on a 1+, you gain 1CP."
    assert catalog_rule_ir_consumers_for_rule(compiled_ability_rule(text))
    session = _session(text)
    status = session.advance_until_decision_or_terminal()
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    state = session.lifecycle.state
    assert state is not None
    assert state.current_battle_phase is BattlePhase.MOVEMENT
    gains = _events(session, "catalog_ir_command_point_phase_gain_resolved")
    assert len(gains) == 1
    payload = cast(dict[str, JsonValue], gains[0].payload)
    assert payload["source_rule_id"] == "test:order121:source:0"
    assert payload["source_model_instance_id"] == "army-alpha:leader:core-character-leader:001"
    assert payload["player_id"] == "player-a"
    assert payload["passed"] is True
    assert state.command_point_total("player-a") == 2
    assert state.command_point_total("player-b") == 1
    events = list(session.lifecycle.decision_controller.event_log.records)
    gain_index = events.index(gains[0])
    cp_index = next(
        index
        for index, event in enumerate(events)
        if event.event_type == "command_points_gained"
        and isinstance(event.payload, dict)
        and event.payload.get("source_kind") == "command_phase_start"
    )
    shock_index = next(
        index
        for index, event in enumerate(events)
        if event.event_type == "battle_shock_step_completed"
    )
    body_open = next(
        index
        for index, event in enumerate(events)
        if event.event_type == "timing_window_opened"
        and isinstance(event.payload, dict)
        and isinstance(event.payload["timing_window"], dict)
        and isinstance(event.payload["timing_window"]["descriptor"], dict)
        and event.payload["timing_window"]["descriptor"]["source_step"] == "command_abilities"
    )
    assert shock_index < body_open
    if timing == "At the start of your Command phase":
        assert gain_index < cp_index < shock_index
    elif timing == "In your Command phase":
        assert cp_index < shock_index < body_open < gain_index
    else:
        assert cp_index < shock_index < gain_index
    session.advance_until_decision_or_terminal()
    assert len(_events(session, "catalog_ir_command_point_phase_gain_resolved")) == 1
    assert_persistence_viewers_replay(session)


def test_command_abilities_sequence_resumes_then_finishes_before_end_effect() -> None:
    session = _session(
        "In your Command phase, roll one D6: on a 1+, you gain 1CP.",
        "In your Command phase, roll one D6: on a 1+, you gain 1CP.",
        "At the end of your Command phase, roll one D6: on a 1+, you gain 1CP.",
    )
    status = session.advance_until_decision_or_terminal()
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = pending_request(session)
    assert request.decision_type == SEQUENCING_DECISION_TYPE
    state = session.lifecycle.state
    assert state is not None
    assert state.command_step_state is not None
    assert state.command_step_state.battle_shock_step_resolved
    assert state.command_point_total("player-a") == 1
    assert not _events(session, "catalog_ir_command_point_phase_gain_resolved")
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    for request_id, option_id in (
        ("stale", request.options[0].option_id),
        (request.request_id, "unknown"),
    ):
        with pytest.raises((DecisionError, GameLifecycleError)):
            session.submit_option(request_id=request_id, option_id=option_id, result_id="invalid")
        assert session.to_persistence_payload() == checkpoint
    result = DecisionResult.for_request(
        result_id="drift",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    for invalid in (replace(result, actor_id="player-b"), replace(result, payload={})):
        with pytest.raises((DecisionError, GameLifecycleError)):
            session.lifecycle.submit_decision(invalid)
        assert session.to_persistence_payload() == checkpoint
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    forked = restored.fork()
    assert_persistence_viewers_replay(restored)
    for current in (session, restored, forked):
        pending = pending_request(current)
        assert pending is not None
        current.submit_option(
            request_id=pending.request_id,
            option_id=pending.options[-1].option_id,
            result_id="command-order",
        )
        current.advance_until_decision_or_terminal()
        gains = _events(current, "catalog_ir_command_point_phase_gain_resolved")
        assert len(gains) == 3
        assert (
            cast(dict[str, JsonValue], gains[-1].payload)["source_rule_id"]
            == "test:order121:source:2"
        )
        state = current.lifecycle.state
        assert state is not None
        assert state.current_battle_phase is BattlePhase.MOVEMENT
        assert state.command_point_total("player-a") == 2
        assert_persistence_viewers_replay(current)
    assert (
        session.to_persistence_payload()
        == restored.to_persistence_payload()
        == forked.to_persistence_payload()
    )


@pytest.mark.parametrize("phase", ["Movement", "Shooting", "Charge", "Fight"])
def test_other_unqualified_phase_does_not_gain_command_consumer(phase: str) -> None:
    rule = compiled_ability_rule(f"In your {phase} phase, roll one D6: on a 1+, you gain 1CP.")
    assert not catalog_rule_ir_consumers_for_rule(rule)


def test_real_battle_shock_finishes_before_command_ability() -> None:
    session = _session(
        "In your Command phase, roll one D6: on a 1+, you gain 1CP.",
        damaged_bodyguard=True,
    )
    session.advance_until_decision_or_terminal()
    for index in range(10):
        state = session.lifecycle.state
        assert state is not None
        if state.current_battle_phase is BattlePhase.MOVEMENT:
            break
        request = pending_request(session)
        if request.decision_type == "submit_stratagem_target_proposal":
            session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"shock-decline-{index}",
                payload=stratagem_decline_payload(),
            )
        else:
            option = next(option for option in request.options if "decline" in option.option_id)
            session.submit_option(
                request_id=request.request_id,
                option_id=option.option_id,
                result_id=f"shock-decline-{index}",
            )
    completed = _events(session, "battle_shock_step_completed")
    assert len(completed) == 1
    assert cast(dict[str, JsonValue], completed[0].payload)["battle_shock_test_count"] == 1
    gains = _events(session, "catalog_ir_command_point_phase_gain_resolved")
    assert len(gains) == 1
    events = list(session.lifecycle.decision_controller.event_log.records)
    assert events.index(completed[0]) < events.index(gains[0])
    assert_persistence_viewers_replay(session)


@pytest.mark.parametrize("source_lost", [False, True])
def test_failed_roll_or_lost_bearer_cannot_gain_cp(source_lost: bool) -> None:
    threshold = 1 if source_lost else 7
    session = _session(
        f"In your Command phase, roll one D6: on a {threshold}+, you gain 1CP.",
        source_lost=source_lost,
    )
    session.advance_until_decision_or_terminal()
    state = session.lifecycle.state
    assert state is not None
    assert state.current_battle_phase is BattlePhase.MOVEMENT
    assert state.command_point_total("player-a") == 1
    gains = _events(session, "catalog_ir_command_point_phase_gain_resolved")
    assert len(gains) == (0 if source_lost else 1)
    if gains:
        payload = cast(dict[str, JsonValue], gains[0].payload)
        assert payload["passed"] is False
        assert payload["command_point_result"] is None
    assert_persistence_viewers_replay(session)


def test_command_body_repeats_only_on_owners_turn_through_full_phase_cycles() -> None:
    session = _session("In your Command phase, roll one D6: on a 1+, you gain 1CP.")
    for index in range(150):
        status = session.advance_until_decision_or_terminal()
        state = session.lifecycle.state
        assert state is not None
        if state.battle_round == 3:
            break
        request = status.decision_request
        assert request is not None
        if request.decision_type == "submit_stratagem_target_proposal":
            session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"cycle-{index}",
                payload=stratagem_decline_payload(),
            )
        else:
            options = tuple(
                option
                for option in request.options
                if option.option_id.startswith("complete_")
                or option.option_id in {"remain_stationary", "decline"}
            )
            option = options[0] if options else request.options[0]
            session.submit_option(
                request_id=request.request_id,
                option_id=option.option_id,
                result_id=f"cycle-{index}",
            )
        if index == 7:
            session = LocalGameSession.from_persistence_payload(
                json.loads(json.dumps(session.to_persistence_payload()))
            )
    gains = [
        cast(dict[str, JsonValue], event.payload)
        for event in _events(session, "catalog_ir_command_point_phase_gain_resolved")
    ]
    assert [row["battle_round"] for row in gains] == [1, 2, 3]
    assert all(row["player_id"] == "player-a" for row in gains)
    assert_persistence_viewers_replay(session)


def test_command_body_rejects_entry_before_core_steps() -> None:
    session = _session()
    state = session.lifecycle.state
    assert state is not None
    with pytest.raises(GameLifecycleError, match="completed Core CP and Battle-shock"):
        command_abilities_window(state)


@pytest.mark.parametrize("qualified_window", ["gain_core_cp", "battle_shock"])
def test_qualified_command_trigger_does_not_gain_body_consumer(qualified_window: str) -> None:
    rule = compiled_ability_rule("In your Command phase, roll one D6: on a 1+, you gain 1CP.")
    clause = rule.clauses[0]
    assert clause.trigger is not None
    qualified = replace(
        clause,
        trigger=replace(
            clause.trigger,
            parameters=(
                *clause.trigger.parameters,
                RuleParameter("timing_window", qualified_window),
            ),
        ),
    )
    assert not catalog_rule_ir_consumers_for_rule(replace(rule, clauses=(qualified,)))
