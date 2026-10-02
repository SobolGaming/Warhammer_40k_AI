"""Reproduce negative Order97 audit observations, without claiming gameplay support."""

from __future__ import annotations

import json
from dataclasses import replace

from tests.model_keyword_helpers import mixed_keyword_catalog
from tests.phase13b_shooting_declaration_helpers import (
    _attack_pool_for_test,
    _blocking_ruin,
    _first_weapon_profile,
    _scenario_with_unit_pose,
    _shooting_lifecycle,
)
from tests.phase15c_fight_order_helpers import fight_lifecycle
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.attack_sequence import (
    AttackSequence,
    gathered_attack_groups_for_target,
)
from warhammer40k_core.engine.attack_sequence_selection import target_has_character_for_attack_group
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.engine.hazard import hazard_mortal_wounds_per_failed_roll
from warhammer40k_core.engine.list_validation import UnitMusterSelection
from warhammer40k_core.engine.shooting_targets import shooting_target_candidate_for_model
from warhammer40k_core.engine.unit_factory import UnitFactory, UnitInstance
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.geometry.pose import Pose


def mixed_hazard_unit(ordinary_keyword: str) -> UnitInstance:
    catalog = mixed_keyword_catalog()
    sheet = catalog.datasheet_by_id("core-intercessor-like-infantry")
    sheet = replace(
        sheet,
        keywords=replace(
            sheet.keywords, keywords=(ordinary_keyword, "VEHICLE", "PSYKER", "BATTLELINE")
        ),
    )
    catalog = replace(
        catalog,
        datasheets=tuple(
            sheet if d.datasheet_id == sheet.datasheet_id else d for d in catalog.datasheets
        ),
        model_keyword_assignments=tuple(
            replace(
                a,
                keywords=("VEHICLE", "PSYKER", "BATTLELINE")
                if a.model_profile_id == "core-keyword-specialist"
                else (ordinary_keyword, "BATTLELINE"),
            )
            for a in catalog.model_keyword_assignments
        ),
    )
    return UnitFactory(catalog=catalog).instantiate_unit(
        army_id="audit",
        datasheet=sheet,
        selection=UnitMusterSelection(
            unit_selection_id="mixed",
            datasheet_id=sheet.datasheet_id,
            model_profile_selections=tuple(
                ModelProfileSelection(model_profile_id=c.model_profile_id, model_count=c.min_models)
                for c in sheet.composition
            ),
        ),
    )


def mixed_hazard() -> dict[str, object]:
    unit = mixed_hazard_unit("MOUNTED")
    return {
        "requirement_ids": ["06.03-obligation-04"],
        "owner": "src/warhammer40k_core/engine/hazard.py:hazard_mortal_wounds_per_failed_roll",
        "model_keywords": [list(m.keywords) for m in unit.own_models],
        "expected_mortal_wounds": 1,
        "observed_mortal_wounds": hazard_mortal_wounds_per_failed_roll(unit),
    }


def precision_grouping() -> dict[str, object]:
    """Observe the current runtime; original negative evidence remains immutable."""
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = lifecycle.state
    assert state is not None
    attacker, target = units["intercessor-1"], units["enemy"]
    base = replace(_first_weapon_profile(lifecycle, attacker), keywords=(), abilities=())
    first = _attack_pool_for_test(
        attacker=attacker, defender=target, weapon_profile=base, attacks=1
    )
    second = replace(
        first,
        weapon_instance_id="audit:precision-copy",
        weapon_profile=replace(base, keywords=(WeaponKeyword.PRECISION,)),
    )
    sequence = AttackSequence.start(
        sequence_id="audit:precision",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(first, second),
    )
    groups = gathered_attack_groups_for_target(
        target_has_character=target_has_character_for_attack_group(
            state=state, target_unit_instance_id=target.unit_instance_id
        ),
        attack_sequence=sequence,
        target_unit_instance_id=target.unit_instance_id,
    )
    return {
        "requirement_ids": ["faq-ee9a398d-3acb-4440-b63a-68bed3e6e217-obligation-01"],
        "owner": (
            "src/warhammer40k_core/engine/attack_sequence_selection.py:identical_attack_signature"
        ),
        "target_model_keywords": [list(m.keywords) for m in target.own_models],
        "expected_identical_groups": 1,
        "observed_identical_groups": len(groups),
    }


def separate_visible_and_in_range_models() -> dict[str, object]:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    attacker, target = units["intercessor-1"], units["enemy"]
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions), battlefield_state=state.battlefield_state
    )
    scenario = _scenario_with_unit_pose(
        scenario=scenario,
        unit=attacker,
        army_id="army-alpha",
        player_id="player-a",
        poses=tuple(Pose.at(10 - 1.4 * i, 35) for i in range(5)),
    )
    scenario = _scenario_with_unit_pose(
        scenario=scenario,
        unit=target,
        army_id="army-beta",
        player_id="player-b",
        poses=tuple(Pose.at(32 + i, 35 + 1.5 * i) for i in range(5)),
    )
    profile = _first_weapon_profile(lifecycle, attacker)
    candidate = shooting_target_candidate_for_model(
        scenario=scenario,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attacker_unit=attacker,
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        weapon_profile=profile,
        target_unit_id=target.unit_instance_id,
        terrain_features=(_blocking_ruin(),),
    )
    witness = candidate.line_of_sight_witness
    assert witness is not None
    assert witness.unit_visible
    assert witness.visible_model_ids
    assert candidate.target_in_range_model_ids
    assert set(witness.visible_model_ids).isdisjoint(candidate.target_in_range_model_ids)
    return {
        "requirement_ids": ["faq-5553f538-6182-4e72-905a-67855489bb1d-obligation-01"],
        "owner": "src/warhammer40k_core/engine/shooting_targets.py:_target_candidate",
        "expected_legal": True,
        "observed": candidate.to_payload(),
    }


def weaponless_fight_session() -> LocalGameSession:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    catalog = replace(
        catalog,
        datasheets=tuple(
            replace(
                sheet,
                wargear_options=tuple(
                    replace(option, default_wargear_ids=(), min_selections=0)
                    for option in sheet.wargear_options
                ),
            )
            if sheet.datasheet_id == "core-character-leader"
            else sheet
            for sheet in catalog.datasheets
        ),
    )
    lifecycle, _ = fight_lifecycle(
        alpha_unit_ids=("unarmed",),
        enemy_unit_ids=("enemy",),
        origins={"unarmed": Pose.at(10, 10), "enemy": Pose.at(12, 10)},
        game_id="order97-unarmed-fight",
        model_count=1,
        catalog=catalog,
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        fights_first_unit_keys=("unarmed",),
    )
    session = LocalGameSession(lifecycle)
    for _ in range(40):
        if any(
            e.event_type == "fight_activation_completed"
            for e in lifecycle.decision_controller.event_log.records
        ):
            return session
        submit_fixture_request(session, pending_request(session))
    raise AssertionError("Unarmed fight selection failed to complete.")


def weaponless_fought_status() -> dict[str, object]:
    session = weaponless_fight_session()
    events = session.lifecycle.decision_controller.event_log.records
    return {
        "requirement_ids": ["04.03.05-obligation-04"],
        "owner": (
            "src/warhammer40k_core/engine/fight_activation_completion.py:"
            "complete_active_fight_activation"
        ),
        "attack_step_count": sum(e.event_type == "attack_sequence_step" for e in events),
        "expected_has_fought_events": 0,
        "observed_has_fought_events": sum(e.event_type == "unit_has_fought" for e in events),
    }


def observations() -> dict[str, object]:
    return {
        "mixed_hazard": mixed_hazard(),
        "precision_grouping": precision_grouping(),
        "separate_range_visibility": separate_visible_and_in_range_models(),
        "weaponless_fought_status": weaponless_fought_status(),
    }


if __name__ == "__main__":
    print(json.dumps(observations(), sort_keys=True, indent=2))
