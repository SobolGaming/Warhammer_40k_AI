"""Runnable observations for source-selected Order 97 disagreements.

Run with ``uv run python -m tests.order97_gap_probes_01_08``.  These are diagnostic
observations, not passing gameplay regressions or implementation evidence.
"""

from __future__ import annotations

import json
from dataclasses import replace

from tests.model_keyword_helpers import mixed_keyword_unit
from tests.order85_overhang_helpers import overhang_session
from tests.unit_keyword_helpers import with_unit_keywords
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.modifiers import (
    Modifier,
    ModifierOperation,
    ModifierScope,
    ModifierStack,
    ModifierTiming,
)
from warhammer40k_core.engine.battlefield_state import geometry_model_for_placement
from warhammer40k_core.engine.unit_keyword_queries import unit_has_keyword
from warhammer40k_core.geometry.measurement import DistanceMeasurementContext


def numeric_bound_observations() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for characteristic, operand, expected in (
        (Characteristic.LEADERSHIP, -10, 5),
        (Characteristic.LEADERSHIP, 10, 8),
        (Characteristic.WEAPON_SKILL, 10, 6),
        (Characteristic.BALLISTIC_SKILL, 10, 6),
    ):
        modifier = Modifier(
            modifier_id=f"order97:{characteristic.value}:{operand}",
            source_id="order97:source-boundary-probe",
            operation=ModifierOperation.ADD,
            operand=operand,
            scope=ModifierScope.for_characteristics((characteristic,)),
            timing=ModifierTiming.ADDITIVE,
        )
        value = ModifierStack(
            characteristic=characteristic, raw_value=6, modifiers=(modifier,)
        ).resolve()
        rows.append(
            {
                "finding": "source-selected-characteristic-bounds",
                "source_ref": "02.02.01",
                "requirement_id": {
                    Characteristic.LEADERSHIP: "02.02.01-obligation-18",
                    Characteristic.WEAPON_SKILL: "02.02.01-obligation-22",
                    Characteristic.BALLISTIC_SKILL: "02.02.01-obligation-23",
                }[characteristic],
                "characteristic": characteristic.value,
                "raw": 6,
                "modifier": operand,
                "expected": expected,
                "observed": value.final,
                "owner": "src/warhammer40k_core/core/attributes.py:CharacteristicBoundPolicy",
                "scope": "Actual numeric policy mismatch; not a source parser inference.",
            }
        )
    return rows


def datasheet_name_keyword_observation() -> dict[str, object]:
    unit = mixed_keyword_unit()
    return {
        "finding": "canonical-fixture-datasheet-name-keyword",
        "source_ref": "02.01.01",
        "requirement_id": "02.01.01-obligation-01",
        "datasheet_id": unit.datasheet_id,
        "name": unit.name,
        "canonical_name_token": unit.name.upper().replace(" ", "_").replace("-", "_"),
        "keywords": list(unit.keywords),
        "expected": True,
        "observed": unit_has_keyword(unit, unit.name),
        "owner": "src/warhammer40k_core/engine/unit_factory.py:UnitInstance.keywords",
        "scope": (
            "Canonical CORE fixture proves no automatic datasheet-name keyword. This alone "
            "does not establish that an official provider omitted an explicit name keyword. "
            "Check provider normalization and runtime identity together before repairing."
        ),
    }


def frame_wholly_within_observation() -> dict[str, object]:
    session = overhang_session(start_y=8)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    army = state.army_definitions[1]
    target = army.units[0]
    target = with_unit_keywords(target, keywords=(*target.keywords, "FRAME"))
    state.replace_army_definitions([state.army_definitions[0], replace(army, units=(target,))])
    source = state.army_definitions[0].units[0]
    source_model = geometry_model_for_placement(
        model=source.own_models[0],
        placement=state.battlefield_state.unit_placement_by_id(
            source.unit_instance_id
        ).model_placements[0],
    )
    target_model = geometry_model_for_placement(
        model=target.own_models[0],
        placement=state.battlefield_state.unit_placement_by_id(
            target.unit_instance_id
        ).model_placements[0],
    )
    context = DistanceMeasurementContext.from_models(source_model, target_model)
    return {
        "finding": "frame-full-body-measurement",
        "source_ref": "01.04.01",
        "requirement_id": "01.04.01-obligation-06",
        "distance_inches": 8.5,
        "target_support_radius": target_model.base.max_radius(),
        "target_body_radius": target_model.body_parts[0].base.max_radius(),
        "source_radius": source_model.base.max_radius(),
        "centre_distance_inches": 6,
        "farthest_body_distance_inches": (
            6 + target_model.body_parts[0].base.max_radius() - source_model.base.max_radius()
        ),
        "expected": False,
        "observed": context.target_wholly_within_distance(8.5),
        "owner": (
            "src/warhammer40k_core/geometry/measurement.py:"
            "DistanceMeasurementContext.target_wholly_within_distance"
        ),
        "scope": (
            "Source-backed synthetic physical geometry through real battlefield conversion; "
            "shares the FRAME measurement bug class with category17.02. The based FRAME "
            "target has an 8in circular body on a 120mm support base."
        ),
    }


def impossible_disembark_retry_observation() -> dict[str, object]:
    from tests.disembark_eligibility_helpers import PASSENGER_ID, TRANSPORT_ID
    from tests.large_model_disembark_helpers import (
        large_disembark_placement,
        large_disembark_session,
    )
    from tests.psychic_modifier_helpers import pending_request
    from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.movement_proposals import PlacementProposalPayload, ProposalKind
    from warhammer40k_core.engine.transports import DisembarkModeKind, TransportMovementStatus

    session = large_disembark_session(diameter=100)
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id, result_id="probe:select", option_id=PASSENGER_ID
    )
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id, result_id="probe:disembark", option_id="disembark"
    )
    request = pending_request(session)
    proposal = PlacementProposalPayload(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.DISEMBARK,
        unit_instance_id=PASSENGER_ID,
        placement_kind=BattlefieldPlacementKind.DISEMBARK,
        attempted_placement=large_disembark_placement(session),
        transport_unit_instance_id=TRANSPORT_ID,
        disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
        transport_movement_status=TransportMovementStatus.NOT_MOVED,
        restriction_overrides=(),
    )
    result = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="probe:impossible",
        payload=validate_json_value(proposal.to_payload()),
    )
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    assert state.movement_phase_state is not None
    retry = pending_request(session)
    return {
        "finding": "failed-setup-retains-selected-move",
        "source_ref": "03.02.01",
        "requirement_ids": ["03.02.01-obligation-01", "03.02.01-obligation-02"],
        "base_diameter_inches": 100,
        "battlefield_dimensions_inches": [
            state.battlefield_state.battlefield_width_inches,
            state.battlefield_state.battlefield_depth_inches,
        ],
        "rejection": result.status_kind.value,
        "expected": {"selected": False, "remain_stationary_available": True},
        "observed": {
            "selected": PASSENGER_ID in state.movement_phase_state.selected_unit_ids,
            "pending_decision_type": retry.decision_type,
            "option_ids": [o.option_id for o in retry.options],
            "placed": state.battlefield_state.unit_placement_or_none(PASSENGER_ID) is not None,
        },
        "owner": (
            "src/warhammer40k_core/engine/phases/movement_transports.py:"
            "_resolve_disembark_placement_submission"
        ),
        "scope": (
            "Real facade. A 100in base cannot fit within the 44x60in battlefield at any "
            "orientation, making complete placement impossible. The invalid result keeps "
            "cargo unplaced but retains selection and exposes only placement retry."
        ),
    }


def flying_advance_restore_observation() -> dict[str, object]:
    from tests.core_clause_evidence_helpers import flying_transit_session
    from warhammer40k_core.adapters.local_session import (
        LocalGameSession,
        LocalGameSessionPersistenceError,
    )

    session = flying_transit_session()
    try:
        LocalGameSession.from_persistence_payload(session.to_persistence_payload())
    except LocalGameSessionPersistenceError as exc:
        return {
            "finding": "flying-advance-restore-authority",
            "source_ref": "03.06",
            "requirement_id": "faq-e5941469-5653-49b2-919e-9c9246e811d4-obligation-01",
            "expected": "exact restore of accepted Fly Advance",
            "observed": str(exc.__cause__),
            "owner": (
                "src/warhammer40k_core/engine/primary_mission_boundary_unit_history_authority.py:"
                "validate_primary_mission_boundary_unit_history_authority"
            ),
            ("scope"): (
                "The accepted, witnessed Fly Advance passes transit and final "
                "engagement checks; its exact facade checkpoint fails Advance "
                "authority reconstruction."
            ),
        }
    raise AssertionError("The retained negative Fly Advance restore observation changed.")


def absent_movement_advance_observation() -> dict[str, object]:
    from tests.core_clause_evidence_helpers import clause_session
    from warhammer40k_core.core.attributes import CharacteristicValue
    from warhammer40k_core.core.dice import DiceRollResult, DiceRollState
    from warhammer40k_core.engine.advance_roll import AdvanceRollRequest, AdvanceRollResult
    from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.phases.movement import resolve_advance_move, resolve_normal_move
    from warhammer40k_core.geometry.pathing import PathWitness
    from warhammer40k_core.geometry.pose import Pose

    session = clause_session(phase=BattlePhase.MOVEMENT)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    army = state.army_definitions[0]
    unit = army.units[0]
    unit = replace(
        unit,
        own_models=tuple(
            replace(
                model,
                characteristics=tuple(
                    CharacteristicValue.source_dash(Characteristic.MOVEMENT)
                    if value.characteristic is Characteristic.MOVEMENT
                    else value
                    for value in model.characteristics
                ),
            )
            for model in unit.own_models
        ),
    )
    scenario = BattlefieldScenario(
        armies=(replace(army, units=(unit,)), state.army_definitions[1]),
        battlefield_state=state.battlefield_state,
    )
    placement = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    witness = PathWitness.for_paths(
        tuple(
            (
                row.model_instance_id,
                (row.pose, Pose.at(row.pose.position.x + 1, row.pose.position.y)),
            )
            for row in placement.model_placements
        )
    )
    request = AdvanceRollRequest.for_unit(
        request_id="order97:advance",
        game_id=state.game_id,
        battle_round=1,
        player_id="player-a",
        unit_instance_id=unit.unit_instance_id,
    )
    roll = AdvanceRollResult.from_roll_state(
        request=request,
        roll_state=DiceRollState.from_result(
            DiceRollResult.from_values(
                roll_id="order97:advance:roll", spec=request.spec, values=(3,), source="fixed"
            )
        ),
    )
    normal = resolve_normal_move(
        scenario=scenario,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=placement,
        path_witness=witness,
    )
    advanced = resolve_advance_move(
        scenario=scenario,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=placement,
        path_witness=witness,
        advance_roll=roll,
    )
    assert not normal.is_valid
    return {
        "finding": "absent-movement-advance-permission",
        "source_ref": "02.02",
        "requirement_id": "02.02-obligation-01",
        "source_movement": "-",
        "advance_roll": 3,
        "path_distance_inches": 1,
        "expected": False,
        "observed": advanced.is_valid,
        "normal_move_valid": normal.is_valid,
        "owner": "src/warhammer40k_core/engine/phases/movement_resolvers.py:resolve_advance_move",
        ("scope"): (
            "Real canonical models retain source-dash M; adding an Advance roll "
            "turns numeric zero into permission for a witnessed one-inch move."
        ),
    }


def unresolved_core_language_observations() -> list[dict[str, object]]:
    from tests.support.ability_presence_fixtures import compiled_ability_rule
    from warhammer40k_core.engine.catalog_rule_consumption import catalog_rule_ir_hook_ids_for_rule

    examples = (
        (
            "nested-condition-consumer-boundary",
            "02.03.01-obligation-01",
            (
                "This unit's ranged attacks that target the closest eligible target "
                "can re-roll hit rolls of 1. "
                "If that target is within range of an objective your opponent "
                "controls, re-roll hit rolls instead."
            ),
            (
                "The selected Core source's own nested-condition example does not "
                "compile to an executable stronger branch. A parser rejection is not "
                "proof of incorrect applied rerolls."
            ),
        ),
        (
            "implicit-unit-keyword-consumer-boundary",
            "02.05.01-obligation-11",
            'Select one friendly PSYKER within 6" of this model.',
            (
                "The typed keyword target is not inferred when model/unit is omitted; "
                "PSYKER is retained as unsupported residual language. The "
                "otherwise-identical explicit PSYKER unit form is parsed separately as "
                "a positive control."
            ),
        ),
    )
    rows: list[dict[str, object]] = []
    for finding, requirement, text, scope in examples:
        rule = compiled_ability_rule(text)
        rows.append(
            {
                "finding": finding,
                "requirement_id": requirement,
                "source_ref": requirement.split("-obligation-")[0],
                "text": text,
                "diagnostics": [diagnostic.to_payload() for diagnostic in rule.diagnostics],
                "runtime_hook_ids": list(catalog_rule_ir_hook_ids_for_rule(rule)),
                "owner": "src/warhammer40k_core/rules/rule_parser.py:parse_rule_ir",
                "scope": scope,
            }
        )
    explicit = compiled_ability_rule('Select one friendly PSYKER unit within 6" of this model.')
    assert not explicit.diagnostics
    rows[-1]["explicit_unit_control"] = explicit.to_payload()
    return rows


def default_trigger_duration_observation(*, triggered: bool = True) -> dict[str, object]:
    from tests.core_clause_evidence_helpers import clause_session
    from tests.support.ability_presence_fixtures import compiled_ability_rule
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.rule_execution import RuleExecutionContext, execute_rule_ir
    from warhammer40k_core.engine.runtime_modifiers import (
        RuntimeModifierRegistry,
        WeaponProfileModifierContext,
    )

    session = clause_session(phase=BattlePhase.SHOOTING)
    state = session.lifecycle.state
    assert state is not None
    source = state.army_definitions[0].units[0]
    target = state.army_definitions[1].units[0]
    text = "Add 1 to the Attacks characteristic of ranged weapons equipped by models in this unit."
    if triggered:
        text = "In the Shooting phase, " + text.lower()
    rule = compiled_ability_rule(text)
    assert not rule.diagnostics
    result = execute_rule_ir(
        rule_ir=rule,
        context=RuleExecutionContext(
            game_id=state.game_id,
            player_id="player-a",
            battle_round=1,
            phase=BattlePhase.SHOOTING,
            active_player_id="player-a",
            timing_window_id="order97:implicit-duration",
            source_unit_instance_id=source.unit_instance_id,
            state=state,
        ),
    )
    profile = next(
        row
        for row in session.lifecycle.config.army_catalog.wargear
        if row.wargear_id == "core-bolt-rifle"
    ).weapon_profiles[0]
    assert profile.attack_profile.fixed_attacks is not None
    modified = RuntimeModifierRegistry.empty().modified_weapon_profile(
        WeaponProfileModifierContext(
            state=state,
            source_phase=BattlePhase.SHOOTING,
            attacking_unit_instance_id=source.unit_instance_id,
            attacker_model_instance_id=source.own_models[0].model_instance_id,
            target_unit_instance_id=target.unit_instance_id,
            weapon_profile=profile,
        )
    )
    return {
        "finding": "implicit-duration-consumer-boundary",
        "explicit_trigger": triggered,
        "source_ref": "01.02.02",
        "requirement_id": f"01.02.02-obligation-{'05' if triggered else '06'}",
        "text": rule.normalized_text,
        "expected_attacks": profile.attack_profile.fixed_attacks + 1,
        "observed_attacks": modified.attack_profile.fixed_attacks,
        "execution": result.to_payload(),
        "owner": "src/warhammer40k_core/engine/rule_execution.py:_persisting_effect_or_none",
        ("scope"): (
            "A compiled, supported characteristic clause executes without an "
            "explicit duration, but the generic effect is not persisted and the "
            "attack-profile consumer receives no bonus. The equivalent "
            "explicit-until-phase effect is covered by the positive foundation "
            "test."
        ),
    }


def infiltrators_redeploy_observation() -> dict[str, object]:
    from tests.deployment_submission_helpers import submit_all_deployments_if_pending
    from tests.phase11c_command_phase_helpers import phase11c_config
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.battlefield_state import ModelPlacement
    from warhammer40k_core.engine.deployment_ability_queries import rules_unit_has_infiltrators
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.mission_setup import MissionSetup
    from warhammer40k_core.engine.mission_state_validation import (
        runtime_ruleset_descriptor_for_mission_setup,
    )
    from warhammer40k_core.engine.prebattle import (
        PreBattlePlacementProposal,
        PreBattleProposalRequest,
    )
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
    from warhammer40k_core.geometry.pose import Pose
    from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack

    config = phase11c_config(game_id="order97:redeploy")
    catalog = replace(
        config.army_catalog,
        datasheets=tuple(
            replace(
                sheet,
                keywords=replace(
                    sheet.keywords, keywords=(*sheet.keywords.keywords, "REDEPLOY", "INFILTRATORS")
                ),
            )
            if sheet.datasheet_id == "core-intercessor-like-infantry"
            else sheet
            for sheet in config.army_catalog.datasheets
        ),
    )
    mission = MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )
    config = replace(
        config,
        army_catalog=catalog,
        mission_setup=mission,
        ruleset_descriptor=runtime_ruleset_descriptor_for_mission_setup(
            mission, rules_overlay_ids=()
        ),
    )
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    session = LocalGameSession(lifecycle)
    for index in range(2):
        status = session.advance_until_decision_or_terminal()
        request = status.decision_request
        assert request is not None
        session.submit_option(
            request_id=request.request_id,
            result_id=f"secondary:{index}",
            option_id="fixed:assassination:bring_it_down",
        )
    status = submit_all_deployments_if_pending(
        lifecycle,
        session.advance_until_decision_or_terminal(),
        result_id_prefix="order97:deployment",
    )
    request = status.decision_request
    assert request is not None
    selected = next(
        option for option in request.options if option.option_id.startswith("redeploy:")
    )
    status = session.submit_option(
        request_id=request.request_id,
        result_id="order97:redeploy:select",
        option_id=selected.option_id,
    )
    request = status.decision_request
    assert request is not None
    context = PreBattleProposalRequest.from_decision_request_payload(request.payload)
    state = lifecycle.state
    assert state is not None
    view = rules_unit_view_by_id(state=state, unit_instance_id=context.unit_instance_id)
    assert rules_unit_has_infiltrators(state=state, view=view)
    assert context.placement_kind is not None
    army = next(army for army in state.army_definitions if army.player_id == context.player_id)
    placements = tuple(
        ModelPlacement(
            army_id=army.army_id,
            player_id=context.player_id,
            unit_instance_id=context.unit_instance_id,
            model_instance_id=model_id,
            pose=Pose.at(31, 3 + index * 1.8),
        )
        for index, model_id in enumerate(context.model_instance_ids)
    )
    proposal = PreBattlePlacementProposal(
        proposal_request_id=context.request_id,
        proposal_kind=context.proposal_kind,
        game_id=context.game_id,
        ruleset_descriptor_hash=context.ruleset_descriptor_hash,
        setup_step=context.setup_step,
        player_id=context.player_id,
        unit_instance_id=context.unit_instance_id,
        action_kind=context.action_kind,
        source_rule_id=context.source_rule_id,
        placement_kind=context.placement_kind,
        model_placements=placements,
        context=context.context,
    )
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order97:redeploy:placement",
        payload=validate_json_value(proposal.to_payload()),
    )
    return {
        "finding": "infiltrators-redeploy-zone-restriction",
        "source_ref": "03.02.03",
        "requirement_id": "03.02.03-obligation-03",
        "expected": "accepted midpoint redeployment with all-model Infiltrators",
        "observed": status.status_kind.value,
        "diagnostics": status.payload,
        "owner": "src/warhammer40k_core/engine/prebattle.py:_resolve_prebattle_placement",
        ("scope"): (
            "Real facade setup, selection and placement; typed all-model "
            "Infiltrators availability is confirmed before the midfield placement "
            "is rejected as outside the deployment zone."
        ),
    }


def sequential_model_movement_observation() -> dict[str, object]:
    from tests.core_clause_evidence_helpers import clause_session
    from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.phases.movement import resolve_normal_move
    from warhammer40k_core.geometry.pathing import PathWitness

    session = clause_session(phase=BattlePhase.MOVEMENT)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    placement = state.battlefield_state.unit_placement_by_id("army-alpha:mover")
    first, second, *others = placement.model_placements
    witness = PathWitness.for_paths(
        (
            (first.model_instance_id, (first.pose, second.pose)),
            (second.model_instance_id, (second.pose, first.pose)),
            *((row.model_instance_id, (row.pose, row.pose)) for row in others),
        )
    )
    result = resolve_normal_move(
        scenario=BattlefieldScenario(
            armies=tuple(state.army_definitions), battlefield_state=state.battlefield_state
        ),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=placement,
        path_witness=witness,
    )
    return {
        "finding": "sequential-movement-cyclic-swap",
        "source_ref": "03.01",
        "requirement_id": "03.01-obligation-03",
        "expected": False,
        "observed": result.is_valid,
        "first_start": first.pose.to_payload(),
        "second_start": second.pose.to_payload(),
        ("owner"): (
            "src/warhammer40k_core/engine/phases/movement_geometry.py:_friendly_geo"
            "metry_models_for_path"
        ),
        ("scope"): (
            "Two real physical models exchange exact occupied starting positions. "
            "Neither can complete its entire move first without ending on the "
            "other model, but validation compares both paths against all final "
            "positions and accepts the simultaneous swap."
        ),
    }


def avoidable_setup_body_overhang_observation(*, y: float = 2.5) -> dict[str, object]:
    from warhammer40k_core.core.deployment_zones import DeploymentZone
    from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
    from warhammer40k_core.engine.deployment import DeploymentPlacementViolation
    from warhammer40k_core.engine.deployment_geometry import append_geometry_violations
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
    from warhammer40k_core.geometry.pose import Pose

    session = overhang_session()
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    unit = state.army_definitions[1].units[0]
    placement = state.battlefield_state.unit_placement_by_id(
        unit.unit_instance_id
    ).model_placements[0]
    model = geometry_model_for_placement(
        model=unit.own_models[0], placement=replace(placement, pose=Pose.at(50, y))
    )
    zone = DeploymentZone.rectangle(
        "order97:deployment", "player-b", min_x=0, min_y=0, max_x=100, max_y=20
    )
    violations: list[DeploymentPlacementViolation] = []
    append_geometry_violations(
        violations=violations,
        state=state,
        scenario=BattlefieldScenario(
            armies=tuple(state.army_definitions), battlefield_state=state.battlefield_state
        ),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        view=rules_unit_view_by_id(state=state, unit_instance_id=unit.unit_instance_id),
        models=(model,),
        deployment_zones=(zone,),
    )
    assert model.base.max_radius() < 2.5 < model.body_parts[0].base.max_radius() < 10
    return {
        "finding": "avoidable-setup-body-overhang",
        "source_ref": "03.02.02",
        "requirement_ids": ["03.02.02-obligation-04", "03.02.02-obligation-09"],
        "expected": "reject body overhang where an ordinary complete-body placement exists",
        "observed": [violation.violation_code.value for violation in violations],
        "base_radius_inches": model.base.max_radius(),
        "body_radius_inches": model.body_parts[0].base.max_radius(),
        "proposed_y": y,
        "ordinary_fit_y": 10,
        "owner": "src/warhammer40k_core/engine/deployment_geometry.py:append_geometry_violations",
        ("scope"): (
            "The authoritative deployment geometry owner accepts an eight-inch "
            "body overhanging the zone and battlefield although its entire body "
            "fits at y10. This directly proves deployment; reserve ingress needs "
            "the same full-body/impossibility audit before claiming its "
            "corresponding clause."
        ),
    }


def observations() -> list[dict[str, object]]:
    return [
        *numeric_bound_observations(),
        datasheet_name_keyword_observation(),
        frame_wholly_within_observation(),
        impossible_disembark_retry_observation(),
        flying_advance_restore_observation(),
        absent_movement_advance_observation(),
        *unresolved_core_language_observations(),
        default_trigger_duration_observation(),
        default_trigger_duration_observation(triggered=False),
        infiltrators_redeploy_observation(),
        sequential_model_movement_observation(),
        avoidable_setup_body_overhang_observation(),
    ]


if __name__ == "__main__":
    print(json.dumps(observations(), indent=2))
