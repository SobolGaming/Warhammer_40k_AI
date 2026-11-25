"""Skulls Beget Blood through the native Shooting selection opportunity."""

from dataclasses import replace
from pathlib import Path

import pytest
from tools.core_deep_strike_catalog_overlay import with_current_deep_strike
from tools.generate_ability_support_matrix import (
    BLOODLETTERS_HEIGHT_OVERRIDES,
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from tests.daemons_native_source_helpers import BELAKOR, SELECTED, native_definitions
from tests.phase11c_command_phase_helpers import center_marker_definition
from tests.save7_allocation_helpers import BLOODLETTERS
from tests.support.faction_batch01 import (
    CRUSHERS,
    LORD,
    Scene,
    anchor,
    events,
    locate,
    scene,
    selection,
    submit_translation,
)
from tests.support.faction_batch01 import request as require_request
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section04_fixtures import pending
from tests.support.section09_fixtures import propose
from tests.support.section10_geometry import blocking_wall
from tests.support.section11_fixtures import begin
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.engine.battle_formation_hooks import BattleFormationRequestContext
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.damage_allocation import DamageKind, apply_damage_to_model
from warhammer40k_core.engine.decision_request import DecisionError, DecisionRequest
from warhammer40k_core.engine.destruction_provenance import ModelDestructionAttribution
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleStage,
    LifecycleStatus,
    SetupStep,
)
from warhammer40k_core.engine.replay import ReplayRunner
from warhammer40k_core.engine.rules_unit_geometry import (
    placed_alive_geometry_models_for_component_unit,
    placed_alive_geometry_models_for_rules_unit,
)
from warhammer40k_core.engine.shooting_selection_range import target_in_range_model_ids
from warhammer40k_core.engine.stratagems import DECLINE_STRATAGEM_WINDOW_OPTION_ID
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.core_deep_strike_successor import ABILITY_ID as DEEP_STRIKE_ABILITY_ID
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_blood_legion_ir_support_2026_27 as blood_legion_ir,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27 as identities,
)

STRATAGEM_ID = blood_legion_ir.SKULLS_BEGET_BLOOD_STRATAGEM_ID
BLOODMASTER = "000001455"
INFRACTORS = "000004080"
INFANTRY = "own:infantry"
MOUNTED = "own:mounted"
WRONG_KEYWORD = "own:undivided"
ENEMY = "foe:target"
DECOY = "foe:decoy"

DETACHMENTS = {
    "chaos-daemons": "blood-legion",
    "emperors-children": "court-of-the-phoenician",
}


@pytest.fixture(scope="module")
def shooting_skulls_definitions(selected_army_source_index: Path | None) -> Section02Definitions:
    return _blood_legion_definitions(native_definitions(selected_army_source_index))


@pytest.fixture(scope="module")
def attached_skulls_definitions(selected_army_source_index: Path | None) -> Section02Definitions:
    # The production bridge has no reviewed Bloodmaster height. Use a test
    # height while retaining the source datasheet, base and attachment relation.
    test_height = replace(
        BLOODLETTERS_HEIGHT_OVERRIDES[0],
        datasheet_id=BLOODMASTER,
        model_name="Bloodmaster",
        height_source_id="test:skulls-beget-blood:bloodmaster:height",
        height_document_reference="Attached formation test fixture",
    )
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "tools.generate_ability_support_matrix.BLOODLETTERS_HEIGHT_OVERRIDES",
            (*BLOODLETTERS_HEIGHT_OVERRIDES, test_height),
        )
        monkeypatch.setattr(
            "tools.generate_ability_support_matrix.with_current_deep_strike",
            _overlay_attached_fixture_deep_strike,
        )
        package = _ability_support_catalog_package(
            datasheet_ids=(*SELECTED, BLOODMASTER, INFRACTORS, LORD, "000004090"),
            source_index_dir=selected_army_source_index,
        )
    return _blood_legion_definitions(Section02Definitions(package, 0.0))


def _overlay_attached_fixture_deep_strike(
    package: CanonicalCatalogPackage,
) -> CanonicalCatalogPackage:
    # This Shooting checkpoint does not exercise the unaudited Bloodmaster
    # reserve descriptor. Keep the production overlay exact for the other rows.
    catalog = package.army_catalog
    sheets = tuple(
        replace(
            sheet,
            abilities=tuple(a for a in sheet.abilities if a.ability_id != DEEP_STRIKE_ABILITY_ID),
        )
        if sheet.datasheet_id == BLOODMASTER
        else sheet
        for sheet in catalog.datasheets
    )
    return with_current_deep_strike(
        replace(package, army_catalog=replace(catalog, datasheets=sheets))
    )


def _blood_legion_definitions(native: Section02Definitions) -> Section02Definitions:
    catalog = native.package.army_catalog
    source_factions = {"CD": "chaos-daemons", "EC": "emperors-children"}
    factions = tuple(
        replace(faction, faction_id=source_factions[faction.faction_id])
        for faction in catalog.factions
    )
    detachments = tuple(
        DetachmentDefinition(
            canonical_detachment_id=row.detachment_id,
            detachment_id=row.detachment_id,
            name=row.name,
            faction_id=faction.faction_id,
            detachment_point_cost=row.detachment_point_cost,
            unit_datasheet_ids=tuple(
                sheet.datasheet_id
                for sheet in catalog.datasheets
                if set(sheet.keywords.faction_keywords).intersection(faction.faction_keywords)
            ),
            force_disposition_ids=tuple(
                sorted({row.force_disposition_id, "take-and-hold", "purge-the-foe"})
            ),
            source_ids=row.source_ids,
        )
        for faction in factions
        for row in identities.detachment_rows()
        if row.detachment_id == DETACHMENTS[faction.faction_id]
    )
    return Section02Definitions(
        replace(
            native.package,
            army_catalog=replace(catalog, factions=factions, detachments=detachments),
        ),
        native.preparation_seconds,
    )


def _submit(session: LocalGameSession, option: str) -> LifecycleStatus:
    request = pending(session)
    return session.submit_option(
        request_id=request.request_id, result_id=f"{request.request_id}:skulls", option_id=option
    )


def _choices(request: DecisionRequest) -> dict[tuple[str, str], str]:
    choices: dict[tuple[str, str], str] = {}
    for option in request.options:
        payload = option.payload
        if not isinstance(payload, dict):
            continue
        record = payload.get("catalog_record")
        if not isinstance(record, dict):
            continue
        definition = record.get("definition")
        if not isinstance(definition, dict) or definition.get("stratagem_id") != STRATAGEM_ID:
            continue
        binding, effect = payload["target_binding"], payload["effect_selection"]
        assert isinstance(binding, dict)
        assert isinstance(effect, dict)
        assert effect["effect_selection_kind"] == "visible_enemy_unit"
        unit_id = binding["target_unit_instance_id"]
        enemy_id = effect["visible_enemy_unit_instance_id"]
        assert isinstance(unit_id, str)
        assert isinstance(enemy_id, str)
        assert (unit_id, enemy_id) not in choices
        choices[unit_id, enemy_id] = option.option_id
    return choices


def _scene(
    definitions: Section02Definitions,
    *,
    cp: int = 2,
    active: str = "owner",
    phase: BattlePhase = BattlePhase.SHOOTING,
    blocked: bool = False,
    engaged: bool = False,
    blood_tainted: bool = False,
) -> Scene:
    battle = scene(
        definitions,
        (
            selection(definitions, BLOODLETTERS, "infantry"),
            selection(definitions, CRUSHERS, "mounted"),
            selection(definitions, BELAKOR, "undivided"),
        ),
        (selection(definitions, LORD, "target"), selection(definitions, LORD, "decoy")),
        phase=phase,
        active=active,
        detachment_id_by_faction=DETACHMENTS,
        seed="skulls-beget-blood",
        terrain_features=(blocking_wall(),) if blocked else (),
    )
    objective = center_marker_definition(battle.state)
    x, y = (20.0, 12.0) if blocked else (objective.x_inches, objective.y_inches)
    locate(
        battle,
        INFANTRY,
        tuple(Pose.at(x - 2.5 - 1.5 * (i // 5), y - 3 + 1.5 * (i % 5)) for i in range(10)),
    )
    locate(
        battle,
        MOUNTED,
        tuple(Pose.at(x - 10.5 + 4 * i, y + 5) for i in range(3))
        if blocked
        else tuple(Pose.at(x + 1 + 4 * i, y + 7) for i in range(3)),
    )
    locate(battle, WRONG_KEYWORD, (Pose.at(x + 6, y - 5),))
    locate(battle, ENEMY, (Pose.at(x + 2.0, y),))
    locate(battle, DECOY, (Pose.at(x - 0.4, y),) if engaged else (Pose.at(55, 40),))
    if cp:
        battle.state.gain_command_points(
            player_id="owner",
            amount=cp,
            source_id="skulls:cp",
            source_kind=CommandPointSourceKind.OTHER,
            cap_exempt=True,
        )
    if phase is BattlePhase.MOVEMENT:
        locate(battle, ENEMY, (Pose.at(x + 3.0, y),))
        locate(battle, DECOY, (Pose.at(x - 6.9, y),))
    target = battle.units[ENEMY].own_models[0]
    apply_damage_to_model(
        state=battle.state,
        target_unit_instance_id=ENEMY,
        model_instance_id=target.model_instance_id,
        damage=target.current_wounds - 1,
        damage_kind=DamageKind.NORMAL,
    )
    if blood_tainted:
        _materialize_battle_formation_effects(battle)
    anchor(battle)
    return battle


def _materialize_battle_formation_effects(battle: Scene) -> None:
    # A constructed Shooting checkpoint skips the Battle Formation step, where
    # the ordinary setup registry grants the persistent detachment effects.
    state = battle.state
    lifecycle = battle.session.lifecycle
    bundle = lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    config = lifecycle._require_config()  # pyright: ignore[reportPrivateUsage]
    state.stage = GameLifecycleStage.SETUP
    state.setup_step_index = state.setup_sequence.index(SetupStep.DECLARE_BATTLE_FORMATIONS)
    request = bundle.battle_formation_hook_registry.next_request_for(
        BattleFormationRequestContext(
            state=state, decisions=lifecycle.decision_controller, config=config
        )
    )
    assert request is None
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None


@pytest.mark.integration
def test_skulls_beget_blood_ordinary_choice_damage_attribution_and_replay(
    shooting_skulls_definitions: Section02Definitions,
) -> None:
    battle = _scene(shooting_skulls_definitions, blood_tainted=True)
    offer = begin(battle.session)
    assert offer.decision_type == "use_stratagem"
    assert offer.actor_id == "owner"
    choices = _choices(offer)
    assert set(choices) == {(INFANTRY, ENEMY), (MOUNTED, ENEMY)}

    checkpoint = battle.session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    assert restored.to_persistence_payload() == checkpoint
    _submit(restored, DECLINE_STRATAGEM_WINDOW_OPTION_ID)
    assert not events(restored, "stratagem_used")

    selected = choices[INFANTRY, ENEMY]
    with pytest.raises(DecisionError, match="option"):
        _submit(battle.session, selected.replace(ENEMY, DECOY))
    assert pending(battle.session) == offer
    assert battle.state.command_point_total("owner") == 2
    _submit(battle.session, selected)
    assert battle.state.command_point_total("owner") == 1
    (use,) = tuple(r for r in battle.state.stratagem_use_records if r.stratagem_id == STRATAGEM_ID)
    assert use.source_id == blood_legion_ir.SKULLS_BEGET_BLOOD_SOURCE_ID
    assert use.targeted_unit_instance_ids == (INFANTRY,)
    assert set(use.affected_unit_instance_ids) == {INFANTRY, ENEMY}
    (resolved,) = events(battle.session, "generic_stratagem_roll_pool_mortal_wounds_resolved")
    rolls = resolved["rolls"]
    assert isinstance(rolls, list)
    assert len(rolls) == 6
    values: list[int] = []
    for roll in rolls:
        assert isinstance(roll, dict)
        result = roll["original_result"]
        assert isinstance(result, dict)
        raw_values = result["values"]
        assert isinstance(raw_values, list)
        (value,) = raw_values
        assert isinstance(value, int)
        values.append(value)
    assert resolved["mortal_wounds"] == sum(value >= 4 for value in values)
    assert resolved["mortal_wounds"] != 0
    (destruction,) = events(battle.session, "model_destroyed")
    assert destruction["target_unit_instance_id"] == ENEMY
    attribution = ModelDestructionAttribution.from_model_destroyed_payload(destruction)
    assert attribution.destroying_player_id == "owner"
    assert attribution.source_rules_unit_instance_id == INFANTRY
    assert attribution.source_model_instance_id is None
    if battle.state.current_battle_phase is BattlePhase.SHOOTING:
        assert pending(battle.session).decision_type == "select_shooting_unit"
        _submit(battle.session, "complete_shooting_phase")
    assert battle.state.current_battle_phase is not BattlePhase.SHOOTING
    (sticky,) = battle.state.sticky_objective_control_states
    assert sticky.originating_unit_instance_id == INFANTRY
    assert sticky.destroyed_unit_instance_id == ENEMY
    assert sticky.objective_id == center_marker_definition(battle.state).objective_marker_id
    replay = ReplayRunner.from_payload(
        battle.session.replay_artifact(artifact_id="skulls-beget-blood")
    ).run()
    assert replay.reproduced_exactly, replay


@pytest.mark.integration
def test_skulls_beget_blood_excludes_both_ends_of_engagement(
    shooting_skulls_definitions: Section02Definitions,
) -> None:
    battle = _scene(shooting_skulls_definitions, engaged=True)
    assert set(_choices(begin(battle.session))) == {(MOUNTED, ENEMY)}


@pytest.mark.integration
@pytest.mark.parametrize("case", ["no_cp", "opponent_turn", "blocked"])
def test_skulls_beget_blood_has_no_option_when_use_is_illegal(
    shooting_skulls_definitions: Section02Definitions, case: str
) -> None:
    battle = _scene(
        shooting_skulls_definitions,
        cp=0 if case == "no_cp" else 2,
        active="opponent" if case == "opponent_turn" else "owner",
        blocked=case == "blocked",
    )
    assert not _choices(begin(battle.session))
    assert not battle.state.stratagem_use_records


@pytest.mark.integration
def test_skulls_beget_blood_allows_advance_but_excludes_fall_back(
    shooting_skulls_definitions: Section02Definitions,
) -> None:
    battle = _scene(shooting_skulls_definitions, phase=BattlePhase.MOVEMENT)

    def decline_movement_stratagem(offer: DecisionRequest) -> DecisionRequest:
        if offer.decision_type != "use_stratagem":
            return offer
        assert any(
            option.option_id.startswith(
                f"use-stratagem:{blood_legion_ir.GORE_HUNGRY_ONSLAUGHT_STRATAGEM_ID}:"
            )
            for option in offer.options
        )
        return require_request(_submit(battle.session, DECLINE_STRATAGEM_WINDOW_OPTION_ID))

    assert decline_movement_stratagem(begin(battle.session)).decision_type == "select_movement_unit"
    require_request(_submit(battle.session, INFANTRY), "select_movement_action")
    proposal = require_request(
        _submit(battle.session, "fall_back:ordered_retreat"), "submit_movement_proposal"
    )
    assert battle.state.battlefield_state is not None
    infantry_placement = battle.state.battlefield_state.unit_placement_by_id(INFANTRY)
    request = require_request(
        propose(
            battle.session,
            proposal,
            battle.units[INFANTRY],
            tuple(
                Pose.at(model.pose.position.x + 1.0, model.pose.position.y, model.pose.position.z)
                for model in infantry_placement.model_placements
            ),
            result_id=f"{proposal.request_id}:retreat",
        )
    )
    assert decline_movement_stratagem(request).decision_type == "select_movement_unit"
    require_request(_submit(battle.session, MOUNTED), "select_movement_action")
    advance = require_request(_submit(battle.session, "advance"), "submit_movement_proposal")
    after_move = require_request(submit_translation(battle, advance, MOUNTED, 0.5))
    assert decline_movement_stratagem(after_move).decision_type == "select_movement_unit"
    require_request(_submit(battle.session, WRONG_KEYWORD), "select_movement_action")
    request = require_request(_submit(battle.session, "remain_stationary"))
    if request.decision_type == "start_mission_action":
        request = require_request(_submit(battle.session, "continue_to_shooting"))
    assert set(_choices(request)) == {(MOUNTED, ENEMY)}
    assert (
        battle.state.fell_back_unit_state_for_unit(
            player_id="owner", battle_round=1, unit_instance_id=INFANTRY
        )
        is not None
    )

    assert (
        battle.state.advanced_unit_state_for_unit(
            player_id="owner", battle_round=1, unit_instance_id=MOUNTED
        )
        is not None
    )
    assert not {"GRENADES", "EXPLOSIVES"}.intersection(battle.units[MOUNTED].keywords)
    _submit(battle.session, _choices(request)[MOUNTED, ENEMY])
    (use,) = tuple(r for r in battle.state.stratagem_use_records if r.stratagem_id == STRATAGEM_ID)
    assert use.targeted_unit_instance_ids == (MOUNTED,)
    assert battle.state.command_point_total("owner") == 1


@pytest.mark.integration
def test_skulls_beget_blood_attached_leader_range_defender_allocation_and_replay(
    attached_skulls_definitions: Section02Definitions,
) -> None:
    definitions = attached_skulls_definitions
    battle = scene(
        definitions,
        (
            selection(definitions, BLOODLETTERS, "body"),
            selection(definitions, BLOODMASTER, "leader"),
        ),
        (selection(definitions, INFRACTORS, "body"), selection(definitions, LORD, "leader")),
        phase=BattlePhase.SHOOTING,
        attachments=(AttachmentDeclaration("leader", "body"),),
        enemy_attachments=(AttachmentDeclaration("leader", "body"),),
        detachment_id_by_faction=DETACHMENTS,
        seed="skulls-beget-blood-attached",
    )
    source_formation = "attached-unit:own:body"
    enemy_formation = "attached-unit:foe:body"
    locate(
        battle,
        "own:body",
        tuple(Pose.at(10.8 + 1.5 * (i // 5), 11 + 1.5 * (i % 5)) for i in range(10)),
    )
    locate(battle, "own:leader", (Pose.at(14, 14),))
    locate(
        battle,
        "foe:body",
        tuple(
            Pose.at(23 + 1.5 * (i // 5), 11 + 1.5 * (i % 5))
            for i in range(len(battle.units["foe:body"].own_models))
        ),
    )
    locate(battle, "foe:leader", (Pose.at(26, 14),))
    targets = placed_alive_geometry_models_for_rules_unit(
        state=battle.state, unit_instance_id=enemy_formation
    )
    for component, within_range in (("own:body", False), ("own:leader", True)):
        assert (
            bool(
                target_in_range_model_ids(
                    attacker_models=placed_alive_geometry_models_for_component_unit(
                        state=battle.state, component_unit_instance_id=component
                    ),
                    target_models=targets,
                    range_inches=8,
                )
            )
            is within_range
        )
    battle.state.gain_command_points(
        player_id="owner",
        amount=2,
        source_id="skulls:cp",
        source_kind=CommandPointSourceKind.OTHER,
        cap_exempt=True,
    )
    anchor(battle)

    request = begin(battle.session)
    choices = _choices(request)
    assert set(choices) == {(source_formation, enemy_formation)}
    allocation = require_request(
        _submit(battle.session, choices[source_formation, enemy_formation]),
        "select_mortal_wound_model",
    )
    assert battle.state.command_point_total("owner") == 1
    bodyguard_ids = set(battle.units["foe:body"].own_model_ids())
    while allocation.decision_type == "select_mortal_wound_model":
        assert allocation.actor_id == "opponent"
        assert {option.option_id for option in allocation.options} <= bodyguard_ids
        allocation = require_request(_submit(battle.session, allocation.options[0].option_id))
    assert events(battle.session, "generic_stratagem_roll_pool_mortal_wounds_resolved")
    destroyed = events(battle.session, "model_destroyed")
    assert destroyed
    for payload in destroyed:
        attribution = ModelDestructionAttribution.from_model_destroyed_payload(payload)
        assert attribution.destroying_player_id == "owner"
        assert attribution.source_rules_unit_instance_id == source_formation
        assert attribution.source_model_instance_id is None

    replay = ReplayRunner.from_payload(
        battle.session.replay_artifact(artifact_id="skulls-beget-blood-attached")
    ).run()
    assert replay.reproduced_exactly, replay
