"""Native admission and staged deployment of the exact v995 Monster Mash export."""

from collections import Counter

from tests.support.monster_mash_v995 import (
    CAVALCADE_PLAYER,
    MONSTER_MASH_PLAYER,
    begin_staged_deployment,
    monster_mash_vs_cavalcade_config,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.phase import GameLifecycleStage, SetupStep
from warhammer40k_core.engine.replay import ReplayRunner
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_daemons_cavalcade_2026_11,
    chaos_daemons_monster_mash_2026_11,
)

# Each weapon key is one item, with the exact number of available attack profiles.
_EXPORT = {
    "belakor": (390, {"belakor-epic-hero": 1}, {"betraying-shades": 2, "the-blade-of-shadows": 2}),
    "kairos-fateweaver": (
        305,
        {"kairos-fateweaver-epic-hero": 1},
        {"infernal-gateway": 2, "staff-of-tomorrow": 1},
    ),
    "rotigus": (280, {"rotigus-epic-hero": 1}, {"gnarlrod": 2, "streams-of-brackish-filth": 1}),
    "shalaxi-helbane": (
        315,
        {"shalaxi-helbane-epic-hero": 1},
        {"lash-of-slaanesh": 1, "pavane-of-slaanesh": 2, "snapping-claws": 1, "soulpiercer": 1},
    ),
    "skarbrand": (
        330,
        {"skarbrand-epic-hero": 1},
        {"bellow-of-endless-fury": 1, "slaughter-and-carnage": 2},
    ),
    "bloodletters": (110, {"bloodreaper": 1, "bloodletters": 9}, {"hellblade": 1}),
    "plaguebearers": (115, {"plagueridden": 1, "plaguebearers": 9}, {"plaguesword": 1}),
    "flamers": (65, {"pyrocaster": 1, "flamers": 2}, {"flamer-mouths": 1, "flickering-flames": 1}),
    "seekers": (85, {"heartseeker": 1, "seekers": 4}, {"lashing-tongue": 1, "slashing-claws": 1}),
}


def test_exact_monster_mash_admission_deployment_and_replay() -> None:
    session = LocalGameSession()
    session.start(monster_mash_vs_cavalcade_config())
    status = begin_staged_deployment(session)

    state = session.lifecycle.state
    assert state is not None
    assert state.stage is GameLifecycleStage.SETUP
    assert state.current_setup_step is SetupStep.DEPLOY_ARMIES
    mission = state.mission_setup
    assert mission is not None
    assert mission.primary_mission_id_for_player(MONSTER_MASH_PLAYER) == "primary-immovable-object"
    assert mission.primary_mission_id_for_player(CAVALCADE_PLAYER) == "primary-unstoppable-force"
    monster_mash, cavalry = state.army_definitions
    assert monster_mash.player_id == MONSTER_MASH_PLAYER
    assert cavalry.player_id == CAVALCADE_PLAYER
    assert monster_mash.force_disposition_id == "take-and-hold"
    assert cavalry.force_disposition_id == "purge-the-foe"
    assert len(cavalry.units) == 9
    assert sum(len(unit.own_models) for unit in cavalry.units) == 39
    assert sum(line.points for line in cavalry.unit_points) == 1945
    assert sum(line.points for line in cavalry.enhancement_point_values) == 55
    _assert_monster_mash_export(monster_mash)
    _assert_retained_cavalcade_rows_and_geometry()

    battlefield = state.battlefield_state
    assert battlefield is not None
    placed = tuple(unit for army in battlefield.placed_armies for unit in army.unit_placements)
    assert {unit.unit_instance_id for unit in placed} == {
        "monster-mash-a:kairos-fateweaver",
        "cavalcade-b:belakor",
    }
    assert sum(len(unit.model_placements) for unit in placed) == 2
    assert status.decision_request is not None
    assert status.decision_request.decision_type == "select_deployment_unit"
    assert status.decision_request.actor_id == CAVALCADE_PLAYER

    stored = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(stored)
    assert restored.to_persistence_payload() == stored
    for player in (MONSTER_MASH_PLAYER, CAVALCADE_PLAYER):
        assert restored.view(viewer_player_id=player) == session.view(viewer_player_id=player)

    replay = ReplayRunner.from_payload(
        session.replay_artifact(artifact_id="monster-mash-v995-staged-deployment")
    ).run()
    assert replay.reproduced_exactly, replay.to_payload()
    assert replay.reproduced_decision_count == session.decision_record_count() == 8


def _assert_monster_mash_export(army: ArmyDefinition) -> None:
    package = chaos_daemons_monster_mash_2026_11.catalog_package()
    catalog = package.army_catalog
    (detachment,) = (
        row for row in catalog.detachments if row.detachment_id == "daemonic-incursion"
    )
    assert detachment.detachment_point_cost == 3
    assert set(detachment.force_disposition_ids) == {"take-and-hold", "disruption"}
    assert army.detachment_selection.detachment_ids == ("daemonic-incursion",)
    assert army.roster_legality_report.is_legal
    assert not army.attached_units
    assert not army.enhancement_assignments
    assert not army.dedicated_transport_manifests
    assert army.battle_size.value == "strike_force"
    assert army.warlord_selection is not None
    assert army.warlord_selection.unit_selection_id == "belakor"
    assert len(army.units) == 9
    assert sum(len(unit.own_models) for unit in army.units) == 33
    assert sum(line.points for line in army.unit_points) == 1995
    assert {line.unit_selection_id: line.points for line in army.unit_points} == {
        unit_name: expected[0] for unit_name, expected in _EXPORT.items()
    }
    wargear = {row.wargear_id: row for row in catalog.wargear}
    for unit in army.units:
        selection = unit.unit_instance_id.removeprefix("monster-mash-a:")
        _, models, weapons = _EXPORT[selection]
        assert Counter(model.model_profile_id.split(":")[1] for model in unit.own_models) == models
        for model in unit.own_models:
            equipped = tuple(wargear[wargear_id] for wargear_id in model.wargear_ids)
            assert len(model.wargear_ids) == len(set(model.wargear_ids))
            assert {
                row.wargear_id.split(":")[1]: len(row.weapon_profiles)
                for row in equipped
                if row.weapon_profiles
            } == weapons
        if selection in {"bloodletters", "plaguebearers", "seekers"}:
            icon, instrument = (
                [
                    model
                    for model in unit.own_models
                    if f"{unit.datasheet_id}:{item}" in model.wargear_ids
                ]
                for item in ("daemonic-icon", "instrument-of-chaos")
            )
            assert len(icon) == len(instrument) == 1
            assert icon[0].model_instance_id != instrument[0].model_instance_id
            assert (
                icon[0].model_profile_id
                == instrument[0].model_profile_id
                == (f"{unit.datasheet_id}:{selection}")
            )


def _assert_retained_cavalcade_rows_and_geometry() -> None:
    previous = chaos_daemons_cavalcade_2026_11.catalog_package()
    current = chaos_daemons_monster_mash_2026_11.catalog_package()
    assert all(
        current.army_catalog.datasheet_by_id(row.datasheet_id) == row
        for row in previous.army_catalog.datasheets
    )
    geometries = {row.model_profile_id: row for row in current.model_geometries}
    assert all(geometries[row.model_profile_id] == row for row in previous.model_geometries)
