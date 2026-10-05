"""Loaded canonical Core permission fixtures for default effect lifetimes."""

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
from warhammer40k_core.engine.stratagems import stratagem_decline_payload

SOURCE_ID = "core-permission:order122:canonical-modifier"
BOOST_TEXT = (
    "Once per battle, at the start of the Fight phase, this model can use this ability. "
    "If it does, add 3 to the Attacks characteristic of melee weapons equipped by this model "
    "and those weapons have the [DEVASTATING WOUNDS] ability, and add 2 to the "
    "Objective Control characteristic of this model."
)


def default_effect_session() -> LocalGameSession:
    config, _, _ = ability_presence_fixture(embarked=False)
    rule = compiled_ability_rule(BOOST_TEXT, source_id=SOURCE_ID)
    assert not rule.diagnostics
    assert len(rule.clauses) == 1
    assert rule.clauses[0].duration is None
    descriptor = DatasheetAbilityDescriptor(
        ability_id="order122-canonical-modifier",
        name="Core default lifetime fixture",
        source_id=SOURCE_ID,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description=BOOST_TEXT,
        rule_ir_payload=cast(CatalogJsonObject, rule.to_payload()),
    )
    anchor_rule = compiled_ability_rule(
        BOOST_TEXT, source_id="core-permission:order122:zz-pending-anchor"
    )
    anchor_descriptor = replace(
        descriptor,
        ability_id="order122-pending-anchor",
        name="Core pending source fixture",
        source_id=anchor_rule.source_id,
        rule_ir_payload=cast(CatalogJsonObject, anchor_rule.to_payload()),
    )
    config = replace(
        config,
        army_catalog=replace(
            config.army_catalog,
            datasheets=tuple(
                replace(sheet, abilities=(*sheet.abilities, descriptor, anchor_descriptor))
                if sheet.datasheet_id == "core-character-leader"
                else sheet
                for sheet in config.army_catalog.datasheets
            ),
        ),
    )
    state = GameState.from_config(config)
    decisions = DecisionController()
    for army in mustered_armies(config):
        state.record_army_definition(army)
    state.record_battlefield_state(
        create_deterministic_battlefield_scenario(
            battlefield_id="order122-battlefield", armies=tuple(state.army_definitions)
        ).battlefield_state
    )
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


def submit_quiet_choice(
    session: LocalGameSession, request: DecisionRequest, *, result_id: str
) -> None:
    if request.decision_type == "submit_stratagem_target_proposal":
        session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id=result_id,
            payload=stratagem_decline_payload(),
        )
        return
    options = tuple(
        option
        for option in request.options
        if option.option_id.startswith("complete_")
        or option.option_id in {"remain_stationary", "decline"}
    )
    option = options[0] if options else request.options[0]
    session.submit_option(
        request_id=request.request_id, option_id=option.option_id, result_id=result_id
    )


def advance_to_default_grant(session: LocalGameSession) -> DecisionRequest:
    for index in range(60):
        status = session.advance_until_decision_or_terminal()
        request = status.decision_request
        assert request is not None
        if isinstance(request.payload, dict) and request.payload.get("source_rule_id") == SOURCE_ID:
            return request
        submit_quiet_choice(session, request, result_id=f"order122-before-{index}")
    raise AssertionError("Loaded default grant was never offered.")
