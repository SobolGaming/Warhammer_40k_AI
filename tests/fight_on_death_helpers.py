"""Canonical retained-death fixtures for focused presence consumers.

Fixture construction establishes a dead model, its saved placement and a real
rule-source decision. Retention itself uses the same cause and finite-selection
owners as lifecycle play. Integration coverage drives lethal damage through the
session facade in test_fight_on_death_presence.py.
"""

from __future__ import annotations

from dataclasses import replace

from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.engine.battlefield_state import ModelPlacement, PlacedArmy, UnitPlacement
from warhammer40k_core.engine.damage_allocation import (
    DestructionReactionKind,
    DestructionReactionSource,
    model_by_id,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.model_destruction_cause_producers import (
    reserve_rule_effect_model_destruction_cause,
)
from warhammer40k_core.engine.retained_destruction_rule import offer_rule_fight_on_death
from warhammer40k_core.engine.retained_destruction_selection import apply_retention_selection
from warhammer40k_core.engine.rule_deadly_demise_continuation import (
    RULE_MODEL_DESTRUCTION_CONTEXT_KIND,
    RULE_MODEL_DESTRUCTION_SOURCE_COMPLETION_KIND,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id


def retain_destroyed_model_for_fixture(
    *,
    state: GameState,
    placement: ModelPlacement,
    effect_id: str,
    source_rule_id: str,
    source_phase: BattlePhaseKind,
    decisions: DecisionController,
) -> None:
    assert not model_by_id(state=state, model_instance_id=placement.model_instance_id).is_alive
    assert state.current_battle_phase is source_phase
    assert state.active_player_id is not None
    _place_retained_fixture_model(state=state, placement=placement)
    controller = decisions
    suspended = controller.queue.pending_requests
    for request in suspended:
        controller.queue.remove_by_id(request.request_id)
    source_request = controller.request_decision(
        DecisionRequest(
            request_id=f"{effect_id}:source-request",
            decision_type="fixture_rule_destruction_source",
            actor_id=placement.player_id,
            payload={
                "model_instance_id": placement.model_instance_id,
                "source_rule_id": source_rule_id,
            },
            options=(DecisionOption(option_id="resolve", label="Resolve fixture rule"),),
        )
    )
    source = controller.submit_result(
        DecisionResult.for_request(
            request=source_request,
            result_id=f"{effect_id}:source-result",
            selected_option_id="resolve",
        )
    )
    unit_id = rules_unit_view_by_id(
        state=state, unit_instance_id=placement.unit_instance_id
    ).unit_instance_id
    liability_id = f"{effect_id}:source-liability"
    state.record_persisting_effect(
        PersistingEffect(
            effect_id=liability_id,
            source_rule_id=source_rule_id,
            owner_player_id=placement.player_id,
            target_unit_instance_ids=(unit_id,),
            started_battle_round=state.battle_round,
            started_phase=source_phase,
            expiration=EffectExpiration.end_of_battle(),
            effect_payload={"effect_kind": "fixture_rule_destruction_source_liability"},
        )
    )
    reaction = DestructionReactionSource(
        source_id=effect_id,
        source_rule_id=source_rule_id,
        reaction_kind=DestructionReactionKind.FIGHT_ON_DEATH,
    )
    state.record_model_destruction_reaction_sources(
        model_instance_id=placement.model_instance_id,
        sources=(
            *state.destruction_reaction_sources_for_model(
                model_instance_id=placement.model_instance_id
            ),
            reaction,
        ),
    )
    context: dict[str, JsonValue] = {
        "context_kind": RULE_MODEL_DESTRUCTION_CONTEXT_KIND,
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "active_player_id": state.active_player_id,
        "phase": source_phase.value,
        "source_step": "fixture-destruction",
        "source_result_id": source.result.result_id,
        "model_instance_id": placement.model_instance_id,
        "target_unit_instance_id": placement.unit_instance_id,
        "rules_unit_instance_id": unit_id,
        "source_rule_id": source_rule_id,
        "source_effect_ids": [liability_id],
        "destroying_player_id": placement.player_id,
        "source_rules_unit_instance_id": None,
        "source_model_instance_id": None,
        "destroyed_model_controller_player_id": placement.player_id,
        "destroyed_model_placement": validate_json_value(placement.to_payload()),
        "damage_application": None,
        "completion_event_type": "fixture_rule_destruction_completed",
        "completion_event_payload": {
            "source_result_id": source.result.result_id,
            "model_instance_id": placement.model_instance_id,
        },
        "completion_kind": RULE_MODEL_DESTRUCTION_SOURCE_COMPLETION_KIND,
        "post_removal_mandatory_sources": [],
    }
    reserve_rule_effect_model_destruction_cause(
        state=state, decisions=controller, root_context=context
    )
    status = offer_rule_fight_on_death(state=state, decisions=controller, root_context=context)
    assert status is not None
    request = controller.queue.peek_next()
    selection = controller.submit_result(
        DecisionResult.for_request(
            request=request,
            result_id=f"{effect_id}:retention-result",
            selected_option_id=effect_id,
        )
    )
    apply_retention_selection(state=state, decisions=controller, result=selection.result)
    for request in suspended:
        controller.queue.append(request)


def _place_retained_fixture_model(*, state: GameState, placement: ModelPlacement) -> None:
    battlefield = state.battlefield_state
    assert battlefield is not None
    current = battlefield.model_placement_or_none(placement.model_instance_id)
    if current is not None:
        assert current == placement
        return
    # Set up the fixture inventory before recording its logical-death history.
    # No engine resurrection or return-to-battlefield service is invoked.
    armies = {army.army_id: army for army in battlefield.placed_armies}
    placed_army = armies.get(placement.army_id)
    units = (
        {}
        if placed_army is None
        else {unit.unit_instance_id: unit for unit in placed_army.unit_placements}
    )
    existing = units.get(placement.unit_instance_id)
    model_placements = (placement,) if existing is None else (*existing.model_placements, placement)
    units[placement.unit_instance_id] = UnitPlacement(
        army_id=placement.army_id,
        player_id=placement.player_id,
        unit_instance_id=placement.unit_instance_id,
        model_placements=tuple(sorted(model_placements, key=lambda model: model.model_instance_id)),
    )
    armies[placement.army_id] = PlacedArmy(
        army_id=placement.army_id,
        player_id=placement.player_id,
        unit_placements=tuple(units[key] for key in sorted(units)),
    )
    state.replace_battlefield_state(
        replace(
            battlefield,
            placed_armies=tuple(armies[key] for key in sorted(armies)),
            removed_model_ids=tuple(
                model_id
                for model_id in battlefield.removed_model_ids
                if model_id != placement.model_instance_id
            ),
        )
    )
