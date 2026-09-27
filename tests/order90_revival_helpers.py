"""Real off-battlefield rules units and recorded casualties for Order 90."""

from __future__ import annotations

from tests.destruction_occurrence_fixture_helpers import destroy_rule_model_for_fixture
from tests.support.ability_presence_fixtures import ability_presence_fixture
from warhammer40k_core.engine.damage_allocation import unit_by_id
from warhammer40k_core.engine.healing import HealingEffect
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id


def offboard_scene(
    *,
    reserves: bool = False,
    full_health: bool = True,
    capacity: int = 10,
    attached: bool = True,
    battle_round: int = 1,
    revive_leader: bool = False,
    cargo_in_reserves: bool = False,
) -> tuple[GameLifecycle, HealingEffect, str]:
    config, state, decisions = ability_presence_fixture(embarked=False, attached=attached)
    target = rules_unit_view_by_id(state=state, unit_instance_id="army-alpha:passengers")
    model_id = (
        unit_by_id(
            state=state,
            unit_instance_id="army-alpha:leader" if revive_leader else "army-alpha:passengers",
        )
        .own_models[0]
        .model_instance_id
    )
    destroy_rule_model_for_fixture(
        state=state,
        decisions=decisions,
        model_id=model_id,
        destroying_player_id="player-b",
        source_unit_id=None,
        source_model_id=None,
    )
    assert state.battlefield_state is not None
    for unit_id in target.component_unit_instance_ids:
        if state.battlefield_state.is_unit_placed(unit_id):
            state.replace_battlefield_state(state.battlefield_state.without_unit_placement(unit_id))
    living_component_ids = tuple(
        unit_id
        for unit_id in target.component_unit_instance_ids
        if any(m.is_alive for m in unit_by_id(state=state, unit_instance_id=unit_id).own_models)
    )
    if reserves:
        from warhammer40k_core.engine.reserve_arrival_requirements import (
            reposition_destruction_policy,
        )
        from warhammer40k_core.engine.reserves import ReserveKind, ReserveState

        reserve = ReserveState.declared_before_battle(
            player_id="player-a",
            unit_instance_id=target.unit_instance_id,
            reserve_kind=ReserveKind.STRATEGIC_RESERVES,
            destruction_deadline_policy=reposition_destruction_policy(
                mission_setup=state.mission_setup, destruction_deadline_policy=None
            ),
        )
        state.record_reserve_state(reserve)
        decisions.event_log.append(
            "reserve_unit_declared",
            {
                "game_id": state.game_id,
                "player_id": "player-a",
                "unit_instance_id": target.unit_instance_id,
                "reserve_state": reserve.to_payload(),
            },
        )
    else:
        from warhammer40k_core.engine.transports import (
            TransportCapacityProfile,
            TransportCargoState,
        )

        state.record_transport_cargo_state(
            TransportCargoState(
                player_id="player-a",
                transport_unit_instance_id="army-alpha:transport",
                embarked_unit_instance_ids=living_component_ids,
                capacity_profile=TransportCapacityProfile(
                    transport_datasheet_id="core-transport",
                    max_model_count=capacity,
                    allowed_keywords=("INFANTRY",),
                ),
            )
        )
    if cargo_in_reserves:
        from warhammer40k_core.engine.reserve_arrival_requirements import (
            reposition_destruction_policy,
        )
        from warhammer40k_core.engine.reserves import ReserveKind, ReserveState

        assert not reserves
        reserve = ReserveState.declared_before_battle(
            player_id="player-a",
            unit_instance_id="army-alpha:transport",
            reserve_kind=ReserveKind.STRATEGIC_RESERVES,
            embarked_unit_instance_ids=living_component_ids,
            destruction_deadline_policy=reposition_destruction_policy(
                mission_setup=state.mission_setup, destruction_deadline_policy=None
            ),
        )
        state.record_reserve_state(reserve)
        state.replace_battlefield_state(
            state.battlefield_state.without_unit_placement("army-alpha:transport")
        )
        decisions.event_log.append(
            "reserve_unit_declared",
            {
                "game_id": state.game_id,
                "player_id": "player-a",
                "unit_instance_id": reserve.unit_instance_id,
                "reserve_state": reserve.to_payload(),
            },
        )
    from tests.destruction_occurrence_fixture_helpers import finish_core_destructions_for_fixture

    finish_core_destructions_for_fixture(state=state, decisions=decisions)
    state.battle_round = battle_round
    lifecycle = GameLifecycle.from_payload(
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": decisions.to_payload(),
            "reaction_queue": ReactionQueue().to_payload(),
        }
    )
    return (
        lifecycle,
        HealingEffect(
            effect_id="order90-return",
            target_unit_instance_id=target.unit_instance_id,
            amount=1,
            opposing_player_id="player-b",
            source_context={"revive_destroyed_models_only": True, "revive_model_full_health": True}
            if full_health
            else None,
        ),
        model_id,
    )


def with_catalog_restoration(lifecycle: GameLifecycle) -> GameLifecycle:
    """Load the existing source-backed Command restoration IR on canonical fixture models."""
    from dataclasses import replace
    from typing import cast

    from tests.phase11c_command_phase_helpers import mustered_armies
    from warhammer40k_core.core.datasheet import (
        CatalogAbilitySourceKind,
        CatalogAbilitySupport,
        CatalogJsonObject,
        DatasheetAbilityDescriptor,
    )
    from warhammer40k_core.engine.game_state import GameConfig
    from warhammer40k_core.rules.rule_ir import RuleIR
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import faction_pack_rule_ir

    payload = lifecycle.to_payload()
    assert payload["config"] is not None
    config = GameConfig.from_payload(payload["config"])
    ir_payload = faction_pack_rule_ir.datasheet_rule_ir_payload_by_source_row_id("000000588:5")
    assert ir_payload is not None
    ir = RuleIR.from_payload(ir_payload)
    descriptor = DatasheetAbilityDescriptor(
        ability_id="order90-restoration",
        name="Order 90 restoration fixture",
        source_id=ir.source_id,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description=ir.normalized_text,
        rule_ir_payload=cast(CatalogJsonObject, ir.to_payload()),
    )
    config = replace(
        config,
        army_catalog=replace(
            config.army_catalog,
            datasheets=tuple(
                replace(sheet, abilities=(*sheet.abilities, descriptor))
                if sheet.datasheet_id == "core-character-leader"
                else replace(
                    sheet,
                    keywords=replace(
                        sheet.keywords, keywords=(*sheet.keywords.keywords, "WRAITH CONSTRUCT")
                    ),
                )
                if sheet.datasheet_id == "core-intercessor-like-infantry"
                else sheet
                for sheet in config.army_catalog.datasheets
            ),
        ),
    )
    state = lifecycle.state
    assert state is not None
    wounds = {
        model.model_instance_id: model.wounds_remaining
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
    }
    state.army_definitions[:] = [
        replace(
            army,
            units=tuple(
                replace(
                    unit,
                    own_models=tuple(
                        replace(model, wounds_remaining=wounds[model.model_instance_id])
                        for model in unit.own_models
                    ),
                )
                for unit in army.units
            ),
        )
        for army in mustered_armies(config)
    ]
    payload["config"] = config.to_payload()
    payload["state"] = state.to_payload()
    return GameLifecycle.from_payload(payload)
