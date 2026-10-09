"""Public Core three-attack fixture preserving the independent D02 entry configuration."""

from dataclasses import replace

from tests.deployment_submission_helpers import deployment_placement_payload_for_request
from tests.phase11c_command_phase_helpers import phase11c_config, unit_selection
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.weapon_profiles import AttackProfile, RangeProfile
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.mission_state_validation import (
    runtime_ruleset_descriptor_for_mission_setup,
)
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.stratagems import stratagem_decline_payload
from warhammer40k_core.geometry.pose import Pose


def native_gathered_shooting_request() -> tuple[LocalGameSession, DecisionRequest]:
    units = (
        unit_selection(
            unit_selection_id="scalar",
            datasheet_id="core-intercessor-like-infantry",
            model_profile_id="core-intercessor-like",
            model_count=5,
        ),
    )
    config = phase11c_config(
        game_id="independent-current98-multiattack", player_a_units=units, player_b_units=units
    )
    assert config.mission_setup is not None
    # Explicit synthetic three-attack/range fixture, declared before start; it
    # makes no provider weapon/body measurement claim and injects no dice/state.
    catalog = replace(
        config.army_catalog,
        wargear=tuple(
            replace(
                weapon,
                weapon_profiles=tuple(
                    replace(
                        profile,
                        range_profile=RangeProfile.distance(60),
                        attack_profile=AttackProfile.fixed(3),
                        skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 2),
                    )
                    for profile in weapon.weapon_profiles
                ),
            )
            if weapon.wargear_id == "core-bolt-rifle"
            else weapon
            for weapon in config.army_catalog.wargear
        ),
    )
    mission = replace(config.mission_setup, terrain_features=())
    session = LocalGameSession()
    session.start(
        replace(
            config,
            army_catalog=catalog,
            mission_setup=mission,
            ruleset_descriptor=runtime_ruleset_descriptor_for_mission_setup(
                mission, rules_overlay_ids=()
            ),
        )
    )
    for index in range(100):
        request = session.advance_until_decision_or_terminal().decision_request
        assert request is not None
        kind = request.decision_type
        if kind == "select_shooting_type":
            status = session.submit_option(
                request_id=request.request_id, option_id="normal", result_id="order135-rng:normal"
            )
            assert status.decision_request is not None
            assert status.decision_request.decision_type == "submit_shooting_declaration"
            return session, status.decision_request
        if kind == "submit_deployment_placement":
            payload = deployment_placement_payload_for_request(
                session.lifecycle,
                request=request,
                pose_factory=lambda i, owner, _model: Pose.at(
                    8 if owner == "player-a" else 52, 26 + 1.5 * i
                ),
            )
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                payload=payload,
                result_id=f"order135-rng:deploy:{index}",
            )
        elif kind == "submit_stratagem_target_proposal":
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                payload=stratagem_decline_payload(),
                result_id=f"order135-rng:decline:{index}",
            )
        else:
            if kind == "select_secondary_missions":
                option = "fixed:assassination:bring_it_down"
            elif kind == "select_shooting_unit":
                option = "army-alpha:scalar"
            elif kind == "select_movement_action":
                option = "remain_stationary"
            else:
                option = next(
                    (
                        value.option_id
                        for value in request.options
                        if value.option_id.startswith(("complete_", "end_", "decline", "skip"))
                    ),
                    request.options[0].option_id,
                )
            status = session.submit_option(
                request_id=request.request_id,
                option_id=option,
                result_id=f"order135-rng:setup:{index}",
            )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    raise AssertionError("Native gathered configuration did not reach Shooting declaration.")
