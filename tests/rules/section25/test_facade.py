"""Public prebattle roster disclosure, real submission and persistence."""

import json
from dataclasses import replace
from typing import cast

import pytest

from tests.support.section25_fixtures import BODY, UPGRADE, assignment, request, selection
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.projection import GameViewPayload
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)


@pytest.fixture(scope="session")
def section25_mission() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-purge-the-foe-vs-purge-the-foe-layout-3",
        terrain_layout_id="purge-the-foe-vs-purge-the-foe-layout-3",
        attacker_player_id="owner",
        defender_player_id="opponent",
        attacker_force_disposition_id="purge-the-foe",
        defender_force_disposition_id="purge-the-foe",
    )


@pytest.mark.parametrize("first", ["owner", "opponent"])
def test_prebattle_public_roster_submission_and_json_restoration(
    section25_catalog: ArmyCatalog,
    section25_mission: MissionSetup,
    first: str,
) -> None:
    c = section25_catalog
    units = (selection(c, "commander"), selection(c, "body", BODY))
    r = request(c, units=units, assignments=(assignment(units[1], UPGRADE),))
    config = GameConfig(
        game_id=f"s25-{first}",
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(),
        army_catalog=c,
        army_muster_requests=(r, replace(r, army_id="s25-enemy", player_id="opponent")),
        player_ids=("owner", "opponent"),
        turn_order=(first, "opponent" if first == "owner" else "owner"),
        fixed_secondary_mission_ids=("area-denial", "assassination"),
        mission_setup=section25_mission,
    )
    session = LocalGameSession()
    session.start(config)
    status = session.advance_until_decision_or_terminal()
    pending = status.decision_request
    assert pending is not None
    state = session.lifecycle.state
    assert state is not None
    assert all(a.roster_legality_report.is_legal for a in state.army_definitions)
    assert all(
        len(a.enhancement_assignments) == 1 and a.warlord_selection is not None
        for a in state.army_definitions
    )
    for viewer, prefix in [("owner", "s25-enemy"), ("opponent", "s25-army")]:
        view = session.view(viewer_player_id=viewer)
        unit = view["unit_display_by_id"][f"{prefix}:body"]
        assert unit["datasheet_id"] == BODY
        assert len(unit["model_instance_ids"]) == 5
        assert unit["selected_wargear_ids"] == ["core-bolt-rifle"]
    persisted = json.loads(json.dumps(session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(persisted)
    assert restored.lifecycle.to_payload() == session.lifecycle.to_payload()
    for viewer in config.player_ids:
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
        assert restored.events_since(
            EventStreamCursor(), viewer_player_id=viewer
        ) == session.events_since(EventStreamCursor(), viewer_player_id=viewer)
    option = pending.options[0]
    result = session.submit_option(
        request_id=pending.request_id, option_id=option.option_id, result_id="s25:public-submit"
    )
    restored_result = restored.submit_option(
        request_id=pending.request_id, option_id=option.option_id, result_id="s25:public-submit"
    )
    assert result == restored_result
    assert session.lifecycle.to_payload() == restored.lifecycle.to_payload()
    bad = replace(
        r,
        enhancement_assignments=(assignment(units[1]),),
        detachment_selection=replace(
            r.detachment_selection, enhancement_ids=("s25-enhancement-0",)
        ),
    )
    rejected = LocalGameSession()
    rejected.start(
        replace(
            config,
            army_muster_requests=(
                bad,
                next(a for a in config.army_muster_requests if a.player_id == "opponent"),
            ),
        )
    )
    with pytest.raises(GameLifecycleError, match=r"muster|roster"):
        rejected.advance_until_decision_or_terminal()


@pytest.mark.parametrize("first", ["owner", "opponent"])
def test_native_roster_disclosure_distinguishes_physical_upgrade_bearers(
    section25_catalog: ArmyCatalog,
    section25_mission: MissionSetup,
    first: str,
) -> None:
    """Normal Core facade path; constructed catalog is not native provider admission."""
    from warhammer40k_core.adapters.access_control import AuthenticatedPrincipal, PrincipalRole
    from warhammer40k_core.engine.list_validation import AttachmentDeclaration
    from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus

    c = section25_catalog
    units = (selection(c, "commander"), selection(c, "body", BODY))
    base = replace(
        request(c, units=units, assignments=(assignment(units[1], UPGRADE),)),
        attachment_declarations=(AttachmentDeclaration("commander", "body"),),
    )
    requests = (base, replace(base, enhancement_assignments=(assignment(units[0], UPGRADE),)))
    views: list[GameViewPayload] = []
    for roster in requests:
        config = GameConfig(
            game_id=f"s25-disclosure-{first}",
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(),
            army_catalog=c,
            army_muster_requests=(roster, replace(base, army_id="s25-enemy", player_id="opponent")),
            player_ids=("owner", "opponent"),
            turn_order=(first, "opponent" if first == "owner" else "owner"),
            fixed_secondary_mission_ids=("area-denial", "assassination"),
            mission_setup=section25_mission,
        )
        session = LocalGameSession()
        session.start(config)
        assert session.advance_until_decision_or_terminal().decision_request is not None
        before = session.lifecycle.to_payload()
        view = session.view(viewer_player_id="opponent")
        assert "public_army_rosters" in view
        public = next(row for row in view["public_army_rosters"] if row["player_id"] == "owner")
        recorded = cast(dict[str, JsonValue], roster.to_payload())
        for key in (
            "army_id",
            "player_id",
            "catalog_id",
            "source_package_id",
            "ruleset_id",
            "battle_size",
            "detachment_selection",
            "force_disposition_id",
            "unit_selections",
            "unit_points",
            "enhancement_point_values",
            "points_source_package_id",
            "enhancement_assignments",
            "warlord_selection",
        ):
            assert public[key] == recorded[key]
        assert public["attachment_declarations"] is None
        assert public["dedicated_transport_manifests"] is None
        bearer = roster.enhancement_assignments[0]
        target_id = f"{roster.army_id}:{bearer.target_unit_selection_id}"
        physical = sorted(
            mid
            for mid in view["unit_display_by_id"][target_id]["model_instance_ids"]
            if view["model_display_by_id"][mid]["model_profile_id"] == bearer.model_profile_id
        )[bearer.model_index - 1]
        assert view["model_display_by_id"][physical]["unit_instance_id"] == target_id
        for role in PrincipalRole:
            player = "opponent" if role in (PrincipalRole.PLAYER, PrincipalRole.COACH) else None
            context = AuthenticatedPrincipal("s25-public", role, player).bind_to_session(
                player_ids=config.player_ids
            )
            projected = session.view_for_context(viewer=context)
            assert "public_army_rosters" in projected
            row = next(r for r in projected["public_army_rosters"] if r["player_id"] == "owner")
            assert row["enhancement_assignments"] == recorded["enhancement_assignments"]
            assert row["attachment_declarations"] == (
                recorded["attachment_declarations"] if context.policy.omniscient else None
            )
        owner = session.view(viewer_player_id="owner")
        assert "public_army_rosters" in owner
        assert (
            next(r for r in owner["public_army_rosters"] if r["player_id"] == "owner")[
                "attachment_declarations"
            ]
            == recorded["attachment_declarations"]
        )
        restored = LocalGameSession.from_persistence_payload(
            json.loads(json.dumps(session.to_persistence_payload()))
        )
        assert restored.view(viewer_player_id="opponent") == view
        fork = session.fork()
        assert fork.view(viewer_player_id="opponent") == view
        assert fork.lifecycle.state is not session.lifecycle.state
        replay = ReplayRunner.from_payload(
            json.loads(json.dumps(session.replay_artifact(artifact_id="s25:roster")))
        ).run()
        assert replay.status is ReplayRunStatus.REPRODUCED
        assert session.lifecycle.to_payload() == before
        views.append(view)
    assert views[0] != views[1]
    assert views[0]["projection_state_hash"] != views[1]["projection_state_hash"]
    excluded = {"public_army_rosters", "projection_state_hash"}
    assert {k: v for k, v in views[0].items() if k not in excluded} == {
        k: v for k, v in views[1].items() if k not in excluded
    }
