from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, cast

from tests.deployment_submission_helpers import submit_all_deployments_if_pending

from warhammer40k_core.adapters.capability_manifest import build_capability_manifest
from warhammer40k_core.adapters.decisions import submit_option
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.datasheet import CatalogAbilitySourceKind
from warhammer40k_core.core.ruleset import RulesetId
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.ability_coverage import (
    AbilityCoverageSupportStage,
    ability_coverage_rows_from_catalog,
)
from warhammer40k_core.engine.advance_hooks import (
    DECLINE_MOVEMENT_ACTION_GRANT_OPTION_ID,
    SELECT_MOVEMENT_ACTION_GRANT_DECISION_TYPE,
    AdvanceMoveGrant,
    AdvanceMoveGrantPayload,
)
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
    muster_army,
)
from warhammer40k_core.engine.army_points import calculate_mfm_army_points
from warhammer40k_core.engine.catalog_movement_action_grant_runtime import (
    CATALOG_RANDOM_MOVEMENT_ATTACK_BOOST_EFFECT_KIND,
)
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.faction_content.runtime import (
    build_runtime_content_bundle_for_armies,
    runtime_content_manifest_for_ruleset,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.emperors_children import (
    army_rule as emperors_children_army_rule,
)
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import LifecycleStatus, LifecycleStatusKind
from warhammer40k_core.engine.phases.movement import (
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    MovementPhaseActionKind,
)
from warhammer40k_core.engine.player_army_list import (
    PlayerArmyList,
    army_muster_request_from_player_army_list,
    load_player_army_list,
    player_army_list_from_json_bytes,
)
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.rule_frequency import RULE_FREQUENCY_LIMIT_CONSUMED_EVENT
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.engine.stratagems import (
    DECLINE_STRATAGEM_WINDOW_OPTION_ID,
    STRATAGEM_DECISION_TYPE,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    court_of_slaughter_anvanth_2026_08,
    mfm_2026_07,
)

_ROOT = Path(__file__).resolve().parents[2]
_COURT_PATH = _ROOT / "data" / "army_lists" / "court-of-slaughter.json"
_ANVANTH_PATH = _ROOT / "data" / "army_lists" / "anvanth-11th.json"

_COURT_SELECTION_IDS = (
    "lucius",
    "flawless-blades-lucius",
    "lord-exultant",
    "infractors",
    "lord-kakophonist-1",
    "noise-marines-1",
    "lord-kakophonist-2",
    "noise-marines-2",
    "daemon-prince-of-slaanesh",
    "fulgrim",
    "tormentors",
    "flawless-blades-2",
    "flawless-blades-3",
    "maulerfiend",
)
_ANVANTH_SELECTION_IDS = (
    "autarch-wayleaper",
    "warp-spiders-1",
    "kharseth",
    "corsair-voidreavers-1",
    "lhykhis",
    "warp-spiders-2",
    "solitaire",
    "corsair-voidreavers-2",
    "fire-dragons",
    "night-spinner",
    "rangers-1",
    "rangers-2",
    "shroud-runners-1",
    "shroud-runners-2",
    "swooping-hawks",
    "war-walkers",
    "wraithblades",
    "wraithlord",
)


def test_checked_in_army_lists_are_canonical_and_preserve_export_order() -> None:
    court = _load_round_tripped(_COURT_PATH)
    anvanth = _load_round_tripped(_ANVANTH_PATH)

    assert court.army_list_id == "court-of-slaughter"
    assert court.faction_id == "emperors-children"
    assert court.force_disposition_id == "purge-the-foe"
    assert court.declared_total_points == 2000
    assert court.detachment_selection.detachment_ids == (
        "court-of-the-phoenician",
        "spectacle-of-slaughter",
    )
    assert tuple(unit.selection.unit_selection_id for unit in court.units) == (_COURT_SELECTION_IDS)
    assert len(court.attachment_declarations) == 4
    assert len(court.enhancement_assignments) == 5
    assert court.provenance.game_result is None

    assert anvanth.army_list_id == "anvanth-11th"
    assert anvanth.faction_id == "aeldari"
    assert anvanth.force_disposition_id == "reconnaissance"
    assert anvanth.declared_total_points == 1995
    assert anvanth.detachment_selection.detachment_ids == (
        "corsair-coterie",
        "path-of-the-outcast",
    )
    assert tuple(unit.selection.unit_selection_id for unit in anvanth.units) == (
        _ANVANTH_SELECTION_IDS
    )
    assert len(anvanth.attachment_declarations) == 3
    assert len(anvanth.enhancement_assignments) == 3
    assert anvanth.provenance.game_result is None


def test_paired_army_lists_muster_with_exact_mfm_points_attachments_and_wargear() -> None:
    package = court_of_slaughter_anvanth_2026_08.catalog_package()
    points_source = mfm_2026_07.source_package()
    court_list = load_player_army_list(_COURT_PATH)
    anvanth_list = load_player_army_list(_ANVANTH_PATH)
    selected_datasheet_ids = {
        unit.selection.datasheet_id
        for army_list in (court_list, anvanth_list)
        for unit in army_list.units
    }
    assert {
        datasheet.datasheet_id for datasheet in package.army_catalog.datasheets
    } - selected_datasheet_ids == {"000002532", "000004081"}
    requests = (
        army_muster_request_from_player_army_list(
            catalog=package.army_catalog,
            army_list=court_list,
            points_source_package=points_source,
            army_id="court-of-slaughter-army",
            player_id="player-emperors-children",
        ),
        army_muster_request_from_player_army_list(
            catalog=package.army_catalog,
            army_list=anvanth_list,
            points_source_package=points_source,
            army_id="anvanth-11th-army",
            player_id="player-aeldari",
        ),
    )
    calculations = tuple(
        calculate_mfm_army_points(
            catalog=package.army_catalog,
            request=request,
            source_package=points_source,
        )
        for request in requests
    )

    assert _point_lines(calculations[0]) == {
        "lucius": (1, 120),
        "flawless-blades-lucius": (1, 190),
        "lord-exultant": (1, 80),
        "infractors": (1, 85),
        "lord-kakophonist-1": (1, 70),
        "noise-marines-1": (1, 145),
        "lord-kakophonist-2": (2, 70),
        "noise-marines-2": (2, 145),
        "daemon-prince-of-slaanesh": (1, 170),
        "fulgrim": (1, 340),
        "tormentors": (1, 80),
        "flawless-blades-2": (2, 190),
        "flawless-blades-3": (3, 95),
        "maulerfiend": (1, 120),
    }
    assert _point_lines(calculations[1]) == {
        "autarch-wayleaper": (1, 70),
        "warp-spiders-1": (1, 105),
        "kharseth": (1, 85),
        "corsair-voidreavers-1": (1, 65),
        "lhykhis": (1, 135),
        "warp-spiders-2": (2, 105),
        "solitaire": (1, 115),
        "corsair-voidreavers-2": (2, 65),
        "fire-dragons": (1, 120),
        "night-spinner": (1, 170),
        "rangers-1": (1, 60),
        "rangers-2": (2, 60),
        "shroud-runners-1": (1, 90),
        "shroud-runners-2": (2, 175),
        "swooping-hawks": (1, 95),
        "war-walkers": (1, 160),
        "wraithblades": (1, 140),
        "wraithlord": (1, 125),
    }
    assert calculations[0].total_points == 2000
    assert calculations[1].total_points == 1995
    assert _enhancement_lines(calculations[0]) == (
        (
            "000010654002",
            "lord-exultant",
            25,
            "gw-11e-mfm-2026-07:faction:emperors-children:detachment:"
            "court-of-the-phoenician:enhancement:tears-of-the-phoenix",
        ),
        (
            "000010654005",
            "daemon-prince-of-slaanesh",
            20,
            "gw-11e-mfm-2026-07:faction:emperors-children:detachment:"
            "court-of-the-phoenician:enhancement:spiritsliver",
        ),
        (
            "000010900002",
            "flawless-blades-3",
            15,
            "gw-11e-mfm-2026-07:faction:emperors-children:detachment:"
            "spectacle-of-slaughter:enhancement:beguiling-grotesquerie",
        ),
        (
            "000010900003",
            "flawless-blades-2",
            20,
            "gw-11e-mfm-2026-07:faction:emperors-children:detachment:"
            "spectacle-of-slaughter:enhancement:eager-patrons",
        ),
        (
            "000010900003",
            "flawless-blades-lucius",
            20,
            "gw-11e-mfm-2026-07:faction:emperors-children:detachment:"
            "spectacle-of-slaughter:enhancement:eager-patrons",
        ),
    )
    assert _enhancement_lines(calculations[1]) == (
        (
            "aeldari:path-of-the-outcast:assassins-eye-upgrade",
            "shroud-runners-2",
            15,
            "gw-11e-mfm-2026-07:faction:aeldari:detachment:"
            "path-of-the-outcast:enhancement:assassins-eye",
        ),
        (
            "voidstone",
            "corsair-voidreavers-2",
            15,
            "gw-11e-mfm-2026-07:faction:aeldari:detachment:corsair-coterie:enhancement:voidstone",
        ),
        (
            "webway-pathstone",
            "corsair-voidreavers-1",
            25,
            "gw-11e-mfm-2026-07:faction:aeldari:detachment:"
            "corsair-coterie:enhancement:webway-pathstone",
        ),
    )
    assert all(
        source_id.startswith("gw-11e-mfm-2026-07:")
        for calculation in calculations
        for line in calculation.unit_lines
        for source_id in line.source_ids
    )

    armies = tuple(
        muster_army(
            catalog=package.army_catalog,
            request=request,
            model_geometries=package.model_geometries,
        )
        for request in requests
    )
    court, anvanth = armies
    assert court.roster_legality_report.is_legal
    assert anvanth.roster_legality_report.is_legal
    assert len(court.units) == 14
    assert len(court.attached_units) == 4
    assert len(anvanth.units) == 18
    assert len(anvanth.attached_units) == 3
    assert _attachment_pairs(court) == {
        ("lucius", "flawless-blades-lucius"),
        ("lord-exultant", "infractors"),
        ("lord-kakophonist-1", "noise-marines-1"),
        ("lord-kakophonist-2", "noise-marines-2"),
    }
    assert _attachment_pairs(anvanth) == {
        ("autarch-wayleaper", "warp-spiders-1"),
        ("kharseth", "corsair-voidreavers-1"),
        ("lhykhis", "warp-spiders-2"),
    }
    assert court.warlord_selection is not None
    assert court.warlord_selection.unit_selection_id == "fulgrim"
    assert anvanth.warlord_selection is not None
    assert anvanth.warlord_selection.unit_selection_id == "autarch-wayleaper"
    _assert_exact_court_wargear(court)
    _assert_exact_anvanth_wargear(anvanth)
    assert all(ArmyDefinition.from_payload(army.to_payload()) == army for army in armies)


def test_paired_armies_form_a_replay_safe_physically_playable_game_config() -> None:
    package = court_of_slaughter_anvanth_2026_08.catalog_package()
    points_source = mfm_2026_07.source_package()
    requests = (
        army_muster_request_from_player_army_list(
            catalog=package.army_catalog,
            army_list=load_player_army_list(_COURT_PATH),
            points_source_package=points_source,
            army_id="court-of-slaughter-army",
            player_id="player-emperors-children",
        ),
        army_muster_request_from_player_army_list(
            catalog=package.army_catalog,
            army_list=load_player_army_list(_ANVANTH_PATH),
            points_source_package=points_source,
            army_id="anvanth-11th-army",
            player_id="player-aeldari",
        ),
    )
    config = GameConfig(
        game_id="court-of-slaughter-vs-anvanth-11th",
        ruleset_descriptor=(
            RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
                descriptor_version="court-of-slaughter-anvanth-2026-08"
            )
        ),
        army_catalog=package.army_catalog,
        army_muster_requests=requests,
        player_ids=("player-emperors-children", "player-aeldari"),
        turn_order=("player-emperors-children", "player-aeldari"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=MissionSetup.from_mission_pack(
            mission_pack=warhammer_event_companion_2026_07_mission_pack(),
            mission_pool_entry_id="mission-purge-the-foe-vs-reconnaissance-layout-1",
            terrain_layout_id="purge-the-foe-vs-reconnaissance-layout-1",
            attacker_player_id="player-emperors-children",
            attacker_force_disposition_id="purge-the-foe",
            defender_player_id="player-aeldari",
            defender_force_disposition_id="reconnaissance",
        ),
        model_geometries=package.model_geometries,
    )
    restored = GameConfig.from_payload(json.loads(json.dumps(config.to_payload(), sort_keys=True)))
    armies = tuple(
        muster_army(
            catalog=config.army_catalog,
            request=request,
            model_geometries=config.model_geometries,
        )
        for request in requests
    )
    runtime_manifest = runtime_content_manifest_for_ruleset(
        ruleset_descriptor=config.ruleset_descriptor,
        config=config,
    )
    runtime_bundle = build_runtime_content_bundle_for_armies(config=config, armies=armies)
    capability_manifest = build_capability_manifest(
        config=config,
        armies=armies,
        runtime_manifest=runtime_manifest,
        runtime_bundle=runtime_bundle,
    )

    assert restored.to_payload() == config.to_payload()
    assert config.model_geometries is not None
    assert {record.model_profile_id for record in config.model_geometries} == {
        model.model_profile_id
        for datasheet in config.army_catalog.datasheets
        for model in datasheet.model_profiles
    }
    assert capability_manifest["roster_rows"]
    assert all(
        _capability_status(row, "PHYSICALLY_PLAYABLE") == "supported"
        for row in capability_manifest["roster_rows"]
    )
    assert all(
        _capability_status(row, "PHYSICALLY_PLAYABLE") == "supported"
        for row in capability_manifest["unit_rows"]
    )

    lifecycle = GameLifecycle()
    lifecycle.start(restored)
    status = lifecycle.advance_until_decision_or_terminal()
    for result_id in ("court-anvanth-secondary-1", "court-anvanth-secondary-2"):
        assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
        request = status.decision_request
        assert request is not None
        assert request.decision_type == SECONDARY_MISSION_DECISION_TYPE
        status = submit_option(
            lifecycle=lifecycle,
            request_id=request.request_id,
            option_id=request.options[0].option_id,
            result_id=result_id,
        )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert lifecycle.state is not None
    court_rule_effects = tuple(
        effect
        for effect in lifecycle.state.persisting_effects
        if effect.owner_player_id == "player-emperors-children"
        and "court-of-the-phoenician:rule:source-text" in effect.source_rule_id
    )
    assert len(court_rule_effects) == 4


def test_every_selected_datasheet_ability_has_direct_engine_consumer_evidence() -> None:
    package = court_of_slaughter_anvanth_2026_08.catalog_package()
    court = load_player_army_list(_COURT_PATH)
    anvanth = load_player_army_list(_ANVANTH_PATH)
    selected_datasheet_ids = tuple(
        sorted(
            {
                unit.selection.datasheet_id
                for army_list in (court, anvanth)
                for unit in army_list.units
            }
        )
    )
    assert len(selected_datasheet_ids) == 24

    rows = ability_coverage_rows_from_catalog(
        package.army_catalog,
        datasheet_ids=selected_datasheet_ids,
    )
    unsupported = {
        (row.datasheet_id, row.ability_id, row.ability_name): (
            row.support_stage.value,
            row.runtime_consumer_ids,
        )
        for row in rows
        if row.support_stage is not AbilityCoverageSupportStage.ENGINE_CONSUMED
    }
    assert not unsupported

    court_datasheet_ids = {unit.selection.datasheet_id for unit in court.units}
    thrill_seekers = tuple(
        row
        for row in rows
        if row.datasheet_id in court_datasheet_ids
        and row.ability_id == emperors_children_army_rule.THRILL_SEEKERS_SOURCE_ABILITY_ID
    )
    assert {row.datasheet_id for row in thrill_seekers} == court_datasheet_ids
    assert all(row.source_kind is CatalogAbilitySourceKind.FACTION for row in thrill_seekers)
    assert all(
        row.semantic_categories == ("faction.army_rule.thrill_seekers",) for row in thrill_seekers
    )
    assert {consumer_id for row in thrill_seekers for consumer_id in row.runtime_consumer_ids} == {
        emperors_children_army_rule.ADVANCE_ELIGIBILITY_HOOK_ID,
        emperors_children_army_rule.CHARGE_TARGET_RESTRICTION_HOOK_ID,
        emperors_children_army_rule.FALL_BACK_ELIGIBILITY_HOOK_ID,
        emperors_children_army_rule.SHOOTING_TARGET_RESTRICTION_HOOK_ID,
    }


def test_solitaire_blitz_uses_the_live_adapter_decision_and_replay_path() -> None:
    session = LocalGameSession()
    session.start(_solitaire_blitz_game_config())
    status = session.advance_until_decision_or_terminal()
    for index in range(2):
        request = _decision_request(status, SECONDARY_MISSION_DECISION_TYPE)
        status = session.submit_option(
            request_id=request.request_id,
            option_id=request.options[0].option_id,
            result_id=f"solitaire-blitz-secondary-{index + 1}",
        )
    status = submit_all_deployments_if_pending(
        session.lifecycle,
        status,
        result_id_prefix="solitaire-blitz-deployment",
        pose_factory=_solitaire_blitz_deployment_pose,
    )
    unit_request = _decision_request(status, SELECT_MOVEMENT_UNIT_DECISION_TYPE)
    status = session.submit_option(
        request_id=unit_request.request_id,
        option_id="anvanth-blitz:solitaire",
        result_id="solitaire-blitz-select-unit",
    )
    status = _decline_stratagem_window_if_present(session, status)
    action_request = _decision_request(status, SELECT_MOVEMENT_ACTION_DECISION_TYPE)
    status = session.submit_option(
        request_id=action_request.request_id,
        option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
        result_id="solitaire-blitz-normal-move",
    )
    grant_request = _decision_request(status, SELECT_MOVEMENT_ACTION_GRANT_DECISION_TYPE)
    blitz_option, blitz_grant = _blitz_option_and_grant(grant_request)
    assert AdvanceMoveGrant.from_payload(blitz_grant.to_payload()) == blitz_grant
    assert blitz_grant.movement_bonus_dice_expression is not None
    assert blitz_grant.movement_bonus_dice_expression.canonical() == "2D6"
    assert blitz_grant.rule_frequency_usage is not None

    owner_pending = session.view(viewer_player_id="player-aeldari")["pending_decision"]
    opponent_pending = session.view(viewer_player_id="player-emperors-children")["pending_decision"]
    assert owner_pending is not None
    assert opponent_pending is not None
    assert owner_pending["request_id"] == grant_request.request_id
    assert opponent_pending == owner_pending
    json.dumps(owner_pending, sort_keys=True)

    checkpoint = session.to_persistence_payload()
    accepted = LocalGameSession.from_persistence_payload(checkpoint)
    declined = LocalGameSession.from_persistence_payload(checkpoint)
    cursor = EventStreamCursor(len(accepted.lifecycle.decision_controller.event_log.records))

    accepted_status = accepted.submit_option(
        request_id=grant_request.request_id,
        option_id=blitz_option.option_id,
        result_id="solitaire-blitz-accept",
    )
    assert accepted_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    accepted_state = accepted.lifecycle.state
    assert accepted_state is not None
    blitz_effects = tuple(
        effect
        for effect in accepted_state.persisting_effects
        if isinstance(effect.effect_payload, dict)
        and effect.effect_payload.get("effect_kind")
        == CATALOG_RANDOM_MOVEMENT_ATTACK_BOOST_EFFECT_KIND
        and effect.source_rule_id == blitz_grant.source_id
    )
    assert len(blitz_effects) == 1
    frequency_events = tuple(
        event
        for event in accepted.lifecycle.decision_controller.event_log.records
        if event.event_type == RULE_FREQUENCY_LIMIT_CONSUMED_EVENT
        and isinstance(event.payload, dict)
        and event.payload.get("usage_key") == blitz_grant.rule_frequency_usage.usage_key
    )
    assert len(frequency_events) == 1

    owner_delta = accepted.events_since(cursor, viewer_player_id="player-aeldari")
    opponent_delta = accepted.events_since(
        cursor,
        viewer_player_id="player-emperors-children",
    )
    assert owner_delta["events"] == opponent_delta["events"]
    assert any(
        event["event_type"] == "movement_action_grant_decision_resolved"
        for event in owner_delta["events"]
    )
    json.dumps(owner_delta, sort_keys=True)

    declined.submit_option(
        request_id=grant_request.request_id,
        option_id=DECLINE_MOVEMENT_ACTION_GRANT_OPTION_ID,
        result_id="solitaire-blitz-decline",
    )
    declined_state = declined.lifecycle.state
    assert declined_state is not None
    assert not any(
        isinstance(effect.effect_payload, dict)
        and effect.effect_payload.get("effect_kind")
        == CATALOG_RANDOM_MOVEMENT_ATTACK_BOOST_EFFECT_KIND
        and effect.source_rule_id == blitz_grant.source_id
        for effect in declined_state.persisting_effects
    )
    assert not any(
        event.event_type == RULE_FREQUENCY_LIMIT_CONSUMED_EVENT
        and isinstance(event.payload, dict)
        and event.payload.get("usage_key") == blitz_grant.rule_frequency_usage.usage_key
        for event in declined.lifecycle.decision_controller.event_log.records
    )

    replay_result = ReplayRunner.from_payload(
        accepted.replay_artifact(artifact_id="solitaire-blitz-adapter-replay")
    ).run()
    assert replay_result.status is ReplayRunStatus.REPRODUCED


def _solitaire_blitz_game_config() -> GameConfig:
    package = court_of_slaughter_anvanth_2026_08.catalog_package()
    catalog = package.army_catalog
    return GameConfig(
        game_id="court-of-slaughter-anvanth-solitaire-blitz",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=(
            RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
                descriptor_version="court-of-slaughter-anvanth-solitaire-blitz-2026-08"
            )
        ),
        army_catalog=catalog,
        army_muster_requests=(
            _single_unit_muster_request(
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                army_id="anvanth-blitz",
                player_id="player-aeldari",
                faction_id="aeldari",
                detachment_ids=("corsair-coterie", "path-of-the-outcast"),
                force_disposition_id="reconnaissance",
                unit_selection_id="solitaire",
                datasheet_id="000002538",
                model_profile_id="000002538:solitaire-epic-hero",
            ),
            _single_unit_muster_request(
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                army_id="court-blitz",
                player_id="player-emperors-children",
                faction_id="emperors-children",
                detachment_ids=(
                    "court-of-the-phoenician",
                    "spectacle-of-slaughter",
                ),
                force_disposition_id="purge-the-foe",
                unit_selection_id="daemon-prince",
                datasheet_id="000004086",
                model_profile_id="000004086:daemon-prince-of-slaanesh",
            ),
        ),
        player_ids=("player-aeldari", "player-emperors-children"),
        turn_order=("player-aeldari", "player-emperors-children"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=MissionSetup.from_mission_pack(
            mission_pack=warhammer_event_companion_2026_07_mission_pack(),
            mission_pool_entry_id="mission-purge-the-foe-vs-reconnaissance-layout-1",
            terrain_layout_id="purge-the-foe-vs-reconnaissance-layout-1",
            attacker_player_id="player-emperors-children",
            attacker_force_disposition_id="purge-the-foe",
            defender_player_id="player-aeldari",
            defender_force_disposition_id="reconnaissance",
        ),
        model_geometries=package.model_geometries,
    )


def _single_unit_muster_request(
    *,
    catalog_id: str,
    source_package_id: str,
    ruleset_id: RulesetId,
    army_id: str,
    player_id: str,
    faction_id: str,
    detachment_ids: tuple[str, ...],
    force_disposition_id: str,
    unit_selection_id: str,
    datasheet_id: str,
    model_profile_id: str,
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog_id,
        source_package_id=source_package_id,
        ruleset_id=ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=faction_id,
            detachment_ids=detachment_ids,
        ),
        force_disposition_id=force_disposition_id,
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id=datasheet_id,
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id=model_profile_id,
                        model_count=1,
                    ),
                ),
            ),
        ),
    )


def _solitaire_blitz_deployment_pose(
    _index: int,
    player_id: str,
    _model_instance_id: str,
) -> Pose:
    if player_id == "player-aeldari":
        return Pose.at(22.0, 5.0, 0.0, facing_degrees=0.0)
    return Pose.at(35.0, 55.0, 0.0, facing_degrees=180.0)


def _decision_request(
    status: LifecycleStatus,
    expected_decision_type: str,
) -> DecisionRequest:
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = status.decision_request
    assert request is not None
    assert request.decision_type == expected_decision_type
    return request


def _decline_stratagem_window_if_present(
    session: LocalGameSession,
    status: LifecycleStatus,
) -> LifecycleStatus:
    request = status.decision_request
    if request is None or request.decision_type != STRATAGEM_DECISION_TYPE:
        return status
    return session.submit_option(
        request_id=request.request_id,
        option_id=DECLINE_STRATAGEM_WINDOW_OPTION_ID,
        result_id="solitaire-blitz-decline-selected-to-move-stratagem",
    )


def _blitz_option_and_grant(
    request: DecisionRequest,
) -> tuple[DecisionOption, AdvanceMoveGrant]:
    for option in request.options:
        if option.option_id == DECLINE_MOVEMENT_ACTION_GRANT_OPTION_ID:
            continue
        payload = option.payload
        if not isinstance(payload, dict):
            continue
        selected = payload.get("selected_movement_action_grants")
        if not isinstance(selected, list):
            continue
        for grant_payload in selected:
            if not isinstance(grant_payload, dict):
                continue
            grant = AdvanceMoveGrant.from_payload(cast(AdvanceMoveGrantPayload, grant_payload))
            if grant.label == "Blitz":
                return option, grant
    raise AssertionError("Live Solitaire movement grant request did not expose Blitz.")


def _load_round_tripped(path: Path) -> PlayerArmyList:
    loaded = load_player_army_list(path)
    restored = player_army_list_from_json_bytes(
        json.dumps(loaded.to_payload(), sort_keys=True, separators=(",", ":")).encode()
    )
    assert restored == loaded
    return loaded


def _point_lines(calculation: Any) -> dict[str, tuple[int, int]]:
    return {
        line.unit_selection_id: (line.unit_number, line.base_points)
        for line in calculation.unit_lines
    }


def _enhancement_lines(calculation: Any) -> tuple[tuple[str, str, int, str], ...]:
    return tuple(
        (
            line.enhancement_id,
            line.target_unit_selection_id,
            line.points,
            line.source_id,
        )
        for line in calculation.enhancement_lines
    )


def _selection_id(army: ArmyDefinition, unit_instance_id: str) -> str:
    return unit_instance_id.removeprefix(f"{army.army_id}:")


def _attachment_pairs(army: ArmyDefinition) -> set[tuple[str, str]]:
    return {
        (
            _selection_id(army, formation.leader_unit_instance_ids[0]),
            _selection_id(army, formation.bodyguard_unit_instance_id),
        )
        for formation in army.attached_units
    }


def _unit(army: ArmyDefinition, selection_id: str) -> UnitInstance:
    return army.unit_by_id(f"{army.army_id}:{selection_id}")


def _wargear_counts(unit: UnitInstance) -> Counter[str]:
    return Counter(wargear_id for model in unit.own_models for wargear_id in model.wargear_ids)


def _assert_exact_court_wargear(army: ArmyDefinition) -> None:
    for selection_id in ("lord-kakophonist-1", "lord-kakophonist-2"):
        counts = _wargear_counts(_unit(army, selection_id))
        assert counts["000004084:screamer-pistol"] == 2
        assert counts["000004084:close-combat-weapon"] == 1
        assert counts["000004084:power-sword"] == 0
    for selection_id in ("noise-marines-1", "noise-marines-2"):
        counts = _wargear_counts(_unit(army, selection_id))
        assert counts["000004088:blastmaster"] == 2
        assert counts["000004088:sonic-blaster"] == 4
    tormentors = _wargear_counts(_unit(army, "tormentors"))
    assert tormentors["000004079:boltgun"] == 2
    assert tormentors["000004079:meltagun"] == 1
    assert tormentors["000004079:plasma-gun"] == 1
    assert tormentors["000004079:icon-of-excess"] == 1


def _assert_exact_anvanth_wargear(army: ArmyDefinition) -> None:
    solitaire = _wargear_counts(_unit(army, "solitaire"))
    assert solitaire["000002538:flip-belt"] == 1
    assert solitaire["000002538:solitaire-weapons"] == 1
    walkers = _wargear_counts(_unit(army, "war-walkers"))
    assert walkers["000000612:bright-lance"] == 2
    assert walkers["000000612:shuriken-cannon"] == 2
    blades = _wargear_counts(_unit(army, "wraithblades"))
    assert blades["000000598:forceshield"] == 5
    assert blades["000000598:ghostaxe"] == 5
    wraithlord = _wargear_counts(_unit(army, "wraithlord"))
    assert wraithlord["000000613:flamer"] == 2
    assert wraithlord["000000613:ghostglaive"] == 1
    assert wraithlord["000000613:bright-lance"] == 1
    assert wraithlord["000000613:starcannon"] == 1
    voidreavers = _wargear_counts(_unit(army, "corsair-voidreavers-1"))
    assert voidreavers["000002531:mistshield"] == 1
    assert voidreavers["000002531:neuro-disruptor"] == 1
    for selection_id, token_id in (
        ("warp-spiders-1", "aeldari:aspect-shrine-token"),
        ("warp-spiders-2", "aeldari:aspect-shrine-token"),
        ("fire-dragons", "aeldari:aspect-shrine-token"),
        ("swooping-hawks", "aeldari:aspect-shrine-token"),
    ):
        assert {
            allocation.resource_kind: allocation.amount
            for allocation in _unit(army, selection_id).starting_resources
        } == {token_id: 1}


def _capability_status(row: Any, dimension: str) -> str:
    result = next(result for result in row["capabilities"] if result["dimension"] == dimension)
    return cast(str, result["status"])
