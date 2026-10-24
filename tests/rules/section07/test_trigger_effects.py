"""Source-compiled trigger qualification reaches actual nonempty effect consumers."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section07_contracts import SOURCE, selected_effect_runtime
from tests.support.section07_fixtures import boundary_state
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionError, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.fight_phase_start_hooks import (
    FightPhaseStartHookRegistry,
    FightPhaseStartRequestContext,
    FightPhaseStartResultContext,
)
from warhammer40k_core.engine.phase import BattlePhase


def test_unqualified_phase_trigger_applies_real_effect_at_each_boundary(
    section07_definitions: Section02Definitions,
) -> None:
    state = boundary_state(section07_definitions, phase=BattlePhase.FIGHT)
    runtime = selected_effect_runtime(section07_definitions, state, "the ")
    registry = FightPhaseStartHookRegistry.from_bindings(runtime.fight_phase_start_bindings())
    decisions = DecisionController()
    observed: list[str] = []
    # Explicit boundary checkpoints isolate recurrence from unrelated phases.
    for battle_round in (1, 2):
        for active in state.turn_order:
            state.battle_round = battle_round
            state.active_player_id = active
            context = FightPhaseStartRequestContext(
                state,
                decisions,
                state.runtime_ruleset_descriptor(),
                section07_definitions.package.army_catalog,
            )
            request = registry.next_request_for(context)
            assert isinstance(request, DecisionRequest)
            assert request.actor_id == "owner"
            assert not state.persisting_effects or all(
                effect.source_rule_id == SOURCE for effect in state.persisting_effects
            )
            decisions.request_decision(request)
            result = DecisionResult.for_request(
                result_id=f"effect-{battle_round}-{active}",
                request=request,
                selected_option_id=request.options[0].option_id,
            )
            before = decisions.to_payload(), state.to_payload()
            with pytest.raises(DecisionError, match="actor"):
                decisions.submit_result(replace(result, actor_id="opponent"))
            assert (decisions.to_payload(), state.to_payload()) == before
            decisions.submit_result(result)
            effect_ids = {effect.effect_id for effect in state.persisting_effects}
            assert (
                registry.apply_result(
                    FightPhaseStartResultContext(
                        state,
                        decisions,
                        request,
                        result,
                        ability_indexes_by_player_id=runtime.ability_indexes_by_player_id,
                    )
                )
                is True
            )
            (effect,) = tuple(
                effect for effect in state.persisting_effects if effect.effect_id not in effect_ids
            )
            assert effect.source_rule_id == SOURCE
            assert effect.expiration.player_id == active
            assert effect.expiration.phase is BattlePhase.FIGHT
            assert effect.effect_payload is not None
            observed.append(active)
            assert registry.next_request_for(context) is None
    assert observed == ["owner", "opponent", "owner", "opponent"]
    assert len(state.persisting_effects) == 4
    assert len({effect.effect_id for effect in state.persisting_effects}) == 4
