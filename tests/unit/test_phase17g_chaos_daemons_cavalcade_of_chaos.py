from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import cast

import pytest
from tests.movement_submission_helpers import (
    straight_line_witness_for_unit,
    submit_action_and_movement_proposal,
)
from tests.unit.test_phase10o_fall_back import (
    _advance_to_movement_unit_selection,  # pyright: ignore[reportPrivateUsage]
    _decision_request,  # pyright: ignore[reportPrivateUsage]
    _fall_back_forward_pose,  # pyright: ignore[reportPrivateUsage]
    _fall_back_witness,  # pyright: ignore[reportPrivateUsage]
    _move_first_enemy_model_into_side_engagement,  # pyright: ignore[reportPrivateUsage]
    _state,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import DatasheetDefinition, DatasheetKeywordSet
from warhammer40k_core.core.detachment import (
    DetachmentDefinition,
    EnhancementDefinition,
    EnhancementSubtype,
)
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.engine.army_mustering import (
    ArmyMusterRequest,
    EnhancementAssignment,
    validate_roster_legality,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons.detachments.cavalcade_of_chaos import (  # noqa: E501
    enhancements,
    rule,
)
from warhammer40k_core.engine.fall_back_hooks import (
    FallBackEligibilityContext,
    FallBackEligibilityGrant,
    FallBackEligibilityHookBinding,
    FallBackEligibilityHookRegistry,
)
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.phases.charge import (
    COMPLETE_CHARGE_PHASE_OPTION_ID,
    SELECT_CHARGING_UNIT_DECISION_TYPE,
    ChargePhaseHandler,
)
from warhammer40k_core.engine.phases.movement import FallBackModeKind, MovementPhaseActionKind
from warhammer40k_core.engine.phases.shooting import (
    COMPLETE_SHOOTING_PHASE_OPTION_ID,
    SELECT_SHOOTING_UNIT_DECISION_TYPE,
    ShootingPhaseHandler,
)
from warhammer40k_core.engine.unit_factory import ModelInstance
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_execution_2026_27,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_coverage_2026_27 import (
    Phase17ECoverageKind,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_execution_2026_27 import (
    Phase17FExecutionRecord,
)

_CAVALCADE_TEST_DATASHEET_ID = "phase17g-cavalcade-mounted-daemon"
_CAVALCADE_UNIT_ID = "army-alpha:intercessor-unit-1"
_ENEMY_UNIT_ID = "army-beta:intercessor-unit-2"
_ORDERED_FALL_BACK_OPTION_ID = (
    f"{MovementPhaseActionKind.FALL_BACK.value}:{FallBackModeKind.ORDERED_RETREAT.value}"
)


def test_cavalcade_unholy_avalanche_grants_fall_back_shoot_and_charge_permissions() -> None:
    config = _cavalcade_config()
    lifecycle, movement_status = _advance_to_movement_unit_selection(config)
    _move_first_enemy_model_into_side_engagement(lifecycle)
    state = _state(lifecycle)
    bundle = _runtime_content_bundle(lifecycle)
    summary = bundle.to_summary_payload()

    assert rule.HOOK_ID in summary["fall_back_hook_ids"]
    assert rule.SOURCE_RULE_ID in summary["selected_execution_record_ids"]
    assert any(
        path.endswith(".chaos_daemons.detachments.cavalcade_of_chaos.manifest")
        for path in summary["selected_module_paths"]
    )

    selection_request = _decision_request(movement_status)
    action_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-cavalcade-select-mounted",
            request=selection_request,
            selected_option_id=_CAVALCADE_UNIT_ID,
        )
    )
    action_request = _decision_request(action_status)
    assert _ORDERED_FALL_BACK_OPTION_ID in {option.option_id for option in action_request.options}
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield_state")
    unit_placement = state.battlefield_state.unit_placement_by_id(_CAVALCADE_UNIT_ID)

    fall_back_status = submit_action_and_movement_proposal(
        lifecycle,
        request=action_request,
        option_id=_ORDERED_FALL_BACK_OPTION_ID,
        action_result_id="phase17g-cavalcade-fall-back-action",
        proposal_result_id="phase17g-cavalcade-fall-back-proposal",
        unit_instance_id=_CAVALCADE_UNIT_ID,
        movement_phase_action=MovementPhaseActionKind.FALL_BACK,
        movement_mode=MovementMode.FALL_BACK,
        fall_back_mode=FallBackModeKind.ORDERED_RETREAT,
        witness=_fall_back_witness(
            unit_placement,
            first_model_end_pose=_fall_back_forward_pose(unit_placement),
        ),
    )

    assert fall_back_status.status_kind in {
        LifecycleStatusKind.ADVANCED,
        LifecycleStatusKind.WAITING_FOR_DECISION,
    }
    fell_back_state = state.fell_back_unit_state_for_unit(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=_CAVALCADE_UNIT_ID,
    )
    assert fell_back_state is not None
    assert fell_back_state.can_shoot
    assert fell_back_state.can_declare_charge
    grant_event = _event_payload(lifecycle, "fall_back_eligibility_hooks_resolved")
    grants = cast(list[JsonValue], grant_event["grants"])
    grant = cast(dict[str, JsonValue], grants[0])
    replay_payload = cast(dict[str, JsonValue], grant["replay_payload"])
    assert grant["hook_id"] == rule.HOOK_ID
    assert grant["source_id"] == rule.SOURCE_RULE_ID
    assert grant["can_shoot"] is True
    assert grant["can_declare_charge"] is True
    assert replay_payload["effect_kind"] == "unholy_avalanche"
    assert replay_payload["unit_instance_id"] == _CAVALCADE_UNIT_ID

    shooting_state = _state_at_phase(state, BattlePhase.SHOOTING)
    shooting_status = ShootingPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
    ).begin_phase(state=shooting_state, decisions=DecisionController())
    shooting_request = _decision_request(shooting_status)
    assert shooting_request.decision_type == SELECT_SHOOTING_UNIT_DECISION_TYPE
    assert {option.option_id for option in shooting_request.options} >= {
        _CAVALCADE_UNIT_ID,
        COMPLETE_SHOOTING_PHASE_OPTION_ID,
    }

    charge_state = _state_at_phase(state, BattlePhase.CHARGE)
    charge_status = ChargePhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor,
    ).begin_phase(state=charge_state, decisions=DecisionController())
    charge_request = _decision_request(charge_status)
    assert charge_request.decision_type == SELECT_CHARGING_UNIT_DECISION_TYPE
    assert {option.option_id for option in charge_request.options} >= {
        _CAVALCADE_UNIT_ID,
        COMPLETE_CHARGE_PHASE_OPTION_ID,
    }


def test_cavalcade_apocalyptic_steeds_applies_movement_upgrade_through_lifecycle() -> None:
    config = _cavalcade_config(apocalyptic_steeds=True)
    lifecycle, movement_status = _advance_to_movement_unit_selection(config)
    state = _state(lifecycle)
    bundle = _runtime_content_bundle(lifecycle)
    summary = bundle.to_summary_payload()
    army = state.army_definitions[0]
    unit = army.unit_by_id(_CAVALCADE_UNIT_ID)

    assert enhancements.EFFECT_ID in summary["enhancement_effect_binding_ids"]
    assert enhancements.SOURCE_RULE_ID in summary["selected_execution_record_ids"]
    assert all(
        enhancements.MODIFIER_ID
        in _characteristic_for_model(model, Characteristic.MOVEMENT).applied_modifier_ids
        for model in unit.own_models
    )
    assert {_model_movement_inches(model) for model in unit.own_models} == {7}

    effect_event = _event_payload(lifecycle, "enhancement_effects_applied")
    effect_payloads = cast(list[JsonValue], effect_event["effects"])
    effect_payload = cast(dict[str, JsonValue], effect_payloads[0])
    replay_payload = cast(dict[str, JsonValue], effect_payload["replay_payload"])
    model_payloads = cast(list[JsonValue], effect_payload["model_modifiers"])
    first_model_payload = cast(dict[str, JsonValue], model_payloads[0])
    assert effect_payload["effect_id"] == enhancements.EFFECT_ID
    assert effect_payload["source_id"] == enhancements.SOURCE_RULE_ID
    assert effect_payload["enhancement_id"] == enhancements.ENHANCEMENT_ID
    assert replay_payload["effect_kind"] == "apocalyptic_steeds_upgrade"
    assert replay_payload["enhancement_source_id"] == enhancements.ENHANCEMENT_SOURCE_ID
    assert first_model_payload["before_final"] == 6
    assert first_model_payload["after_final"] == 7

    selection_request = _decision_request(movement_status)
    action_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-cavalcade-select-apocalyptic-steeds",
            request=selection_request,
            selected_option_id=_CAVALCADE_UNIT_ID,
        )
    )
    action_request = _decision_request(action_status)
    move_status = submit_action_and_movement_proposal(
        lifecycle,
        request=action_request,
        option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
        action_result_id="phase17g-cavalcade-normal-move-action",
        proposal_result_id="phase17g-cavalcade-normal-move-proposal",
        unit_instance_id=_CAVALCADE_UNIT_ID,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
        movement_mode=MovementMode.NORMAL,
        witness=straight_line_witness_for_unit(
            lifecycle,
            unit_instance_id=_CAVALCADE_UNIT_ID,
            dx=7.0,
        ),
    )

    assert move_status.status_kind in {
        LifecycleStatusKind.ADVANCED,
        LifecycleStatusKind.WAITING_FOR_DECISION,
    }


def test_cavalcade_apocalyptic_steeds_roster_requires_mounted_target() -> None:
    config = _cavalcade_config(
        apocalyptic_steeds=True,
        friendly_keywords=("Khorne",),
    )

    report = validate_roster_legality(
        catalog=config.army_catalog,
        request=config.army_muster_requests[0],
    )

    assert "enhancement_target_keyword_required" in {
        violation.violation_code for violation in report.violations
    }


def test_cavalcade_enhancement_effect_uses_phase17f_execution_source_id() -> None:
    record = _cavalcade_enhancement_execution_record()
    contribution = enhancements.runtime_contribution()
    binding = contribution.enhancement_effect_bindings[0]

    assert record.execution_id == enhancements.SOURCE_RULE_ID
    assert binding.source_id == record.execution_id


def test_cavalcade_rule_hook_uses_phase17f_execution_source_id() -> None:
    record = _cavalcade_rule_execution_record()
    contribution = rule.runtime_contribution()
    binding = contribution.fall_back_hook_bindings[0]

    assert record.execution_id == rule.SOURCE_RULE_ID
    assert binding.source_id == record.execution_id


def test_cavalcade_rule_requires_target_unit_owned_by_selected_player() -> None:
    lifecycle, _movement_status = _advance_to_movement_unit_selection(
        _cavalcade_config(
            enemy_faction_id=rule.CHAOS_DAEMONS_FACTION_ID,
            enemy_detachment_id=rule.CAVALCADE_DETACHMENT_ID,
            enemy_datasheet_id=_CAVALCADE_TEST_DATASHEET_ID,
        )
    )
    state = _state(lifecycle)
    context = FallBackEligibilityContext(
        state=state,
        player_id="player-a",
        battle_round=1,
        unit_instance_id=_ENEMY_UNIT_ID,
        movement_request_id="phase17g-cavalcade-enemy-unit-request",
        movement_result_id="phase17g-cavalcade-enemy-unit-result",
    )

    with pytest.raises(GameLifecycleError, match="not in the selected player army"):
        rule.fall_back_eligibility_grant(context)


def test_fall_back_hook_registry_rejects_cavalcade_handler_identity_drift() -> None:
    context = FallBackEligibilityContext(
        state=GameState.from_config(_cavalcade_config()),
        player_id="player-a",
        battle_round=1,
        unit_instance_id=_CAVALCADE_UNIT_ID,
        movement_request_id="phase17g-cavalcade-request",
        movement_result_id="phase17g-cavalcade-result",
    )

    def hook_id_drift(
        _context: FallBackEligibilityContext,
    ) -> FallBackEligibilityGrant:
        return FallBackEligibilityGrant(
            hook_id="phase17g:wrong-hook",
            source_id=rule.SOURCE_RULE_ID,
            can_shoot=True,
            can_declare_charge=True,
        )

    hook_drift_registry = FallBackEligibilityHookRegistry.from_bindings(
        (
            FallBackEligibilityHookBinding(
                hook_id=rule.HOOK_ID,
                source_id=rule.SOURCE_RULE_ID,
                handler=hook_id_drift,
            ),
        )
    )
    with pytest.raises(GameLifecycleError, match="hook_id drift"):
        hook_drift_registry.grants_for(context)

    def source_id_drift(
        _context: FallBackEligibilityContext,
    ) -> FallBackEligibilityGrant:
        return FallBackEligibilityGrant(
            hook_id=rule.HOOK_ID,
            source_id="phase17g:wrong-source",
            can_shoot=True,
            can_declare_charge=True,
        )

    source_drift_registry = FallBackEligibilityHookRegistry.from_bindings(
        (
            FallBackEligibilityHookBinding(
                hook_id=rule.HOOK_ID,
                source_id=rule.SOURCE_RULE_ID,
                handler=source_id_drift,
            ),
        )
    )
    with pytest.raises(GameLifecycleError, match="source_id drift"):
        source_drift_registry.grants_for(context)


def _cavalcade_rule_execution_record() -> Phase17FExecutionRecord:
    records = tuple(
        record
        for record in faction_execution_2026_27.execution_records()
        if record.faction_id == rule.CHAOS_DAEMONS_FACTION_ID
        and record.coverage_kind is Phase17ECoverageKind.DETACHMENT_RULE
        and record.detachment_id == rule.CAVALCADE_DETACHMENT_ID
    )
    if len(records) != 1:
        raise AssertionError("expected one Cavalcade of Chaos detachment-rule execution record")
    return records[0]


def _cavalcade_enhancement_execution_record() -> Phase17FExecutionRecord:
    records = tuple(
        record
        for record in faction_execution_2026_27.execution_records()
        if record.faction_id == rule.CHAOS_DAEMONS_FACTION_ID
        and record.coverage_kind is Phase17ECoverageKind.DETACHMENT_ENHANCEMENT_DESCRIPTORS
        and record.detachment_id == rule.CAVALCADE_DETACHMENT_ID
    )
    if len(records) != 1:
        raise AssertionError("expected one Cavalcade of Chaos enhancement execution record")
    return records[0]


def _characteristic_for_model(
    model: ModelInstance,
    characteristic: Characteristic,
) -> CharacteristicValue:
    for value in model.characteristics:
        if value.characteristic is characteristic:
            return value
    raise AssertionError(f"model is missing {characteristic.value}")


def _model_movement_inches(model: ModelInstance) -> int:
    value = _characteristic_for_model(model, Characteristic.MOVEMENT)
    return value.final


def _runtime_content_bundle(lifecycle: GameLifecycle) -> RuntimeContentBundle:
    require_runtime_content_bundle = cast(
        Callable[[], RuntimeContentBundle],
        object.__getattribute__(lifecycle, "_require_runtime_content_bundle"),
    )
    return require_runtime_content_bundle()


def _state_at_phase(state: GameState, phase: BattlePhase) -> GameState:
    phase_state = GameState.from_payload(state.to_payload())
    while phase_state.current_battle_phase is not phase:
        if phase_state.current_battle_phase is None:
            raise AssertionError("battle state ended before expected phase")
        phase_state.advance_to_next_battle_phase()
    return phase_state


def _cavalcade_config(
    *,
    apocalyptic_steeds: bool = False,
    friendly_keywords: tuple[str, ...] = (rule.MOUNTED, "Khorne"),
    enemy_faction_id: str = "core-marine-force",
    enemy_detachment_id: str = "core-combined-arms",
    enemy_datasheet_id: str = "core-intercessor-like-infantry",
) -> GameConfig:
    catalog = _cavalcade_catalog(friendly_keywords=friendly_keywords)
    return GameConfig(
        game_id="phase17g-cavalcade-unholy-avalanche",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-phase17g-cavalcade-test"
        ),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                army_id="army-alpha",
                player_id="player-a",
                faction_id=rule.CHAOS_DAEMONS_FACTION_ID,
                detachment_id=rule.CAVALCADE_DETACHMENT_ID,
                unit_selection_id="intercessor-unit-1",
                datasheet_id=_CAVALCADE_TEST_DATASHEET_ID,
                apocalyptic_steeds=apocalyptic_steeds,
            ),
            _army_muster_request(
                catalog=catalog,
                army_id="army-beta",
                player_id="player-b",
                faction_id=enemy_faction_id,
                detachment_id=enemy_detachment_id,
                unit_selection_id="intercessor-unit-2",
                datasheet_id=enemy_datasheet_id,
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=_mission_setup(),
    )


def _cavalcade_catalog(
    *,
    friendly_keywords: tuple[str, ...] = (rule.MOUNTED, "Khorne"),
) -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    daemon_datasheet = _cavalcade_datasheet(base_datasheet, keywords=friendly_keywords)
    return replace(
        base_catalog,
        datasheets=(*base_catalog.datasheets, daemon_datasheet),
        factions=(
            *base_catalog.factions,
            FactionDefinition(
                faction_id=rule.CHAOS_DAEMONS_FACTION_ID,
                name="Chaos Daemons",
                faction_keywords=("Legiones Daemonica",),
                source_ids=("gw-11e-faction-detachments-2026-27:faction:chaos-daemons",),
            ),
        ),
        detachments=(
            *base_catalog.detachments,
            DetachmentDefinition(
                detachment_id=rule.CAVALCADE_DETACHMENT_ID,
                name="Cavalcade of Chaos",
                faction_id=rule.CHAOS_DAEMONS_FACTION_ID,
                detachment_point_cost=1,
                unit_datasheet_ids=(_CAVALCADE_TEST_DATASHEET_ID,),
                force_disposition_ids=("phase17g-force",),
                enhancement_ids=(enhancements.ENHANCEMENT_ID,),
                source_ids=(
                    "gw-11e-faction-detachments-2026-27:detachment:"
                    "chaos-daemons:cavalcade-of-chaos",
                ),
            ),
        ),
        enhancements=(
            *base_catalog.enhancements,
            EnhancementDefinition(
                enhancement_id=enhancements.ENHANCEMENT_ID,
                name="Apocalyptic Steeds Upgrade",
                source_id=enhancements.ENHANCEMENT_SOURCE_ID,
                subtypes=(EnhancementSubtype.UPGRADE,),
                points=0,
                target_required_keywords=(enhancements.MOUNTED,),
                target_required_faction_keywords=(enhancements.LEGIONES_DAEMONICA,),
            ),
        ),
    )


def _cavalcade_datasheet(
    base_datasheet: DatasheetDefinition,
    *,
    keywords: tuple[str, ...],
) -> DatasheetDefinition:
    return replace(
        base_datasheet,
        datasheet_id=_CAVALCADE_TEST_DATASHEET_ID,
        name="Mounted Manifestation Daemon",
        keywords=DatasheetKeywordSet(
            keywords=keywords,
            faction_keywords=("Legiones Daemonica",),
        ),
        attachment_eligibilities=(),
        source_ids=("phase17g:test:chaos-daemons:cavalcade-mounted-daemon",),
    )


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    army_id: str,
    player_id: str,
    faction_id: str,
    detachment_id: str,
    unit_selection_id: str,
    datasheet_id: str,
    apocalyptic_steeds: bool = False,
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
            enhancement_ids=(
                (enhancements.ENHANCEMENT_ID,)
                if apocalyptic_steeds
                and faction_id == rule.CHAOS_DAEMONS_FACTION_ID
                and detachment_id == rule.CAVALCADE_DETACHMENT_ID
                else ()
            ),
        ),
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id=datasheet_id,
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
        ),
        enhancement_assignments=(
            (
                EnhancementAssignment(
                    enhancement_id=enhancements.ENHANCEMENT_ID,
                    target_unit_selection_id=unit_selection_id,
                    source_id="phase17g:test:apocalyptic-steeds-assignment",
                ),
            )
            if apocalyptic_steeds
            and faction_id == rule.CHAOS_DAEMONS_FACTION_ID
            and detachment_id == rule.CAVALCADE_DETACHMENT_ID
            else ()
        ),
    )


def _event_payload(lifecycle: GameLifecycle, event_type: str) -> dict[str, JsonValue]:
    for event in lifecycle.decision_controller.event_log.records:
        if event.event_type == event_type:
            return cast(dict[str, JsonValue], event.payload)
    raise AssertionError(f"missing event {event_type}")
