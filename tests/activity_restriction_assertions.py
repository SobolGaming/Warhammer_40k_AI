"""Shared checkpoint-corruption assertions for completed shooting consumers."""

from __future__ import annotations

import json

import pytest

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.mission_action_eligibility import (
    MISSION_ACTION_UNIT_ALREADY_SHOT,
    mission_action_unit_ineligibility_reason,
)
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

    for attack_phase in ("fight", "movement"):
        for model_mutation in ("unchanged", "empty", "foreign"):
            for remove_effect in (True, False):
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
                # The original declaration, activation and ordinary shot state remain.
                assert forged["decisions"]["records"] == original["decisions"]["records"]
                assert (
                    forged["state"]["ranged_attack_history_records"]
                    == original_state["ranged_attack_history_records"]
                )
                assert (
                    forged["state"]["shooting_phase_state"]
                    == original_state["shooting_phase_state"]
                )
                with pytest.raises(GameLifecycleError, match="Model attack history"):
                    GameLifecycle.from_payload(forged)
    assert session.lifecycle.to_payload() == original
