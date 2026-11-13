"""Native admission and finite route evidence, without a screening-value claim."""

import json
from dataclasses import replace
from typing import Literal

import pytest

from tests.support.cavalcade_native_prefix import (
    RANGED_ID,
    SCREEN_ID,
    THREAT_ID,
    complete_native_prefix,
    native_ranged_audit,
)
from tests.support.cavalcade_v995 import (
    deployment_fixture,
    mirror_router,
    strict_mirror_session,
)
from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.runner import BoundedPolicyRunner, RunBoundary, RunLimits
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.catalog_named_weapon_profiles import equipped_named_weapon_profile_ids
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.faction_content.runtime import build_runtime_content_bundle_for_armies
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner
from warhammer40k_core.engine.runtime_modifiers import (
    WeaponProfileModifierContext,
)


@pytest.fixture(scope="module")
def native_command_checkpoint() -> JsonValue:
    session = strict_mirror_session()
    report = BoundedPolicyRunner(
        session=session,
        router=mirror_router(deployment_fixture()),
        limits=RunLimits(policy_seed=19, max_decisions=42, max_seconds=120),
    ).run(stop_at=RunBoundary("battle", "command"))
    assert len(report.decisions) == 42
    assert all(d.accepted for d in report.decisions)
    return session.to_persistence_payload()


@pytest.fixture(scope="module")
def native_mustered_session() -> LocalGameSession:
    return strict_mirror_session()


@pytest.mark.parametrize(
    ("unit_id", "model_count", "weapons"),
    [
        (SCREEN_ID, 3, ("000001133:diseased-claws-and-teeth",)),
        (THREAT_ID, 6, ("000001115:hellblade", "000001115:juggernauts-bladed-horn")),
        (
            RANGED_ID,
            1,
            (
                "000001120:bolt-of-change",
                "000001120:rod-of-sorcery",
                "000001120:staff-of-tzeentch",
            ),
        ),
    ],
)
def test_native_roles_keep_complete_equipment_in_full_legal_rosters(
    native_mustered_session: LocalGameSession,
    unit_id: str,
    model_count: int,
    weapons: tuple[str, ...],
) -> None:
    session = native_mustered_session
    state = session.lifecycle.state
    assert state is not None
    assert len(state.army_definitions) == 2
    for army in state.army_definitions:
        assert army.roster_legality_report.is_legal
        assert len(army.units) == 9
        assert sum(len(u.own_models) for u in army.units) == 39
    for request in session.lifecycle.config.army_muster_requests:
        assert request.roster_legality_required
        assert sum(p.points for p in request.unit_points) == 1945
        assert sum(p.points for p in request.enhancement_point_values) == 55
    unit = next(
        u for army in state.army_definitions for u in army.units if u.unit_instance_id == unit_id
    )
    assert len(unit.own_models) == model_count
    catalog = session.lifecycle.config.army_catalog
    weapon_ids = {w.wargear_id for w in catalog.wargear if w.weapon_profiles}
    for model in unit.own_models:
        assert set(model.wargear_ids) & weapon_ids == set(weapons)
        for weapon_id in weapons:
            gear = next(w for w in catalog.wargear if w.wargear_id == weapon_id)
            assert gear.source_ids
            assert all(p.source_ids for p in gear.weapon_profiles)
    if unit_id == THREAT_ID:
        for bearer in ("000001115:daemonic-icon", "000001115:instrument-of-chaos"):
            assert sum(bearer in m.wargear_ids for m in unit.own_models) == 1
        assert all(
            not {"000001115:daemonic-icon", "000001115:instrument-of-chaos"} <= set(m.wargear_ids)
            for m in unit.own_models
        )
    if unit_id == RANGED_ID:
        assert "MONSTER" in unit.keywords
        bolt = next(w for w in catalog.wargear if w.wargear_id == "000001120:bolt-of-change")
        assert {p.profile_id for p in bolt.weapon_profiles} == {
            "000001120:bolt-of-change:witchfire",
            "000001120:bolt-of-change:focused-witchfire",
        }
        assert all(p.range_profile.distance_inches == 18 for p in bolt.weapon_profiles)
        model = unit.own_models[0]
        assert equipped_named_weapon_profile_ids(
            army_catalog=catalog, model=model, weapon_names=("Bolt of Change",)
        ) == tuple(sorted(p.profile_id for p in bolt.weapon_profiles))
        assert equipped_named_weapon_profile_ids(
            army_catalog=catalog, model=model, weapon_names=("Bolt of Change - witchfire",)
        ) == ("000001120:bolt-of-change:witchfire",)
        # Quantity representation control; the admitted native roster stays unchanged.
        repeated_equipment = replace(model, wargear_ids=(*model.wargear_ids, bolt.wargear_id))
        assert equipped_named_weapon_profile_ids(
            army_catalog=catalog,
            model=repeated_equipment,
            weapon_names=("Bolt of Change",),
        ) == tuple(sorted(p.profile_id for p in bolt.weapon_profiles))
        assert equipped_named_weapon_profile_ids(
            army_catalog=catalog,
            model=repeated_equipment,
            weapon_names=("Bolt of Change - witchfire",),
        ) == ("000001120:bolt-of-change:witchfire",)
        assert (
            equipped_named_weapon_profile_ids(
                army_catalog=catalog, model=model, weapon_names=("Baleful sword",)
            )
            == ()
        )
        assert (
            equipped_named_weapon_profile_ids(
                army_catalog=catalog,
                model=replace(model, wargear_ids=()),
                weapon_names=("Bolt of Change",),
            )
            == ()
        )
        repeated_profile = replace(
            bolt.weapon_profiles[0],
            profile_id=f"{bolt.weapon_profiles[0].profile_id}:ambiguous-copy",
        )
        ambiguous_family = replace(bolt, weapon_profiles=(*bolt.weapon_profiles, repeated_profile))
        ambiguous_catalog = replace(
            catalog,
            wargear=tuple(
                ambiguous_family if gear.wargear_id == bolt.wargear_id else gear
                for gear in catalog.wargear
            ),
        )
        assert (
            len(
                equipped_named_weapon_profile_ids(
                    army_catalog=ambiguous_catalog, model=model, weapon_names=("Bolt of Change",)
                )
            )
            == 3
        )
        with pytest.raises(GameLifecycleError, match="ambiguous equipped profiles"):
            equipped_named_weapon_profile_ids(
                army_catalog=ambiguous_catalog,
                model=model,
                weapon_names=(bolt.weapon_profiles[0].name,),
            )
        duplicate = replace(
            bolt,
            wargear_id="test-ambiguous-bolt",
            weapon_profiles=tuple(
                replace(profile, profile_id=f"test-ambiguous:{profile.profile_id}")
                for profile in bolt.weapon_profiles
            ),
        )
        with pytest.raises(GameLifecycleError, match="ambiguous equipped wargear"):
            equipped_named_weapon_profile_ids(
                army_catalog=replace(catalog, wargear=(*catalog.wargear, duplicate)),
                model=replace(model, wargear_ids=(*model.wargear_ids, duplicate.wargear_id)),
                weapon_names=("Bolt of Change",),
            )


@pytest.mark.parametrize("recipe", ["ranged-sidestep", "blocked-screen", "blocked-ranged"])
def test_native_prefix_preserves_real_rules_terrain_and_exact_history(
    native_command_checkpoint: JsonValue,
    recipe: Literal["ranged-sidestep", "blocked-screen", "blocked-ranged"],
) -> None:
    session = LocalGameSession.from_persistence_payload(native_command_checkpoint)
    state = session.lifecycle.state
    assert state is not None
    before = state.battlefield_state
    assert before is not None
    if recipe != "ranged-sidestep":
        diagnostic = (
            "model_cannot_be_placed_at_endpoint"
            if recipe == "blocked-screen"
            else "friendly_vehicle_monster_transit_forbidden"
        )
        with pytest.raises(AssertionError, match=diagnostic):
            complete_native_prefix(session, recipe=recipe)
        assert state.current_battle_phase is BattlePhase.MOVEMENT
        assert state.battlefield_state == before
        request = session.lifecycle.pending_decision_request()
        assert request is not None
        assert request.decision_type == "submit_movement_proposal"
        records = session.lifecycle.decision_controller.records
        assert records[-1].request.decision_type == "submit_movement_proposal"
        assert session.decision_record_count() == (47 if recipe == "blocked-screen" else 49)
    else:
        complete_native_prefix(session)
        assert state.battle_round == 1
        assert state.active_player_id == "player-a"
        assert state.current_battle_phase is BattlePhase.SHOOTING
        after = state.battlefield_state
        assert after is not None
        for army in before.placed_armies:
            for unit in army.unit_placements:
                current = after.unit_placement_by_id(unit.unit_instance_id)
                for old, new in zip(unit.model_placements, current.model_placements, strict=True):
                    assert new.model_instance_id == old.model_instance_id
                    delta = -1 if unit.unit_instance_id == RANGED_ID else 0
                    assert new.pose.position.y == old.pose.position.y + delta
                    assert new.pose.position.x == old.pose.position.x + (4 if delta else 0)
                    assert new.pose.position.z == old.pose.position.z
                    assert new.pose.facing == old.pose.facing
        before_audit = session.to_persistence_payload()
        audit = native_ranged_audit(session)
        assert audit["monster"] is True
        assert audit["can_select_to_shoot"] is True
        assert audit["has_legal_declaration_against_B"] is False
        candidates = audit["B_candidates"]
        assert isinstance(candidates, list)
        assert len(candidates) == 3  # Rod and both mutually exclusive Bolt profiles.
        for candidate in candidates:
            assert isinstance(candidate, dict)
            assert candidate["is_legal"] is False
            assert candidate["violation_code"] == "out_of_range"
            assert candidate["target_in_range_model_ids"] == []
        assert session.to_persistence_payload() == before_audit
        # The normal phase-entry request must bind the actual two-profile family.
        public = session.view(viewer_player_id="player-a")["pending_decision"]
        assert public is not None
        assert public["decision_type"] == "select_faction_rule_shooting_phase_start_option"
        choice_ids: list[str] = []
        for option in public["options"]:
            payload = option["payload"]
            assert isinstance(payload, dict)
            selected = payload["selected_named_weapon_ability_choice"]
            assert isinstance(selected, dict)
            if selected["keyword"] == "Ignores Cover":
                choice_ids.append(option["option_id"])
        assert len(choice_ids) == 1
        result = session.submit_viewer_option(
            viewer=ViewerContext.for_player("player-a"),
            request_id=public["request_id"],
            option_id=choice_ids[0],
            result_id="native-master-ignores-cover",
        )
        assert result.status_kind not in (
            LifecycleStatusKind.INVALID,
            LifecycleStatusKind.UNSUPPORTED,
        )
        ranged_unit = next(
            u for a in state.army_definitions for u in a.units if u.unit_instance_id == RANGED_ID
        )
        model = ranged_unit.own_models[0]
        catalog = session.lifecycle.config.army_catalog
        bundle = build_runtime_content_bundle_for_armies(
            config=session.lifecycle.config, armies=tuple(state.army_definitions)
        )
        registry = bundle.runtime_modifier_registry
        for gear in catalog.wargear:
            if gear.wargear_id not in model.wargear_ids:
                continue
            for profile in gear.weapon_profiles:
                modified = registry.modified_weapon_profile(
                    WeaponProfileModifierContext(
                        state=state,
                        source_phase=BattlePhase.SHOOTING,
                        attacking_unit_instance_id=RANGED_ID,
                        attacker_model_instance_id=model.model_instance_id,
                        target_unit_instance_id=THREAT_ID,
                        weapon_profile=profile,
                    )
                )
                assert (WeaponKeyword.IGNORES_COVER in modified.keywords) == (
                    gear.wargear_id == "000001120:bolt-of-change"
                )
    assert sum(len(u.own_models) for a in state.army_definitions for u in a.units) == 78
    assert all(
        m.is_alive and m.wounds_remaining == m.starting_wounds
        for army in state.army_definitions
        for unit in army.units
        for m in unit.own_models
    )
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    assert restored.to_persistence_payload() == checkpoint
    for player in ("player-a", "player-b"):
        assert restored.view(viewer_player_id=player) == session.view(viewer_player_id=player)
        assert restored.events_since(
            EventStreamCursor(), viewer_player_id=player
        ) == session.events_since(EventStreamCursor(), viewer_player_id=player)
    replay = ReplayRunner.from_payload(
        session.replay_artifact(artifact_id=f"native-prefix-{recipe}")
    ).run()
    assert replay.reproduced_exactly
    assert session.to_persistence_payload() == checkpoint
