"""Real accepted Shooting actions paused at an adapter-visible resolution choice."""

from dataclasses import replace
from typing import cast

from tests.core_stratagem_helpers import _replace_unit_poses
from tests.phase13b_shooting_declaration_helpers import (
    _catalog_with_replaced_bolt_profiles,
    _decision_request,
    _proposal_from_request,
    _select_shooting_unit_and_type,
    _shooting_lifecycle,
    _submit_payload,
    _weapon_profile_by_wargear,
)
from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.core.weapon_profiles import AttackProfile, WeaponKeyword, WeaponProfile
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import Pose


def replacement_scene(
    *,
    mode: str = "normal",
    moved: bool = True,
    alternatives: bool = True,
) -> tuple[GameLifecycle, dict[str, UnitInstance], DecisionRequest]:
    profile = _weapon_profile_by_wargear(wargear_id="core-bolt-rifle", weapon_profile_id=None)
    if mode == "one_shot":
        profile = replace(profile, keywords=(*profile.keywords, WeaponKeyword.ONE_SHOT))
    if mode == "random":
        profile = replace(
            profile, attack_profile=AttackProfile.dice(DiceExpression(quantity=1, sides=3))
        )
    profiles: tuple[WeaponProfile, ...] = (profile,)
    if mode == "snap":
        profiles = (
            profile,
            replace(
                profile, profile_id="order42:second-profile", attack_profile=AttackProfile.fixed(3)
            ),
        )
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("source",),
        enemy_unit_specs=(
            ("old", "core-intercessor-like-infantry", "core-intercessor-like", 5),
            ("new", "core-intercessor-like-infantry", "core-intercessor-like", 5),
        ),
        catalog=_catalog_with_replaced_bolt_profiles(profiles),
    )
    lifecycle = GameLifecycle.from_payload(lifecycle.to_payload())
    state = lifecycle.state
    assert state is not None
    _replace_unit_poses(
        state,
        unit_instance_id=units["new"].unit_instance_id,
        poses=tuple(Pose.at(18 + i, 25) for i in range(5)),
    )
    if mode in {"snap", "charge_interrupt"}:
        from warhammer40k_core.engine.phase import BattlePhase
        from warhammer40k_core.engine.phases.shooting_requests import (
            request_out_of_phase_shooting_declaration,
        )
        from warhammer40k_core.engine.weapon_abilities import FIRE_OVERWATCH_RULE_ID

        parent_phase = BattlePhase.CHARGE if mode == "charge_interrupt" else BattlePhase.MOVEMENT
        state.battle_phase_index = state.battle_phase_sequence.index(parent_phase)
        state.active_player_id = "player-b"
        request = _decision_request(
            request_out_of_phase_shooting_declaration(
                state=state,
                decisions=lifecycle.decision_controller,
                ruleset_descriptor=lifecycle.config.ruleset_descriptor,
                army_catalog=lifecycle.config.army_catalog,
                player_id="player-a",
                unit_instance_id=units["source"].unit_instance_id,
                parent_phase=parent_phase,
                source_rule_id=(
                    "order46:shooting-interruption"
                    if mode == "charge_interrupt"
                    else FIRE_OVERWATCH_RULE_ID
                ),
                source_decision_request_id="order42:overwatch-request",
                source_decision_result_id="order42:overwatch-result",
                source_context={"triggering_enemy_unit_instance_id": units["old"].unit_instance_id},
                target_unit_ids=None
                if mode == "charge_interrupt"
                else (units["old"].unit_instance_id,),
            )
        )
    else:
        request = _select_shooting_unit_and_type(
            lifecycle,
            selection_request=_decision_request(lifecycle.advance_until_decision_or_terminal()),
            unit_instance_id=units["source"].unit_instance_id,
            selection_result_id="order42:source",
            shooting_type=ShootingType.NORMAL,
        )
    original = _proposal_from_request(request=request, target_unit_id=units["old"].unit_instance_id)
    payload = cast(dict[str, object], request.payload)
    proposal_request = cast(dict[str, object], payload["proposal_request"])
    weapons = cast(list[dict[str, object]], proposal_request["available_weapons"])
    first = original.declarations[0]
    second = next(
        w
        for w in weapons
        if w["model_instance_id"] != first.attacker_model_instance_id
        and w["weapon_profile_id"] == profiles[-1].profile_id
    )
    declaration = replace(
        first,
        weapon_instance_id=cast(str, second["weapon_instance_id"]),
        attacker_model_instance_id=cast(str, second["model_instance_id"]),
        weapon_profile_id=cast(str, second["weapon_profile_id"]),
        target_unit_instance_id=units["old" if mode == "snap" else "new"].unit_instance_id,
    )
    request = _decision_request(
        _submit_payload(
            lifecycle,
            request=request,
            payload=replace(original, declarations=(first, declaration)).to_payload(),
            result_id="order42:declaration",
        )
    )
    assert request.decision_type in ("select_resolve_target_unit", "select_attack_weapon_group")
    if moved:
        _replace_unit_poses(
            state,
            unit_instance_id=units["old"].unit_instance_id,
            poses=tuple(Pose.at(90 + i, 90) for i in range(5)),
        )
    if not alternatives:
        _replace_unit_poses(
            state,
            unit_instance_id=units["new"].unit_instance_id,
            poses=tuple(Pose.at(90 + i, 80) for i in range(5)),
        )
    return lifecycle, units, request
