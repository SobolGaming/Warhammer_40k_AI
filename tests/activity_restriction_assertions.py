"""Shared checkpoint-corruption assertions for completed shooting consumers."""

from __future__ import annotations

import json
from itertools import product

import pytest

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.mission_action_eligibility import (
    MISSION_ACTION_UNIT_ALREADY_SHOT,
    mission_action_unit_ineligibility_reason,
)
from warhammer40k_core.engine.model_attack_history import validate_model_attack_history
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


def assert_completed_shooting_kind_is_authenticated(
    session: LocalGameSession, *, player_id: str, unit_instance_id: str
) -> None:
    original = session.lifecycle.to_payload()
    original_state = original["state"]
    assert original_state is not None
    restored = GameLifecycle.from_payload(json.loads(json.dumps(original)))
    assert restored.to_payload() == original
    for lifecycle in (session.lifecycle, restored):
        state = lifecycle.state
        assert state is not None
        assert (
            mission_action_unit_ineligibility_reason(
                state=state,
                player_id=player_id,
                unit_instance_id=unit_instance_id,
                runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            )
            == MISSION_ACTION_UNIT_ALREADY_SHOT
        )

    for (attack_phase, rename_sequence), model_mutation, remove_effect in product(
        (
            ("fight", True),
            ("movement", True),
            ("shooting", True),
            ("fight", False),
            ("movement", False),
        ),
        ("unchanged", "empty", "foreign"),
        (True, False),
    ):
        forged = json.loads(json.dumps(original))
        participation = next(
            event["payload"]
            for event in forged["decisions"]["event_log"]
            if event["event_type"] == "attack_sequence_models_attacked"
            and event["payload"]["attacking_unit_instance_id"] == unit_instance_id
            and event["payload"]["attack_phase"] == "shooting"
        )
        participation["attack_phase"] = attack_phase
        if model_mutation != "unchanged":
            participation["model_instance_ids"] = (
                [] if model_mutation == "empty" else ["foreign-model"]
            )
        if remove_effect:
            effects = forged["state"]["persisting_effects"]
            effect = next(
                effect
                for effect in effects
                if effect["effect_payload"].get("activity") == "completed_shooting"
                and effect["effect_payload"]["activity_id"] == participation["sequence_id"]
            )
            effects.remove(effect)
        if rename_sequence:
            sequence_id = participation["sequence_id"]
            for event in forged["decisions"]["event_log"]:
                if (
                    event["event_type"]
                    in {
                        "attack_sequence_models_attacked",
                        "attack_sequence_completed",
                        "attack_sequence_attacks_resolved",
                    }
                    and event["payload"]["sequence_id"] == sequence_id
                ):
                    event["payload"]["sequence_id"] = "attack-sequence:renamed-unrelated"
        # The original declaration, activation and ordinary shot state remain.
        assert [
            event
            for event in forged["decisions"]["event_log"]
            if event["event_type"].endswith("declaration_accepted")
        ] == [
            event
            for event in original["decisions"]["event_log"]
            if event["event_type"].endswith("declaration_accepted")
        ]
        assert forged["decisions"]["records"] == original["decisions"]["records"]
        assert (
            forged["state"]["ranged_attack_history_records"]
            == original_state["ranged_attack_history_records"]
        )
        assert forged["state"]["shooting_phase_state"] == original_state["shooting_phase_state"]
        with pytest.raises(GameLifecycleError, match="Model attack history"):
            GameLifecycle.from_payload(forged)
    assert session.lifecycle.to_payload() == original


def assert_completed_melee_is_authenticated(session: LocalGameSession) -> None:
    """A non-shooting classification needs its own genuine accepted origin."""
    original = session.lifecycle.to_payload()
    events = session.lifecycle.decision_controller.event_log.records
    completion = next(event for event in events if event.event_type == "attack_sequence_completed")
    with pytest.raises(GameLifecycleError, match="completion lacks its declaration"):
        validate_model_attack_history(event_records=(completion,))
    with pytest.raises(GameLifecycleError, match="duplicate completions"):
        validate_model_attack_history(event_records=(*events, completion))

    for mutation in ("sequence", "request", "models", "active_player", "game", "round", "phase"):
        forged = json.loads(json.dumps(original))
        declaration = next(
            event["payload"]
            for event in forged["decisions"]["event_log"]
            if event["event_type"] == "melee_declaration_accepted"
        )
        sequence_id = declaration["attack_sequence_id"]
        participation = next(
            event["payload"]
            for event in forged["decisions"]["event_log"]
            if event["event_type"] == "attack_sequence_models_attacked"
            and event["payload"]["sequence_id"] == sequence_id
        )
        if mutation == "sequence":
            declaration["attack_sequence_id"] = "melee-sequence:renamed"
            for event in forged["decisions"]["event_log"]:
                if (
                    event["event_type"]
                    in {
                        "attack_sequence_models_attacked",
                        "attack_sequence_completed",
                        "attack_sequence_attacks_resolved",
                    }
                    and event["payload"]["sequence_id"] == sequence_id
                ):
                    event["payload"]["sequence_id"] = "melee-sequence:renamed"
        elif mutation == "request":
            declaration["request_id"] = "missing-request"
        elif mutation == "models":
            for entry in declaration["proposal"]["declarations"]:
                entry["attacker_model_instance_id"] = "foreign-model"
            participation["model_instance_ids"] = ["foreign-model"]
        elif mutation == "active_player":
            declaration["proposal_request"]["active_player_id"] = "foreign-player"
            participation["active_player_id"] = "foreign-player"
        elif mutation == "phase":
            declaration["phase"] = "shooting"
        else:
            field = "game_id" if mutation == "game" else "battle_round"
            declaration[field] = "foreign-game" if mutation == "game" else 99
            participation[field] = declaration[field]
        assert forged["decisions"]["records"] == original["decisions"]["records"]
        with pytest.raises(GameLifecycleError, match=r"Model attack history|Mutation decision"):
            GameLifecycle.from_payload(forged)
    assert session.lifecycle.to_payload() == original
