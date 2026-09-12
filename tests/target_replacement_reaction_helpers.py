"""Accepted Shooting with untouched and fresh replacement targets."""

from dataclasses import replace
from typing import cast

from tests.core_stratagem_helpers import _replace_unit_poses
from tests.phase13b_shooting_declaration_helpers import (
    _compact_intercessor_catalog,
    _decision_request,
    _proposal_from_request,
    _select_shooting_unit_and_type,
    _shooting_lifecycle,
    _submit_payload,
)
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request
from tests.retained_attack_helpers import lethal_retained_attack_catalog, unending_fidelity_catalog
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.damage_allocation import (
    DestructionReactionKind,
    DestructionReactionSource,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    retained_attack_sources_2026_09 as retained_sources,
)


def replacement_reaction_scene(
    *, out_of_phase: bool = False, command_points: int = 1
) -> tuple[GameLifecycle, dict[str, UnitInstance], DecisionRequest]:
    if out_of_phase:
        return _retained_replacement_scene()
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("source",),
        enemy_unit_specs=tuple(
            (key, "core-intercessor-like-infantry", "core-intercessor-like", 3)
            for key in ("old", "unchanged", "new")
        ),
        catalog=unending_fidelity_catalog(),
        enemy_detachment_ids=(retained_sources.stratagem_profile().detachment_id,),
    )
    state = lifecycle.state
    assert state is not None
    for key, x, y in (("old", 20, 35), ("unchanged", 18, 25), ("new", 25, 25)):
        _replace_unit_poses(
            state,
            unit_instance_id=units[key].unit_instance_id,
            poses=tuple(Pose.at(x + i, y) for i in range(3)),
        )
    state.gain_command_points(
        player_id="player-b",
        amount=command_points,
        source_id="order42:starting-cp",
        source_kind=CommandPointSourceKind.COMMAND_PHASE_START,
    )
    lifecycle = GameLifecycle.from_payload(lifecycle.to_payload())
    state = lifecycle.state
    assert state is not None
    request = _select_shooting_unit_and_type(
        lifecycle,
        selection_request=_decision_request(lifecycle.advance_until_decision_or_terminal()),
        unit_instance_id=units["source"].unit_instance_id,
        selection_result_id="order42:source",
    )
    original = _proposal_from_request(request=request, target_unit_id=units["old"].unit_instance_id)
    payload = cast(dict[str, object], request.payload)
    proposal_request = cast(dict[str, object], payload["proposal_request"])
    weapons = cast(list[dict[str, object]], proposal_request["available_weapons"])
    first = original.declarations[0]
    weapon = next(
        weapon
        for weapon in weapons
        if weapon["model_instance_id"] != first.attacker_model_instance_id
    )
    second = replace(
        first,
        attacker_model_instance_id=cast(str, weapon["model_instance_id"]),
        weapon_instance_id=cast(str, weapon["weapon_instance_id"]),
        wargear_id=cast(str, weapon["wargear_id"]),
        weapon_profile_id=cast(str, weapon["weapon_profile_id"]),
        target_unit_instance_id=units["unchanged"].unit_instance_id,
    )
    request = _decision_request(
        _submit_payload(
            lifecycle,
            request=request,
            payload=replace(original, declarations=(*original.declarations, second)).to_payload(),
            result_id="order42:declaration",
        )
    )
    return lifecycle, units, request


def _retained_replacement_scene() -> tuple[GameLifecycle, dict[str, UnitInstance], DecisionRequest]:
    """Reach unrestricted out-of-phase Shooting through a real destruction decision."""
    catalog = _compact_intercessor_catalog(lethal_retained_attack_catalog())
    rifle = next(w for w in catalog.wargear if w.wargear_id == "core-bolt-rifle")
    second = replace(
        rifle,
        wargear_id="order42:second-rifle",
        weapon_profiles=tuple(
            replace(p, profile_id=f"order42:second:{p.profile_id}") for p in rifle.weapon_profiles
        ),
    )
    catalog = replace(
        catalog,
        wargear=(*catalog.wargear, second),
        datasheets=tuple(
            replace(
                sheet,
                wargear_options=tuple(
                    replace(
                        option,
                        default_wargear_ids=(rifle.wargear_id, second.wargear_id),
                        allowed_wargear_ids=(rifle.wargear_id, second.wargear_id),
                        min_selections=2,
                        max_selections=2,
                    )
                    for option in sheet.wargear_options
                ),
            )
            if sheet.datasheet_id == "core-intercessor-like-infantry"
            else sheet
            for sheet in catalog.datasheets
        ),
    )
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("old", "unchanged", "new"),
        enemy_unit_specs=(
            ("source", "core-intercessor-like-infantry", "core-intercessor-like", 3),
        ),
        catalog=catalog,
    )
    state = lifecycle.state
    assert state is not None
    for key, x, y in (("old", 10, 35), ("source", 20, 35), ("unchanged", 18, 25), ("new", 25, 25)):
        _replace_unit_poses(
            state,
            unit_instance_id=units[key].unit_instance_id,
            poses=tuple(Pose.at(x + i, y) for i in range(len(units[key].own_models))),
        )
    for model in units["source"].own_models:
        state.record_model_destruction_reaction_sources(
            model_instance_id=model.model_instance_id,
            sources=(
                DestructionReactionSource(
                    source_id="order42:retained-shots",
                    source_rule_id="order42:retained-shots",
                    reaction_kind=DestructionReactionKind.SHOOT_ON_DEATH,
                ),
            ),
        )
    lifecycle = GameLifecycle.from_payload(lifecycle.to_payload())
    request = _select_shooting_unit_and_type(
        lifecycle,
        selection_request=_decision_request(lifecycle.advance_until_decision_or_terminal()),
        unit_instance_id=units["old"].unit_instance_id,
        selection_result_id="order42:parent-selection",
    )
    session = LocalGameSession(lifecycle=lifecycle)
    request = _decision_request(
        session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id="order42:parent-declaration",
            payload=validate_json_value(
                _proposal_from_request(
                    request=request, target_unit_id=units["source"].unit_instance_id
                ).to_payload()
            ),
        )
    )
    for _ in range(20):
        if request.decision_type == "select_destruction_reaction":
            break
        submit_fixture_request(session, request)
        request = pending_request(session)
    else:
        raise AssertionError("The parent attack did not reach the retained-shooting choice.")
    request = _decision_request(
        session.submit_option(
            request_id=request.request_id,
            result_id="order42:retain",
            option_id="order42:retained-shots",
        )
    )
    assert request.decision_type == "submit_shooting_declaration"
    first_proposal = _proposal_from_request(
        request=request, target_unit_id=units["old"].unit_instance_id
    )
    second_proposal = _proposal_from_request(
        request=request,
        target_unit_id=units["unchanged"].unit_instance_id,
        weapon_profile_id=second.weapon_profiles[0].profile_id,
    )
    request = _decision_request(
        session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id="order42:declaration",
            payload=validate_json_value(
                replace(
                    first_proposal,
                    declarations=(*first_proposal.declarations, *second_proposal.declarations),
                ).to_payload()
            ),
        )
    )
    return lifecycle, units, request
