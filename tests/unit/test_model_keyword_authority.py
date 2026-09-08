from dataclasses import replace

import pytest
from tests.model_keyword_helpers import mixed_keyword_catalog, mixed_keyword_unit

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.model_keywords import ModelKeywordError
from warhammer40k_core.engine.rules_units import RulesUnitComponent, RulesUnitView
from warhammer40k_core.engine.unit_factory import UnitInstance


def test_removed_specialist_stops_contributing_without_expiring_component() -> None:
    unit = mixed_keyword_unit()
    specialist = next(model for model in unit.own_models if "PSYKER" in model.keywords)
    assert "PSYKER" in unit.keywords
    dead = replace(
        unit,
        own_models=tuple(
            replace(model, wounds_remaining=0) if model == specialist else model
            for model in unit.own_models
        ),
    )
    view = RulesUnitView(
        unit_instance_id=unit.unit_instance_id,
        owner_player_id="player-a",
        components=(RulesUnitComponent(unit=dead, role="unit"),),
    )
    assert view.living_components == view.components
    assert "PSYKER" not in dead.keywords
    assert "PSYKER" not in view.keywords
    retained = replace(view, retained_model_ids=(specialist.model_instance_id,))
    assert "PSYKER" in retained.keywords
    assert UnitInstance.from_payload(dead.to_payload()) == dead
    revived = replace(dead, own_models=unit.own_models)
    assert "PSYKER" in revived.keywords
    assert specialist.keyword_assignment.source_ids == ("core-keyword-specialist:keyword-source",)


def test_catalog_requires_complete_unambiguous_model_keyword_scope() -> None:
    catalog = mixed_keyword_catalog()
    assert ArmyCatalog.from_payload(catalog.to_payload()) == catalog
    with pytest.raises(ModelKeywordError, match="complete"):
        replace(catalog, model_keyword_assignments=catalog.model_keyword_assignments[:1])
    with pytest.raises(ModelKeywordError, match="duplicate"):
        replace(
            catalog,
            model_keyword_assignments=(
                *catalog.model_keyword_assignments,
                catalog.model_keyword_assignments[0],
            ),
        )


@pytest.mark.integration
@pytest.mark.parametrize("retained", [False, True])
def test_keyword_casualty_facade_restore_replay_and_both_viewers(retained: bool) -> None:
    import copy
    import json

    from tests.model_keyword_helpers import mixed_keyword_shooting_session
    from tests.model_keyword_target_helpers import assert_keyword_target_eligibility
    from tests.psychic_modifier_helpers import pending_request, submit_fixture_request

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.decision_request import DecisionError
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatusKind
    from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner, ReplayRunStatus
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    session, model_id = mixed_keyword_shooting_session(retained=retained)
    pending_request(session)
    initial = session.lifecycle.to_payload()
    assert_keyword_target_eligibility(session, present=True)
    accepted_retention = False
    for _ in range(45):
        state = session.lifecycle.state
        assert state is not None
        assert state.battlefield_state is not None
        if model_id in state.battlefield_state.removed_model_ids:
            break
        request = pending_request(session)
        if request.decision_type == "select_damage_allocation_model":
            option = next(option for option in request.options if option.option_id == model_id)
            status = session.submit_option(
                request_id=request.request_id,
                result_id=f"{request.request_id}:specialist",
                option_id=option.option_id,
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID
        elif request.decision_type == "select_destruction_reaction":
            before = session.lifecycle.to_payload()
            with pytest.raises(DecisionError, match="finite action space"):
                session.submit_option(
                    request_id=request.request_id,
                    result_id="order31-malformed",
                    option_id="unoffered-keyword-choice",
                )
            assert session.lifecycle.to_payload() == before
            session.submit_option(
                request_id=request.request_id,
                result_id="order31-retain",
                option_id="order31-retention",
            )
            accepted_retention = True
            state = session.lifecycle.state
            assert state is not None
            view = rules_unit_view_by_id(state=state, unit_instance_id="army-beta:enemy")
            assert "PSYKER" in view.keywords
            assert_keyword_target_eligibility(session, present=True)
            assert not next(m for m in view.own_models if m.model_instance_id == model_id).is_alive
            for viewer in ("player-a", "player-b"):
                projection = session.view(viewer_player_id=viewer)
                assert "PSYKER" in projection["unit_display_by_id"]["army-beta:enemy"]["keywords"]
            checkpoint = session.lifecycle.to_payload()
            session = LocalGameSession(lifecycle=GameLifecycle.from_payload(checkpoint))
            assert session.lifecycle.to_payload() == checkpoint
            assert_keyword_target_eligibility(session, present=True)
        elif accepted_retention and request.decision_type == "select_shooting_unit":
            session.submit_option(
                request_id=request.request_id,
                result_id=f"{request.request_id}:finish",
                option_id="complete_shooting_phase",
            )
        else:
            submit_fixture_request(session, request)
    else:
        raise AssertionError("Specialist removal was not reached.")
    assert accepted_retention is retained
    state = session.lifecycle.state
    assert state is not None
    view = rules_unit_view_by_id(state=state, unit_instance_id="army-beta:enemy")
    assert len(view.alive_models()) == 2
    assert "PSYKER" not in view.keywords
    assert_keyword_target_eligibility(session, present=False)
    for viewer in ("player-a", "player-b"):
        projection = session.view(viewer_player_id=viewer)
        assert "PSYKER" not in projection["unit_display_by_id"]["army-beta:enemy"]["keywords"]
        assert projection["model_display_by_id"][model_id]["keywords"] == [
            "BATTLELINE",
            "INFANTRY",
            "PSYKER",
        ]
        assert "object at 0x" not in json.dumps(projection, sort_keys=True)
    checkpoint = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(checkpoint).to_payload() == checkpoint
    forged = copy.deepcopy(checkpoint)
    models = forged["state"]["army_definitions"][1]["units"][0]["own_models"]
    models[0]["keyword_assignment"]["source_ids"] = ["forged-keyword-source"]
    with pytest.raises(GameLifecycleError):
        GameLifecycle.from_payload(forged)
    session.advance_until_decision_or_terminal()
    artifact = ReplayArtifact.capture(
        artifact_id="order31-casualty",
        initial_lifecycle_payload=initial,
        final_lifecycle=session.lifecycle,
    )
    replay = ReplayRunner.from_payload(artifact.to_payload()).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, json.dumps(replay.to_payload())


@pytest.mark.parametrize("scope", ["Jakhal Pack Leader", "JAKHAL PACK LEADERS"])
def test_scoped_source_keyword_rows_survive_bridge_catalog_and_factory(scope: str) -> None:
    from tests.support.wahapedia_bridge_fixtures import jakhals_bridge_artifacts
    from tests.support.wahapedia_source_fixtures import catalog_package_id, catalog_version

    from warhammer40k_core.engine.list_validation import UnitMusterSelection
    from warhammer40k_core.engine.unit_factory import UnitFactory
    from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
    from warhammer40k_core.rules.catalog_generation import build_canonical_catalog_package
    from warhammer40k_core.rules.wahapedia_bridge import WahapediaBridgeError

    package = build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=jakhals_bridge_artifacts(keyword_scope=scope),
    )
    catalog = package.army_catalog
    assert len(catalog.model_keyword_assignments) == 3
    sheet = catalog.datasheets[0]
    unit = UnitFactory(catalog=catalog, model_geometries=package.model_geometries).instantiate_unit(
        army_id="keyword-bridge",
        datasheet=sheet,
        selection=UnitMusterSelection(
            unit_selection_id="unit",
            datasheet_id=sheet.datasheet_id,
            model_profile_selections=tuple(
                ModelProfileSelection(model_profile_id=p.model_profile_id, model_count=p.min_models)
                for p in sheet.composition
            ),
        ),
    )
    owners = tuple(model for model in unit.own_models if "GRENADES" in model.keywords)
    assert len(owners) == 1
    assert owners[0].name == "Jakhal Pack Leader"
    assert any(
        "Datasheets_keywords:" in source for source in owners[0].keyword_assignment.source_ids
    )
    dead = replace(
        unit,
        own_models=tuple(
            replace(m, wounds_remaining=0) if m == owners[0] else m for m in unit.own_models
        ),
    )
    assert "GRENADES" not in dead.keywords
    assert UnitInstance.from_payload(dead.to_payload()) == dead
    with pytest.raises(WahapediaBridgeError, match="exact composition owner"):
        jakhals_bridge_artifacts(keyword_scope="unknown-model")


@pytest.mark.parametrize("field", ["keywords", "faction_keywords", "source_ids"])
def test_runtime_keyword_authority_rejects_malformed_inventories(field: str) -> None:
    from typing import Any, cast

    from warhammer40k_core.core.model_keywords import ModelKeywordAssignment
    from warhammer40k_core.engine.unit_factory import ModelInstance, UnitFactoryError

    model = mixed_keyword_unit().own_models[0]
    payload = cast(Any, model.keyword_assignment.to_payload())
    payload[field] = "not-an-array"
    with pytest.raises(ModelKeywordError, match="string lists"):
        ModelKeywordAssignment.from_payload(payload)
    runtime = cast(Any, model.to_payload())
    del runtime["keyword_assignment"]
    with pytest.raises(UnitFactoryError, match="requires keyword_assignment"):
        ModelInstance.from_payload(runtime)
    unit = mixed_keyword_unit()
    unit_payload = unit.to_payload()
    unit_payload["keywords"] = []
    with pytest.raises(UnitFactoryError, match="projection"):
        UnitInstance.from_payload(unit_payload)


def test_model_keyword_source_is_pinned_and_executable() -> None:
    from warhammer40k_core.rules.source_packages.artifact_loader import package_artifact_bytes
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        core_model_keywords_2026_09 as source,
    )

    assert source.source_package().source_catalog.documents
    (rule,) = source.source_rules()
    assert rule.source_id == source.DESTROYED_MODEL_KEYWORDS_SOURCE_ID
    assert rule.semantic_execution_status == "executable_engine_runtime"
    assert source.source_evidence_records()
    raw = package_artifact_bytes(source.__name__, "artifacts/package.json")
    with pytest.raises(source.ModelKeywordsSourceError, match="reviewed pin"):
        source.validate_source_artifact_bytes(raw + b" ")


def test_split_successors_keep_only_their_models_keyword_authority() -> None:
    from tests.model_keyword_helpers import mixed_keyword_shooting_session

    from warhammer40k_core.engine.army_mustering import ArmyDefinition
    from warhammer40k_core.engine.rules_units import rules_unit_views_from_armies
    from warhammer40k_core.engine.unit_splitting import build_split_army

    session, model_id = mixed_keyword_shooting_session()
    state = session.lifecycle.state
    assert state is not None
    army = state.army_definitions[1]
    unit = army.units[0]
    split = build_split_army(
        army=army,
        unit_instance_id=unit.unit_instance_id,
        first_model_ids=(model_id,),
        request_id="keyword-split",
        source_id="keyword-split-source",
        specified_strengths=None,
    )
    views = rules_unit_views_from_armies(armies=(split,))
    assert sum("PSYKER" in view.keywords for view in views) == 1
    owner = next(view for view in views if "PSYKER" in view.keywords)
    assert owner.own_models[0].model_instance_id == model_id
    assert ArmyDefinition.from_payload(split.to_payload()) == split


def test_model_scoped_rolls_and_visibility_use_the_exact_model_owner() -> None:
    from warhammer40k_core.engine.catalog_model_scope import scoped_roll_model_ids_for_effect
    from warhammer40k_core.engine.shooting_terrain_visibility import (
        model_visibility_keywords_for_rules_unit,
    )
    from warhammer40k_core.geometry.pose import Pose
    from warhammer40k_core.geometry.volume import Model, ModelVolume

    unit = mixed_keyword_unit()
    view = RulesUnitView(
        unit_instance_id=unit.unit_instance_id,
        owner_player_id="player-a",
        components=(RulesUnitComponent(unit=unit, role="unit"),),
    )
    specialist = next(model for model in unit.own_models if "PSYKER" in model.keywords)
    assert scoped_roll_model_ids_for_effect(
        source_rules_unit=view,
        current_roll_model_instance_ids=unit.own_model_ids(),
        effect_parameters={"required_model_keyword": "PSYKER"},
    ) == (specialist.model_instance_id,)
    geometry = tuple(
        Model(
            model_id=model.model_instance_id,
            pose=Pose.at(10 + index, 10),
            base=model.geometry.base_shape(),
            volume=ModelVolume(height=model.geometry.height_inches),
        )
        for index, model in enumerate(unit.own_models)
    )
    visibility_keywords = dict(
        model_visibility_keywords_for_rules_unit(rules_unit=view, models=geometry)
    )
    assert {
        model_id for model_id, keywords in visibility_keywords.items() if "PSYKER" in keywords
    } == {specialist.model_instance_id}
    from warhammer40k_core.engine.phase import GameLifecycleError

    with pytest.raises(GameLifecycleError, match="not in the rules unit"):
        view.model_by_id("unknown-model")


def test_model_keyword_lineage_and_materialization_identity_fail_closed() -> None:
    from warhammer40k_core.core.model_keywords import model_keyword_assignment
    from warhammer40k_core.engine.unit_factory import UnitFactoryError

    catalog = mixed_keyword_catalog()
    assignment = catalog.model_keyword_assignments[0]
    for invalid in (
        replace(assignment, datasheet_id="unknown-sheet"),
        replace(assignment, model_profile_id="unknown-profile"),
    ):
        with pytest.raises(ModelKeywordError, match="unknown lineage"):
            replace(catalog, model_keyword_assignments=(invalid,))
    with pytest.raises(ModelKeywordError, match="union"):
        replace(
            catalog,
            model_keyword_assignments=tuple(
                replace(row, keywords=(*row.keywords, "UNKNOWN"))
                for row in catalog.model_keyword_assignments
            ),
        )
    variant = replace(assignment, materialization_descriptor_id="source-backed-variant")
    catalog = replace(
        catalog, model_keyword_assignments=(*catalog.model_keyword_assignments, variant)
    )
    assert ArmyCatalog.from_payload(catalog.to_payload()) == catalog
    sheet = catalog.datasheet_by_id(assignment.datasheet_id)
    assert (
        model_keyword_assignment(
            datasheet=sheet,
            model_profile_id=assignment.model_profile_id,
            assignments=catalog.model_keyword_assignments,
            materialization_descriptor_id="source-backed-variant",
        )
        == variant
    )
    with pytest.raises(ModelKeywordError, match="unknown materialization"):
        model_keyword_assignment(
            datasheet=sheet,
            model_profile_id=assignment.model_profile_id,
            assignments=catalog.model_keyword_assignments,
            materialization_descriptor_id="forged-variant",
        )
    model = next(
        m
        for m in mixed_keyword_unit().own_models
        if m.model_profile_id == assignment.model_profile_id
    )
    with pytest.raises(UnitFactoryError, match="materialization source identity"):
        replace(model, keyword_assignment=variant)
