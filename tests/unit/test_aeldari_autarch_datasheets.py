from __future__ import annotations

import json
import math
from dataclasses import replace
from functools import cache
from typing import Any, cast

import pytest
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)
from tools.generate_aeldari_autarchs_rule_ir import (
    ASPECT_TRAINING_ROW_ID,
    INDOMITABLE_STRENGTH_ROW_ID,
    OUTPUT_PATH,
    SUPERLATIVE_STRATEGIST_ROW_ID,
    generated_artifact_payload,
)

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind, RulesetDescriptor
from warhammer40k_core.core.validation import canonical_keyword_token
from warhammer40k_core.engine.ability_catalog import (
    build_player_ability_index,
    catalog_ability_records_from_catalog,
)
from warhammer40k_core.engine.advance_hooks import AdvanceMoveContext
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
    muster_army,
)
from warhammer40k_core.engine.catalog_conditional_leader_abilities import (
    CatalogConditionalLeaderAbilityRuntime,
)
from warhammer40k_core.engine.catalog_conditional_leader_queries import (
    conditional_faction_resource_refund_roll_payload,
    conditional_granted_ability_effects_for_rules_unit,
    conditional_leading_roll_reroll_permission,
)
from warhammer40k_core.engine.catalog_datasheet_rule_descriptors import (
    conditional_leader_ability_grant_descriptor_for_clause,
    faction_resource_refund_roll_descriptor_for_clause,
)
from warhammer40k_core.engine.catalog_datasheet_rule_support import (
    CATALOG_IR_AGILE_MANOEUVRE_ROLL_REROLL_CONSUMER_ID,
    CATALOG_IR_CONDITIONAL_LEADER_ABILITY_CONSUMER_IDS,
    CATALOG_IR_FACTION_RESOURCE_REFUND_ROLL_CONSUMER_ID,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_ADVANCE_ROLL_REROLL_CONSUMER_ID,
    catalog_rule_ir_consumers_for_rule,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE, DiceRollManager
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.aeldari import army_rule
from warhammer40k_core.engine.faction_resources import resolve_faction_resource_refund_roll
from warhammer40k_core.engine.fight_order import FightsFirstRegistry
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.list_validation import (
    AttachmentDeclaration,
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.movement_proposals import MOVEMENT_PROPOSAL_DECISION_TYPE
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleStage,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.prebattle import scout_ability_instances_for_rules_unit
from warhammer40k_core.engine.reaction_windows import ReactionWindow, ReactionWindowKind
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.triggered_movement import (
    TriggeredMovementDescriptor,
    TriggeredMovementEligibleUnit,
    TriggeredMovementHandler,
    TriggeredMovementKind,
    apply_triggered_movement_distance_reroll_decision,
    is_triggered_movement_distance_reroll_request,
    triggered_movement_unit_selection_request,
)
from warhammer40k_core.engine.unit_factory import UnitFactory, UnitInstance
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
    WargearSelection,
)
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack
from warhammer40k_core.rules.rule_ir import RuleClause, RuleIR
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    aeldari_autarchs_2026_06 as source_package,
)
from warhammer40k_core.rules.wahapedia_bridge_defaults import (
    AELDARI_AUTARCHS_HEIGHT_OVERRIDES,
)

AUTARCH_ID = "000000577"
WAYLEAPER_ID = "000002759"
HOWLING_BANSHEES_ID = "000000594"
STRIKING_SCORPIONS_ID = "000000595"
HAWKS_ID = "000000600"
WRAITHBLADES_ID = "000000598"
AUTARCH_BANSHEE_BLADE_ID = "000000577:banshee-blade"
AUTARCH_SCORPION_CHAINSWORD_ID = "000000577:scorpion-chainsword"
AUTARCH_STAR_GLAIVE_ID = "000000577:star-glaive"
AUTARCH_ATTACHED_ID = "attached-unit:army-a:autarch-bodyguard"
WAYLEAPER_ATTACHED_ID = "attached-unit:army-a:wayleaper-bodyguard"
TEST_DETACHMENT_ID = "autarch-aspect-training-test"


@cache
def _package() -> Any:
    return _ability_support_catalog_package()


@cache
def _mustering_catalog() -> ArmyCatalog:
    generated = _package().army_catalog
    aeldari_datasheet_ids = tuple(
        datasheet.datasheet_id
        for datasheet in generated.datasheets
        if "ASURYANI" in datasheet.keywords.faction_keywords
    )
    return ArmyCatalog(
        catalog_id="aeldari-autarch-aspect-training-test",
        ruleset_id=generated.ruleset_id,
        source_package_id=generated.source_package_id,
        datasheets=generated.datasheets,
        wargear=generated.wargear,
        factions=tuple(
            replace(faction, faction_id="aeldari") if faction.faction_id == "AE" else faction
            for faction in generated.factions
        ),
        army_rules=generated.army_rules,
        detachments=(
            DetachmentDefinition(
                detachment_id=TEST_DETACHMENT_ID,
                name="Autarch Aspect Training Test",
                faction_id="aeldari",
                detachment_point_cost=1,
                unit_datasheet_ids=aeldari_datasheet_ids,
                force_disposition_ids=("purge-the-foe",),
                source_ids=("test:aeldari-autarch-aspect-training-detachment",),
            ),
        ),
        source_ids=generated.source_ids,
    )


def _muster_autarch_army(
    *,
    bodyguard_datasheet_id: str,
    autarch_wargear_id: str | None,
    attach_autarch: bool = True,
    include_wayleaper: bool = True,
) -> ArmyDefinition:
    catalog = _mustering_catalog()
    unit_selections = [
        _unit_muster_selection(
            catalog=catalog,
            selection_id="autarch",
            datasheet_id=AUTARCH_ID,
            selected_wargear_id=autarch_wargear_id,
        ),
        _unit_muster_selection(
            catalog=catalog,
            selection_id="autarch-bodyguard",
            datasheet_id=bodyguard_datasheet_id,
        ),
    ]
    attachment_declarations: list[AttachmentDeclaration] = []
    if attach_autarch:
        attachment_declarations.append(
            AttachmentDeclaration(
                source_unit_selection_id="autarch",
                bodyguard_unit_selection_id="autarch-bodyguard",
            )
        )
    if include_wayleaper:
        unit_selections.extend(
            (
                _unit_muster_selection(
                    catalog=catalog,
                    selection_id="wayleaper",
                    datasheet_id=WAYLEAPER_ID,
                ),
                _unit_muster_selection(
                    catalog=catalog,
                    selection_id="wayleaper-bodyguard",
                    datasheet_id=HAWKS_ID,
                ),
            )
        )
        attachment_declarations.append(
            AttachmentDeclaration(
                source_unit_selection_id="wayleaper",
                bodyguard_unit_selection_id="wayleaper-bodyguard",
            )
        )
    return muster_army(
        catalog=catalog,
        request=ArmyMusterRequest(
            army_id="army-a",
            player_id="player-a",
            catalog_id=catalog.catalog_id,
            source_package_id=catalog.source_package_id,
            ruleset_id=catalog.ruleset_id,
            detachment_selection=DetachmentSelection(
                faction_id="aeldari",
                detachment_ids=(TEST_DETACHMENT_ID,),
            ),
            force_disposition_id="purge-the-foe",
            unit_selections=tuple(unit_selections),
            attachment_declarations=tuple(attachment_declarations),
        ),
        model_geometries=_package().model_geometries,
    )


def _unit_muster_selection(
    *,
    catalog: ArmyCatalog,
    selection_id: str,
    datasheet_id: str,
    selected_wargear_id: str | None = None,
) -> UnitMusterSelection:
    datasheet = catalog.datasheet_by_id(datasheet_id)
    wargear_selections: tuple[WargearSelection, ...] = ()
    if selected_wargear_id is not None:
        matching_options = tuple(
            option
            for option in datasheet.wargear_options
            if selected_wargear_id in option.allowed_wargear_ids
        )
        assert len(matching_options) == 1
        option = matching_options[0]
        wargear_selections = (
            WargearSelection(
                option_id=option.option_id,
                model_profile_id=option.model_profile_id,
                wargear_ids=(selected_wargear_id,),
            ),
        )
    return UnitMusterSelection(
        unit_selection_id=selection_id,
        datasheet_id=datasheet_id,
        model_profile_selections=tuple(
            ModelProfileSelection(part.model_profile_id, part.min_models)
            for part in datasheet.composition
            if part.min_models > 0
        ),
        wargear_selections=wargear_selections,
    )


def test_generated_autarch_rule_ir_is_current_source_bound_and_fail_fast() -> None:
    committed = cast(dict[str, Any], json.loads(OUTPUT_PATH.read_text(encoding="utf-8")))

    assert committed == generated_artifact_payload()
    assert source_package.supported_datasheet_source_row_ids() == (
        SUPERLATIVE_STRATEGIST_ROW_ID,
        ASPECT_TRAINING_ROW_ID,
        INDOMITABLE_STRENGTH_ROW_ID,
    )
    assert committed["package_hash"] == source_package.PACKAGE_HASH

    committed["package_hash"] = "0" * 64
    with pytest.raises(source_package.AeldariAutarchsRuleIrArtifactError, match="hash is stale"):
        source_package.validate_generated_artifact_bytes(json.dumps(committed).encode())


def test_autarch_exact_rules_have_registered_source_backed_consumers() -> None:
    superlative = _static_rule(SUPERLATIVE_STRATEGIST_ROW_ID)
    aspect_training = _static_rule(ASPECT_TRAINING_ROW_ID)
    indomitable = _static_rule(INDOMITABLE_STRENGTH_ROW_ID)

    assert catalog_rule_ir_consumers_for_rule(superlative) == (
        CATALOG_IR_ADVANCE_ROLL_REROLL_CONSUMER_ID,
        CATALOG_IR_AGILE_MANOEUVRE_ROLL_REROLL_CONSUMER_ID,
    )
    assert catalog_rule_ir_consumers_for_rule(aspect_training) == (
        CATALOG_IR_CONDITIONAL_LEADER_ABILITY_CONSUMER_IDS["fights_first"],
        CATALOG_IR_CONDITIONAL_LEADER_ABILITY_CONSUMER_IDS["infiltrators"],
        CATALOG_IR_CONDITIONAL_LEADER_ABILITY_CONSUMER_IDS["scouts"],
        CATALOG_IR_CONDITIONAL_LEADER_ABILITY_CONSUMER_IDS["stealth"],
    )
    assert catalog_rule_ir_consumers_for_rule(indomitable) == (
        CATALOG_IR_FACTION_RESOURCE_REFUND_ROLL_CONSUMER_ID,
    )


def test_aspect_training_descriptor_uses_shared_canonical_keyword_tokens() -> None:
    payload = json.loads(json.dumps(_static_rule(ASPECT_TRAINING_ROW_ID).to_payload()))
    keyword_parameters = payload["clauses"][0]["conditions"][1]["parameters"]
    next(parameter for parameter in keyword_parameters if parameter["key"] == "required_keyword")[
        "value"
    ] = "howling-banshees"
    clause = RuleClause.from_payload(payload["clauses"][0])

    descriptor = conditional_leader_ability_grant_descriptor_for_clause(clause)

    assert descriptor is not None
    assert descriptor.required_bodyguard_keyword == canonical_keyword_token("howling-banshees")


@pytest.mark.parametrize(
    "drift",
    [
        "missing_dice_gate",
        "changed_threshold",
        "extra_condition",
        "target_parameters",
        "duration_parameters",
    ],
)
def test_indomitable_strength_descriptor_rejects_rule_ir_shape_drift(drift: str) -> None:
    payload = json.loads(json.dumps(_static_rule(INDOMITABLE_STRENGTH_ROW_ID).to_payload()))
    clause_payload = payload["clauses"][0]
    if drift == "missing_dice_gate":
        clause_payload["conditions"].pop()
    elif drift == "changed_threshold":
        threshold = next(
            parameter
            for parameter in clause_payload["conditions"][1]["parameters"]
            if parameter["key"] == "threshold"
        )
        threshold["value"] = 4
    elif drift == "extra_condition":
        clause_payload["conditions"].append(clause_payload["conditions"][0])
    elif drift == "target_parameters":
        clause_payload["target"]["parameters"][0]["value"] = "another_unit"
    elif drift == "duration_parameters":
        clause_payload["duration"]["parameters"].append({"key": "unsupported", "value": True})
    else:
        raise AssertionError("Unknown Indomitable Strength drift fixture.")
    clause = RuleClause.from_payload(clause_payload)

    assert faction_resource_refund_roll_descriptor_for_clause(clause) is None


def test_catalog_preserves_autarch_stats_geometry_abilities_weapons_and_leader_targets() -> None:
    package = _package()
    catalog = package.army_catalog
    autarch = catalog.datasheet_by_id(AUTARCH_ID)
    wayleaper = catalog.datasheet_by_id(WAYLEAPER_ID)

    assert _characteristics(autarch) == (7, 3, 3, 4, 6, 1, 4)
    assert _characteristics(wayleaper) == (14, 3, 3, 4, 6, 1, 4)
    assert math.isclose(autarch.model_profiles[0].base_size.diameter_mm or 0.0, 32.0)
    assert math.isclose(wayleaper.model_profiles[0].base_size.diameter_mm or 0.0, 32.0)
    assert autarch.keywords.keywords == (
        "AELDARI",
        "AUTARCH",
        "CHARACTER",
        "GRENADES",
        "INFANTRY",
    )
    assert wayleaper.keywords.keywords == (
        "AELDARI",
        "AUTARCH WAYLEAPER",
        "CHARACTER",
        "FLY",
        "GRENADES",
        "INFANTRY",
        "JUMP PACK",
    )
    assert {ability.name for ability in autarch.abilities} == {
        "ASPECT TRAINING",
        "Battle Focus",
        "Leader",
        "Path of Command",
        "Superlative Strategist",
    }
    assert {ability.name for ability in wayleaper.abilities} == {
        "Battle Focus",
        "Deep Strike",
        "Indomitable Strength of Will",
        "Leader",
        "Path of Command",
    }
    expected_weapon_names = {
        "Banshee blade",
        "Death spinner",
        "Dragon fusion gun",
        "Dragon fusion pistol",
        "Reaper launcher - starshot",
        "Reaper launcher - starswarm",
        "Scorpion chainsword",
        "Shuriken pistol",
        "Star glaive",
    }
    assert _weapon_names(AUTARCH_ID) == expected_weapon_names
    assert _weapon_names(WAYLEAPER_ID) == expected_weapon_names
    assert _leader_target_ids(autarch) == {
        HOWLING_BANSHEES_ID,
        STRIKING_SCORPIONS_ID,
        "000000596",
    }
    assert _leader_target_ids(wayleaper) == {HAWKS_ID, "000000601"}
    assert {
        target.bodyguard_datasheet_id: target.required_wargear_ids
        for eligibility in autarch.attachment_eligibilities
        for target in eligibility.targets
    } == {
        HOWLING_BANSHEES_ID: (),
        STRIKING_SCORPIONS_ID: (),
        "000000596": (),
    }
    assert {
        (override.datasheet_id, override.model_name, override.height)
        for override in AELDARI_AUTARCHS_HEIGHT_OVERRIDES
    } == {
        (AUTARCH_ID, "Autarch", 2.25),
        (WAYLEAPER_ID, "Autarch Wayleaper", 3.25),
    }


@pytest.mark.parametrize(
    "bodyguard_datasheet_id",
    [HOWLING_BANSHEES_ID, STRIKING_SCORPIONS_ID],
)
@pytest.mark.parametrize(
    "autarch_wargear_id",
    [
        None,
        AUTARCH_BANSHEE_BLADE_ID,
        AUTARCH_SCORPION_CHAINSWORD_ID,
    ],
)
def test_autarch_aspect_attachments_accept_every_legal_melee_loadout(
    bodyguard_datasheet_id: str,
    autarch_wargear_id: str | None,
) -> None:
    legal = _muster_autarch_army(
        bodyguard_datasheet_id=bodyguard_datasheet_id,
        autarch_wargear_id=autarch_wargear_id,
        include_wayleaper=False,
    )

    assert len(legal.attached_units) == 1
    formation = legal.attached_units[0]
    assert formation.attached_unit_instance_id == AUTARCH_ATTACHED_ID
    assert any("Datasheets_leader:000000577:" in value for value in formation.attachment_source_ids)
    expected_wargear_id = (
        AUTARCH_STAR_GLAIVE_ID if autarch_wargear_id is None else autarch_wargear_id
    )
    assert expected_wargear_id in legal.unit_by_id("army-a:autarch").own_models[0].wargear_ids


def test_aspect_training_is_live_attachment_and_bodyguard_keyword_scoped() -> None:
    scorpions = _runtime_fixture(
        autarch_bodyguard_datasheet_id=STRIKING_SCORPIONS_ID,
        autarch_wargear_id=None,
    )
    view = rules_unit_view_by_id(
        state=scorpions.state,
        unit_instance_id=scorpions.autarch_bodyguard.unit_instance_id,
    )

    for ability in ("infiltrators", "scouts", "stealth"):
        assert conditional_granted_ability_effects_for_rules_unit(
            state=scorpions.state,
            rules_unit_instance_id=view.unit_instance_id,
            ability=ability,
        )
    assert not conditional_granted_ability_effects_for_rules_unit(
        state=scorpions.state,
        rules_unit_instance_id=view.unit_instance_id,
        ability="fights_first",
    )
    scout_instances = scout_ability_instances_for_rules_unit(
        state=scorpions.state,
        view=view,
        army_catalog=_package().army_catalog,
    )
    assert len(scout_instances) == len(view.alive_models())
    assert {instance.distance_inches for instance in scout_instances} == {7.0}

    banshees = _runtime_fixture(
        autarch_bodyguard_datasheet_id=HOWLING_BANSHEES_ID,
        autarch_wargear_id=None,
    )
    assert FightsFirstRegistry.from_state(banshees.state).has_unit(AUTARCH_ATTACHED_ID)
    assert not conditional_granted_ability_effects_for_rules_unit(
        state=banshees.state,
        rules_unit_instance_id=AUTARCH_ATTACHED_ID,
        ability="stealth",
    )

    detached = _runtime_fixture(
        autarch_bodyguard_datasheet_id=STRIKING_SCORPIONS_ID,
        autarch_wargear_id=None,
        attach_autarch=False,
    )
    assert not conditional_granted_ability_effects_for_rules_unit(
        state=detached.state,
        rules_unit_instance_id=detached.autarch.unit_instance_id,
        ability="stealth",
    )
    dead = _runtime_fixture(
        autarch_bodyguard_datasheet_id=STRIKING_SCORPIONS_ID,
        autarch_wargear_id=None,
        autarch_alive=False,
    )
    assert not conditional_granted_ability_effects_for_rules_unit(
        state=dead.state,
        rules_unit_instance_id=AUTARCH_ATTACHED_ID,
        ability="stealth",
    )


def test_superlative_and_indomitable_descriptors_follow_live_leader_attachment() -> None:
    fixture = _runtime_fixture()
    advance = conditional_leading_roll_reroll_permission(
        state=fixture.state,
        rules_unit_instance_id=fixture.autarch_bodyguard.unit_instance_id,
        player_id="player-a",
        rule_roll_type="advance_roll",
        eligible_roll_type="advance_roll",
        timing_window="after_advance_roll",
    )
    agile = conditional_leading_roll_reroll_permission(
        state=fixture.state,
        rules_unit_instance_id=fixture.autarch_bodyguard.unit_instance_id,
        player_id="player-a",
        rule_roll_type="agile_manoeuvre_roll",
        eligible_roll_type="movement_end_surge.distance",
        timing_window="after_agile_manoeuvre_distance_roll",
    )
    refund = conditional_faction_resource_refund_roll_payload(
        state=fixture.state,
        rules_unit_instance_id=fixture.wayleaper_bodyguard.unit_instance_id,
        player_id="player-a",
        resource_kind="battle_focus_token",
    )

    assert advance is not None
    assert advance.eligible_roll_type == "advance_roll"
    assert agile is not None
    assert agile.eligible_roll_type == "movement_end_surge.distance"
    assert isinstance(refund, dict)
    assert refund["success_threshold"] == 3
    assert refund["amount"] == 1

    grant = army_rule.flitting_shadows_movement_grant(
        AdvanceMoveContext(
            state=fixture.state,
            player_id="player-a",
            battle_round=1,
            unit_instance_id=fixture.wayleaper_bodyguard.unit_instance_id,
            movement_phase_action="normal_move",
            movement_request_id="request:wayleaper-battle-focus",
            movement_result_id="result:wayleaper-battle-focus",
        )
    )
    assert grant is not None
    assert isinstance(grant.decision_effect_payload, dict)
    assert grant.decision_effect_payload["faction_resource_refund_roll"] == refund


@pytest.mark.parametrize(
    ("game_id", "expected_success"),
    [("autarch-refund-a", True), ("autarch-refund-b", False)],
)
def test_indomitable_strength_refund_roll_is_deterministic_audited_and_ledger_owned(
    game_id: str,
    expected_success: bool,
) -> None:
    fixture = _runtime_fixture(game_id=game_id)
    grant = army_rule.flitting_shadows_movement_grant(
        AdvanceMoveContext(
            state=fixture.state,
            player_id="player-a",
            battle_round=1,
            unit_instance_id=fixture.wayleaper_bodyguard.unit_instance_id,
            movement_phase_action="normal_move",
            movement_request_id=f"request:{game_id}",
            movement_result_id=f"result:{game_id}",
        )
    )
    assert grant is not None
    spend_effect = PersistingEffect(
        effect_id=f"effect:{game_id}:battle-focus-spend",
        source_rule_id=army_rule.SOURCE_RULE_ID,
        owner_player_id="player-a",
        target_unit_instance_ids=(fixture.wayleaper_bodyguard.unit_instance_id,),
        started_battle_round=1,
        started_phase=BattlePhaseKind.MOVEMENT,
        expiration=EffectExpiration.end_of_battle(),
        effect_payload=grant.decision_effect_payload,
    )
    decisions = DecisionController()

    resolution = resolve_faction_resource_refund_roll(
        state=fixture.state,
        decisions=decisions,
        spend_effect=spend_effect,
    )

    assert resolution is not None
    succeeded = resolution.roll_state.current_total >= 3
    assert succeeded is expected_success
    assert (resolution.resource_result is not None) is succeeded
    assert fixture.state.faction_resource_total(
        player_id="player-a",
        resource_kind="battle_focus_token",
    ) == (1 if succeeded else 0)
    assert (
        json.loads(json.dumps(resolution.to_payload(), sort_keys=True)) == resolution.to_payload()
    )
    event = decisions.event_log.records[-1]
    assert event.event_type == "faction_resource_refund_roll_resolved"
    assert isinstance(event.payload, dict)
    assert event.payload["resolution"] == resolution.to_payload()


def test_superlative_agile_distance_uses_standard_reroll_then_proposal_path() -> None:
    fixture = _runtime_fixture(game_id="autarch-agile-reroll")
    permission = conditional_leading_roll_reroll_permission(
        state=fixture.state,
        rules_unit_instance_id=fixture.autarch_bodyguard.unit_instance_id,
        player_id="player-a",
        rule_roll_type="agile_manoeuvre_roll",
        eligible_roll_type="movement_end_surge.distance",
        timing_window="after_agile_manoeuvre_distance_roll",
    )
    assert permission is not None
    decisions = DecisionController()
    roll_state = DiceRollManager(
        fixture.state.game_id,
        event_log=decisions.event_log,
    ).roll(
        DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason="Autarch Agile Manoeuvre distance",
            roll_type="movement_end_surge.distance",
            actor_id="player-a",
        )
    )
    eligible = TriggeredMovementEligibleUnit(
        unit_instance_id=fixture.autarch_bodyguard.unit_instance_id,
        hook_id=army_rule.OPPORTUNITY_SEIZED_HOOK_ID,
        source_id=army_rule.SOURCE_RULE_ID,
        replay_payload={"maneuver": army_rule.OPPORTUNITY_SEIZED_MANEUVER},
        distance_roll_state=roll_state,
        distance_roll_bonus_inches=1,
        distance_reroll_permission=permission,
    )
    assert TriggeredMovementEligibleUnit.from_payload(eligible.to_payload()) == eligible
    descriptor = TriggeredMovementDescriptor(
        movement_kind=TriggeredMovementKind.SURGE,
        source_rule_id=army_rule.SOURCE_RULE_ID,
        trigger_timing=ReactionWindow(
            phase=BattlePhaseKind.MOVEMENT,
            window_kind=ReactionWindowKind.RULE_TRIGGER,
            source_event_id="event:autarch-agile-trigger",
        ),
        max_distance_inches=float(roll_state.current_total + 1),
    )
    request = triggered_movement_unit_selection_request(
        state=fixture.state,
        player_id="player-a",
        descriptor=descriptor,
        eligible_units=(eligible,),
    )
    decisions.request_decision(request)
    selection = DecisionResult.for_request(
        result_id="result:autarch-agile-selection",
        request=request,
        selected_option_id=f"surge:{eligible.unit_instance_id}",
    )
    decisions.submit_result(selection)

    reroll_status = TriggeredMovementHandler(
        ruleset_descriptor=fixture.state.runtime_ruleset_descriptor()
    ).apply_decision(
        state=fixture.state,
        result=selection,
        decisions=decisions,
    )
    assert reroll_status is not None
    assert reroll_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    reroll_request = decisions.queue.peek_next()
    assert reroll_request.decision_type == DICE_REROLL_DECISION_TYPE
    assert is_triggered_movement_distance_reroll_request(reroll_request)
    assert isinstance(reroll_request.payload, dict)
    assert reroll_request.payload["selected_unit"] == eligible.to_payload()

    reroll = DecisionResult.for_request(
        result_id="result:autarch-agile-reroll",
        request=reroll_request,
        selected_option_id="reroll:0",
    )
    decisions.submit_result(reroll)
    proposal_status = apply_triggered_movement_distance_reroll_decision(
        state=fixture.state,
        result=reroll,
        decisions=decisions,
    )
    assert proposal_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    proposal_request = decisions.queue.peek_next()
    assert proposal_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    assert isinstance(proposal_request.payload, dict)
    context = cast(dict[str, Any], proposal_request.payload["proposal_request"])["context"]
    assert cast(dict[str, Any], context)["context_kind"] == "triggered_movement"
    assert any(
        event.event_type == "triggered_movement_distance_reroll_resolved"
        for event in decisions.event_log.records
    )


class _RuntimeFixture:
    def __init__(
        self,
        *,
        state: GameState,
        autarch: UnitInstance,
        autarch_bodyguard: UnitInstance,
        wayleaper: UnitInstance,
        wayleaper_bodyguard: UnitInstance,
    ) -> None:
        self.state = state
        self.autarch = autarch
        self.autarch_bodyguard = autarch_bodyguard
        self.wayleaper = wayleaper
        self.wayleaper_bodyguard = wayleaper_bodyguard


def _runtime_fixture(
    *,
    game_id: str = "aeldari-autarch-test",
    autarch_bodyguard_datasheet_id: str = STRIKING_SCORPIONS_ID,
    autarch_wargear_id: str | None = None,
    attach_autarch: bool = True,
    autarch_alive: bool = True,
) -> _RuntimeFixture:
    package = _package()
    catalog = _mustering_catalog()
    factory = UnitFactory(catalog=catalog, model_geometries=package.model_geometries)
    army_a = _muster_autarch_army(
        bodyguard_datasheet_id=autarch_bodyguard_datasheet_id,
        autarch_wargear_id=autarch_wargear_id,
        attach_autarch=attach_autarch,
    )
    autarch = army_a.unit_by_id("army-a:autarch")
    if not autarch_alive:
        autarch = replace(
            autarch,
            own_models=(replace(autarch.own_models[0], wounds_remaining=0),),
        )
        army_a = replace(
            army_a,
            units=tuple(
                autarch if unit.unit_instance_id == autarch.unit_instance_id else unit
                for unit in army_a.units
            ),
        )
    autarch_bodyguard = army_a.unit_by_id("army-a:autarch-bodyguard")
    wayleaper = army_a.unit_by_id("army-a:wayleaper")
    wayleaper_bodyguard = army_a.unit_by_id("army-a:wayleaper-bodyguard")
    enemy = _instantiate(
        factory,
        army_id="army-b",
        selection_id="enemy",
        datasheet_id=WRAITHBLADES_ID,
    )
    armies = (
        army_a,
        _army(catalog, army_id="army-b", player_id="player-b", units=(enemy,)),
    )
    state = _state(game_id=game_id, armies=armies)
    records = catalog_ability_records_from_catalog(catalog)
    indexes = {
        army.player_id: build_player_ability_index(records, army=army, catalog=catalog)
        for army in armies
    }
    CatalogConditionalLeaderAbilityRuntime(indexes, armies).record_static_effects(state=state)
    return _RuntimeFixture(
        state=state,
        autarch=autarch,
        autarch_bodyguard=autarch_bodyguard,
        wayleaper=wayleaper,
        wayleaper_bodyguard=wayleaper_bodyguard,
    )


def _state(*, game_id: str, armies: tuple[ArmyDefinition, ...]) -> GameState:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    phases = tuple(descriptor.battle_phase_sequence.phases)
    state = GameState(
        game_id=game_id,
        ruleset_descriptor_hash=descriptor.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(descriptor.setup_sequence.steps),
        battle_phase_sequence=phases,
        setup_step_index=None,
        battle_phase_index=phases.index(BattlePhase.MOVEMENT),
        battle_round=1,
        active_player_id="player-a",
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        tactical_secondary_draw_count=2,
        mission_setup=MissionSetup.from_mission_pack(
            mission_pack=chapter_approved_2026_27_mission_pack(),
            mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
            terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
            attacker_player_id="player-a",
            defender_player_id="player-b",
        ),
    )
    for army in armies:
        state.record_army_definition(army)
    from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario

    state.battlefield_state = create_deterministic_battlefield_scenario(
        battlefield_id=f"{game_id}:battlefield",
        armies=armies,
    ).battlefield_state
    return state


def _army(
    catalog: Any,
    *,
    army_id: str,
    player_id: str,
    units: tuple[UnitInstance, ...],
) -> ArmyDefinition:
    return ArmyDefinition(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="aeldari" if player_id == "player-a" else "test-opponent",
            detachment_ids=("corsair-coterie",),
        ),
        force_disposition_id="purge-the-foe",
        units=units,
    )


def _instantiate(
    factory: UnitFactory,
    *,
    army_id: str,
    selection_id: str,
    datasheet_id: str,
) -> UnitInstance:
    datasheet = factory.catalog.datasheet_by_id(datasheet_id)
    profile_selections = tuple(
        ModelProfileSelection(part.model_profile_id, part.min_models)
        for part in datasheet.composition
        if part.min_models > 0
    )
    return factory.instantiate_unit(
        army_id=army_id,
        datasheet=datasheet,
        selection=UnitMusterSelection(
            unit_selection_id=selection_id,
            datasheet_id=datasheet_id,
            model_profile_selections=profile_selections,
        ),
    )


def _static_rule(source_row_id: str) -> RuleIR:
    payload = source_package.datasheet_rule_ir_payload_by_source_row_id(source_row_id)
    assert payload is not None
    return RuleIR.from_payload(payload)


def _characteristics(datasheet: Any) -> tuple[int, ...]:
    values = {
        value.characteristic: value.final for value in datasheet.model_profiles[0].characteristics
    }
    return (
        values[Characteristic.MOVEMENT],
        values[Characteristic.TOUGHNESS],
        values[Characteristic.SAVE],
        values[Characteristic.WOUNDS],
        values[Characteristic.LEADERSHIP],
        values[Characteristic.OBJECTIVE_CONTROL],
        values[Characteristic.INVULNERABLE_SAVE],
    )


def _weapon_names(datasheet_id: str) -> set[str]:
    return {
        profile.name
        for wargear in _package().army_catalog.wargear
        if wargear.wargear_id.startswith(f"{datasheet_id}:")
        for profile in wargear.weapon_profiles
    }


def _leader_target_ids(datasheet: Any) -> set[str]:
    return {
        target.bodyguard_datasheet_id
        for eligibility in datasheet.attachment_eligibilities
        for target in eligibility.targets
    }
