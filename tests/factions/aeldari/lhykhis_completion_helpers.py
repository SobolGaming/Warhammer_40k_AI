"""Explicit shared completion contracts using native executor evidence."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from tests.support.faction_batch01 import Scene
from warhammer40k_core.engine.attack_completion_triggers import attack_context_for_trigger
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rule_trigger_state import rule_trigger_history


def assert_partial_completion_authority(s: Scene) -> None:
    decisions = s.session.lifecycle.decision_controller
    trigger = next(
        t
        for t in rule_trigger_history(decisions).observed
        if isinstance(t.context, dict) and "completed_model_instance_ids" in t.context
    )
    bundle = s.session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    context = attack_context_for_trigger(
        state=s.state,
        decisions=decisions,
        trigger=trigger,
        runtime_modifiers=bundle.runtime_modifier_registry,
    )
    assert context.completed_model_instance_ids == s.units["own:lhykhis"].own_model_ids()
    original = cast(dict[str, JsonValue], trigger.context)
    mutations: list[dict[str, JsonValue]] = [
        {**original, "completed_model_instance_ids": [s.units["own:spiders"].own_model_ids()[0]]},
        {**original, "trigger_event_id": "unrecorded-model-completion"},
        {**original, "source_phase": "fight"},
        {k: v for k, v in original.items() if k != "completed_model_instance_ids"},
    ]
    for payload in mutations:
        with pytest.raises(GameLifecycleError):
            attack_context_for_trigger(
                state=s.state,
                decisions=decisions,
                trigger=replace(trigger, context=payload),
                runtime_modifiers=bundle.runtime_modifier_registry,
            )
