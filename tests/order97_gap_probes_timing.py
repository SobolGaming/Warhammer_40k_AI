"""Reproduce the missing unqualified Command-body consumer without certifying it."""

from __future__ import annotations

import json
from typing import cast

from tests.support.ability_presence_fixtures import ability_presence_fixture, compiled_ability_rule
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.catalog_rule_consumption import catalog_rule_ir_consumers_for_rule
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.reaction_queue import ReactionQueue


def command_body_observation() -> dict[str, object]:
    observations: list[dict[str, object]] = []
    for timing in ("In your Command phase", "At the start of your Command phase"):
        text = f"{timing}, roll one D6: on a 1+, you gain 1CP."
        rule = compiled_ability_rule(text)
        assert not rule.diagnostics
        assert all(clause.is_supported for clause in rule.clauses)
        config, state, decisions = ability_presence_fixture(embarked=False, ability_text=text)
        session = LocalGameSession(
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
        status = session.advance_until_decision_or_terminal()
        assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
        current = session.lifecycle.state
        assert current is not None
        assert current.current_battle_phase is BattlePhase.MOVEMENT
        events = session.lifecycle.decision_controller.event_log.records
        observations.append(
            {
                "source_text": text,
                "source_id": rule.source_id,
                "compiled_supported": True,
                "runtime_consumers": list(catalog_rule_ir_consumers_for_rule(rule)),
                "effect_events": sum(
                    event.event_type == "catalog_ir_command_point_phase_gain_resolved"
                    for event in events
                ),
                "next_phase": current.current_battle_phase.value,
            }
        )
    assert observations[0]["effect_events"] == 0
    assert observations[1]["effect_events"] == 1
    return {
        "requirement_id": "08.04-ability-window",
        "observations": observations,
        "expected": "The unqualified supported clause executes in the Command-abilities step.",
        "qualification": (
            "A canonical source-linked RuleIR fixture isolates the timing difference. "
            "The unqualified clause compiles but has no runtime consumer and the facade "
            "advances to Movement without executing it; the explicit start control executes. "
            "This is a consumer-registration/Command-body gap, not a named faction support claim."
        ),
    }


if __name__ == "__main__":
    print(json.dumps(command_body_observation(), ensure_ascii=False, indent=2))
