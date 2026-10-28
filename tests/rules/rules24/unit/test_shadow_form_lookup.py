# pyright: reportPrivateUsage=false
"""Canonical record filtering at the public Shadow Form selection boundary."""

from __future__ import annotations

from dataclasses import replace

import pytest

from tests.shared.category_migration.tracked_targets import (
    BELAKOR_SHADOW_FORM_SOURCE_ID,
    BELAKOR_WREATHED_IN_SHADOWS_SOURCE_ID,
    CATALOG_SHADOW_FORM_SELECTED_EVENT,
    CATALOG_SHADOW_FORM_SELECTION_EFFECT_KIND,
    CATALOG_SHADOW_FORM_SUBMISSION_KIND,
    _battle_state_with_scenario,
    _belakor_shadow_form_records,
)
from warhammer40k_core.engine.abilities import CORE_LEADER_HANDLER_ID, AbilityCatalogIndex
from warhammer40k_core.engine.ability_catalog import eleventh_edition_core_ability_catalog_records
from warhammer40k_core.engine.battle_round_hooks import (
    BattleRoundStartRequestContext,
    BattleRoundStartResultContext,
)
from warhammer40k_core.engine.catalog_shadow_form_runtime import CatalogShadowFormRuntime
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.phase import GameLifecycleError


@pytest.mark.parametrize(
    "record_kind", ["canonical_non_generic", "disabled_generic", "malformed_active_generic"]
)
def test_shadow_form_lookup_filters_inactive_and_non_generic_records(record_kind: str) -> None:
    # Constructed canonical state; this is public runtime selection, not full pregame play.
    state = _battle_state_with_scenario(
        alpha_datasheet_id="core-character-leader",
        alpha_model_profile_id="core-character-leader",
        alpha_model_count=1,
    )
    records = _belakor_shadow_form_records()
    if record_kind == "canonical_non_generic":
        extra = next(
            record
            for record in eleventh_edition_core_ability_catalog_records()
            if record.definition.handler_id == CORE_LEADER_HANDLER_ID
        )
        assert extra.definition.replay_payload is None
    else:
        extra = replace(
            records[1],
            record_id="record:shadow-form-filter-control",
            disabled=record_kind == "disabled_generic",
            definition=replace(records[1].definition, replay_payload=None),
        )
    runtime = CatalogShadowFormRuntime(
        ability_indexes_by_player_id={
            "player-a": AbilityCatalogIndex.from_records((*records, extra)),
            "player-b": AbilityCatalogIndex.from_records(()),
        },
        armies=tuple(state.army_definitions),
    )
    decisions = DecisionController()
    if record_kind == "malformed_active_generic":
        before_state = state.to_payload()
        before_decisions = decisions.to_payload()
        with pytest.raises(GameLifecycleError):
            runtime.battle_round_start_request(
                BattleRoundStartRequestContext(state=state, decisions=decisions)
            )
        assert state.to_payload() == before_state
        assert decisions.to_payload() == before_decisions
        return

    bindings = runtime.battle_round_start_bindings()
    request = runtime.battle_round_start_request(
        BattleRoundStartRequestContext(state=state, decisions=decisions)
    )
    assert len(bindings) == 1
    assert request is not None
    assert request.actor_id == "player-a"
    assert isinstance(request.payload, dict)
    assert request.payload["submission_kind"] == CATALOG_SHADOW_FORM_SUBMISSION_KIND
    assert request.payload["source_rule_id"] == BELAKOR_SHADOW_FORM_SOURCE_ID
    selected_option = next(
        option
        for option in request.options
        if isinstance(option.payload, dict)
        and option.payload["selected_shadow_form_source_id"]
        == BELAKOR_WREATHED_IN_SHADOWS_SOURCE_ID
    )
    result = DecisionResult.for_request(
        result_id="result:shadow-form",
        request=request,
        selected_option_id=selected_option.option_id,
    )
    applied = runtime.apply_battle_round_start_result(
        BattleRoundStartResultContext(
            state=state, decisions=decisions, request=request, result=result
        )
    )
    assert applied
    selection_effects = [
        effect
        for effect in state.persisting_effects_for_unit(
            state.army_definitions[0].units[0].unit_instance_id
        )
        if isinstance(effect.effect_payload, dict)
        and effect.effect_payload.get("effect_kind") == CATALOG_SHADOW_FORM_SELECTION_EFFECT_KIND
    ]
    assert len(selection_effects) == 1
    assert any(
        event.event_type == CATALOG_SHADOW_FORM_SELECTED_EVENT
        for event in decisions.event_log.records
    )
    assert (
        runtime.battle_round_start_request(
            BattleRoundStartRequestContext(state=state, decisions=decisions)
        )
        is None
    )
