"""06.03-obligation-04: every current model must be MONSTER or VEHICLE."""

import json
from dataclasses import replace
from typing import cast

import pytest
from tests.hazard_all_models_helpers import hazard_scene
from tests.order97_gap_probes_04_06 import mixed_hazard_unit
from tests.phase13b_shooting_declaration_helpers import (
    _fixed_roll_result,
    _proposal_from_request,
    _unit_placement_at,
)
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.emergency_disembark import (
    resolve_destroyed_transport_rules_unit_hazard_rolls_service,
)
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.hazard import hazard_mortal_wounds_per_failed_roll, hazard_roll_spec
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.phases.movement_rules_unit_disembark import (
    RulesUnitDisembarkSelection,
    resolve_rules_unit_combat_disembark,
)
from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement
from warhammer40k_core.engine.rules_units import (
    RulesUnitComponent,
    RulesUnitView,
    rules_unit_view_by_id,
)
from warhammer40k_core.engine.transports import (
    DisembarkModeKind,
    TransportCapacityProfile,
    TransportCargoState,
    TransportMovementStatus,
)
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize(("keyword", "expected"), [("MOUNTED", 1), ("INFANTRY", 1), ("MONSTER", 3)])
def test_mixed_model_hazard_uses_every_model(keyword: str, expected: int) -> None:
    unit = mixed_hazard_unit(keyword)
    assert hazard_mortal_wounds_per_failed_roll(unit) == expected
    assert "VEHICLE" in unit.keywords
    assert ["VEHICLE" in model.keywords for model in unit.own_models] == [False, False, True]


def test_removed_ordinary_models_do_not_supply_current_hazard_keywords() -> None:
    unit = mixed_hazard_unit("MOUNTED")
    unit = replace(
        unit,
        own_models=tuple(
            replace(model, wounds_remaining=0) if "MOUNTED" in model.keywords else model
            for model in unit.own_models
        ),
    )
    assert hazard_mortal_wounds_per_failed_roll(unit) == 3


def test_rules_present_retained_model_keeps_its_own_hazard_keywords() -> None:
    unit = mixed_hazard_unit("MOUNTED")
    unit = replace(
        unit,
        own_models=tuple(
            replace(model, wounds_remaining=0) if "MOUNTED" in model.keywords else model
            for model in unit.own_models
        ),
    )
    rules_unit = RulesUnitView(
        unit_instance_id=unit.unit_instance_id,
        owner_player_id="player-a",
        components=(RulesUnitComponent(unit, "unit"),),
        retained_model_ids=(unit.own_models[0].model_instance_id,),
    )
    assert hazard_mortal_wounds_per_failed_roll(rules_unit) == 1
    assert hazard_mortal_wounds_per_failed_roll(replace(rules_unit, retained_model_ids=())) == 3


def test_each_large_model_qualifies_even_with_additional_infantry_keyword() -> None:
    unit = mixed_hazard_unit("MONSTER")
    unit = replace(
        unit,
        own_models=tuple(
            replace(
                model,
                keyword_assignment=replace(
                    model.keyword_assignment, keywords=(*model.keywords, "INFANTRY")
                ),
            )
            for model in unit.own_models
        ),
    )
    assert hazard_mortal_wounds_per_failed_roll(unit) == 3


@pytest.mark.parametrize(("keyword", "expected"), [("MOUNTED", 1), ("INFANTRY", 1), ("MONSTER", 3)])
def test_attached_combat_hazard_counts_the_whole_unit(keyword: str, expected: int) -> None:
    session, units = hazard_scene(keyword, attached=True)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    rules_unit = rules_unit_view_by_id(
        state=state, unit_instance_id=units["shooter"].unit_instance_id
    )
    transport = units["transport"]
    transport_placement = _unit_placement_at(
        transport, army_id="army-alpha", player_id="player-a", poses=(Pose.at(10, 10),)
    )
    battlefield = state.battlefield_state.with_unit_placement(transport_placement)
    for component in rules_unit.components:
        battlefield = battlefield.without_unit_placement(component.unit.unit_instance_id)
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions), battlefield_state=battlefield
    )
    cargo = TransportCargoState(
        player_id="player-a",
        transport_unit_instance_id=transport.unit_instance_id,
        capacity_profile=TransportCapacityProfile(
            transport_datasheet_id=transport.datasheet_id,
            max_model_count=10,
            allowed_keywords=(keyword, "VEHICLE"),
        ),
        embarked_unit_instance_ids=tuple(sorted(rules_unit.component_unit_instance_ids)),
        phase_battle_round=1,
        started_phase_embarked_unit_instance_ids=tuple(
            sorted(rules_unit.component_unit_instance_ids)
        ),
    )
    placement = RulesUnitPlacement(
        rules_unit_instance_id=rules_unit.unit_instance_id,
        component_unit_placements=(
            _unit_placement_at(
                units["shooter"],
                army_id="army-alpha",
                player_id="player-a",
                poses=(Pose.at(11.6, 13), Pose.at(13, 13), Pose.at(14.4, 13)),
            ),
            _unit_placement_at(
                units["leader"],
                army_id="army-alpha",
                player_id="player-a",
                poses=(Pose.at(15.6, 11.8),),
            ),
        ),
    )
    result = resolve_rules_unit_combat_disembark(
        scenario=scenario,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        cargo_state=cargo,
        selection=RulesUnitDisembarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=rules_unit.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            attempted_placement=placement,
            disembark_mode=DisembarkModeKind.COMBAT_DISEMBARK,
            transport_movement_status=TransportMovementStatus.REMAIN_STATIONARY,
        ),
        rules_unit=rules_unit,
        transport_placement=transport_placement,
        dice_manager=DiceRollManager("order105-combat"),
    )
    assert result.is_valid, result.to_payload()
    assert len(result.model_rolls) == 4
    assert {row.mortal_wounds_per_failed_roll for row in result.model_rolls} == {expected}
    assert result.mortal_wounds > 0
    assert result.mortal_wounds == expected * sum(
        row.roll.mortal_wound_inflicted for row in result.model_rolls
    )


@pytest.mark.parametrize("attached", [False, True])
@pytest.mark.parametrize(("keyword", "expected"), [("MOUNTED", 1), ("INFANTRY", 1), ("MONSTER", 3)])
def test_mixed_emergency_hazard_resolves_complete_cargo(
    keyword: str, expected: int, attached: bool
) -> None:
    session, units = hazard_scene(keyword, attached=attached)
    state = session.lifecycle.state
    assert state is not None
    rules_unit = rules_unit_view_by_id(
        state=state, unit_instance_id=units["shooter"].unit_instance_id
    )
    transport = units["transport"]
    cargo = TransportCargoState(
        player_id="player-a",
        transport_unit_instance_id=transport.unit_instance_id,
        capacity_profile=TransportCapacityProfile(
            transport_datasheet_id=transport.datasheet_id,
            max_model_count=10,
            allowed_keywords=tuple(sorted({keyword, "VEHICLE", "INFANTRY"})),
        ),
        embarked_unit_instance_ids=tuple(sorted(rules_unit.component_unit_instance_ids)),
        phase_battle_round=1,
        started_phase_embarked_unit_instance_ids=tuple(
            sorted(rules_unit.component_unit_instance_ids)
        ),
    )
    result = resolve_destroyed_transport_rules_unit_hazard_rolls_service(
        cargo_state=cargo,
        rules_unit=rules_unit,
        dice_manager=DiceRollManager(
            "order105-emergency",
            injected_results=tuple(
                _fixed_roll_result(
                    roll_id=f"order105-emergency:{index}",
                    spec=hazard_roll_spec(
                        reason=f"Emergency Disembark hazard roll for {model.model_instance_id}",
                        roll_type="destroyed_transport_disembark",
                        actor_id=model.model_instance_id,
                    ),
                    value=1 if index == 0 else 6,
                )
                for index, model in enumerate(
                    sorted(rules_unit.alive_models(), key=lambda row: row.model_instance_id)
                )
            ),
        ),
        battle_round=1,
        disembark_mode=DisembarkModeKind.EMERGENCY_DISEMBARK,
    )
    assert result.mortal_wounds_per_failed_roll == expected
    assert result.model_instance_ids == tuple(
        sorted(model.model_instance_id for model in rules_unit.alive_models())
    )
    assert result.mortal_wound_count > 0
    assert result.mortal_wound_count == expected * sum(
        row.mortal_wound_inflicted for row in result.model_rolls
    )


@pytest.mark.parametrize("attached", [False, True])
def test_mixed_hazardous_facade_restore_and_replay(attached: bool) -> None:
    session, units = hazard_scene(
        "MOUNTED",
        attached=attached,
        game_id="order105-hazard-1" if attached else "order105-hazard",
    )
    initial = json.loads(json.dumps(session.lifecycle.to_payload()))
    request = pending_request(session)
    state = session.lifecycle.state
    assert state is not None
    shooter = rules_unit_view_by_id(state=state, unit_instance_id=units["shooter"].unit_instance_id)
    session.submit_option(
        request_id=request.request_id,
        result_id="order105:select",
        option_id=shooter.unit_instance_id,
    )
    for _ in range(60):
        if any(
            event.event_type == "hazardous_test_resolved"
            for event in session.lifecycle.decision_controller.event_log.records
        ):
            break
        request = pending_request(session)
        if request.decision_type == "submit_shooting_declaration":
            proposal = _proposal_from_request(request=request, target_unit_id="army-beta:enemy")
            context = cast(dict[str, object], request.payload)
            proposal_request = cast(dict[str, object], context["proposal_request"])
            weapons = cast(list[dict[str, object]], proposal_request["available_weapons"])
            proposal = replace(
                proposal,
                declarations=tuple(
                    replace(
                        proposal.declarations[0],
                        attacker_model_instance_id=cast(str, weapon["model_instance_id"]),
                        weapon_instance_id=cast(str, weapon["weapon_instance_id"]),
                        wargear_id=cast(str, weapon["wargear_id"]),
                        weapon_profile_id=cast(str, weapon["weapon_profile_id"]),
                    )
                    for weapon in weapons
                ),
            )
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id="order105:all-weapons",
                payload=validate_json_value(proposal.to_payload()),
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status
        else:
            submit_fixture_request(session, request)
    else:
        raise AssertionError("Hazardous completion was not reached.")
    event = next(
        event
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type == "hazardous_test_resolved"
    )
    payload = cast(dict[str, object], event.payload)
    failed = cast(list[str], payload["failed_hazardous_weapon_instance_ids"])
    assert failed, payload
    assert payload["mortal_wounds"] == len(failed)
    restored = LocalGameSession.from_persistence_payload(
        json.loads(json.dumps(session.to_persistence_payload()))
    )
    for current in (session, restored):
        for _ in range(30):
            if any(
                event.event_type == "hazardous_mortal_wounds_applied"
                for event in current.lifecycle.decision_controller.event_log.records
            ):
                break
            submit_fixture_request(current, pending_request(current))
        else:
            raise AssertionError("Hazardous damage did not complete.")
    assert restored.to_persistence_payload() == session.to_persistence_payload()
    applied = next(
        event
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type == "hazardous_mortal_wounds_applied"
    )
    applied_payload = cast(dict[str, object], applied.payload)
    application = cast(dict[str, object], applied_payload["mortal_wound_application"])
    applications = cast(list[dict[str, object]], application["applications"])
    assert application["mortal_wounds"] == len(failed)
    assert sum(cast(int, row["wounds_lost"]) for row in applications) == len(failed)
    for viewer in ("player-a", "player-b"):
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
        assert restored.events_since(
            EventStreamCursor(), viewer_player_id=viewer
        ) == session.events_since(EventStreamCursor(), viewer_player_id=viewer)
    replay = ReplayRunner.from_payload(
        ReplayArtifact.capture(
            artifact_id="order105:replay",
            initial_lifecycle_payload=initial,
            final_lifecycle=session.lifecycle,
        ).to_payload()
    ).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay
