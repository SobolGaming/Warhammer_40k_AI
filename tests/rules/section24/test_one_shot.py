"""Physical copies of the same native weapon have independent One Shot state."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import native_state
from tests.support.section24_fixtures import LORD, bolt, profile_grant, with_profile
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.weapon_instances import equipped_weapon_profile_instances_for_model


def test_same_weapon_copies_are_independently_spent_once_and_not_reset_by_turn(
    section24_definitions: Section02Definitions,
) -> None:
    p = profile_grant(bolt(section24_definitions), WeaponKeyword.ONE_SHOT)
    d = with_profile(section24_definitions, p)
    own = d.unit(LORD)
    # Explicit two-copy physical equipment premise, not native roster admission.
    own = replace(
        own, own_models=(replace(own.own_models[0], wargear_ids=(f"{LORD}:bolt-pistol",) * 2),)
    )
    state = native_state(d, own)
    copies = equipped_weapon_profile_instances_for_model(
        model=own.own_models[0], army_catalog=d.package.army_catalog
    )
    assert len(copies) == 2
    assert copies[0].weapon_instance_id != copies[1].weapon_instance_id
    assert copies[0].wargear_id == copies[1].wargear_id
    for index, physical in enumerate(copies):
        fields = {
            "weapon_instance_id": physical.weapon_instance_id,
            "model_instance_id": physical.model_instance_id,
            "wargear_id": physical.wargear_id,
            "weapon_profile_id": physical.weapon_profile.profile_id,
        }
        assert state.one_shot_weapon_available(**fields)
        state.record_one_shot_weapon_selected(
            **fields, source_phase=BattlePhase.SHOOTING, selection_id=f"s24:copy:{index}"
        )
        assert not state.one_shot_weapon_available(**fields)
        with pytest.raises(GameLifecycleError, match="already"):
            state.record_one_shot_weapon_selected(
                **fields, source_phase=BattlePhase.SHOOTING, selection_id=f"s24:duplicate:{index}"
            )
    state.battle_round = 2
    assert len(state.one_shot_weapon_use_records) == 2
    assert all(
        not state.one_shot_weapon_available(
            weapon_instance_id=p.weapon_instance_id,
            model_instance_id=p.model_instance_id,
            wargear_id=p.wargear_id,
            weapon_profile_id=p.weapon_profile.profile_id,
        )
        for p in copies
    )


@pytest.mark.parametrize("first_profile", ["standard", "alternate"])
def test_alternate_profile_shares_physical_budget_and_rejects_duplicate_restore(
    section24_definitions: Section02Definitions, first_profile: str
) -> None:
    from warhammer40k_core.engine.game_state import GameState, OneShotWeaponUseRecord

    p = profile_grant(bolt(section24_definitions), WeaponKeyword.ONE_SHOT)
    d = with_profile(section24_definitions, p)
    own = d.unit(LORD)
    own = replace(
        own, own_models=(replace(own.own_models[0], wargear_ids=(f"{LORD}:bolt-pistol",) * 2),)
    )
    state = native_state(d, own)
    copies = equipped_weapon_profile_instances_for_model(
        model=own.own_models[0], army_catalog=d.package.army_catalog
    )
    physical = copies[0]
    fields = {
        "weapon_instance_id": physical.weapon_instance_id,
        "model_instance_id": physical.model_instance_id,
        "wargear_id": physical.wargear_id,
    }
    # Explicit profile identity component inputs: no fabricated native provider.
    selected = p.profile_id if first_profile == "standard" else p.profile_id + ":alternate"
    alternate = p.profile_id + ":alternate" if first_profile == "standard" else p.profile_id
    record = state.record_one_shot_weapon_selected(
        **fields,
        weapon_profile_id=selected,
        source_phase=BattlePhase.SHOOTING,
        selection_id="d11:first",
    )
    assert record.weapon_profile_id == selected
    assert state.one_shot_weapon_use_record(**fields, weapon_profile_id=alternate) == record
    assert not state.one_shot_weapon_available(**fields, weapon_profile_id=alternate)
    before = state.to_payload()
    with pytest.raises(GameLifecycleError, match="already"):
        state.record_one_shot_weapon_selected(
            **fields,
            weapon_profile_id=alternate,
            source_phase=BattlePhase.FIGHT,
            selection_id="d11:illegal",
        )
    assert state.to_payload() == before
    restored = GameState.from_payload(before)
    assert not restored.one_shot_weapon_available(**fields, weapon_profile_id=alternate)
    # Each supplied duplicate is individually well formed; physical duplication fails.
    duplicate = replace(record, weapon_profile_id=alternate, selection_id="d11:duplicate")
    payload = state.to_payload()
    payload["one_shot_weapon_use_records"].append(duplicate.to_payload())
    with pytest.raises(GameLifecycleError, match="duplicate weapons"):
        GameState.from_payload(payload)
    assert OneShotWeaponUseRecord.from_payload(record.to_payload()) == record
    other = copies[1]
    assert state.one_shot_weapon_available(
        weapon_instance_id=other.weapon_instance_id,
        model_instance_id=other.model_instance_id,
        wargear_id=other.wargear_id,
        weapon_profile_id=alternate,
    )


def test_native_two_round_profile_rejection_and_independent_copy_continuation() -> None:
    """Native facade flow with predeclared analytical equipment, not faction admission."""
    import json

    from tests.d10_profile_helpers import advertised_weapons, profile_catalog
    from tests.deployment_submission_helpers import deployment_placement_payload_for_request
    from tests.phase11c_command_phase_helpers import phase11c_config, unit_selection
    from tests.phase13b_shooting_declaration_helpers import _proposal_from_declarations
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.core.weapon_profiles import AttackProfile, RangeProfile
    from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
    from warhammer40k_core.engine.mission_state_validation import (
        runtime_ruleset_descriptor_for_mission_setup,
    )
    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
    from warhammer40k_core.engine.shooting_types import ShootingType
    from warhammer40k_core.engine.stratagems import stratagem_decline_payload
    from warhammer40k_core.engine.weapon_declaration import (
        AvailableWeaponPayload,
        WeaponDeclaration,
    )
    from warhammer40k_core.geometry.pose import Pose

    units = (
        unit_selection(
            unit_selection_id="scalar",
            datasheet_id="core-intercessor-like-infantry",
            model_profile_id="core-intercessor-like",
            model_count=5,
        ),
    )
    config = phase11c_config(
        game_id="d11-physical-budget", player_a_units=units, player_b_units=units
    )
    catalog = profile_catalog(copies=2)
    catalog = replace(
        catalog,
        wargear=tuple(
            replace(
                w,
                weapon_profiles=tuple(
                    replace(
                        p,
                        range_profile=RangeProfile.distance(60),
                        attack_profile=AttackProfile.fixed(1),
                        keywords=(*p.keywords, WeaponKeyword.ONE_SHOT),
                        source_ids=(*p.source_ids, "constructed:d11:one-shot"),
                    )
                    for p in w.weapon_profiles
                ),
            )
            if w.wargear_id == "core-bolt-rifle"
            else w
            for w in catalog.wargear
        ),
    )
    assert config.mission_setup is not None
    mission = replace(
        config.mission_setup,
        terrain_features=(),
        terrain_areas=(),
        objective_terrain_areas=(),
        battlefield_regions=(),
    )
    config = replace(
        config,
        army_catalog=catalog,
        mission_setup=mission,
        ruleset_descriptor=runtime_ruleset_descriptor_for_mission_setup(
            mission, rules_overlay_ids=()
        ),
    )
    session = LocalGameSession()
    session.start(config)
    first: AvailableWeaponPayload | None = None
    selections = 0
    pending_checked = False

    def checkpoint() -> None:
        payload = json.loads(json.dumps(session.to_persistence_payload()))
        clone = LocalGameSession.from_persistence_payload(payload)
        fork = session.fork()
        assert clone.to_persistence_payload() == fork.to_persistence_payload() == payload
        assert clone.lifecycle.state is not session.lifecycle.state
        assert fork.lifecycle.state is not session.lifecycle.state
        replay = ReplayRunner.from_payload(session.replay_artifact(artifact_id="d11-budget")).run()
        assert replay.status is ReplayRunStatus.REPRODUCED, replay

    payload: JsonValue
    for index in range(180):
        status = session.advance_until_decision_or_terminal()
        state = session.lifecycle.state
        assert state is not None
        events = session.lifecycle.decision_controller.event_log.records
        completed = sum(e.event_type == "attack_sequence_completed" for e in events)
        if selections == 2 and completed == 2:
            assert len(state.one_shot_weapon_use_records) == 2
            assert len({r.weapon_instance_id for r in state.one_shot_weapon_use_records}) == 2
            checkpoint()
            return
        request = status.decision_request
        assert request is not None, status
        ids = [o.option_id for o in request.options]
        if request.decision_type == "submit_deployment_placement":
            payload = deployment_placement_payload_for_request(
                session.lifecycle,
                request=request,
                pose_factory=lambda i, owner, model: Pose.at(
                    8 if owner == "player-a" else 52, 10 + 1.5 * i
                ),
            )
        elif request.decision_type == "submit_stratagem_target_proposal":
            payload = stratagem_decline_payload()
        elif request.decision_type == "submit_shooting_declaration":
            weapons = [
                w for w in advertised_weapons(request) if w["wargear_id"] == "core-bolt-rifle"
            ]
            if first is None:
                first = weapons[0]
                weapon = first
            else:
                assert state.battle_round == 2
                assert not any(
                    w["weapon_instance_id"] == first["weapon_instance_id"] for w in weapons
                )
                copies = [
                    w for w in weapons if w["model_instance_id"] == first["model_instance_id"]
                ]
                assert len(copies) == 2  # both profiles of the other physical copy
                assert any(w["model_instance_id"] != first["model_instance_id"] for w in weapons)
                weapon = next(
                    w for w in copies if w["weapon_profile_id"] != first["weapon_profile_id"]
                )
                illegal = replace(
                    WeaponDeclaration(
                        attacker_model_instance_id=first["model_instance_id"],
                        weapon_instance_id=first["weapon_instance_id"],
                        wargear_id=first["wargear_id"],
                        weapon_profile_id=weapon["weapon_profile_id"],
                        target_unit_instance_id="army-beta:scalar",
                        shooting_type=ShootingType.NORMAL,
                    )
                )
                proposal = _proposal_from_declarations(request=request, declarations=(illegal,))
                before = session.to_persistence_payload()
                rejected = session.submit_parameterized_payload(
                    request_id=request.request_id,
                    result_id="d11:spent",
                    payload=validate_json_value(proposal.to_payload()),
                )
                assert rejected.status_kind is LifecycleStatusKind.INVALID
                assert session.to_persistence_payload() == before
            declaration = WeaponDeclaration(
                attacker_model_instance_id=weapon["model_instance_id"],
                weapon_instance_id=weapon["weapon_instance_id"],
                wargear_id=weapon["wargear_id"],
                weapon_profile_id=weapon["weapon_profile_id"],
                target_unit_instance_id="army-beta:scalar",
                shooting_type=ShootingType.NORMAL,
            )
            payload = validate_json_value(
                _proposal_from_declarations(
                    request=request, declarations=(declaration,)
                ).to_payload()
            )
            selections += 1
        else:
            if (
                request.decision_type == "select_shooting_unit"
                and state.active_player_id == "player-a"
                and state.battle_round == selections + 1
            ):
                option = "army-alpha:scalar"
            elif request.decision_type == "select_shooting_type":
                option = "normal"
            else:
                option = (
                    "fixed:assassination:bring_it_down"
                    if request.decision_type == "select_secondary_missions"
                    else next(
                        (
                            x
                            for x in ids
                            if x.startswith(("complete_", "end_", "decline", "skip"))
                            or x == "remain_stationary"
                        ),
                        ids[0] if ids else "",
                    )
                )
            result = session.submit_option(
                request_id=request.request_id, result_id=f"d11:{index}", option_id=option
            )
            assert result.status_kind is not LifecycleStatusKind.INVALID, result
            continue
        result = session.submit_parameterized_payload(
            request_id=request.request_id, result_id=f"d11:{index}", payload=payload
        )
        assert result.status_kind is not LifecycleStatusKind.INVALID, result
        if selections == 1 and not pending_checked:
            assert completed == 0
            checkpoint()
            pending_checked = True
    raise AssertionError("D11 native continuation exceeded decision bound")
