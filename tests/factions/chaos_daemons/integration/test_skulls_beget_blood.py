"""Skulls Beget Blood through the native Shooting selection opportunity."""

from dataclasses import replace
from pathlib import Path

import pytest

from tests.daemons_native_source_helpers import BELAKOR, native_definitions
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
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleStage,
    LifecycleStatus,
    SetupStep,
)
from warhammer40k_core.engine.replay import ReplayRunner
from warhammer40k_core.engine.stratagems import DECLINE_STRATAGEM_WINDOW_OPTION_ID
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_blood_legion_ir_support_2026_27 as blood_legion_ir,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27 as identities,
)

STRATAGEM_ID = blood_legion_ir.SKULLS_BEGET_BLOOD_STRATAGEM_ID
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
    native = native_definitions(selected_army_source_index)
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
    begin(battle.session)
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
    assert request.decision_type == "select_movement_unit"
    require_request(_submit(battle.session, MOUNTED), "select_movement_action")
    advance = require_request(_submit(battle.session, "advance"), "submit_movement_proposal")
    require_request(submit_translation(battle, advance, MOUNTED, 0.5), "select_movement_unit")
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
