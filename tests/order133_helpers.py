"""Catalog-loaded default-unit Core permission fixtures; no injected runtime hooks."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from tests.phase11c_command_phase_helpers import (
    complete_setup_through_gate,
    mustered_armies,
    secondary_choice,
)
from tests.support.ability_presence_fixtures import ability_presence_fixture, compiled_ability_rule
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    CatalogJsonObject,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.game_state import GameState, SecondaryMissionMode
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.geometry.pose import Pose

SOURCE_ID = "core-permission:order133:default-unit-exemplar"


def number_keyword_text(*, noun: str = "", keyword: str = "CHARACTER") -> str:
    return (
        f"At the start of your opponent's Shooting phase, select one friendly {keyword}{noun} "
        'within 6" of this model. Until the end of the phase, add 1 to the Charge '
        "rolls for that unit."
    )


def number_keyword_session(
    *, noun: str = " unit", attached: bool = True, keyword: str = "CHARACTER"
) -> LocalGameSession:
    config, _, _ = ability_presence_fixture(embarked=False, attached=attached)
    text = number_keyword_text(noun=noun, keyword=keyword)
    rule = compiled_ability_rule(text, source_id=SOURCE_ID)
    assert not rule.diagnostics
    descriptor = DatasheetAbilityDescriptor(
        ability_id="order133-default-unit-exemplar",
        name="Core default-unit permission fixture",
        source_id=SOURCE_ID,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description=text,
        rule_ir_payload=cast(CatalogJsonObject, rule.to_payload()),
    )
    config = replace(
        config,
        army_catalog=replace(
            config.army_catalog,
            datasheets=tuple(
                replace(sheet, abilities=(*sheet.abilities, descriptor))
                if sheet.datasheet_id == "core-transport"
                else sheet
                for sheet in config.army_catalog.datasheets
            ),
        ),
    )
    state = GameState.from_config(config)
    decisions = DecisionController()
    for army in mustered_armies(config):
        state.record_army_definition(army)
    battlefield = create_deterministic_battlefield_scenario(
        battlefield_id="order133-battlefield", armies=tuple(state.army_definitions)
    ).battlefield_state
    # A non-CHARACTER bodyguard can supply unit range; the keyword belongs to its Leader.
    for unit_id, origin in (
        ("army-alpha:passengers", Pose.at(16, 10)),
        ("army-alpha:leader", Pose.at(24, 12) if attached else Pose.at(16, 12)),
        ("army-alpha:transport", Pose.at(12, 10)),
    ):
        placement = battlefield.unit_placement_by_id(unit_id)
        anchor = placement.model_placements[0].pose
        battlefield = battlefield.with_unit_placement(
            replace(
                placement,
                model_placements=tuple(
                    replace(
                        row,
                        pose=Pose.at(
                            origin.position.x + row.pose.position.x - anchor.position.x,
                            origin.position.y + row.pose.position.y - anchor.position.y,
                        ),
                    )
                    for row in placement.model_placements
                ),
            )
        )
    state.record_battlefield_state(battlefield)
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


def advance_to_number_keyword_selection(session: LocalGameSession) -> DecisionRequest:
    from tests.order122_helpers import submit_quiet_choice

    for index in range(180):
        status = session.advance_until_decision_or_terminal()
        request = status.decision_request
        assert request is not None
        if isinstance(request.payload, dict) and request.payload.get("source_rule_id") == SOURCE_ID:
            return request
        submit_quiet_choice(session, request, result_id=f"order133-before-{index}")
    raise AssertionError("Catalog-loaded default-unit selection was never offered.")
