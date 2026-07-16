from __future__ import annotations

# pyright: reportPrivateUsage=false
from dataclasses import replace
from typing import cast

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import BaseSizeDefinition
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine import generic_detachment_rule_effects as generic_detachment_effects
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.decision_request import DecisionOption
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons.detachments.lords_of_the_warp import (  # noqa: E501
    manifest,
    stratagems,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.list_validation import DetachmentSelection
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage
from warhammer40k_core.engine.stratagems import (
    CORE_COUNTEROFFENSIVE_HANDLER_ID,
    COUNTEROFFENSIVE_TARGET_POLICY_ID,
    GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
    SELECTED_TO_FIGHT_CHARGED_TARGET_POLICY_ID,
    SELECTED_TO_FIGHT_UNIT_CONTEXT_KEY,
    SELECTED_TO_SHOOT_TARGET_POLICY_ID,
    SELECTED_TO_SHOOT_UNIT_CONTEXT_KEY,
    STRATAGEM_DECISION_TYPE,
    TARGET_BINDING_UNIT_CONTEXT_KEY,
    VISIBLE_ENEMY_RANGE_INCHES_KEY,
    VISIBLE_ENEMY_SOURCE_UNIT_CONTEXT_KEY,
    VISIBLE_ENEMY_UNIT_EFFECT_SELECTION_KIND,
    StratagemAvailabilityKind,
    StratagemCatalogIndex,
    StratagemCatalogRecord,
    StratagemEligibilityContext,
    StratagemTargetKind,
    stratagem_use_options_from_index,
)
from warhammer40k_core.engine.stratagems_generic_metadata import EFFECT_SELECTION_KIND_KEY
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.geometry.model_geometry import ModelGeometry
from warhammer40k_core.rules.rule_ir import RuleEffectKind, parameter_payload
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_execution_2026_27,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_generic_ir_support_2026_27 as generic_ir_support,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_lords_of_the_warp_ir_support_2026_27 as lords_ir,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_execution_2026_27 import (
    Phase17FExecutionStatus,
)


def test_lords_source_backed_rule_ir_rows_are_executable_generic_ir() -> None:
    descriptor_ids = {
        lords_ir.LORDS_OF_THE_WARP_DETACHMENT_RULE_DESCRIPTOR_ID,
        lords_ir.SWOLLEN_WITH_POWER_DESCRIPTOR_ID,
        lords_ir.CARNIVAL_OF_EXCESS_DESCRIPTOR_ID,
        lords_ir.CALL_TO_MURDER_DESCRIPTOR_ID,
        lords_ir.BILIOUS_BLESSING_DESCRIPTOR_ID,
        lords_ir.SKIRLING_MAGICKS_DESCRIPTOR_ID,
    }
    records_by_descriptor = {
        record.coverage_descriptor_id: record
        for record in faction_execution_2026_27.execution_records()
        if record.coverage_descriptor_id in descriptor_ids
    }

    assert set(records_by_descriptor) == descriptor_ids
    assert {record.execution_status for record in records_by_descriptor.values()} == {
        Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR
    }
    assert all(record.rule_ir_hash is not None for record in records_by_descriptor.values())


def test_lords_detachment_rule_ir_modifies_only_non_monster_daemon_characters() -> None:
    rule_ir = generic_ir_support.generic_rule_ir_by_coverage_descriptor_id(
        lords_ir.LORDS_OF_THE_WARP_DETACHMENT_RULE_DESCRIPTOR_ID
    )
    modifier_parameters = tuple(
        parameter_payload(effect.parameters)
        for clause in rule_ir.clauses
        for effect in clause.effects
        if effect.kind is RuleEffectKind.MODIFY_CHARACTERISTIC
    )

    assert {
        cast(str, parameters["characteristic"]): cast(int, parameters["delta"])
        for parameters in modifier_parameters
    } == {"leadership": -1, "objective_control": 1}
    assert all(
        parameters["required_faction_keyword_sequence"] == (lords_ir.LEGIONES_DAEMONICA_KEYWORD,)
        for parameters in modifier_parameters
    )
    assert all(
        parameters["required_keyword_sequence"] == (lords_ir.CHARACTER_KEYWORD,)
        for parameters in modifier_parameters
    )
    assert all(
        parameters["excluded_keyword_sequence"] == (lords_ir.MONSTER_KEYWORD,)
        for parameters in modifier_parameters
    )

    army = _army(
        army_id="army-alpha",
        player_id="player-a",
        ruleset=RulesetDescriptor.warhammer_40000_eleventh(),
        faction_id=lords_ir.CHAOS_DAEMONS_FACTION_ID,
        detachment_id=lords_ir.LORDS_OF_THE_WARP_DETACHMENT_ID,
        units=(
            _unit(
                unit_instance_id="army-alpha:slaanesh-character",
                datasheet_id="slaanesh-character",
                name="Slaanesh Character",
                keywords=(lords_ir.CHARACTER_KEYWORD, lords_ir.SLAANESH_KEYWORD),
                faction_keywords=(lords_ir.LEGIONES_DAEMONICA_KEYWORD,),
            ),
            _unit(
                unit_instance_id="army-alpha:tzeentch-monster-character",
                datasheet_id="tzeentch-monster-character",
                name="Tzeentch Monster Character",
                keywords=(
                    lords_ir.CHARACTER_KEYWORD,
                    lords_ir.MONSTER_KEYWORD,
                    lords_ir.TZEENTCH_KEYWORD,
                ),
                faction_keywords=(lords_ir.LEGIONES_DAEMONICA_KEYWORD,),
            ),
            _unit(
                unit_instance_id="army-alpha:nurgle-infantry",
                datasheet_id="nurgle-infantry",
                name="Nurgle Infantry",
                keywords=(lords_ir.NURGLE_KEYWORD, "INFANTRY"),
                faction_keywords=(lords_ir.LEGIONES_DAEMONICA_KEYWORD,),
            ),
            _unit(
                unit_instance_id="army-alpha:marine-character",
                datasheet_id="marine-character",
                name="Marine Character",
                keywords=(lords_ir.CHARACTER_KEYWORD,),
                faction_keywords=("ADEPTUS ASTARTES",),
            ),
        ),
    )

    assert generic_detachment_effects._target_unit_ids_for_record(
        record=_lords_execution_record(),
        rule_ir=rule_ir,
        army=army,
    ) == ("army-alpha:slaanesh-character",)


def test_lords_runtime_manifest_and_stratagem_records_are_source_backed() -> None:
    contribution = stratagems.runtime_contribution()
    records_by_id = {
        record.definition.stratagem_id: record for record in contribution.stratagem_records
    }

    assert manifest.runtime_contribution().contribution_id == manifest.CONTRIBUTION_ID
    assert not manifest.CONTRIBUTION_ID.endswith(":scaffold")
    assert contribution.contribution_id == stratagems.CONTRIBUTION_ID
    assert not contribution.contribution_id.endswith(":scaffold")
    assert set(records_by_id) == {
        lords_ir.CARNIVAL_OF_EXCESS_STRATAGEM_ID,
        lords_ir.CALL_TO_MURDER_STRATAGEM_ID,
        lords_ir.BILIOUS_BLESSING_STRATAGEM_ID,
        lords_ir.SKIRLING_MAGICKS_STRATAGEM_ID,
    }
    for record in records_by_id.values():
        assert record.availability_kind is StratagemAvailabilityKind.DETACHMENT
        assert record.detachment_id == lords_ir.LORDS_OF_THE_WARP_DETACHMENT_ID
        assert record.definition.command_point_cost == 1
        assert record.definition.target_spec.required_faction_keywords == (
            lords_ir.LEGIONES_DAEMONICA_KEYWORD,
        )
        assert record.definition.target_spec.excluded_keywords == (lords_ir.MONSTER_KEYWORD,)
        assert isinstance(record.definition.effect_payload, dict)
        assert "rule_ir" in record.definition.effect_payload

    carnival = records_by_id[lords_ir.CARNIVAL_OF_EXCESS_STRATAGEM_ID]
    assert carnival.definition.handler_id == CORE_COUNTEROFFENSIVE_HANDLER_ID
    assert carnival.definition.target_spec.target_policy_id == COUNTEROFFENSIVE_TARGET_POLICY_ID
    assert carnival.definition.target_spec.required_keywords == (
        lords_ir.CHARACTER_KEYWORD,
        lords_ir.SLAANESH_KEYWORD,
    )
    assert carnival.definition.timing.trigger_kind is (
        TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_HAS_FOUGHT
    )

    call = records_by_id[lords_ir.CALL_TO_MURDER_STRATAGEM_ID]
    assert call.definition.handler_id == GENERIC_RULE_IR_STRATAGEM_HANDLER_ID
    assert call.definition.target_spec.target_policy_id == (
        SELECTED_TO_FIGHT_CHARGED_TARGET_POLICY_ID
    )
    assert call.definition.target_spec.required_keywords == (
        lords_ir.CHARACTER_KEYWORD,
        lords_ir.KHORNE_KEYWORD,
    )
    assert call.definition.timing.trigger_kind is (
        TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_SELECTED_TO_FIGHT
    )

    bilious = records_by_id[lords_ir.BILIOUS_BLESSING_STRATAGEM_ID]
    assert bilious.definition.handler_id == GENERIC_RULE_IR_STRATAGEM_HANDLER_ID
    assert bilious.definition.target_spec.target_policy_id == (
        stratagems.FRIENDLY_UNIT_TARGET_POLICY_ID
    )
    assert bilious.definition.target_spec.required_keywords == (
        lords_ir.CHARACTER_KEYWORD,
        lords_ir.NURGLE_KEYWORD,
    )
    assert isinstance(bilious.definition.effect_payload, dict)
    assert bilious.definition.effect_payload["requires_own_turn"] is True
    assert bilious.definition.effect_payload[EFFECT_SELECTION_KIND_KEY] == (
        VISIBLE_ENEMY_UNIT_EFFECT_SELECTION_KIND
    )
    assert bilious.definition.effect_payload[VISIBLE_ENEMY_SOURCE_UNIT_CONTEXT_KEY] == (
        TARGET_BINDING_UNIT_CONTEXT_KEY
    )
    assert bilious.definition.effect_payload[VISIBLE_ENEMY_RANGE_INCHES_KEY] == 8

    skirling = records_by_id[lords_ir.SKIRLING_MAGICKS_STRATAGEM_ID]
    assert skirling.definition.handler_id == GENERIC_RULE_IR_STRATAGEM_HANDLER_ID
    assert skirling.definition.target_spec.target_policy_id == SELECTED_TO_SHOOT_TARGET_POLICY_ID
    assert skirling.definition.target_spec.required_keywords == (
        lords_ir.CHARACTER_KEYWORD,
        lords_ir.TZEENTCH_KEYWORD,
    )
    assert skirling.definition.timing.trigger_kind is (
        TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_SELECTED_TO_SHOOT
    )


def test_lords_selected_unit_stratagem_targeting_uses_trigger_context() -> None:
    records_by_id = {
        record.definition.stratagem_id: _zero_cost_record(record)
        for record in stratagems.runtime_contribution().stratagem_records
    }
    shooting_state = _lords_battle_state(BattlePhase.SHOOTING)
    shooting_context = StratagemEligibilityContext.from_state(
        state=shooting_state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_SELECTED_TO_SHOOT,
        timing_window_id="lords-selected-to-shoot-window",
        trigger_payload={
            SELECTED_TO_SHOOT_UNIT_CONTEXT_KEY: "army-alpha:tzeentch-character",
            "selected_unit_instance_id": "army-alpha:tzeentch-character",
        },
    )

    shooting_options = stratagem_use_options_from_index(
        state=shooting_state,
        index=StratagemCatalogIndex.from_records(
            (records_by_id[lords_ir.SKIRLING_MAGICKS_STRATAGEM_ID],)
        ),
        context=shooting_context,
    )

    assert tuple(option.option_id for option in shooting_options) == (
        "use-stratagem:chaos-daemons:lords-of-the-warp:skirling-magicks:"
        "target:army-alpha:tzeentch-character",
    )
    assert _target_binding_payload(shooting_options[0]) == {
        "target_kind": StratagemTargetKind.FRIENDLY_UNIT.value,
        "target_player_id": "player-a",
        "target_unit_instance_id": "army-alpha:tzeentch-character",
    }

    monster_context = replace(
        shooting_context,
        trigger_payload={
            SELECTED_TO_SHOOT_UNIT_CONTEXT_KEY: "army-alpha:tzeentch-monster-character",
            "selected_unit_instance_id": "army-alpha:tzeentch-monster-character",
        },
    )
    assert (
        stratagem_use_options_from_index(
            state=shooting_state,
            index=StratagemCatalogIndex.from_records(
                (records_by_id[lords_ir.SKIRLING_MAGICKS_STRATAGEM_ID],)
            ),
            context=monster_context,
        )
        == ()
    )

    fight_state = _lords_battle_state(BattlePhase.FIGHT)
    fight_state.record_persisting_effect(
        PersistingEffect(
            effect_id="phase17g-lords:khorne-character:charge",
            source_rule_id="phase15b:charge:fights-first",
            owner_player_id="player-a",
            target_unit_instance_ids=("army-alpha:khorne-character",),
            started_battle_round=1,
            started_phase=BattlePhase.CHARGE,
            expiration=EffectExpiration.end_phase(
                battle_round=1,
                phase=BattlePhase.FIGHT,
                player_id="player-a",
            ),
            effect_payload={"effect_kind": "charge_grants_fights_first"},
        )
    )
    fight_context = StratagemEligibilityContext.from_state(
        state=fight_state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_SELECTED_TO_FIGHT,
        timing_window_id="lords-selected-to-fight-window",
        trigger_payload={
            SELECTED_TO_FIGHT_UNIT_CONTEXT_KEY: "army-alpha:khorne-character",
            "selected_unit_instance_id": "army-alpha:khorne-character",
        },
    )

    fight_options = stratagem_use_options_from_index(
        state=fight_state,
        index=StratagemCatalogIndex.from_records(
            (records_by_id[lords_ir.CALL_TO_MURDER_STRATAGEM_ID],)
        ),
        context=fight_context,
    )

    assert tuple(option.option_id for option in fight_options) == (
        "use-stratagem:chaos-daemons:lords-of-the-warp:call-to-murder:"
        "target:army-alpha:khorne-character",
    )

    uncharged_state = _lords_battle_state(BattlePhase.FIGHT)
    assert (
        stratagem_use_options_from_index(
            state=uncharged_state,
            index=StratagemCatalogIndex.from_records(
                (records_by_id[lords_ir.CALL_TO_MURDER_STRATAGEM_ID],)
            ),
            context=replace(
                fight_context,
                game_id=uncharged_state.game_id,
                active_player_id=uncharged_state.active_player_id,
            ),
        )
        == ()
    )


def _zero_cost_record(record: StratagemCatalogRecord) -> StratagemCatalogRecord:
    return replace(
        record,
        definition=replace(record.definition, command_point_cost=0),
    )


def _target_binding_payload(option: DecisionOption) -> dict[str, object]:
    payload = cast(dict[str, object], option.payload)
    assert payload["submission_kind"] == STRATAGEM_DECISION_TYPE
    return cast(dict[str, object], payload["target_binding"])


def _lords_battle_state(phase: BattlePhase) -> GameState:
    ruleset = RulesetDescriptor.warhammer_40000_eleventh()
    phase_sequence = tuple(ruleset.battle_phase_sequence.phases)
    state = GameState(
        game_id=f"phase17g-lords-{phase.value}",
        ruleset_descriptor_hash=ruleset.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(ruleset.setup_sequence.steps),
        battle_phase_sequence=phase_sequence,
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        tactical_secondary_draw_count=2,
        setup_step_index=None,
        battle_phase_index=phase_sequence.index(phase),
        battle_round=1,
        active_player_id="player-a",
    )
    state.record_army_definition(
        _army(
            army_id="army-alpha",
            player_id="player-a",
            ruleset=ruleset,
            faction_id=lords_ir.CHAOS_DAEMONS_FACTION_ID,
            detachment_id=lords_ir.LORDS_OF_THE_WARP_DETACHMENT_ID,
            units=(
                _unit(
                    unit_instance_id="army-alpha:tzeentch-character",
                    datasheet_id="tzeentch-character",
                    name="Tzeentch Character",
                    keywords=(lords_ir.CHARACTER_KEYWORD, lords_ir.TZEENTCH_KEYWORD),
                    faction_keywords=(lords_ir.LEGIONES_DAEMONICA_KEYWORD,),
                ),
                _unit(
                    unit_instance_id="army-alpha:tzeentch-monster-character",
                    datasheet_id="tzeentch-monster-character",
                    name="Tzeentch Monster Character",
                    keywords=(
                        lords_ir.CHARACTER_KEYWORD,
                        lords_ir.TZEENTCH_KEYWORD,
                        lords_ir.MONSTER_KEYWORD,
                    ),
                    faction_keywords=(lords_ir.LEGIONES_DAEMONICA_KEYWORD,),
                ),
                _unit(
                    unit_instance_id="army-alpha:khorne-character",
                    datasheet_id="khorne-character",
                    name="Khorne Character",
                    keywords=(lords_ir.CHARACTER_KEYWORD, lords_ir.KHORNE_KEYWORD),
                    faction_keywords=(lords_ir.LEGIONES_DAEMONICA_KEYWORD,),
                ),
            ),
        )
    )
    state.record_army_definition(
        _army(
            army_id="army-beta",
            player_id="player-b",
            ruleset=ruleset,
            faction_id="space-marines",
            detachment_id="gladius-task-force",
            units=(
                _unit(
                    unit_instance_id="army-beta:intercessors",
                    datasheet_id="intercessors",
                    name="Intercessors",
                    keywords=("INFANTRY",),
                    faction_keywords=("ADEPTUS ASTARTES",),
                ),
            ),
        )
    )
    return state


def _army(
    *,
    army_id: str,
    player_id: str,
    ruleset: RulesetDescriptor,
    faction_id: str,
    detachment_id: str,
    units: tuple[UnitInstance, ...],
) -> ArmyDefinition:
    return ArmyDefinition(
        army_id=army_id,
        player_id=player_id,
        catalog_id="lords-detachment-test-catalog",
        source_package_id=lords_ir.SOURCE_PACKAGE_ID,
        ruleset_id=ruleset.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=faction_id,
            detachment_ids=(detachment_id,),
        ),
        force_disposition_id="purge-the-foe",
        units=units,
    )


def _unit(
    *,
    unit_instance_id: str,
    datasheet_id: str,
    name: str,
    keywords: tuple[str, ...],
    faction_keywords: tuple[str, ...],
) -> UnitInstance:
    model = _model(
        model_instance_id=f"{unit_instance_id}:model-001",
        datasheet_id=datasheet_id,
        model_profile_id=f"{datasheet_id}-profile",
        name=f"{name} model",
        keywords=keywords,
    )
    return UnitInstance(
        unit_instance_id=unit_instance_id,
        datasheet_id=datasheet_id,
        name=name,
        keywords=keywords,
        faction_keywords=faction_keywords,
        datasheet_abilities=(),
        datasheet_source_ids=(f"source:{datasheet_id}",),
        own_models=(model,),
        wargear_selections=(),
    )


def _model(
    *,
    model_instance_id: str,
    datasheet_id: str,
    model_profile_id: str,
    name: str,
    keywords: tuple[str, ...],
) -> ModelInstance:
    base_size = BaseSizeDefinition.circular(32.0)
    return ModelInstance(
        model_instance_id=model_instance_id,
        datasheet_id=datasheet_id,
        model_profile_id=model_profile_id,
        name=name,
        characteristics=(
            CharacteristicValue.from_raw(Characteristic.WOUNDS, 1),
            CharacteristicValue.from_raw(Characteristic.LEADERSHIP, 7),
            CharacteristicValue.from_raw(Characteristic.OBJECTIVE_CONTROL, 1),
        ),
        base_size=base_size,
        geometry=ModelGeometry.from_base_size(
            base_size,
            keywords=keywords,
            geometry_source_id=model_profile_id,
        ),
        starting_wounds=1,
        wounds_remaining=1,
        wargear_ids=(),
        source_ids=(f"source:{model_profile_id}",),
    )


def _lords_execution_record() -> faction_execution_2026_27.Phase17FExecutionRecord:
    return next(
        record
        for record in faction_execution_2026_27.execution_records()
        if record.coverage_descriptor_id == lords_ir.LORDS_OF_THE_WARP_DETACHMENT_RULE_DESCRIPTOR_ID
    )
