"""Order 85 preflight: source-backed physical geometry reaches a real Charge facade."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from tests.charge_distance_helpers import add_modifier, request_from, select_targets
from tests.phase15c_fight_order_helpers import fight_config, unit_placement_at
from tests.setup_completion_helpers import (
    ensure_army_mustered_events_for_fixture,
    record_completed_command_occurrences_for_fixture,
    record_current_battlefield_placements_for_fixture,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.datasheet import DatasheetAbilityDescriptor
from warhammer40k_core.core.model_geometry_catalog import (
    GeometryEvidenceKind,
    GeometryMeasurementKind,
    GeometryRulesFootprintPolicy,
    GeometrySourceUnits,
    ModelFootprintDefinition,
    ModelFootprintKind,
    ModelFootprintPartDefinition,
    ModelGeometryCatalogRecord,
    ModelGeometrySourceEvidence,
    ModelHeightDefinition,
)
from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.engine.army_mustering import muster_army
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.game_state import (
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.movement_proposals import ProposalKind
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage
from warhammer40k_core.engine.phases.charge import ChargeMoveProposal
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


def evidence(
    label: str, kind: GeometryMeasurementKind, dimension: str, value: float
) -> ModelGeometrySourceEvidence:
    return ModelGeometrySourceEvidence.from_source_dimensions(
        evidence_id=f"order85-fixture:{label}",
        evidence_kind=GeometryEvidenceKind.MANUAL_MEASUREMENT,
        measurement_kind=kind,
        source_id="order85-fixture:solid-cylinder",
        source_units=GeometrySourceUnits.INCHES,
        source_dimensions=((dimension, value),),
        document_reference="Synthetic fixture: solid cylinder, 8 inch body on 120 mm base",
    )


def footprint(label: str, source: ModelGeometrySourceEvidence) -> ModelFootprintDefinition:
    return ModelFootprintDefinition.single_part(
        footprint_id=f"order85-fixture:{label}",
        footprint_kind=ModelFootprintKind.CIRCULAR,
        part=ModelFootprintPartDefinition.from_evidence(
            part_id=label, footprint_kind=ModelFootprintKind.CIRCULAR, evidence=source
        ),
    )


def overhang_session(
    *,
    phase: BattlePhase = BattlePhase.CHARGE,
    start_y: float = 8.0,
    consolidate: bool = False,
    attached: bool = False,
    turn_owner: str = "player-a",
    second_enemy: bool = False,
    source_abilities: tuple[DatasheetAbilityDescriptor, ...] = (),
    source_keywords: tuple[str, ...] = (),
    persisted_permissions: bool = False,
    reserve_enemy: bool = False,
) -> LocalGameSession:
    from warhammer40k_core.engine.list_validation import AttachmentDeclaration

    body = evidence("body", GeometryMeasurementKind.FOOTPRINT, "diameter", 8.0)
    base = evidence("base", GeometryMeasurementKind.SUPPORT_BASE, "diameter", 120.0 / 25.4)
    height = evidence("height", GeometryMeasurementKind.HEIGHT, "height", 2.0)
    record = ModelGeometryCatalogRecord(
        model_geometry_id="order85-overhang",
        model_profile_id="core-vehicle-monster",
        rules_footprint_policy=GeometryRulesFootprintPolicy.USE_SUPPORT_BASE,
        footprint=footprint("body", body),
        support_base=footprint("base", base),
        z_offset=None,
        height=ModelHeightDefinition.from_evidence(height),
        evidence=(body, base, height),
        source_ids=("order85-fixture:solid-cylinder",),
    )
    config = replace(
        fight_config(
            game_id="order85-preflight",
            alpha_unit_ids=("source", "bodyguard") if attached else ("source",),
            alpha_unit_specs={
                "bodyguard": ("core-intercessor-like-infantry", "core-intercessor-like", 5)
            }
            if attached
            else None,
            alpha_attachment_declarations=(AttachmentDeclaration("source", "bodyguard"),)
            if attached
            else (),
            enemy_unit_ids=("enemy", "second") if second_enemy else ("enemy",),
            datasheet_id="core-character-leader",
            model_profile_id="core-character-leader",
            model_count=1,
            enemy_unit_specs={"enemy": ("core-vehicle-monster", "core-vehicle-monster", 1)},
        ),
        model_geometries=(record,),
    )
    from warhammer40k_core.engine.mission_state_validation import (
        runtime_ruleset_descriptor_for_mission_setup,
    )

    config = replace(
        config,
        ruleset_descriptor=runtime_ruleset_descriptor_for_mission_setup(
            config.mission_setup, rules_overlay_ids=config.ruleset_descriptor.rules_overlay_ids
        ),
    )
    assert config.army_catalog is not None
    config = replace(
        config,
        army_catalog=replace(
            config.army_catalog,
            datasheets=tuple(
                replace(
                    sheet,
                    abilities=(*sheet.abilities, *source_abilities),
                    keywords=replace(
                        sheet.keywords,
                        keywords=tuple(sorted({*sheet.keywords.keywords, *source_keywords})),
                    ),
                )
                if sheet.datasheet_id == "core-character-leader"
                else replace(
                    sheet,
                    keywords=replace(
                        sheet.keywords, keywords=(*sheet.keywords.keywords, "DEEP_STRIKE")
                    ),
                )
                if reserve_enemy and sheet.datasheet_id == "core-vehicle-monster"
                else sheet
                for sheet in config.army_catalog.datasheets
            ),
        ),
    )
    armies = tuple(
        muster_army(
            catalog=config.army_catalog, request=request, model_geometries=config.model_geometries
        )
        for request in config.army_muster_requests
    )
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="order85-battlefield",
        armies=armies,
        battlefield_width_inches=100,
        battlefield_depth_inches=100,
    )
    battlefield = scenario.battlefield_state
    for army, pose in zip(armies, (Pose.at(10, start_y), Pose.at(10, 14)), strict=True):
        for unit in army.units:
            unit_poses = (
                (
                    Pose.at(12, start_y),
                    Pose.at(12, start_y - 1.5),
                    Pose.at(10.5, start_y - 1.5),
                    Pose.at(9, start_y - 1.5),
                    Pose.at(9, start_y - 3),
                )
                if unit.unit_instance_id.endswith(":bodyguard")
                else (pose,)
            )
            if unit.unit_instance_id.endswith(":second"):
                unit_poses = (Pose.at(12, 9.2),)
            battlefield = battlefield.with_unit_placement(
                unit_placement_at(
                    unit, army_id=army.army_id, player_id=army.player_id, poses=unit_poses
                )
            )
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    state.record_battlefield_state(battlefield)
    for player_id in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player_id=player_id,
                mode=SecondaryMissionMode.FIXED,
                fixed_mission_ids=("assassination", "bring_it_down"),
            )
        )
    decisions = DecisionController()
    if reserve_enemy:
        from tests.setup_completion_helpers import enter_battle_for_fixture
        from warhammer40k_core.engine.reserve_arrival_requirements import (
            reposition_destruction_policy,
        )
        from warhammer40k_core.engine.reserves import ReserveKind, ReserveState

        assert state.battlefield_state is not None
        state.battlefield_state = state.battlefield_state.without_unit_placement("army-beta:enemy")
        reserve = ReserveState.declared_before_battle(
            player_id="player-b",
            unit_instance_id="army-beta:enemy",
            reserve_kind=ReserveKind.DEEP_STRIKE,
            destruction_deadline_policy=reposition_destruction_policy(
                mission_setup=state.mission_setup, destruction_deadline_policy=None
            ),
        )
        state.record_reserve_state(reserve)
        decisions.event_log.append(
            "reserve_unit_declared",
            {
                "game_id": state.game_id,
                "player_id": "player-b",
                "unit_instance_id": "army-beta:enemy",
                "reserve_state": reserve.to_payload(),
            },
        )
        enter_battle_for_fixture(state, decisions=decisions)
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(phase)
    state.battle_round = 2 if reserve_enemy else 1
    state.active_player_id = turn_owner
    ensure_army_mustered_events_for_fixture(state, decisions=decisions)
    if not reserve_enemy:
        record_current_battlefield_placements_for_fixture(state, decisions=decisions)
    else:
        from warhammer40k_core.engine.battlefield_state import (
            BattlefieldPlacementKind,
            BattlefieldTransitionBatch,
            ModelPlacementRecord,
        )

        assert state.battlefield_state is not None
        initial = BattlefieldTransitionBatch(
            placements=tuple(
                ModelPlacementRecord(
                    model_instance_id=p.model_instance_id,
                    placement_kind=BattlefieldPlacementKind.DEPLOYMENT,
                    pose=p.pose,
                    source_phase="setup",
                    source_step="deploy_armies",
                )
                for army in state.battlefield_state.placed_armies
                for unit in army.unit_placements
                for p in unit.model_placements
            )
        )
        decisions.event_log.append(
            "battlefield_models_placed",
            {
                "game_id": state.game_id,
                "setup_step": "deploy_armies",
                "battlefield_id": state.battlefield_state.battlefield_id,
                "placement_kind": "deployment",
                "placed_model_count": len(initial.placements),
                "transition_batch": initial.to_payload(),
            },
        )
    if persisted_permissions:
        from warhammer40k_core.engine.rule_execution import (
            RuleExecutionContext,
            RuleExecutionStatus,
            execute_rule_ir,
        )
        from warhammer40k_core.rules.rule_ir import RuleIR, RuleIRPayload

        descriptor = next(
            a for a in source_abilities if a.ability_id == "order85-charge-permissions"
        )
        assert descriptor.rule_ir_payload is not None
        state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.COMMAND)
        result = execute_rule_ir(
            rule_ir=RuleIR.from_payload(cast(RuleIRPayload, descriptor.rule_ir_payload)),
            context=RuleExecutionContext(
                game_id=state.game_id,
                player_id="player-a",
                battle_round=1,
                phase=BattlePhase.COMMAND,
                active_player_id="player-a",
                source_unit_instance_id="army-alpha:source",
                target_unit_instance_ids=("army-alpha:source",),
                state=state,
                event_log=decisions.event_log,
            ),
        )
        assert result.status is RuleExecutionStatus.APPLIED
        assert len(result.created_persisting_effects) == 2
        state.battle_phase_index = state.battle_phase_sequence.index(phase)
    record_completed_command_occurrences_for_fixture(state, decisions=decisions, config=config)
    add_modifier(state, effect_id="order85-fixture-budget", kind="modify_dice_roll", delta=10)
    lifecycle = GameLifecycle.from_payload(
        cast(
            GameLifecyclePayload,
            {
                "config": config.to_payload(),
                "parameterized_movement_proposals": True,
                "state": state.to_payload(),
                "decisions": decisions.to_payload(),
                "reaction_queue": {"frames": []},
            },
        )
    )
    if consolidate:
        seed_consolidation(lifecycle)
    return LocalGameSession(lifecycle)


def overhang_charge_session(
    *,
    flight: bool = False,
    source_abilities: tuple[DatasheetAbilityDescriptor, ...] = (),
    persisted_permissions: bool = False,
) -> tuple[LocalGameSession, ChargeMoveProposal]:
    session = overhang_session(
        source_abilities=source_abilities,
        source_keywords=("FLY",) if flight else (),
        persisted_permissions=persisted_permissions,
    )
    state = session.lifecycle.state
    assert state is not None
    armies = state.army_definitions
    request = request_from(session.advance_until_decision_or_terminal())
    request = request_from(
        session.submit_option(
            request_id=request.request_id,
            option_id="army-alpha:source:take_to_the_skies" if flight else "army-alpha:source",
            result_id="order85-select-source",
        )
    )
    request = select_targets(session, request, ("army-beta:enemy",), result_id="order85-targets")
    model_id = armies[0].units[0].own_models[0].model_instance_id
    source_radius = 20.0 / 25.4
    end = Pose.at(10, 14 - 4.0 - source_radius)
    proposal = ChargeMoveProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.CHARGE_MOVE,
        unit_instance_id="army-alpha:source",
        movement_phase_action="charge_move",
        movement_mode=MovementMode.CHARGE,
        charge_target_unit_instance_ids=("army-beta:enemy",),
        witness=PathWitness.for_paths(((model_id, (Pose.at(10, 8), end)),)),
    )
    return session, proposal


def seed_consolidation(lifecycle: GameLifecycle) -> None:
    """Canonical initial fixture at the start of the universal Consolidate step."""
    from warhammer40k_core.core.ruleset_descriptor import FightPhaseStepKind
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.fight_order import FightPhaseState, FightsFirstRegistry

    state = lifecycle.state
    assert state is not None
    assert state.active_player_id is not None
    policy = state.runtime_ruleset_descriptor().fight_policy
    started = FightPhaseState.start(
        battle_round=state.battle_round,
        active_player_id=state.active_player_id,
        policy=policy,
        engaged_at_fight_step_start_unit_ids=(),
        fights_first_registry=FightsFirstRegistry.from_state(state),
    )
    common = {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "active_player_id": state.active_player_id,
        "phase": "fight",
    }
    lifecycle.decision_controller.event_log.append(
        "fight_phase_started",
        validate_json_value(
            {
                **common,
                "phase_body_status": "fight_phase_started",
                "fight_phase_state": started.to_payload(),
            }
        ),
    )
    movement = started.pile_in_state
    assert movement is not None
    for player in state.player_ids:
        movement = movement.with_completed_player(
            next_player_id=state.player_ids[
                (state.player_ids.index(player) + 1) % len(state.player_ids)
            ]
        )
    state.fight_phase_state = (
        started.with_pile_in_state(movement)
        .with_ordering_band(
            ordering_band=policy.ordering_bands[-1], next_player_id=state.player_ids[-1]
        )
        .with_current_step(current_step=FightPhaseStepKind.CONSOLIDATE, policy=policy)
    )
    lifecycle.decision_controller.event_log.append(
        "fight_step_completed",
        validate_json_value(
            {
                **common,
                "phase_body_status": "fight_step_completed",
                "fight_phase_state": state.fight_phase_state.to_payload(),
            }
        ),
    )


def transit_ability(*, persisted: bool = False) -> DatasheetAbilityDescriptor:
    """Reviewed synthetic RuleIR isolates capability authority from text parsing."""
    from warhammer40k_core.core.datasheet import (
        CatalogAbilitySourceKind,
        CatalogAbilitySupport,
        CatalogJsonObject,
    )
    from warhammer40k_core.rules.parsed_tokens import TextSpan
    from warhammer40k_core.rules.rule_ir import (
        RuleClause,
        RuleDuration,
        RuleDurationKind,
        RuleEffectKind,
        RuleEffectSpec,
        RuleIR,
        RuleTargetKind,
        RuleTargetSpec,
        RuleTrigger,
        RuleTriggerKind,
        parameters_from_pairs,
    )

    text = (
        "Until the end of the turn, this unit can move through models (excluding Vehicles) "
        "and terrain features when making Charge moves."
        if persisted
        else "Each time this unit makes a Normal, Advance, Fall Back or Charge move, "
        "ignore any vertical distance."
    )
    span = TextSpan(text=text, start=0, end=len(text))
    source = "fixture:order85:charge-permissions"
    rule = RuleIR(
        rule_id=source,
        source_id=source,
        normalized_text=text,
        parser_version="fixture:reviewed-permission-v1",
        clauses=(
            RuleClause(
                clause_id=source + ":clause",
                source_span=span,
                target=RuleTargetSpec(RuleTargetKind.THIS_UNIT, span),
                trigger=None
                if persisted
                else RuleTrigger(
                    RuleTriggerKind.TIMING_WINDOW,
                    span,
                    parameters_from_pairs(
                        (
                            ("phase", "movement"),
                            ("edge", "during"),
                            ("timing_window", "unit_makes_move"),
                            ("subject", "this_unit"),
                            ("movement_modes", ("advance", "charge", "fall_back", "normal")),
                        )
                    ),
                ),
                duration=RuleDuration(
                    RuleDurationKind.UNTIL_TIMING_ENDPOINT,
                    span,
                    parameters_from_pairs((("endpoint", "turn"),)),
                )
                if persisted
                else None,
                effects=(
                    RuleEffectSpec(
                        RuleEffectKind.MOVEMENT_TRANSIT_PERMISSION,
                        span,
                        parameters_from_pairs(
                            (
                                ("permission", "ignore_vertical_distance"),
                                ("movement_modes", ("advance", "charge", "fall_back", "normal")),
                            )
                        ),
                    ),
                )
                if not persisted
                else (
                    RuleEffectSpec(
                        RuleEffectKind.MOVEMENT_TRANSIT_PERMISSION,
                        span,
                        parameters_from_pairs(
                            (
                                ("permission", "move_through_models"),
                                ("movement_modes", ("charge",)),
                                ("model_allegiance", "any"),
                                ("excluded_model_keyword_any", ("VEHICLE",)),
                            )
                        ),
                    ),
                    RuleEffectSpec(
                        RuleEffectKind.MOVEMENT_TRANSIT_PERMISSION,
                        span,
                        parameters_from_pairs(
                            (
                                ("permission", "move_through_terrain_features"),
                                ("movement_modes", ("charge",)),
                                ("terrain_features", True),
                            )
                        ),
                    ),
                ),
            ),
        ),
    )
    return DatasheetAbilityDescriptor(
        ability_id="order85-charge-permissions",
        name="Charge permissions fixture",
        source_id=source,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description=text,
        rule_ir_payload=cast(CatalogJsonObject, rule.to_payload()),
    )


def reactive_charge_session() -> tuple[LocalGameSession, ChargeMoveProposal]:
    """A real reserve ingress supplies the opponent-turn reactive Charge trigger."""
    from tests.support.ability_presence_fixtures import compiled_ability_rule
    from warhammer40k_core.core.datasheet import (
        CatalogAbilitySourceKind,
        CatalogAbilitySupport,
        CatalogJsonObject,
    )
    from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.movement_proposals import (
        MovementProposalRequest,
        PlacementProposalPayload,
    )

    text = (
        "At the end of your opponent's Movement phase, you can select one enemy unit that was "
        'set up on the battlefield within 12" of this model; this model can then either: '
        "Shoot at that unit, but only if it is an eligible target. Declare a charge. This unit "
        "must end that charge move engaged with the enemy unit you selected (note that even if "
        "this charge is successful, this unit does not receive any Charge bonus this turn)."
    )
    rule = compiled_ability_rule(text)
    ability = DatasheetAbilityDescriptor(
        ability_id="order85-reactive",
        name="Reactive Charge fixture",
        source_id=rule.source_id,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description=text,
        rule_ir_payload=cast(CatalogJsonObject, rule.to_payload()),
    )
    session = overhang_session(
        phase=BattlePhase.MOVEMENT,
        turn_owner="player-b",
        source_abilities=(ability,),
        reserve_enemy=True,
    )
    state = session.lifecycle.state
    assert state is not None
    request = request_from(session.advance_until_decision_or_terminal())
    request = request_from(
        session.submit_option(
            request_id=request.request_id,
            result_id="reactive-select-reserve",
            option_id="army-beta:enemy",
        )
    )
    request = request_from(
        session.submit_option(
            request_id=request.request_id, result_id="reactive-ingress", option_id="ingress"
        )
    )
    pending = MovementProposalRequest.from_decision_request_payload(request.payload)
    ingress = PlacementProposalPayload(
        proposal_request_id=request.request_id,
        proposal_kind=pending.proposal_kind,
        unit_instance_id=pending.unit_instance_id,
        placement_kind=BattlefieldPlacementKind.DEEP_STRIKE,
        attempted_placement=unit_placement_at(
            state.army_definitions[1].units[0],
            army_id="army-beta",
            player_id="player-b",
            poses=(Pose.at(10, 21),),
        ),
    )
    request = request_from(
        session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id="reactive-arrival",
            payload=validate_json_value(ingress.to_payload()),
        )
    )
    assert request.decision_type == "resolve_sequencing_order"
    option = next(
        o for o in request.options if o.option_id.startswith("next:catalog-setup-reactive-")
    )
    request = request_from(
        session.submit_option(
            request_id=request.request_id, result_id="reactive-sequence", option_id=option.option_id
        )
    )
    request = request_from(
        session.submit_option(
            request_id=request.request_id, result_id="reactive-charge", option_id="charge"
        )
    )
    model_id = state.army_definitions[0].units[0].own_models[0].model_instance_id
    return session, ChargeMoveProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.CHARGE_MOVE,
        unit_instance_id="army-alpha:source",
        movement_phase_action="charge_move",
        movement_mode=MovementMode.CHARGE,
        charge_target_unit_instance_ids=("army-beta:enemy",),
        witness=PathWitness.for_paths(
            ((model_id, (Pose.at(10, 8), Pose.at(10, 21 - 4 - 20 / 25.4))),)
        ),
    )
