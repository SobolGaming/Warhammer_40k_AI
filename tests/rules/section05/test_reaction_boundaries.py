"""Observe real physical removal at the reaction boundary without changing outcomes."""

from dataclasses import replace
from typing import cast

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section05_fixtures import replace_unit
from tests.support.section05_retention import retain, terminal_retention
from tests.support.section05_sequence import fixed_sequence_dice, native_sequence, payloads, resolve
from warhammer40k_core.engine.damage_allocation import DestructionReactionSource
from warhammer40k_core.engine.destruction_reaction_kind import DestructionReactionKind
from warhammer40k_core.engine.event_log import EventLog, EventRecord, JsonValue
from warhammer40k_core.engine.retained_destruction_cleanup import (
    begin_retained_destruction_cleanup,
)


def test_attack_reactions_wait_for_all_attacks(
    section05_definitions: Section02Definitions,
) -> None:
    _state, _target, decisions, request = terminal_retention(section05_definitions, demise=True)
    assert len(payloads(decisions, "attack_sequence_attacks_resolved")) == 1
    assert not payloads(decisions, "destruction_reaction_resolved")
    assert not payloads(decisions, "model_destroyed")
    events = decisions.event_log.records
    finished = next(
        i for i, e in enumerate(events) if e.event_type == "attack_sequence_attacks_resolved"
    )
    offered = next(
        i
        for i, e in enumerate(events)
        if e.event_type == "decision_requested"
        and cast(dict[str, JsonValue], e.payload)["request_id"] == request.request_id
    )
    assert finished < offered


def test_faq20_deadly_demise_resolves_after_retained_model_removed(
    section05_definitions: Section02Definitions, monkeypatch: pytest.MonkeyPatch
) -> None:
    state, target, decisions, request = terminal_retention(section05_definitions, demise=True)
    retain(state, decisions, request)
    mid = target.own_model_ids()[0]
    observations: list[bool] = []
    original = EventLog.append

    def observe(log: EventLog, event_type: str, payload: object) -> EventRecord:
        if log is decisions.event_log and event_type == "destruction_reaction_resolved":
            assert state.battlefield_state is not None
            observations.append(mid in state.battlefield_state.removed_model_ids)
        return original(log, event_type, payload)

    monkeypatch.setattr(EventLog, "append", observe)
    assert (
        begin_retained_destruction_cleanup(state=state, decisions=decisions, reason="phase_end")
        is None
    )
    assert observations == [True]


def test_ordinary_destroyed_trigger_resolves_before_removal(
    section05_definitions: Section02Definitions, monkeypatch: pytest.MonkeyPatch
) -> None:
    state, target, sequence = native_sequence(section05_definitions)
    target = replace(target, own_models=(replace(target.own_models[0], wounds_remaining=1),))
    replace_unit(state, target)
    mid = target.own_model_ids()[0]
    state.record_model_destruction_reaction_sources(
        model_instance_id=mid,
        sources=(
            DestructionReactionSource(
                source_id="constructed:s05:ordinary-demise",
                source_rule_id="constructed:s05:ordinary-demise",
                reaction_kind=DestructionReactionKind.DEADLY_DEMISE,
                optional=False,
                payload={
                    "trigger_roll_threshold": 6,
                    "range_inches": 6.0,
                    "mortal_wounds": {"kind": "fixed", "value": 1},
                },
            ),
        ),
    )
    observed: list[bool] = []
    original = EventLog.append

    def observe(log: EventLog, event_type: str, payload: object) -> EventRecord:
        if event_type == "destruction_reaction_resolved":
            assert state.battlefield_state is not None
            observed.append(mid in state.battlefield_state.removed_model_ids)
        return original(log, event_type, payload)

    monkeypatch.setattr(EventLog, "append", observe)
    decisions, remaining, status = resolve(
        state, sequence, fixed_sequence_dice(sequence, target, (6,), (6,), (1,))
    )
    assert remaining is None
    assert status is None
    assert observed == [False]
    assert state.battlefield_state is not None
    assert mid in state.battlefield_state.removed_model_ids
    assert len(payloads(decisions, "model_destroyed")) == 1
