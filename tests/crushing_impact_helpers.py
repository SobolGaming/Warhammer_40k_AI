"""Real Charge-to-Crushing-Impact facade workload."""

from dataclasses import replace
from typing import cast

from tests.charge_distance_helpers import add_modifier, request_from, select_targets
from tests.phase15a_charge_declaration_helpers import charge_lifecycle, compact_test_unit_poses
from tests.setup_completion_helpers import record_primary_turn_start_evidence_for_fixture
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.core.random_profile_values import (
    RandomProfileValue,
    resolved_profile_characteristic,
)
from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.charge_movement_source import charge_movement_placement
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.movement_proposals import ProposalKind
from warhammer40k_core.engine.phase import LifecycleStatus
from warhammer40k_core.engine.phases.charge import ChargeMoveProposal
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose

SOURCE = "army-alpha:source"
ENEMY = "army-beta:enemy"


def crushing_session(
    *,
    keyword: str = "VEHICLE",
    toughness: int = 4,
    random_toughness: bool = False,
    attached: bool = False,
    wounds: int = 2,
    game_id: str = "order48-crushing-impact",
    enemy_attached: bool = False,
    leader_toughness: int | None = None,
    catalog: ArmyCatalog | None = None,
) -> LocalGameSession:
    catalog = ArmyCatalog.phase9a_canonical_content_pack() if catalog is None else catalog
    catalog = replace(
        catalog,
        datasheets=tuple(
            replace(
                sheet,
                keywords=replace(
                    sheet.keywords, keywords=tuple(sorted(set(sheet.keywords.keywords) | {keyword}))
                ),
                model_profiles=tuple(
                    replace(
                        profile,
                        characteristics=tuple(
                            RandomProfileValue(
                                Characteristic.TOUGHNESS,
                                DiceExpression(1, 3, 1),
                                profile.source_ids[0],
                            )
                            if random_toughness and value.characteristic is Characteristic.TOUGHNESS
                            else replace(
                                resolved_profile_characteristic(value), raw=n, base=n, final=n
                            )
                            if (
                                n := {
                                    Characteristic.TOUGHNESS: (
                                        leader_toughness
                                        if leader_toughness is not None
                                        and sheet.datasheet_id == "core-character-leader"
                                        else toughness
                                    ),
                                    Characteristic.WOUNDS: wounds,
                                }.get(value.characteristic)
                            )
                            is not None
                            else value
                            for value in profile.characteristics
                        ),
                    )
                    for profile in sheet.model_profiles
                ),
            )
            for sheet in catalog.datasheets
        ),
    )
    lifecycle, _ = charge_lifecycle(
        alpha_unit_ids=("source", "leader", "next") if attached else ("source", "next"),
        alpha_attached_unit_ids=("source", "leader") if attached else None,
        alpha_origins={"leader": Pose.at(17, 20), "next": Pose.at(10, 35)},
        game_id=game_id,
        battle_round=2,
        catalog=catalog,
        enemy_unit_ids=("enemy", "enemy-leader", "other") if enemy_attached else ("enemy", "other"),
        enemy_attached_unit_ids=("enemy", "enemy-leader") if enemy_attached else None,
        enemy_origins={"other": Pose.at(10, 44), "enemy-leader": Pose.at(17, 27)},
        enemy_model_poses=compact_test_unit_poses(origin=Pose.at(10, 26), model_count=5),
    )
    state = lifecycle.state
    assert state is not None
    record_primary_turn_start_evidence_for_fixture(state, decisions=lifecycle.decision_controller)
    add_modifier(state, effect_id="order48-charge", kind="modify_dice_roll", delta=10)
    state.gain_command_points(
        player_id="player-a",
        amount=2,
        source_id="order48:fixture-cp",
        source_kind=CommandPointSourceKind.COMMAND_PHASE_START,
    )
    return LocalGameSession(lifecycle)


def complete_charge(session: LocalGameSession) -> LifecycleStatus:
    state = session.lifecycle.state
    assert state is not None
    source_id = rules_unit_view_by_id(state=state, unit_instance_id=SOURCE).unit_instance_id
    enemy_id = rules_unit_view_by_id(state=state, unit_instance_id=ENEMY).unit_instance_id
    request = request_from(session.advance_until_decision_or_terminal())
    request = request_from(
        session.submit_option(
            request_id=request.request_id, option_id=source_id, result_id="order48:charger"
        )
    )
    request = select_targets(session, request, (enemy_id,), result_id="order48:targets")
    placement = charge_movement_placement(
        scenario=battlefield_scenario_for_state(state=state), unit_instance_id=source_id
    )
    paths = tuple(
        (
            model.model_instance_id,
            (
                model.pose,
                Pose.at(model.pose.position.x, model.pose.position.y + distance / 2),
                Pose.at(model.pose.position.x, model.pose.position.y + distance),
            ),
        )
        for model in placement.model_placements
        for distance in (5 if model.unit_instance_id == "army-alpha:leader" else 4,)
    )
    proposal = ChargeMoveProposal(
        proposal_request_id=request.request_id,
        unit_instance_id=source_id,
        proposal_kind=ProposalKind.CHARGE_MOVE,
        movement_phase_action="charge_move",
        movement_mode=MovementMode.CHARGE,
        charge_target_unit_instance_ids=(enemy_id,),
        witness=PathWitness.for_paths(paths),
    )
    return session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order48:move",
        payload=cast(JsonValue, proposal.to_payload()),
    )


def record_deadly_demise_for_fixture(
    session: LocalGameSession,
    *,
    model_instance_id: str,
    range_inches: float = 30.0,
    duplicated: bool = False,
) -> None:
    from warhammer40k_core.engine.damage_allocation import (
        DestructionReactionKind,
        DestructionReactionSource,
    )

    state = session.lifecycle.state
    assert state is not None
    state.record_model_destruction_reaction_sources(
        model_instance_id=model_instance_id,
        sources=tuple(
            DestructionReactionSource(
                source_id=f"order48:deadly-demise:{value}"
                if duplicated
                else "order48:deadly-demise",
                source_rule_id="order48:fixture:deadly-demise",
                reaction_kind=DestructionReactionKind.DEADLY_DEMISE,
                optional=False,
                payload={
                    "trigger_roll_threshold": 1,
                    "range_inches": range_inches,
                    "mortal_wounds": {"kind": "fixed", "value": value},
                },
            )
            for value in ((1, 2) if duplicated else (1,))
        ),
    )


def crushing_deadly_demise_session(*, duplicated: bool = False) -> LocalGameSession:
    session = crushing_session(toughness=96, wounds=1)
    state = session.lifecycle.state
    assert state is not None
    model = rules_unit_view_by_id(state=state, unit_instance_id=SOURCE).alive_models()[0]
    record_deadly_demise_for_fixture(
        session, model_instance_id=model.model_instance_id, duplicated=duplicated
    )
    return session
