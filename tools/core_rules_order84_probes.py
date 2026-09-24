"""Diagnostic counterexamples for the Order 84 audit; never a gameplay certificate.

Run from the repository root with ``python -m tools.core_rules_order84_probes``.
These observations deliberately do not assert that current defects are correct.
Canonical fixture builders supply real domain objects; no controllers are replaced.
"""

from __future__ import annotations

import json
from dataclasses import replace

from tests.destruction_occurrence_fixture_helpers import destroy_rule_model_for_fixture
from tests.healing_phase_start_helpers import record_healing_phase_start
from tests.phase13b_shooting_declaration_helpers import _shooting_lifecycle
from tests.phase15c_fight_order_helpers import fight_lifecycle
from tests.phase15d_fight_resolution_helpers import melee_fixture, melee_proposal, melee_request
from tests.unit_keyword_helpers import with_unit_keywords

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.core.dice_errors import DiceRollSpecError
from warhammer40k_core.core.dice_result_override import DiceRollOverrideRecord
from warhammer40k_core.core.weapon_profiles import AttackProfile
from warhammer40k_core.engine.attack_sequence import wound_roll_target_number
from warhammer40k_core.engine.battlefield_state import geometry_model_for_placement
from warhammer40k_core.engine.damage_allocation import model_by_id
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.fight_resolution import (
    MeleeTargetAllocation,
    MeleeWeaponDeclaration,
    validate_melee_declaration_rules,
)
from warhammer40k_core.engine.healing import (
    HealingEffect,
    apply_healing_model_decision,
    healing_army_definitions_with_model_wounds,
    resolve_healing_until_blocked,
)
from warhammer40k_core.engine.healing_geometry import healing_phase_start_model_ids
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.secondary_scoring_occupancy import _table_quarter_id_or_none
from warhammer40k_core.engine.transports import TransportCapacityProfile, TransportCargoState
from warhammer40k_core.geometry.pose import Pose


def dice_override() -> dict[str, object]:
    values: dict[str, object] = {}
    for value in (6, 7):
        try:
            record = DiceRollOverrideRecord(
                "audit-result", "audit-request", "audit-source", (2,), value
            )
        except DiceRollSpecError as exc:
            values[str(value)] = {"status": "rejected", "diagnostic": str(exc)}
        else:
            values[str(value)] = {"status": "accepted", "replacement": record.replacement_value}
    return values


def strength_dash() -> dict[str, object]:
    catalog, _, _, _, _, _ = melee_fixture()
    profile = catalog.wargear[0].weapon_profiles[0]
    no_strength = replace(
        profile, strength=CharacteristicValue.source_dash(Characteristic.STRENGTH)
    )
    try:
        target = wound_roll_target_number(strength=no_strength.strength.final, toughness=4)
    except GameLifecycleError as exc:
        return {"profile_accepted": True, "status": "rejected", "diagnostic": str(exc)}
    return {"profile_accepted": True, "status": "resolved", "wound_target": target}


def shooting_selection() -> dict[str, object]:
    observations: dict[str, object] = {}
    for label, pose in (("near", Pose.at(15, 10)), ("out_of_range", Pose.at(55, 40))):
        lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("audit-shooter",), enemy_pose=pose)
        session = LocalGameSession(lifecycle)
        session.advance_until_decision_or_terminal()
        pending = lifecycle.decision_controller.queue.pending_requests
        observations[label] = {
            "unit_id": units["audit-shooter"].unit_instance_id,
            "pending": [
                {"type": r.decision_type, "options": [o.option_id for o in r.options]}
                for r in pending
            ],
            "both_viewers_project": all(
                session.view(viewer_player_id=p) for p in ("player-a", "player-b")
            ),
        }
    return observations


def table_quarters() -> dict[str, object]:
    _, _, scenario, attacker, _, _ = melee_fixture()
    model = attacker.own_models[0]
    placement = scenario.battlefield_state.model_placement_by_id(model.model_instance_id)
    geometry = geometry_model_for_placement(model=model, placement=placement)
    radius = geometry.base.max_radius()
    # The right edge is 0.01 inches left of the centre: inside the 0.5 mm half-strip.
    geometry = replace(geometry, pose=Pose.at(30 - radius - 0.01, 10))
    return {
        "edge_to_center_inches": 0.01,
        "half_divider_inches": 0.5 / 25.4,
        "observed_quarter": _table_quarter_id_or_none(
            geometry_models=(geometry,), center_x=30, center_y=22
        ),
        "expected_quarter": None,
    }


def healing(
    *, embarked: bool, multiple_wounded: bool = False, character: bool = False
) -> dict[str, object]:
    lifecycle, units = fight_lifecycle(
        alpha_unit_ids=("patient", "transport"),
        enemy_unit_ids=("enemy",),
        origins={
            "patient": Pose.at(10, 10),
            "transport": Pose.at(20, 10),
            "enemy": Pose.at(35, 30),
        },
        alpha_unit_specs={"transport": ("core-transport", "core-transport", 1)},
        game_id="order84-healing",
        record_deployment=True,
        battle_phase=BattlePhase.COMMAND,
    )
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    patient = units["patient"]
    if character:
        patient = with_unit_keywords(patient, keywords=(*patient.keywords, "CHARACTER"))
        state.replace_army_definitions(
            [
                replace(
                    army,
                    units=tuple(
                        patient if unit.unit_instance_id == patient.unit_instance_id else unit
                        for unit in army.units
                    ),
                )
                for army in state.army_definitions
            ]
        )
    model = patient.own_models[-1]
    if multiple_wounded:
        # Explicit legal domain state for two wounded models; tests already model this state.
        for wounded in patient.own_models[:2]:
            state.replace_army_definitions(
                list(
                    healing_army_definitions_with_model_wounds(
                        armies=tuple(state.army_definitions),
                        model_instance_id=wounded.model_instance_id,
                        wounds_remaining=1,
                    )
                )
            )
    else:
        destroy_rule_model_for_fixture(
            state=state,
            decisions=lifecycle.decision_controller,
            model_id=model.model_instance_id,
            destroying_player_id="player-b",
            source_unit_id=units["enemy"].unit_instance_id,
            source_model_id=units["enemy"].own_models[0].model_instance_id,
        )
    if embarked:
        state.replace_battlefield_state(
            state.battlefield_state.without_unit_placement(patient.unit_instance_id)
        )
        transport = units["transport"]
        state.record_transport_cargo_state(
            TransportCargoState(
                player_id="player-a",
                transport_unit_instance_id=transport.unit_instance_id,
                capacity_profile=TransportCapacityProfile(
                    transport_datasheet_id=transport.datasheet_id,
                    max_model_count=10,
                    allowed_keywords=("INFANTRY",),
                ),
                embarked_unit_instance_ids=(patient.unit_instance_id,),
            )
        )
    record_healing_phase_start(state=state, decisions=lifecycle.decision_controller)
    effect = HealingEffect(
        effect_id="order84-heal",
        target_unit_instance_id=patient.unit_instance_id,
        amount=1,
        opposing_player_id="player-b",
        selection_actor_player_id="player-a",
        phase_start_model_ids=()
        if embarked or multiple_wounded
        else healing_phase_start_model_ids(
            state=state,
            decisions=lifecycle.decision_controller,
            rules_unit=rules_unit_view_by_id(
                state=state, unit_instance_id=patient.unit_instance_id
            ),
        ),
        source_context={}
        if multiple_wounded or character
        else {"revive_model_full_health": True, "revive_destroyed_models_only": True},
    )
    try:
        blocked, request = resolve_healing_until_blocked(
            state=state,
            decisions=lifecycle.decision_controller,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            effect=effect,
        )
    except GameLifecycleError as exc:
        return {"status": "rejected", "diagnostic": str(exc)}
    if request is None:
        return {
            "status": "complete",
            "steps": [step.step_kind.value for step in blocked.resolved_steps],
        }
    if not embarked:
        return {
            "status": "requested",
            "decision_type": request.decision_type,
            "character": character,
        }
    resolved, _ = apply_healing_model_decision(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        effect=blocked,
        result=DecisionResult.for_request(
            request=request,
            result_id="order84-heal-result",
            selected_option_id=request.options[0].option_id,
        ),
    )
    return {
        "status": "resolved",
        "step": resolved.resolved_steps[0].step_kind.value,
        "expected_wounds": model.starting_wounds,
        "actual_wounds": model_by_id(
            state=state, model_instance_id=model.model_instance_id
        ).wounds_remaining,
    }


def random_melee_split() -> dict[str, object]:
    catalog, ruleset, scenario, attacker, target_a, target_b = melee_fixture()
    blade = next(w for w in catalog.wargear if w.wargear_id == "core-leader-blade")
    updated = replace(
        blade,
        weapon_profiles=(
            replace(
                blade.weapon_profiles[0],
                attack_profile=AttackProfile.dice(DiceExpression(quantity=1, sides=6)),
            ),
        ),
    )
    catalog = replace(
        catalog,
        wargear=tuple(updated if w.wargear_id == blade.wargear_id else w for w in catalog.wargear),
    )
    request = melee_request(catalog=catalog, ruleset=ruleset, scenario=scenario, attacker=attacker)
    proposal = melee_proposal(
        request=request,
        attacker=attacker,
        declarations=(
            MeleeWeaponDeclaration(
                attacker_model_instance_id=attacker.own_models[0].model_instance_id,
                wargear_id=blade.wargear_id,
                weapon_profile_id=blade.weapon_profiles[0].profile_id,
                target_allocations=(
                    MeleeTargetAllocation(target_a.unit_instance_id, attacks=1),
                    MeleeTargetAllocation(target_b.unit_instance_id, attacks=1),
                ),
            ),
        ),
    )
    validation = validate_melee_declaration_rules(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        request=request,
        proposal=proposal,
        army_catalog=catalog,
    )
    return {
        "is_valid": validation.is_valid,
        "violations": [v.violation_code for v in validation.violations],
    }


def observations() -> dict[str, object]:
    return {
        "dice_override": dice_override(),
        "strength_dash": strength_dash(),
        "shooting_selection": shooting_selection(),
        "table_quarters": table_quarters(),
        "embarked_full_health_revival": healing(embarked=True),
        "multiple_wounded_healing": healing(embarked=False, multiple_wounded=True),
        "ordinary_character_healing": healing(embarked=False, character=True),
        "random_melee_split": random_melee_split(),
    }


if __name__ == "__main__":
    print(json.dumps(observations(), indent=2, sort_keys=True))
