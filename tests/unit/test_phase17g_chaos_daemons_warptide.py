from __future__ import annotations

# pyright: reportPrivateUsage=false
from dataclasses import replace
from typing import cast

import pytest
from tests.deployment_submission_helpers import submit_all_deployments_if_pending
from tests.movement_submission_helpers import (
    straight_line_witness_for_unit,
    submit_movement_proposal,
)

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import (
    BaseSizeDefinition,
    DatasheetDefinition,
    DatasheetKeywordSet,
)
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.engine import generic_detachment_rule_effects as generic_detachment_effects
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import (
    GENERIC_RULE_EFFECT_KIND,
    EffectExpiration,
    EffectExpirationKind,
    PersistingEffect,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.faction_content.activation import RuntimeContentActivation
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons.detachments.warptide import (  # noqa: E501
    manifest,
    stratagems,
)
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.movement_proposals import MOVEMENT_PROPOSAL_DECISION_TYPE
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.movement import (
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    MovementPhaseActionKind,
)
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.engine.stratagems import (
    DECLINE_STRATAGEM_WINDOW_OPTION_ID,
    ENGAGED_ENEMY_UNIT_CONTEXT_KEY,
    ENGAGED_ENEMY_UNIT_EFFECT_SELECTION_KIND,
    GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
    HIT_ENEMY_UNIT_CONTEXT_KEY,
    HIT_ENEMY_UNIT_EFFECT_SELECTION_KIND,
    SELECTED_TARGET_UNIT_TARGET_POLICY_ID,
    STRATAGEM_DECISION_TYPE,
    TARGET_BINDING_UNIT_CONTEXT_KEY,
    VISIBLE_ENEMY_RANGE_INCHES_KEY,
    VISIBLE_ENEMY_SOURCE_UNIT_CONTEXT_KEY,
    VISIBLE_ENEMY_UNIT_CONTEXT_KEY,
    VISIBLE_ENEMY_UNIT_EFFECT_SELECTION_KIND,
    StratagemAvailabilityKind,
    StratagemEligibilityContext,
    StratagemTargetBinding,
    StratagemUseRecord,
)
from warhammer40k_core.engine.stratagems_generic_metadata import EFFECT_SELECTION_KIND_KEY
from warhammer40k_core.engine.stratagems_generic_rule_ir_context import (
    effect_selection_unit_id,
    rule_effect_source_unit_id_for_context,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.geometry.model_geometry import ModelGeometry
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack
from warhammer40k_core.rules.rule_ir import (
    RuleEffectKind,
    RuleIR,
    RuleParameterValue,
    parameter_payload,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_execution_2026_27,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_generic_ir_support_2026_27 as generic_ir_support,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_warptide_ir_support_2026_27 as warptide_ir,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_execution_2026_27 import (
    Phase17FExecutionStatus,
)

_WARPTIDE_LIFECYCLE_DATASHEET_ID = "phase17g-warptide-daemonettes"
_WARPTIDE_LIFECYCLE_UNIT_SELECTION_ID = "daemonettes"
_WARPTIDE_LIFECYCLE_UNIT_ID = f"army-alpha:{_WARPTIDE_LIFECYCLE_UNIT_SELECTION_ID}"
_WARPTIDE_LIFECYCLE_ENEMY_UNIT_SELECTION_ID = "enemy-unit"
_WARPTIDE_LIFECYCLE_ENEMY_UNIT_ID = f"army-beta:{_WARPTIDE_LIFECYCLE_ENEMY_UNIT_SELECTION_ID}"


def test_warptide_source_backed_rule_ir_rows_are_executable_generic_ir() -> None:
    descriptor_ids = {
        warptide_ir.WARPTIDE_DETACHMENT_RULE_DESCRIPTOR_ID,
        warptide_ir.BANE_FORGED_WEAPONS_DESCRIPTOR_ID,
        warptide_ir.SOUL_HUNGRY_SLAUGHTERERS_DESCRIPTOR_ID,
        warptide_ir.DAEMONIC_INFESTATION_DESCRIPTOR_ID,
        warptide_ir.SOULSEEING_DESCRIPTOR_ID,
        warptide_ir.INCORPOREAL_ENTITIES_DESCRIPTOR_ID,
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


def test_warptide_detachment_rule_ir_grants_advance_move_and_charge_hooks() -> None:
    rule_ir = generic_ir_support.generic_rule_ir_by_coverage_descriptor_id(
        warptide_ir.WARPTIDE_DETACHMENT_RULE_DESCRIPTOR_ID
    )
    grant_parameters = tuple(
        parameter_payload(effect.parameters)
        for clause in rule_ir.clauses
        for effect in clause.effects
        if effect.kind is RuleEffectKind.GRANT_ABILITY
    )

    assert {parameters["ability"] for parameters in grant_parameters} == {
        warptide_ir.SHUDDERBLINK_ASSAULT_AFTER_ADVANCE_ABILITY,
        warptide_ir.SHUDDERBLINK_CHARGE_AFTER_ADVANCE_ABILITY,
    }
    assert {parameters["hook_family"] for parameters in grant_parameters} == {
        "advance_move",
        "advance_eligibility",
    }
    assert all(
        parameters["required_faction_keyword_sequence"] == (warptide_ir.LEGIONES_DAEMONICA_KEYWORD,)
        for parameters in grant_parameters
    )
    assert all(
        parameters["required_keyword_sequence"] == (warptide_ir.BATTLELINE_KEYWORD,)
        for parameters in grant_parameters
    )


def test_warptide_runtime_stratagems_delegate_to_generic_rule_ir() -> None:
    contribution = stratagems.runtime_contribution()
    records_by_id = {
        record.definition.stratagem_id: record for record in contribution.stratagem_records
    }

    assert contribution.contribution_id == stratagems.CONTRIBUTION_ID
    assert not contribution.contribution_id.endswith(":scaffold")
    assert set(records_by_id) == {
        warptide_ir.DAEMONIC_INFESTATION_STRATAGEM_ID,
        warptide_ir.SOULSEEING_STRATAGEM_ID,
        warptide_ir.INCORPOREAL_ENTITIES_STRATAGEM_ID,
    }
    for record in records_by_id.values():
        assert record.availability_kind is StratagemAvailabilityKind.DETACHMENT
        assert record.detachment_id == warptide_ir.WARPTIDE_DETACHMENT_ID
        assert record.definition.handler_id == GENERIC_RULE_IR_STRATAGEM_HANDLER_ID
        assert record.definition.target_spec.required_keywords == (warptide_ir.BATTLELINE_KEYWORD,)
        assert record.definition.target_spec.required_faction_keywords == (
            warptide_ir.LEGIONES_DAEMONICA_KEYWORD,
        )
        assert isinstance(record.definition.effect_payload, dict)
        assert "rule_ir" in record.definition.effect_payload

    daemonic = records_by_id[warptide_ir.DAEMONIC_INFESTATION_STRATAGEM_ID]
    assert daemonic.definition.target_spec.excluded_keywords == (warptide_ir.PINK_HORRORS_KEYWORD,)

    soulseeing = records_by_id[warptide_ir.SOULSEEING_STRATAGEM_ID]
    assert isinstance(soulseeing.definition.effect_payload, dict)
    assert soulseeing.definition.effect_payload["requires_own_turn"] is True
    assert (
        soulseeing.definition.effect_payload[EFFECT_SELECTION_KIND_KEY]
        == VISIBLE_ENEMY_UNIT_EFFECT_SELECTION_KIND
    )
    assert (
        soulseeing.definition.effect_payload[VISIBLE_ENEMY_SOURCE_UNIT_CONTEXT_KEY]
        == TARGET_BINDING_UNIT_CONTEXT_KEY
    )
    assert (
        soulseeing.definition.effect_payload[VISIBLE_ENEMY_RANGE_INCHES_KEY]
        == warptide_ir.SOULSEEING_RANGE_INCHES
    )

    incorporeal = records_by_id[warptide_ir.INCORPOREAL_ENTITIES_STRATAGEM_ID]
    assert incorporeal.definition.target_spec.target_policy_id == (
        SELECTED_TARGET_UNIT_TARGET_POLICY_ID
    )
    assert isinstance(incorporeal.definition.effect_payload, dict)
    assert incorporeal.definition.effect_payload["requires_opponent_turn"] is True


def test_warptide_manifest_aggregates_rule_enhancement_and_stratagem_contributions() -> None:
    contribution = manifest.runtime_contribution()

    assert contribution.contribution_id == manifest.CONTRIBUTION_ID
    assert not contribution.contribution_id.endswith(":scaffold")
    assert len(contribution.stratagem_records) == 3
    assert contribution.stratagem_handler_bindings == ()
    assert contribution.faction_named_handlers == {}


def test_warptide_shudderblink_automatic_advance_grant_persists_assault_effect() -> None:
    config = _warptide_lifecycle_config()
    lifecycle, movement_status = _advance_to_warptide_movement_unit_selection(config)
    action_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-warptide-select-daemonettes",
            request=_decision_request(movement_status),
            selected_option_id=_WARPTIDE_LIFECYCLE_UNIT_ID,
        )
    )
    action_status = _decline_stratagem_window_if_present(
        lifecycle,
        action_status,
        result_id="phase17g-warptide-decline-selected-to-move",
    )
    action_request = _decision_request(action_status)
    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE

    proposal_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-warptide-advance-action",
            request=action_request,
            selected_option_id=MovementPhaseActionKind.ADVANCE.value,
        )
    )
    proposal_request = _decision_request(proposal_status)
    assert proposal_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE

    auto_event = _event_payload(lifecycle, "advance_move_grants_auto_selected")
    grants = cast(list[JsonValue], auto_event["selected_grants"])
    grant = cast(dict[str, JsonValue], grants[0])
    assert grant["hook_id"] == warptide_ir.SHUDDERBLINK_ADVANCE_MOVE_HOOK_ID
    assert grant["source_id"] == warptide_ir.WARPTIDE_SOURCE_RULE_ID
    assert grant["automatic"] is True

    auto_effects = cast(list[JsonValue], auto_event["persisting_effects"])
    assert len(auto_effects) == 1

    advance_status = submit_movement_proposal(
        lifecycle,
        request=proposal_request,
        result_id="phase17g-warptide-advance-proposal",
        unit_instance_id=_WARPTIDE_LIFECYCLE_UNIT_ID,
        movement_phase_action=MovementPhaseActionKind.ADVANCE,
        movement_mode=MovementMode.ADVANCE,
        witness=straight_line_witness_for_unit(
            lifecycle,
            unit_instance_id=_WARPTIDE_LIFECYCLE_UNIT_ID,
            dx=6.0,
        ),
    )
    _decline_stratagem_window_if_present(
        lifecycle,
        advance_status,
        result_id="phase17g-warptide-decline-after-advance",
    )

    state = _state(lifecycle)
    advanced_state = state.advanced_unit_state_for_unit(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=_WARPTIDE_LIFECYCLE_UNIT_ID,
    )
    assert advanced_state is not None
    assert advanced_state.can_shoot
    assert advanced_state.can_declare_charge

    effect = _single_persisting_effect_for_unit_by_kind(
        state,
        _WARPTIDE_LIFECYCLE_UNIT_ID,
        "ranged_weapon_keyword_grant",
    )
    effect_payload = cast(dict[str, JsonValue], effect.effect_payload)
    assert effect.source_rule_id == warptide_ir.WARPTIDE_SOURCE_RULE_ID
    assert effect.owner_player_id == "player-a"
    assert effect.target_unit_instance_ids == (_WARPTIDE_LIFECYCLE_UNIT_ID,)
    assert effect.expiration.expiration_kind is EffectExpirationKind.END_TURN
    assert effect_payload == {
        "effect_kind": "ranged_weapon_keyword_grant",
        "granted_weapon_keywords": [warptide_ir.ASSAULT_WEAPON_KEYWORD],
        "source_movement_request_id": action_request.request_id,
        "source_movement_result_id": "phase17g-warptide-advance-action",
    }
    auto_effect = cast(dict[str, JsonValue], auto_effects[0])
    assert auto_effect["effect_id"] == effect.effect_id


def test_warptide_visible_enemy_effect_selection_context_helpers() -> None:
    use_record = _warptide_use_record(
        stratagem_id=warptide_ir.SOULSEEING_STRATAGEM_ID,
        target_unit_id="army-a:daemonettes",
        effect_selection={
            "effect_selection_kind": VISIBLE_ENEMY_UNIT_EFFECT_SELECTION_KIND,
            VISIBLE_ENEMY_UNIT_CONTEXT_KEY: "army-b:intercessors",
        },
    )
    context = StratagemEligibilityContext(
        game_id="warptide-visible-context",
        player_id="player-a",
        battle_round=1,
        phase=BattlePhase.SHOOTING,
        active_player_id="player-a",
        trigger_kind=TimingTriggerKind.START_PHASE,
        timing_window_id="warptide-soulseeing-window",
        trigger_payload={"source_unit": "army-a:bloodletters"},
    )

    assert (
        effect_selection_unit_id(
            use_record,
            expected_selection_kind=VISIBLE_ENEMY_UNIT_EFFECT_SELECTION_KIND,
        )
        == "army-b:intercessors"
    )
    assert (
        rule_effect_source_unit_id_for_context(
            context=context,
            use_record=use_record,
            effect_payload=_source_unit_context_effect_payload(TARGET_BINDING_UNIT_CONTEXT_KEY),
        )
        == "army-a:daemonettes"
    )
    assert (
        rule_effect_source_unit_id_for_context(
            context=context,
            use_record=use_record,
            effect_payload=_source_unit_context_effect_payload("source_unit"),
        )
        == "army-a:bloodletters"
    )
    assert (
        effect_selection_unit_id(
            replace(
                use_record,
                effect_selection={
                    "effect_selection_kind": HIT_ENEMY_UNIT_EFFECT_SELECTION_KIND,
                    HIT_ENEMY_UNIT_CONTEXT_KEY: "army-b:hit-target",
                },
            ),
            expected_selection_kind=HIT_ENEMY_UNIT_EFFECT_SELECTION_KIND,
        )
        == "army-b:hit-target"
    )
    assert (
        effect_selection_unit_id(
            replace(
                use_record,
                effect_selection={
                    "effect_selection_kind": ENGAGED_ENEMY_UNIT_EFFECT_SELECTION_KIND,
                    ENGAGED_ENEMY_UNIT_CONTEXT_KEY: "army-b:engaged-target",
                },
            ),
            expected_selection_kind=ENGAGED_ENEMY_UNIT_EFFECT_SELECTION_KIND,
        )
        == "army-b:engaged-target"
    )


def test_warptide_visible_enemy_effect_selection_context_helpers_are_fail_fast() -> None:
    use_record = _warptide_use_record(
        stratagem_id=warptide_ir.SOULSEEING_STRATAGEM_ID,
        target_unit_id="army-a:daemonettes",
        effect_selection=None,
    )
    context = StratagemEligibilityContext(
        game_id="warptide-visible-context",
        player_id="player-a",
        battle_round=1,
        phase=BattlePhase.SHOOTING,
        active_player_id="player-a",
        trigger_kind=TimingTriggerKind.START_PHASE,
        timing_window_id="warptide-soulseeing-window",
        trigger_payload=None,
    )

    with pytest.raises(GameLifecycleError, match="requires effect selection"):
        effect_selection_unit_id(
            use_record,
            expected_selection_kind=VISIBLE_ENEMY_UNIT_EFFECT_SELECTION_KIND,
        )
    with pytest.raises(GameLifecycleError, match="selection kind drift"):
        effect_selection_unit_id(
            replace(
                use_record,
                effect_selection={"effect_selection_kind": "wrong-kind"},
            ),
            expected_selection_kind=VISIBLE_ENEMY_UNIT_EFFECT_SELECTION_KIND,
        )
    with pytest.raises(GameLifecycleError, match="missing unit"):
        effect_selection_unit_id(
            replace(
                use_record,
                effect_selection={
                    "effect_selection_kind": VISIBLE_ENEMY_UNIT_EFFECT_SELECTION_KIND,
                    VISIBLE_ENEMY_UNIT_CONTEXT_KEY: 1,
                },
            ),
            expected_selection_kind=VISIBLE_ENEMY_UNIT_EFFECT_SELECTION_KIND,
        )
    with pytest.raises(GameLifecycleError, match="structured trigger payload"):
        rule_effect_source_unit_id_for_context(
            context=context,
            use_record=use_record,
            effect_payload=_source_unit_context_effect_payload("source_unit"),
        )
    with pytest.raises(GameLifecycleError, match="selection kind is unsupported"):
        effect_selection_unit_id(
            replace(
                use_record,
                effect_selection={"effect_selection_kind": "custom-selection"},
            ),
            expected_selection_kind="custom-selection",
        )
    with pytest.raises(GameLifecycleError, match="requires one target unit"):
        rule_effect_source_unit_id_for_context(
            context=context,
            use_record=replace(
                use_record,
                targeted_unit_instance_ids=("army-a:one", "army-a:two"),
            ),
            effect_payload=_source_unit_context_effect_payload(TARGET_BINDING_UNIT_CONTEXT_KEY),
        )
    with pytest.raises(GameLifecycleError, match="missing a unit"):
        rule_effect_source_unit_id_for_context(
            context=replace(context, trigger_payload={"source_unit": 1}),
            use_record=use_record,
            effect_payload=_source_unit_context_effect_payload("source_unit"),
        )
    with pytest.raises(GameLifecycleError, match="requires effect object"):
        rule_effect_source_unit_id_for_context(
            context=context,
            use_record=use_record,
            effect_payload={},
        )
    with pytest.raises(GameLifecycleError, match="parameters must be a list"):
        rule_effect_source_unit_id_for_context(
            context=context,
            use_record=use_record,
            effect_payload={"effect": {"parameters": "bad"}},
        )
    with pytest.raises(GameLifecycleError, match="parameter must be an object"):
        rule_effect_source_unit_id_for_context(
            context=context,
            use_record=use_record,
            effect_payload={"effect": {"parameters": ["bad"]}},
        )
    with pytest.raises(GameLifecycleError, match="must be a string"):
        rule_effect_source_unit_id_for_context(
            context=context,
            use_record=use_record,
            effect_payload={
                "effect": {
                    "parameters": [{"key": "source_unit_context_key", "value": 1}],
                },
            },
        )


def test_warptide_registered_detachment_binding_uses_generic_rule_ir_descriptor() -> None:
    activation = RuntimeContentActivation(
        selected_faction_ids=(warptide_ir.CHAOS_DAEMONS_FACTION_ID,),
        selected_detachment_ids=(warptide_ir.WARPTIDE_DETACHMENT_ID,),
        selected_enhancement_ids=(),
        selected_stratagem_ids=(),
        selected_datasheet_ids=(),
        selected_wargear_ids=(),
        selected_weapon_profile_ids=(),
        selected_weapon_keywords=(),
        loaded_unit_instance_ids=(),
    )
    record = _warptide_execution_record()

    bindings = generic_detachment_effects.generic_detachment_rule_battle_formation_hook_bindings(
        activation=activation,
        execution_records=(record,),
    )

    assert len(bindings) == 1
    assert bindings[0].hook_id == f"{record.execution_id}:battle-formation"
    assert (
        bindings[0].source_id
        == generic_ir_support.generic_rule_ir_by_coverage_descriptor_id(
            warptide_ir.WARPTIDE_DETACHMENT_RULE_DESCRIPTOR_ID
        ).source_id
    )


def test_warptide_detachment_target_selection_is_rule_ir_keyword_driven() -> None:
    ruleset = RulesetDescriptor.warhammer_40000_eleventh()
    matching = _unit(
        unit_instance_id="army-a:bloodletters",
        datasheet_id="bloodletters",
        name="Bloodletters",
        keywords=(warptide_ir.BATTLELINE_KEYWORD,),
        faction_keywords=(warptide_ir.LEGIONES_DAEMONICA_KEYWORD,),
    )
    wrong_keyword = _unit(
        unit_instance_id="army-a:beast",
        datasheet_id="beast-of-nurgle",
        name="Beast of Nurgle",
        keywords=("BEAST",),
        faction_keywords=(warptide_ir.LEGIONES_DAEMONICA_KEYWORD,),
    )
    wrong_faction = _unit(
        unit_instance_id="army-a:cultists",
        datasheet_id="cultists",
        name="Cultists",
        keywords=(warptide_ir.BATTLELINE_KEYWORD,),
        faction_keywords=("HERETIC ASTARTES",),
    )
    army = _army(
        army_id="army-a",
        player_id="player-a",
        ruleset=ruleset,
        faction_id=warptide_ir.CHAOS_DAEMONS_FACTION_ID,
        detachment_id=warptide_ir.WARPTIDE_DETACHMENT_ID,
        units=(matching, wrong_keyword, wrong_faction),
    )
    rule_ir = generic_ir_support.generic_rule_ir_by_coverage_descriptor_id(
        warptide_ir.WARPTIDE_DETACHMENT_RULE_DESCRIPTOR_ID
    )
    record = replace(
        _warptide_execution_record(),
        coverage_descriptor_id="phase17e:chaos-daemons:warptide:synthetic-rule",
    )

    assert generic_detachment_effects._target_unit_ids_for_record(
        record=record,
        rule_ir=rule_ir,
        army=army,
    ) == ("army-a:bloodletters",)


def test_warptide_generic_keyword_requirement_helpers_are_fail_fast() -> None:
    with pytest.raises(GameLifecycleError, match="required_keyword must be a string"):
        generic_detachment_effects._unit_keyword_requirement_from_parameters(
            cast(dict[str, RuleParameterValue], {"required_keyword": 1})
        )
    with pytest.raises(GameLifecycleError, match="required_keyword_sequence must be a tuple"):
        generic_detachment_effects._unit_keyword_requirement_from_parameters(
            cast(dict[str, RuleParameterValue], {"required_keyword_sequence": ["BATTLELINE"]})
        )
    with pytest.raises(GameLifecycleError, match="required_keyword_sequence must contain strings"):
        generic_detachment_effects._unit_keyword_requirement_from_parameters(
            cast(dict[str, RuleParameterValue], {"required_keyword_sequence": ("BATTLELINE", 1)})
        )
    with pytest.raises(GameLifecycleError, match="required_keyword_any must be a tuple"):
        generic_detachment_effects._unit_keyword_requirement_from_parameters(
            cast(dict[str, RuleParameterValue], {"required_keyword_any": ["INFANTRY"]})
        )
    with pytest.raises(GameLifecycleError, match="required_keyword_any must not be empty"):
        generic_detachment_effects._unit_keyword_requirement_from_parameters(
            cast(dict[str, RuleParameterValue], {"required_keyword_any": ()})
        )
    with pytest.raises(GameLifecycleError, match="required_keyword_any item is invalid"):
        generic_detachment_effects._unit_keyword_requirement_from_parameters(
            cast(dict[str, RuleParameterValue], {"required_keyword_any": ("INFANTRY", 1)})
        )
    assert (
        generic_detachment_effects._unit_keyword_requirement_from_parameters(
            cast(dict[str, RuleParameterValue], {})
        )
        is None
    )


def test_warptide_generic_detachment_effect_helpers_cover_error_branches() -> None:
    record = _warptide_execution_record()
    rule_ir = generic_ir_support.generic_rule_ir_by_coverage_descriptor_id(
        warptide_ir.WARPTIDE_DETACHMENT_RULE_DESCRIPTOR_ID
    )
    ruleset = RulesetDescriptor.warhammer_40000_eleventh()
    army = _army(
        army_id="army-a",
        player_id="player-a",
        ruleset=ruleset,
        faction_id=warptide_ir.CHAOS_DAEMONS_FACTION_ID,
        detachment_id=warptide_ir.WARPTIDE_DETACHMENT_ID,
        units=(
            _unit(
                unit_instance_id="army-a:beast",
                datasheet_id="beast-of-nurgle",
                name="Beast of Nurgle",
                keywords=("BEAST",),
                faction_keywords=(warptide_ir.LEGIONES_DAEMONICA_KEYWORD,),
            ),
        ),
    )

    with pytest.raises(GameLifecycleError, match="requires execution record"):
        generic_detachment_effects._GenericDetachmentRuleBindingSource(
            record=cast(faction_execution_2026_27.Phase17FExecutionRecord, object()),
            rule_ir=rule_ir,
        )
    with pytest.raises(GameLifecycleError, match="requires RuleIR"):
        generic_detachment_effects._GenericDetachmentRuleBindingSource(
            record=record,
            rule_ir=cast(RuleIR, object()),
        )
    with pytest.raises(GameLifecycleError, match="stale RuleIR hash"):
        generic_detachment_effects._GenericDetachmentRuleBindingSource(
            record=replace(record, rule_ir_hash="0" * 64),
            rule_ir=rule_ir,
        )
    with pytest.raises(GameLifecycleError, match="require activation"):
        generic_detachment_effects.generic_detachment_rule_battle_formation_hook_bindings(
            activation=cast(RuntimeContentActivation, object()),
            execution_records=(record,),
        )
    with pytest.raises(GameLifecycleError, match="require execution records"):
        generic_detachment_effects.generic_detachment_rule_battle_formation_hook_bindings(
            activation=_warptide_activation(),
            execution_records=cast(
                tuple[faction_execution_2026_27.Phase17FExecutionRecord, ...], object()
            ),
        )
    with pytest.raises(GameLifecycleError, match="require execution records"):
        generic_detachment_effects.generic_detachment_rule_battle_formation_hook_bindings(
            activation=_warptide_activation(),
            execution_records=cast(
                tuple[faction_execution_2026_27.Phase17FExecutionRecord, ...],
                (object(),),
            ),
        )
    with pytest.raises(GameLifecycleError, match="require ArmyDefinition"):
        generic_detachment_effects._army_uses_record(
            army=cast(ArmyDefinition, object()),
            record=record,
        )
    with pytest.raises(GameLifecycleError, match="requires detachment_id"):
        generic_detachment_effects._army_uses_record(
            army=army,
            record=replace(record, detachment_id=None),
        )
    with pytest.raises(GameLifecycleError, match="not supported by runtime"):
        generic_detachment_effects._target_unit_ids_for_record(
            record=replace(
                record,
                coverage_descriptor_id="phase17e:chaos-daemons:warptide:synthetic-rule",
            ),
            rule_ir=rule_ir,
            army=army,
        )
    with pytest.raises(GameLifecycleError, match="requires RuleIR"):
        generic_detachment_effects._target_unit_ids_from_rule_ir_keyword_requirements(
            rule_ir=cast(RuleIR, object()),
            army=army,
        )
    with pytest.raises(GameLifecycleError, match="requires army"):
        generic_detachment_effects._target_unit_ids_from_rule_ir_keyword_requirements(
            rule_ir=rule_ir,
            army=cast(ArmyDefinition, object()),
        )
    with pytest.raises(GameLifecycleError, match="requires UnitInstance"):
        generic_detachment_effects._unit_matches_keyword_requirement(
            cast(UnitInstance, object()),
            generic_detachment_effects._UnitKeywordRequirement(
                required_keywords=(),
                required_faction_keywords=(),
                required_keyword_any=None,
                excluded_keywords=(),
            ),
        )
    with pytest.raises(GameLifecycleError, match="payload requires clause_id"):
        generic_detachment_effects._payload_string({}, "clause_id")


def test_generic_detachment_existing_keyword_target_predicates_remain_strict() -> None:
    ruleset = RulesetDescriptor.warhammer_40000_eleventh()
    units = (
        _unit(
            unit_instance_id="army-a:ork-boyz",
            datasheet_id="ork-boyz",
            name="Ork Boyz",
            keywords=("INFANTRY",),
            faction_keywords=("ORKS",),
        ),
        _unit(
            unit_instance_id="army-a:ork-trukk",
            datasheet_id="ork-trukk",
            name="Ork Trukk",
            keywords=("VEHICLE",),
            faction_keywords=("ORKS",),
        ),
        _unit(
            unit_instance_id="army-a:flawless-blades",
            datasheet_id="flawless-blades",
            name="Flawless Blades",
            keywords=("FLAWLESS BLADES",),
            faction_keywords=("EMPEROR'S CHILDREN",),
        ),
        _unit(
            unit_instance_id="army-a:emperor-children",
            datasheet_id="emperor-children",
            name="Emperor's Children",
            keywords=("INFANTRY",),
            faction_keywords=("EMPEROR'S CHILDREN",),
        ),
        _unit(
            unit_instance_id="army-a:shadow-legion",
            datasheet_id="shadow-legion",
            name="Shadow Legion",
            keywords=("SHADOW LEGION",),
            faction_keywords=(warptide_ir.LEGIONES_DAEMONICA_KEYWORD,),
        ),
        _unit(
            unit_instance_id="army-a:khorne-daemons",
            datasheet_id="khorne-daemons",
            name="Khorne Daemons",
            keywords=("KHORNE",),
            faction_keywords=(warptide_ir.LEGIONES_DAEMONICA_KEYWORD,),
        ),
    )
    army = _army(
        army_id="army-a",
        player_id="player-a",
        ruleset=ruleset,
        faction_id=warptide_ir.CHAOS_DAEMONS_FACTION_ID,
        detachment_id=warptide_ir.WARPTIDE_DETACHMENT_ID,
        units=units,
    )
    record = _warptide_execution_record()
    rule_ir = generic_ir_support.generic_rule_ir_by_coverage_descriptor_id(
        warptide_ir.WARPTIDE_DETACHMENT_RULE_DESCRIPTOR_ID
    )

    assert generic_detachment_effects._target_unit_ids_for_record(
        record=replace(
            record,
            coverage_descriptor_id=generic_detachment_effects.MORE_DAKKA_DETACHMENT_RULE_DESCRIPTOR_ID,
        ),
        rule_ir=rule_ir,
        army=army,
    ) == ("army-a:ork-boyz",)
    assert generic_detachment_effects._target_unit_ids_for_record(
        record=replace(
            record,
            coverage_descriptor_id=(
                generic_detachment_effects.SPECTACLE_OF_SLAUGHTER_DETACHMENT_RULE_DESCRIPTOR_ID
            ),
        ),
        rule_ir=rule_ir,
        army=army,
    ) == ("army-a:flawless-blades",)
    assert generic_detachment_effects._target_unit_ids_for_record(
        record=replace(
            record,
            coverage_descriptor_id=(
                generic_detachment_effects.COURT_OF_THE_PHOENICIAN_DETACHMENT_RULE_DESCRIPTOR_ID
            ),
        ),
        rule_ir=rule_ir,
        army=army,
    ) == ("army-a:emperor-children", "army-a:flawless-blades")
    assert generic_detachment_effects._target_unit_ids_for_record(
        record=replace(
            record,
            coverage_descriptor_id=generic_detachment_effects.SHADOW_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID,
        ),
        rule_ir=rule_ir,
        army=army,
    ) == ("army-a:shadow-legion",)
    assert generic_detachment_effects._target_unit_ids_for_record(
        record=replace(
            record,
            coverage_descriptor_id=generic_detachment_effects.BLOOD_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID,
        ),
        rule_ir=rule_ir,
        army=army,
    ) == ("army-a:khorne-daemons",)

    for predicate in (
        generic_detachment_effects._unit_is_spectacle_of_slaughter_detachment_target,
        generic_detachment_effects._unit_is_more_dakka_detachment_target,
        generic_detachment_effects._unit_is_court_of_the_phoenician_detachment_target,
        generic_detachment_effects._unit_is_shadow_legion_detachment_target,
        generic_detachment_effects._unit_is_blood_legion_detachment_target,
    ):
        with pytest.raises(GameLifecycleError, match="requires UnitInstance"):
            predicate(cast(UnitInstance, object()))


def test_generic_detachment_persisting_effect_payload_handles_fights_first_and_invalid() -> None:
    effect = generic_detachment_effects._persisting_effect_for_detachment_payload(
        effect_id="warptide:fights-first-effect",
        source_rule_id="source:warptide:fights-first",
        owner_player_id="player-a",
        target_unit_instance_ids=("army-a:bloodletters",),
        started_battle_round=1,
        started_phase=BattlePhase.COMMAND,
        expiration=EffectExpiration.end_of_battle(),
        effect_payload={
            "effect_kind": GENERIC_RULE_EFFECT_KIND,
            "effect": {
                "kind": "grant_ability",
                "parameters": [{"key": "ability", "value": "fights_first"}],
            },
        },
    )

    payload = effect.effect_payload
    assert isinstance(payload, dict)
    assert payload["effect_kind"] == "fights_first"
    with pytest.raises(GameLifecycleError, match="payload must be an object"):
        generic_detachment_effects._persisting_effect_for_detachment_payload(
            effect_id="warptide:invalid-effect",
            source_rule_id="source:warptide:invalid",
            owner_player_id="player-a",
            target_unit_instance_ids=("army-a:bloodletters",),
            started_battle_round=1,
            started_phase=BattlePhase.COMMAND,
            expiration=EffectExpiration.end_of_battle(),
            effect_payload=cast(JsonValue, "not-an-object"),
        )


def _warptide_use_record(
    *,
    stratagem_id: str,
    target_unit_id: str,
    effect_selection: JsonValue,
) -> StratagemUseRecord:
    definition = next(
        record.definition
        for record in stratagems.runtime_contribution().stratagem_records
        if record.definition.stratagem_id == stratagem_id
    )
    return StratagemUseRecord(
        use_id=f"warptide:{stratagem_id}:fixture-use",
        player_id="player-a",
        stratagem_id=stratagem_id,
        source_id=definition.source_id,
        battle_round=1,
        phase=BattlePhase.SHOOTING,
        active_player_id="player-a",
        timing_window_id="warptide-fixture-window",
        request_id=f"warptide:{stratagem_id}:fixture-request",
        result_id=f"warptide:{stratagem_id}:fixture-result",
        selected_option_id=f"warptide:{stratagem_id}:fixture-option",
        target_binding=StratagemTargetBinding(
            target_kind=definition.target_spec.target_kind,
            target_player_id="player-a",
            target_unit_instance_id=target_unit_id,
        ),
        targeted_unit_instance_ids=(target_unit_id,),
        affected_unit_instance_ids=(target_unit_id,),
        command_point_cost=definition.command_point_cost,
        command_point_transaction_id=f"warptide:{stratagem_id}:fixture-cp",
        handler_id=definition.handler_id,
        effect_selection=effect_selection,
        effect_payload=definition.effect_payload,
    )


def _warptide_execution_record() -> faction_execution_2026_27.Phase17FExecutionRecord:
    return next(
        record
        for record in faction_execution_2026_27.execution_records()
        if record.coverage_descriptor_id == warptide_ir.WARPTIDE_DETACHMENT_RULE_DESCRIPTOR_ID
    )


def _warptide_activation() -> RuntimeContentActivation:
    return RuntimeContentActivation(
        selected_faction_ids=(warptide_ir.CHAOS_DAEMONS_FACTION_ID,),
        selected_detachment_ids=(warptide_ir.WARPTIDE_DETACHMENT_ID,),
        selected_enhancement_ids=(),
        selected_stratagem_ids=(),
        selected_datasheet_ids=(),
        selected_wargear_ids=(),
        selected_weapon_profile_ids=(),
        selected_weapon_keywords=(),
        loaded_unit_instance_ids=(),
    )


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
        catalog_id="warptide-detachment-effects-test-catalog",
        source_package_id=warptide_ir.SOURCE_PACKAGE_ID,
        ruleset_id=ruleset.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=faction_id,
            detachment_ids=(detachment_id,),
        ),
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


def _warptide_lifecycle_config() -> GameConfig:
    catalog = _warptide_lifecycle_catalog()
    return GameConfig(
        game_id="phase17g-warptide-shudderblink",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-phase17g-warptide-test"
        ),
        army_catalog=catalog,
        army_muster_requests=(
            _warptide_lifecycle_muster_request(
                catalog=catalog,
                army_id="army-alpha",
                player_id="player-a",
                faction_id=warptide_ir.CHAOS_DAEMONS_FACTION_ID,
                detachment_id=warptide_ir.WARPTIDE_DETACHMENT_ID,
                unit_selection_id=_WARPTIDE_LIFECYCLE_UNIT_SELECTION_ID,
                datasheet_id=_WARPTIDE_LIFECYCLE_DATASHEET_ID,
                model_profile_id="core-intercessor-like",
                model_count=5,
            ),
            _warptide_lifecycle_muster_request(
                catalog=catalog,
                army_id="army-beta",
                player_id="player-b",
                faction_id="core-marine-force",
                detachment_id="core-combined-arms",
                unit_selection_id=_WARPTIDE_LIFECYCLE_ENEMY_UNIT_SELECTION_ID,
                datasheet_id="core-intercessor-like-infantry",
                model_profile_id="core-intercessor-like",
                model_count=5,
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=_warptide_lifecycle_mission_setup(),
    )


def _warptide_lifecycle_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    daemon_datasheet = _warptide_daemon_datasheet(
        base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    )
    return replace(
        base_catalog,
        datasheets=(*base_catalog.datasheets, daemon_datasheet),
        factions=(
            *base_catalog.factions,
            FactionDefinition(
                faction_id=warptide_ir.CHAOS_DAEMONS_FACTION_ID,
                name="Chaos Daemons",
                faction_keywords=(warptide_ir.LEGIONES_DAEMONICA_KEYWORD,),
                source_ids=("gw-11e-faction-detachments-2026-27:faction:chaos-daemons",),
            ),
        ),
        detachments=(
            *base_catalog.detachments,
            DetachmentDefinition(
                detachment_id=warptide_ir.WARPTIDE_DETACHMENT_ID,
                name="Warptide",
                faction_id=warptide_ir.CHAOS_DAEMONS_FACTION_ID,
                detachment_point_cost=3,
                unit_datasheet_ids=(_WARPTIDE_LIFECYCLE_DATASHEET_ID,),
                force_disposition_ids=("phase17g-force",),
                source_ids=(
                    "gw-11e-faction-detachments-2026-27:detachment:chaos-daemons:warptide",
                ),
            ),
        ),
    )


def _warptide_daemon_datasheet(base_datasheet: DatasheetDefinition) -> DatasheetDefinition:
    return replace(
        base_datasheet,
        datasheet_id=_WARPTIDE_LIFECYCLE_DATASHEET_ID,
        name="Shudderblink Test Daemonettes",
        keywords=DatasheetKeywordSet(
            keywords=(warptide_ir.BATTLELINE_KEYWORD, "INFANTRY"),
            faction_keywords=(warptide_ir.LEGIONES_DAEMONICA_KEYWORD,),
        ),
        attachment_eligibilities=(),
        source_ids=("phase17g:test:warptide:daemonettes",),
    )


def _warptide_lifecycle_muster_request(
    *,
    catalog: ArmyCatalog,
    army_id: str,
    player_id: str,
    faction_id: str,
    detachment_id: str,
    unit_selection_id: str,
    datasheet_id: str,
    model_profile_id: str,
    model_count: int,
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=faction_id,
            detachment_ids=(detachment_id,),
        ),
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id=datasheet_id,
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id=model_profile_id,
                        model_count=model_count,
                    ),
                ),
            ),
        ),
    )


def _warptide_lifecycle_mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )


def _advance_to_warptide_movement_unit_selection(
    config: GameConfig,
) -> tuple[GameLifecycle, LifecycleStatus]:
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    status = lifecycle.advance_until_decision_or_terminal()
    secondary_index = 1
    while (
        status.decision_request is not None
        and status.decision_request.decision_type == SECONDARY_MISSION_DECISION_TYPE
    ):
        status = lifecycle.submit_decision(
            DecisionResult.for_request(
                result_id=f"phase17g-warptide-secondary-{secondary_index:06d}",
                request=_decision_request(status),
                selected_option_id="fixed:assassination:bring_it_down",
            )
        )
        secondary_index += 1
    status = submit_all_deployments_if_pending(
        lifecycle,
        status,
        result_id_prefix="phase17g-warptide-deploy",
        pose_factory=_warptide_lifecycle_deployment_pose,
    )
    request = _decision_request(status)
    assert request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    return lifecycle, status


def _decline_stratagem_window_if_present(
    lifecycle: GameLifecycle,
    status: LifecycleStatus,
    *,
    result_id: str,
) -> LifecycleStatus:
    request = _decision_request(status)
    if request.decision_type != STRATAGEM_DECISION_TYPE:
        return status
    return lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id=result_id,
            request=request,
            selected_option_id=DECLINE_STRATAGEM_WINDOW_OPTION_ID,
        )
    )


def _warptide_lifecycle_deployment_pose(
    index: int,
    player_id: str,
    model_instance_id: str,
) -> Pose:
    unit_instance_id = model_instance_id.rsplit(":", 2)[0]
    if unit_instance_id == _WARPTIDE_LIFECYCLE_UNIT_ID:
        return Pose.at(15.5, 17.0 + (index * 1.8), 0.0, facing_degrees=0.0)
    if unit_instance_id == _WARPTIDE_LIFECYCLE_ENEMY_UNIT_ID:
        return Pose.at(43.5, 17.0 + (index * 1.8), 0.0, facing_degrees=180.0)
    if player_id == "player-b":
        return Pose.at(57.0, 24.0 + (index * 1.8), 0.0, facing_degrees=180.0)
    return Pose.at(3.0, 24.0 + (index * 1.8), 0.0, facing_degrees=0.0)


def _single_persisting_effect_for_unit_by_kind(
    state: GameState,
    unit_instance_id: str,
    effect_kind: str,
) -> PersistingEffect:
    effects = _persisting_effects_for_unit_by_kind(state, unit_instance_id, effect_kind)
    assert len(effects) == 1
    return effects[0]


def _persisting_effects_for_unit_by_kind(
    state: GameState,
    unit_instance_id: str,
    effect_kind: str,
) -> tuple[PersistingEffect, ...]:
    effects: list[PersistingEffect] = []
    for effect in state.persisting_effects_for_unit(unit_instance_id):
        payload = cast(dict[str, JsonValue], effect.effect_payload)
        if payload.get("effect_kind") == effect_kind:
            effects.append(effect)
    return tuple(effects)


def _event_payload(lifecycle: GameLifecycle, event_type: str) -> dict[str, JsonValue]:
    for event in lifecycle.decision_controller.event_log.records:
        if event.event_type == event_type:
            return cast(dict[str, JsonValue], event.payload)
    raise AssertionError(f"missing event {event_type}")


def _decision_request(status: LifecycleStatus) -> DecisionRequest:
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request


def _state(lifecycle: GameLifecycle) -> GameState:
    assert lifecycle.state is not None
    return lifecycle.state


def _source_unit_context_effect_payload(context_key: str) -> dict[str, JsonValue]:
    return cast(
        dict[str, JsonValue],
        {
            "effect": {
                "parameters": [
                    {"key": "source_unit_context_key", "value": context_key},
                ],
            },
        },
    )
