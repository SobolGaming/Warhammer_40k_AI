"""02.02 wounds / 02.02.04 healing / 02.02.05 full wounds: direct engine owners."""

from dataclasses import replace
from pathlib import Path

import pytest
from tools.ability_support_sources import ability_support_index_inputs, load_ability_support_sources
from tools.generate_ability_support_matrix import DEFAULT_SOURCE_JSON_DIR

from tests.order130_helpers import session_from_casualty_checkpoint
from tests.phase11c_command_phase_helpers import destroy_models_with_recorded_mortal_wounds
from tests.support.faction_batch01 import (
    anchor,
    events,
    scene,
    selection,
)
from tests.support.section02_fixtures import Section02Definitions, health_state
from tests.support.section11_fixtures import begin
from tests.support.wahapedia_source_fixtures import bridge_package_id, catalog_version
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.model_geometry_catalog import GeometrySourceUnits
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.boundary_sequencing import boundary_context
from warhammer40k_core.engine.catalog_datasheet_rule_support import (
    CATALOG_IR_PHASE_END_SELF_HEALING_CONSUMER_ID,
)
from warhammer40k_core.engine.damage_allocation import (
    DamageKind,
    MortalWoundApplicationProgress,
    apply_damage_to_model,
    continue_mortal_wound_application,
    model_by_id,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.destruction_provenance import DestructionSourceKind
from warhammer40k_core.engine.healing import (
    HealingEffect,
    HealingStepKind,
    resolve_healing_until_blocked,
)
from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
    MortalWoundDestructionEvidence,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.replay import ReplayRunner
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.rules.catalog_generation import build_canonical_catalog_report
from warhammer40k_core.rules.data_package import DataPackageId
from warhammer40k_core.rules.selected_source_index import load_selected_source_rows
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27 as identities,
)
from warhammer40k_core.rules.wahapedia_bridge import (
    ModelHeightOverride,
    build_wahapedia_canonical_bridge_artifacts,
)


@pytest.mark.parametrize(
    ("damage", "remaining", "destroyed", "excess"),
    [
        (1, 1, False, 0),
        (2, 0, True, 0),
        (3, 0, True, 1),
    ],
)
def test_02_02_wound_threshold_and_excess_damage(
    section02_definitions: Section02Definitions,
    damage: int,
    remaining: int,
    destroyed: bool,
    excess: int,
) -> None:
    unit = section02_definitions.unit()
    state = health_state(section02_definitions, unit)
    model = unit.own_models[0]
    result = apply_damage_to_model(
        state=state,
        target_unit_instance_id=unit.unit_instance_id,
        model_instance_id=model.model_instance_id,
        damage=damage,
        damage_kind=DamageKind.NORMAL,
        remove_destroyed_model=False,
    )
    assert result.final_wounds_remaining == remaining
    assert result.destroyed is destroyed
    assert result.excess_damage_lost == excess
    assert (
        model_by_id(state=state, model_instance_id=model.model_instance_id).is_alive
        is not destroyed
    )
    assert all(m.current_wounds == 2 for m in state.army_definitions[0].units[0].own_models[1:])
    assert unit.own_models[0].current_wounds == 2


@pytest.mark.parametrize("amount", [1, 3])
def test_02_02_04_healing_restores_one_wound_without_exceeding_starting_wounds(
    section02_definitions: Section02Definitions,
    amount: int,
) -> None:
    unit = section02_definitions.unit()
    state = health_state(section02_definitions, unit)
    model = unit.own_models[0]
    apply_damage_to_model(
        state=state,
        target_unit_instance_id=unit.unit_instance_id,
        model_instance_id=model.model_instance_id,
        damage=1,
        damage_kind=DamageKind.NORMAL,
    )
    effect, request = resolve_healing_until_blocked(
        state=state,
        decisions=DecisionController(),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        effect=HealingEffect("section02-heal", unit.unit_instance_id, amount, "opponent"),
    )
    assert request is None
    assert effect.is_complete()
    assert sum(s.step_kind is HealingStepKind.HEAL_WOUND for s in effect.resolved_steps) == 1
    healed = model_by_id(state=state, model_instance_id=model.model_instance_id)
    assert healed.current_wounds == healed.initial_wounds == 2


def test_02_02_04_model_scope_discards_excess_and_does_not_revive(
    section02_definitions: Section02Definitions,
) -> None:
    unit = section02_definitions.unit()
    state = health_state(section02_definitions, unit)
    selected, other, dead = unit.own_models[:3]
    for model, amount in ((selected, 1), (other, 1), (dead, 2)):
        apply_damage_to_model(
            state=state,
            target_unit_instance_id=unit.unit_instance_id,
            model_instance_id=model.model_instance_id,
            damage=amount,
            damage_kind=DamageKind.NORMAL,
            remove_destroyed_model=False,
        )
    effect, request = resolve_healing_until_blocked(
        state=state,
        decisions=DecisionController(),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        effect=HealingEffect(
            "model-heal",
            unit.unit_instance_id,
            5,
            "opponent",
            source_context={"healing_model_instance_id": selected.model_instance_id},
        ),
    )
    assert request is None
    assert effect.is_complete()
    assert [
        model_by_id(state=state, model_instance_id=m.model_instance_id).current_wounds
        for m in (selected, other, dead)
    ] == [2, 1, 0]
    assert sum(s.step_kind is HealingStepKind.HEAL_WOUND for s in effect.resolved_steps) == 1


def test_02_02_04_foreign_model_scope_fails_before_healing(
    section02_definitions: Section02Definitions,
) -> None:
    unit = section02_definitions.unit()
    state = health_state(section02_definitions, unit)
    before = state.army_definitions[0].to_payload()
    with pytest.raises(GameLifecycleError, match="belong"):
        resolve_healing_until_blocked(
            state=state,
            decisions=DecisionController(),
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            effect=HealingEffect(
                "wrong-model",
                unit.unit_instance_id,
                1,
                "opponent",
                source_context={"healing_model_instance_id": "foreign"},
            ),
        )
    assert state.army_definitions[0].to_payload() == before


_BEASTS_CHAOS_DAEMONS = "000001134"
_BEASTS_DEATH_GUARD = "000004115"
_BEASTS_DETACHMENTS = {"chaos-daemons": "cavalcade-of-chaos", "death-guard": "tallyband-summoners"}


@pytest.fixture(scope="module")
def beasts_definitions(selected_army_source_index: Path | None) -> Section02Definitions:
    source_factions = {"CD": "chaos-daemons", "DG": "death-guard"}
    source_dir = Path(__file__).resolve().parents[3] / DEFAULT_SOURCE_JSON_DIR
    datasheet_ids = (_BEASTS_CHAOS_DAEMONS, _BEASTS_DEATH_GUARD)
    sources = (
        load_ability_support_sources(source_dir)
        if selected_army_source_index is None
        else load_selected_source_rows(
            selected_army_source_index,
            input_files=ability_support_index_inputs(source_dir),
            datasheet_ids=datasheet_ids,
        )
    )
    artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=sources,
        bridge_package_id=bridge_package_id(),
        datasheet_ids=datasheet_ids,
        height_overrides=tuple(
            ModelHeightOverride(
                datasheet_id=datasheet_id,
                model_name=name,
                height=1,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id=f"regeneration-test-height:{datasheet_id}",
                height_document_reference="Synthetic height for a phase timing checkpoint",
            )
            for datasheet_id, name in zip(
                datasheet_ids, ("Beasts Of Nurgle", "Beasts of Nurgle"), strict=True
            )
        ),
    )
    report = build_canonical_catalog_report(
        package_id=DataPackageId("tests", "grotesque-regeneration", "v1"),
        catalog_version=catalog_version(),
        source_artifacts=artifacts,
    )
    assert report.package is not None, report.diagnostics
    package = report.package
    catalog = package.army_catalog
    factions = tuple(
        replace(
            faction,
            faction_id=source_factions[faction.faction_id],
            faction_keywords=("DEATH GUARD",)
            if faction.faction_id == "DG"
            else faction.faction_keywords,
        )
        for faction in catalog.factions
    )
    detachments = tuple(
        DetachmentDefinition(
            canonical_detachment_id=row.detachment_id,
            detachment_id=row.detachment_id,
            name=row.name,
            faction_id=row.faction_id,
            detachment_point_cost=row.detachment_point_cost,
            unit_datasheet_ids=(datasheet_id,),
            force_disposition_ids=tuple(
                sorted({row.force_disposition_id, "take-and-hold", "purge-the-foe"})
            ),
            source_ids=row.source_ids,
        )
        for datasheet_id, faction_id in zip(datasheet_ids, source_factions.values(), strict=True)
        for row in identities.detachment_rows()
        if row.detachment_id == _BEASTS_DETACHMENTS[faction_id]
    )
    # The current roster gate does not admit Plague Legions via Pact of Decay.
    # Add the parent faction keyword only in this component catalog so exact
    # replay can remuster it. Keep the unit's source ability and Plague Legions token.
    datasheets = tuple(
        replace(
            datasheet,
            keywords=replace(
                datasheet.keywords,
                faction_keywords=(*datasheet.keywords.faction_keywords, "DEATH GUARD"),
            ),
        )
        if datasheet.datasheet_id == _BEASTS_DEATH_GUARD
        else datasheet
        for datasheet in catalog.datasheets
    )
    return Section02Definitions(
        replace(
            package,
            army_catalog=replace(
                catalog, datasheets=datasheets, factions=factions, detachments=detachments
            ),
        ),
        0,
    )


@pytest.mark.integration
@pytest.mark.replay
@pytest.mark.parametrize(
    ("datasheet_id", "enemy_id", "source_package_id"),
    [
        (
            _BEASTS_CHAOS_DAEMONS,
            _BEASTS_DEATH_GUARD,
            "gw-11e-chaos-daemons-beasts-of-nurgle-datasheet-2026-07",
        ),
        (
            _BEASTS_DEATH_GUARD,
            _BEASTS_CHAOS_DAEMONS,
            "gw-11e-death-guard-beasts-of-nurgle-datasheet-2026-07",
        ),
    ],
    ids=("chaos-daemons", "death-guard"),
)
@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
def test_grotesque_regeneration_native_phase_end_and_replay(
    beasts_definitions: Section02Definitions,
    datasheet_id: str,
    enemy_id: str,
    source_package_id: str,
    phase: BattlePhase,
) -> None:
    d = beasts_definitions
    s = scene(
        d,
        (selection(d, datasheet_id, "wounded", full=True), selection(d, datasheet_id, "healthy")),
        (selection(d, enemy_id, "target"),),
        phase=phase,
        active="opponent",
        seed=f"grotesque-regeneration:{datasheet_id}:{phase.value}",
        detachment_id_by_faction=_BEASTS_DETACHMENTS,
    )
    bundle = s.session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    assert [
        binding.trigger_kind
        for binding in bundle.turn_end_hook_registry.all_bindings()
        if binding.hook_id == CATALOG_IR_PHASE_END_SELF_HEALING_CONSUMER_ID
    ] == [TimingTriggerKind.END_PHASE]
    unit = s.units["own:wounded"]
    wounded, destroyed = unit.own_models
    healthy = s.units["own:healthy"].own_models[0]
    anchor(s)
    decisions = s.session.lifecycle.decision_controller
    destroy_models_with_recorded_mortal_wounds(
        state=s.state,
        decisions=decisions,
        unit_instance_id=unit.unit_instance_id,
        model_instance_ids=(destroyed.model_instance_id,),
        application_id="regeneration:prior-casualty",
        destroying_player_id="opponent",
    )
    wounded_checkpoint = continue_mortal_wound_application(
        state=s.state,
        decisions=decisions,
        request_id="regeneration:prior-wounds",
        progress=MortalWoundApplicationProgress.start(
            application_id="regeneration:prior-wounds",
            source_rule_id="fixture:prior-wounds",
            source_context={"source_kind": "fixture"},
            target_unit_instance_id=unit.unit_instance_id,
            defender_player_id="owner",
            mortal_wounds=4,
            spill_over=False,
            priority_model_ids=(wounded.model_instance_id,),
            destruction_evidence=MortalWoundDestructionEvidence.for_non_attack_state(
                state=s.state,
                destroying_player_id="opponent",
                source_rules_unit_instance_id=None,
                source_model_instance_id=None,
                destruction_source_kind=DestructionSourceKind.ABILITY,
                action_phase=phase,
                source_step="fixture",
            ),
        ),
    )
    assert wounded_checkpoint.request is None
    assert wounded_checkpoint.application is not None
    s.session = session_from_casualty_checkpoint(s.session.lifecycle)
    window = boundary_context(s.state, TimingTriggerKind.END_PHASE).timing_window
    assert (
        model_by_id(state=s.state, model_instance_id=wounded.model_instance_id).current_wounds == 3
    )
    assert not events(s.session, "healing_resolved")
    next_request = begin(s.session)
    if next_request.decision_type == "select_shooting_unit":
        status = s.session.submit_option(
            request_id=next_request.request_id,
            option_id="complete_shooting_phase",
            result_id="regeneration:complete-shooting",
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status

    assert (
        model_by_id(state=s.state, model_instance_id=wounded.model_instance_id).current_wounds == 7
    )
    assert (
        model_by_id(state=s.state, model_instance_id=destroyed.model_instance_id).current_wounds
        == 0
    )
    assert (
        model_by_id(state=s.state, model_instance_id=healthy.model_instance_id).current_wounds == 7
    )
    assert s.state.battlefield_state is not None
    assert destroyed.model_instance_id in s.state.battlefield_state.removed_model_ids

    (resolution,) = events(s.session, "healing_resolved")
    effect = resolution["effect"]
    assert isinstance(effect, dict)
    assert effect["source_rule_id"] == f"{source_package_id}:datasheet:{datasheet_id}:5"
    assert str(effect["effect_id"]).startswith(f"{window.window_id}:")
    assert effect["amount"] == 4
    assert effect["target_unit_instance_id"] == unit.unit_instance_id
    steps = effect["resolved_steps"]
    assert isinstance(steps, list)
    assert len(steps) == 4
    for step in steps:
        assert isinstance(step, dict)
        assert step["model_instance_id"] == wounded.model_instance_id
        assert step["step_kind"] == HealingStepKind.HEAL_WOUND.value
    assert all(
        record.request.decision_type != "select_healing_model"
        for record in s.session.lifecycle.decision_controller.records
    )

    records = s.session.lifecycle.decision_controller.event_log.records
    heal_index = next(
        i for i, record in enumerate(records) if record.event_type == "healing_resolved"
    )
    phase_end_index = next(
        i
        for i, record in enumerate(records)
        if record.event_type == "timing_window_resolved"
        and isinstance(record.payload, dict)
        and record.payload["timing_window"] == window.to_payload()
    )
    assert heal_index < phase_end_index
    if phase is BattlePhase.FIGHT:
        turn_end_index = next(
            i
            for i, record in enumerate(records)
            if record.event_type == "timing_window_resolved"
            and isinstance(record.payload, dict)
            and isinstance(timing := record.payload["timing_window"], dict)
            and str(timing["window_id"]).endswith(":turn:opponent:end")
        )
        assert phase_end_index < turn_end_index
        assert not any(
            record.event_type == "healing_resolved" for record in records[phase_end_index:]
        )

    replay = ReplayRunner.from_payload(s.session.replay_artifact(artifact_id="regeneration")).run()
    assert replay.reproduced_exactly
