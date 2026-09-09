"""Real facade-ready fixtures for the geometrically justified P06C counterexamples."""

from __future__ import annotations

from dataclasses import replace

from tests.phase13b_shooting_declaration_helpers import (
    _canonical_catalog,
    _compact_intercessor_catalog,
    _config,
    _configure_shooting_battle_state,
    _display_geometry,
    _mustered_armies,
    _scenario_with_unit_pose,
    _state,
)
from tests.retained_attack_helpers import lethal_retained_attack_catalog
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.model_geometry_catalog import (
    GeometryEvidenceKind,
    GeometryMeasurementKind,
    GeometryRulesFootprintPolicy,
    GeometrySourceUnits,
    ModelFootprintDefinition,
    ModelFootprintKind,
    ModelFootprintPartDefinition,
    ModelGeometryCatalogRecord,
    ModelGeometrySourceEvidence,
    ModelHeightDefinition,
)
from warhammer40k_core.core.ruleset_descriptor import TerrainFeatureKind
from warhammer40k_core.engine.damage_allocation import (
    DestructionReactionKind,
    DestructionReactionSource,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainWallDefinition
from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleCondition,
    RuleConditionKind,
    RuleTargetKind,
    RuleTargetSpec,
    parameters_from_pairs,
)


def retained_observer_session(*, attached: bool) -> tuple[LocalGameSession, str, str]:
    """A lethal facade shot leaves a retained-only component beside a blocked Leader."""
    catalog = _compact_intercessor_catalog(lethal_retained_attack_catalog())
    enemy_specs: tuple[tuple[str, str, str, int], ...] = (
        ("enemy", "core-intercessor-like-infantry", "core-intercessor-like", 1),
    )
    if attached:
        enemy_specs += (("leader", "core-character-leader", "core-character-leader", 1),)
    config = _config(
        game_id=f"r32-retained-observer:{attached}",
        alpha_unit_ids=("intercessor-1", "intercessor-2"),
        alpha_datasheets=None,
        alpha_unit_specs=tuple(
            (key, "core-intercessor-like-infantry", "core-intercessor-like", 1)
            for key in ("intercessor-1", "intercessor-2")
        ),
        enemy_datasheet=None,
        enemy_unit_specs=enemy_specs,
        enemy_attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="leader", bodyguard_unit_selection_id="enemy"
            ),
        )
        if attached
        else (),
        catalog=catalog,
    )
    display = _display_geometry(
        center_x_inches=15, center_y_inches=10, width_inches=0.1, depth_inches=2.2
    )
    feature = TerrainFeatureDefinition(
        feature_id="r32-observer-wall",
        feature_kind=TerrainFeatureKind.HILLS,
        footprint_center_x_inches=15,
        footprint_center_y_inches=10,
        footprint_width_inches=0.1,
        footprint_depth_inches=2.2,
        rules_footprint_polygon=display.footprint_polygon,
        display_geometry=display,
        walls=(TerrainWallDefinition("wall", 15, 10, 0, 0.1, 2.2, 3),),
        source_id="r32-retained-observer-geometry",
    )
    assert config.mission_setup is not None
    config = replace(
        config,
        mission_setup=replace(config.mission_setup, terrain_features=(feature,)),
        model_geometries=tuple(
            _analytic_geometry(profile, 0.5)
            for profile in ("core-intercessor-like", "core-character-leader")
        ),
    )
    armies = _mustered_armies(config)
    units = {unit.unit_instance_id.split(":", 1)[1]: unit for army in armies for unit in army.units}
    assert config.mission_setup is not None
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="r32-observer-battlefield",
        armies=armies,
        battlefield_width_inches=config.mission_setup.battlefield_width_inches,
        battlefield_depth_inches=config.mission_setup.battlefield_depth_inches,
    )
    poses = {
        "intercessor-1": (10.0, 10.0),
        "intercessor-2": (10.0, 30.0),
        "enemy": (20.0, 13.0),
        "leader": (20.0, 10.0),
    }
    for army in armies:
        for unit in army.units:
            key = unit.unit_instance_id.split(":", 1)[1]
            scenario = _scenario_with_unit_pose(
                scenario=scenario,
                unit=unit,
                army_id=army.army_id,
                player_id=army.player_id,
                poses=(Pose.at(*poses[key]),),
            )
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    state = _state(lifecycle)
    _configure_shooting_battle_state(
        state=state,
        decisions=lifecycle.decision_controller,
        armies=armies,
        battlefield=replace(scenario.battlefield_state, terrain_features=(feature,)),
        units=units,
        embarked_unit_ids=(),
    )
    observer_id = units["enemy"].own_models[0].model_instance_id
    state.record_model_destruction_reaction_sources(
        model_instance_id=observer_id,
        sources=(
            DestructionReactionSource(
                source_id="r32-retain-observer",
                source_rule_id="r32-retain-observer",
                reaction_kind=DestructionReactionKind.FIGHT_ON_DEATH,
            ),
        ),
    )
    return (
        LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle.to_payload())),
        observer_id,
        units["intercessor-1"].unit_instance_id,
    )


def visible_enemy_selection(*, observer: str) -> RuleClause:
    """Typed visibility condition for the real generic target-eligibility consumer."""
    text = "Select one enemy unit visible to this unit."
    span = TextSpan(text=text, start=0, end=len(text))
    return RuleClause(
        clause_id="r32-visible-enemy",
        template_id="phase17c:selected-target-constraint",
        source_span=span,
        target=RuleTargetSpec(
            kind=RuleTargetKind.ENEMY_UNIT,
            source_span=span,
            parameters=parameters_from_pairs((("allegiance", "enemy"),)),
        ),
        conditions=(
            RuleCondition(
                kind=RuleConditionKind.VISIBILITY_PREDICATE,
                source_span=span,
                parameters=parameters_from_pairs(
                    (
                        ("observer", observer),
                        ("predicate", "visible_to"),
                        ("target_reference", "selected_unit"),
                    )
                ),
            ),
        ),
    )


def counterexample_session(kind: str) -> tuple[LocalGameSession, str, str]:
    if kind not in {"opening", "partial"}:
        raise ValueError("Unsupported Order 32 counterexample.")
    catalog = _compact_intercessor_catalog(_canonical_catalog())
    config = _config(
        game_id=f"order32:{kind}",
        alpha_unit_ids=("intercessor-1",),
        alpha_datasheets=None,
        alpha_unit_specs=(
            ("intercessor-1", "core-intercessor-like-infantry", "core-intercessor-like", 1),
        ),
        enemy_datasheet=("core-character-leader", "core-character-leader", 1),
        catalog=catalog,
    )
    feature = _counterexample_feature(kind)
    assert config.mission_setup is not None
    config = replace(
        config,
        mission_setup=replace(config.mission_setup, terrain_features=(feature,)),
        model_geometries=(
            _analytic_geometry("core-intercessor-like", 0.001 if kind == "partial" else 0.5),
            _analytic_geometry("core-character-leader", 0.5),
        ),
    )
    armies = _mustered_armies(config)
    units = {unit.unit_instance_id.split(":", 1)[1]: unit for army in armies for unit in army.units}
    assert config.mission_setup is not None
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id=f"order32:{kind}:battlefield",
        battlefield_width_inches=config.mission_setup.battlefield_width_inches,
        battlefield_depth_inches=config.mission_setup.battlefield_depth_inches,
        armies=armies,
    )
    for label, army, player, x in (
        ("intercessor-1", "army-alpha", "player-a", 13.0),
        ("enemy", "army-beta", "player-b", 19.0),
    ):
        scenario = _scenario_with_unit_pose(
            scenario=scenario,
            unit=units[label],
            army_id=army,
            player_id=player,
            poses=(Pose.at(x, 20.0),),
        )
    battlefield = replace(scenario.battlefield_state, terrain_features=(feature,))
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    _configure_shooting_battle_state(
        state=_state(lifecycle),
        decisions=lifecycle.decision_controller,
        armies=armies,
        battlefield=battlefield,
        units=units,
        embarked_unit_ids=(),
    )
    return (
        LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle.to_payload())),
        units["intercessor-1"].unit_instance_id,
        units["enemy"].unit_instance_id,
    )


def _counterexample_feature(kind: str) -> TerrainFeatureDefinition:
    walls: tuple[TerrainWallDefinition, ...]
    if kind == "opening":
        center_x, center_y, depth = 16.0, 20.0, 8.0
        walls = (
            TerrainWallDefinition("lower", 16.0, 18.05, 0.0, 0.1, 4.1, 3.0),
            TerrainWallDefinition("upper", 16.0, 22.1, 0.0, 0.1, 3.8, 3.0),
        )
    else:
        center_x, center_y, depth = 18.4, 20.15, 0.1
        walls = (TerrainWallDefinition("partial", center_x, center_y, 0.0, 0.1, depth, 3.0),)
    display = _display_geometry(
        center_x_inches=center_x, center_y_inches=center_y, width_inches=0.1, depth_inches=depth
    )
    return TerrainFeatureDefinition(
        feature_id=f"order32:{kind}:terrain",
        feature_kind=TerrainFeatureKind.HILLS,
        footprint_center_x_inches=center_x,
        footprint_center_y_inches=center_y,
        footprint_width_inches=0.1,
        footprint_depth_inches=depth,
        rules_footprint_polygon=display.footprint_polygon,
        display_geometry=display,
        walls=walls,
        source_id=f"order32:{kind}:analytic-counterexample",
    )


def _analytic_geometry(profile_id: str, radius: float) -> ModelGeometryCatalogRecord:
    footprint = ModelGeometrySourceEvidence.from_source_dimensions(
        evidence_id=f"{profile_id}:order32:footprint",
        evidence_kind=GeometryEvidenceKind.MANUAL_MEASUREMENT,
        measurement_kind=GeometryMeasurementKind.FOOTPRINT,
        source_id="order32:analytic-counterexample",
        source_units=GeometrySourceUnits.INCHES,
        source_dimensions=(("diameter", radius * 2),),
        document_reference="Order 32 analytic regression fixture",
    )
    height = ModelGeometrySourceEvidence.from_source_dimensions(
        evidence_id=f"{profile_id}:order32:height",
        evidence_kind=GeometryEvidenceKind.MANUAL_MEASUREMENT,
        measurement_kind=GeometryMeasurementKind.HEIGHT,
        source_id="order32:analytic-counterexample",
        source_units=GeometrySourceUnits.INCHES,
        source_dimensions=(("height", 2.0),),
        document_reference="Order 32 analytic regression fixture",
    )
    return ModelGeometryCatalogRecord(
        model_geometry_id=f"{profile_id}:order32",
        model_profile_id=profile_id,
        rules_footprint_policy=GeometryRulesFootprintPolicy.USE_FOOTPRINT,
        footprint=ModelFootprintDefinition.single_part(
            footprint_id=f"{profile_id}:order32:footprint",
            footprint_kind=ModelFootprintKind.CIRCULAR,
            part=ModelFootprintPartDefinition.from_evidence(
                part_id="base", footprint_kind=ModelFootprintKind.CIRCULAR, evidence=footprint
            ),
        ),
        support_base=None,
        z_offset=None,
        height=ModelHeightDefinition.from_evidence(height),
        evidence=(footprint, height),
        source_ids=("order32:analytic-counterexample",),
    )
