from __future__ import annotations

from dataclasses import replace
from enum import StrEnum
from typing import cast

from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.core.dice import D3RollResult, DiceExpression, DiceRollSpec
from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockHookBinding,
    BattleShockModifierContext,
    BattleShockOutcomeContext,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.damage_allocation import apply_mortal_wounds_to_unit
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.faction_content.common import canonical_keyword as _canonical_keyword
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons import (
    datasheets as chaos_daemons_datasheets,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.healing import HealingEffect, resolve_healing_until_blocked
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlRecord,
    ObjectiveControlStatus,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rule_execution import (
    RuleExecutionContext,
    RuleExecutionResult,
    RuleExecutionStatus,
    default_rule_execution_registry,
    execute_rule_ir,
)
from warhammer40k_core.engine.sticky_objective_control import apply_sticky_objective_control
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.measurement import DistanceMeasurementContext
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model as GeometryModel
from warhammer40k_core.rules.rule_ir import (
    RuleEffectKind,
    RuleEffectSpec,
    RuleEffectSpecPayload,
    RuleIR,
    RuleIRError,
    RuleIRPayload,
    parameter_payload,
)

CONTRIBUTION_ID = "warhammer_40000_11th:chaos_daemons:army_rule:scaffold"
HOOK_ID = "warhammer_40000_11th:chaos_daemons:army_rule:shadow_of_chaos"
SOURCE_RULE_ID = "phase17f:phase17e:chaos-daemons:army-rule"
CHAOS_DAEMONS_FACTION_ID = "chaos-daemons"
LEGIONES_DAEMONICA = "LEGIONES DAEMONICA"
CORRUPTED_REALSPACE_STICKY_EFFECT_KIND = "chaos_daemons_corrupted_realspace_objective"
CORRUPTED_REALSPACE_SHADOW_AURA_INCHES = 6.0
GREATER_DAEMON_SHADOW_AURA_KEYWORDS_BY_SOURCE_ID = (
    (chaos_daemons_datasheets.BLOODTHIRSTER_GREATER_DAEMON_SOURCE_ID, "KHORNE"),
    (chaos_daemons_datasheets.SKARBRAND_GREATER_DAEMON_SOURCE_ID, "KHORNE"),
    (chaos_daemons_datasheets.LORD_OF_CHANGE_GREATER_DAEMON_SOURCE_ID, "TZEENTCH"),
    (chaos_daemons_datasheets.KAIROS_GREATER_DAEMON_SOURCE_ID, "TZEENTCH"),
    (chaos_daemons_datasheets.GREAT_UNCLEAN_ONE_GREATER_DAEMON_SOURCE_ID, "NURGLE"),
    (chaos_daemons_datasheets.ROTIGUS_GREATER_DAEMON_SOURCE_ID, "NURGLE"),
    (chaos_daemons_datasheets.KEEPER_GREATER_DAEMON_SOURCE_ID, "SLAANESH"),
    (chaos_daemons_datasheets.SHALAXI_GREATER_DAEMON_SOURCE_ID, "SLAANESH"),
)


class ShadowRegion(StrEnum):
    OWN_DEPLOYMENT_ZONE = "own_deployment_zone"
    NO_MANS_LAND = "no_mans_land"
    OPPONENT_DEPLOYMENT_ZONE = "opponent_deployment_zone"


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        battle_shock_hook_bindings=(
            BattleShockHookBinding(
                hook_id=HOOK_ID,
                source_id=SOURCE_RULE_ID,
                modifier_handler=battle_shock_modifiers,
                outcome_handler=resolve_battle_shock_outcome,
            ),
        ),
    )


def battle_shock_modifiers(
    context: BattleShockModifierContext,
) -> tuple[RollModifier, ...]:
    if type(context) is not BattleShockModifierContext:
        raise GameLifecycleError("Chaos Daemons Battle-shock modifiers require a context.")
    target_unit = _unit_by_id(context.state, context.request.unit_instance_id)
    target_player_id = context.request.player_id
    modifiers: list[RollModifier] = []
    for daemon_army in _chaos_daemons_armies(context.state):
        if daemon_army.player_id == target_player_id:
            if _daemonic_manifestation_applies(
                state=context.state,
                daemon_player_id=daemon_army.player_id,
                unit=target_unit,
                battle_shocked_unit_ids=context.phase_start_battle_shocked_unit_ids,
            ):
                modifiers.append(
                    RollModifier(
                        modifier_id=(
                            f"{HOOK_ID}:daemonic-manifestation:"
                            f"{context.request.request_id}:{daemon_army.player_id}"
                        ),
                        source_id=SOURCE_RULE_ID,
                        operand=1,
                    )
                )
            continue
        if _daemonic_terror_applies(
            state=context.state,
            daemon_army=daemon_army,
            target_unit=target_unit,
            battle_shocked_unit_ids=context.phase_start_battle_shocked_unit_ids,
        ):
            modifiers.append(
                RollModifier(
                    modifier_id=(
                        f"{HOOK_ID}:daemonic-terror:"
                        f"{context.request.request_id}:{daemon_army.player_id}"
                    ),
                    source_id=SOURCE_RULE_ID,
                    operand=-1,
                )
            )
    return tuple(modifiers)


def resolve_battle_shock_outcome(context: BattleShockOutcomeContext) -> None:
    if type(context) is not BattleShockOutcomeContext:
        raise GameLifecycleError("Chaos Daemons Battle-shock outcomes require a context.")
    target_unit = _unit_by_id(context.state, context.result.request.unit_instance_id)
    target_player_id = context.result.request.player_id
    for daemon_army in _chaos_daemons_armies(context.state):
        if daemon_army.player_id == target_player_id:
            _resolve_daemonic_manifestation(
                context=context,
                daemon_player_id=daemon_army.player_id,
                target_unit=target_unit,
            )
            continue
        _resolve_daemonic_terror(
            context=context,
            daemon_army=daemon_army,
            target_unit=target_unit,
        )


def _resolve_daemonic_manifestation(
    *,
    context: BattleShockOutcomeContext,
    daemon_player_id: str,
    target_unit: UnitInstance,
) -> None:
    result = context.result
    if not result.passed:
        return
    if not _daemonic_manifestation_applies(
        state=context.state,
        daemon_player_id=daemon_player_id,
        unit=target_unit,
        battle_shocked_unit_ids=context.phase_start_battle_shocked_unit_ids,
    ):
        return
    d3_result = _roll_d3(
        context=context,
        reason="Daemonic Manifestation",
        roll_type="chaos_daemons.daemonic_manifestation_d3",
        actor_id=target_unit.unit_instance_id,
    )
    if _unit_has_keyword(target_unit, "BATTLELINE"):
        destroyed_model_ids = _destroyed_model_ids_for_unit(
            state=context.state,
            unit=target_unit,
        )
        if destroyed_model_ids:
            _emit_daemonic_manifestation_unsupported(
                context=context,
                target_unit=target_unit,
                d3_result=d3_result,
                unsupported_reason="battleline_model_return_requires_placement_decision",
            )
        else:
            _emit_daemonic_manifestation_no_effect(
                context=context,
                target_unit=target_unit,
                d3_result=d3_result,
                no_effect_reason="battleline_unit_has_no_destroyed_models",
            )
        return
    wounded_models: list[ModelInstance] = []
    for model in target_unit.own_models:
        if model.is_alive and model.wounds_remaining < model.starting_wounds:
            wounded_models.append(model)
    if not wounded_models:
        _emit_daemonic_manifestation_no_effect(
            context=context,
            target_unit=target_unit,
            d3_result=d3_result,
            no_effect_reason="unit_has_no_wounded_models",
        )
        return
    if len(wounded_models) > 1:
        _emit_daemonic_manifestation_unsupported(
            context=context,
            target_unit=target_unit,
            d3_result=d3_result,
            unsupported_reason="multiple_wounded_models_require_decision",
        )
        return
    model = wounded_models[0]
    missing_wounds = model.starting_wounds - model.wounds_remaining
    healing_amount = min(d3_result.value, missing_wounds)
    effect = HealingEffect(
        effect_id=f"{HOOK_ID}:daemonic-manifestation:{result.result_id}",
        target_unit_instance_id=target_unit.unit_instance_id,
        amount=healing_amount,
        opposing_player_id=_opposing_player_id(
            state=context.state,
            player_id=daemon_player_id,
        ),
        source_rule_id=SOURCE_RULE_ID,
        source_context=validate_json_value(
            {
                "hook_id": HOOK_ID,
                "effect_kind": "daemonic_manifestation",
                "battle_shock_result_id": result.result_id,
                "player_id": daemon_player_id,
                "unit_instance_id": target_unit.unit_instance_id,
                "model_instance_id": model.model_instance_id,
                "d3_result": d3_result.to_payload(),
            }
        ),
        phase_start_model_ids=_placed_model_ids_for_unit(
            state=context.state,
            unit_instance_id=target_unit.unit_instance_id,
        ),
    )
    resolved_effect, pending_request = resolve_healing_until_blocked(
        state=context.state,
        decisions=context.decisions,
        ruleset_descriptor=context.state.runtime_ruleset_descriptor(),
        effect=effect,
    )
    if pending_request is not None:
        raise GameLifecycleError("Daemonic Manifestation healing unexpectedly requested a choice.")
    context.decisions.event_log.append(
        "chaos_daemons_daemonic_manifestation_healing_resolved",
        {
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "phase": context.phase.value,
            "source_rule_id": SOURCE_RULE_ID,
            "battle_shock_result_id": result.result_id,
            "player_id": daemon_player_id,
            "unit_instance_id": target_unit.unit_instance_id,
            "d3_result": validate_json_value(d3_result.to_payload()),
            "healing_effect": validate_json_value(resolved_effect.to_payload()),
        },
    )


def _resolve_daemonic_terror(
    *,
    context: BattleShockOutcomeContext,
    daemon_army: ArmyDefinition,
    target_unit: UnitInstance,
) -> None:
    result = context.result
    if result.passed:
        return
    if not _daemonic_terror_applies(
        state=context.state,
        daemon_army=daemon_army,
        target_unit=target_unit,
        battle_shocked_unit_ids=context.phase_start_battle_shocked_unit_ids,
    ):
        return
    d3_result = _roll_d3(
        context=context,
        reason="Daemonic Terror mortal wounds",
        roll_type="chaos_daemons.daemonic_terror_mortal_wounds_d3",
        actor_id=target_unit.unit_instance_id,
    )
    if _unit_has_feel_no_pain_choice(context.state, target_unit):
        context.decisions.event_log.append(
            "chaos_daemons_daemonic_terror_unsupported",
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": context.phase.value,
                "source_rule_id": SOURCE_RULE_ID,
                "battle_shock_result_id": result.result_id,
                "player_id": daemon_army.player_id,
                "target_unit_instance_id": target_unit.unit_instance_id,
                "unsupported_reason": "mortal_wound_feel_no_pain_requires_decision",
                "d3_result": validate_json_value(d3_result.to_payload()),
            },
        )
        return
    application = apply_mortal_wounds_to_unit(
        state=context.state,
        target_unit_instance_id=target_unit.unit_instance_id,
        mortal_wounds=d3_result.value,
        spill_over=True,
        dice_manager=context.dice_manager,
        defender_player_id=result.request.player_id,
    )
    context.decisions.event_log.append(
        "chaos_daemons_daemonic_terror_mortal_wounds_applied",
        {
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "phase": context.phase.value,
            "source_rule_id": SOURCE_RULE_ID,
            "battle_shock_result_id": result.result_id,
            "player_id": daemon_army.player_id,
            "target_unit_instance_id": target_unit.unit_instance_id,
            "d3_result": validate_json_value(d3_result.to_payload()),
            "mortal_wound_application": validate_json_value(application.to_payload()),
        },
    )


def shadow_regions_for_player(
    *,
    state: GameState,
    player_id: str,
    battle_shocked_unit_ids: tuple[str, ...] | None = None,
) -> tuple[ShadowRegion, ...]:
    if type(state) is not GameState:
        raise GameLifecycleError("Shadow of Chaos requires a GameState.")
    if state.mission_setup is None:
        raise GameLifecycleError("Shadow of Chaos requires MissionSetup.")
    if state.battlefield_state is None:
        raise GameLifecycleError("Shadow of Chaos requires battlefield_state.")
    requested_player_id = _validate_identifier("player_id", player_id)
    regions: list[ShadowRegion] = [ShadowRegion.OWN_DEPLOYMENT_ZONE]
    objective_context = ObjectiveControlContext.from_game_state(
        state,
        timing=ObjectiveControlTiming.PHASE_END,
        phase=state.current_battle_phase or BattlePhase.COMMAND,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
    )
    if battle_shocked_unit_ids is not None:
        objective_context = replace(
            objective_context,
            battle_shocked_unit_ids=_validate_identifier_tuple(
                "battle_shocked_unit_ids",
                battle_shocked_unit_ids,
            ),
        )
    objective_record = resolve_objective_control(objective_context)
    objective_record = apply_sticky_objective_control(
        record=objective_record,
        states=tuple(state.sticky_objective_control_states),
    )
    no_mans_land_objective_ids = _no_mans_land_objective_ids(state)
    if _controls_at_least_half(
        objective_record=objective_record,
        objective_ids=no_mans_land_objective_ids,
        player_id=requested_player_id,
    ):
        regions.append(ShadowRegion.NO_MANS_LAND)
    opponent_deployment_objective_ids = _opponent_deployment_objective_ids(
        state,
        player_id=requested_player_id,
    )
    if _controls_at_least_half(
        objective_record=objective_record,
        objective_ids=opponent_deployment_objective_ids,
        player_id=requested_player_id,
    ):
        regions.append(ShadowRegion.OPPONENT_DEPLOYMENT_ZONE)
    return tuple(regions)


def unit_within_shadow_of_chaos(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
) -> bool:
    if type(state) is not GameState:
        raise GameLifecycleError("Shadow of Chaos unit lookup requires a GameState.")
    return _unit_within_shadow(
        state=state,
        player_id=_validate_identifier("player_id", player_id),
        unit_instance_id=_validate_identifier("unit_instance_id", unit_instance_id),
        battle_shocked_unit_ids=tuple(state.battle_shocked_unit_ids),
    )


def _daemonic_manifestation_applies(
    *,
    state: GameState,
    daemon_player_id: str,
    unit: UnitInstance,
    battle_shocked_unit_ids: tuple[str, ...],
) -> bool:
    return _unit_has_faction_keyword(unit, LEGIONES_DAEMONICA) and _unit_within_shadow(
        state=state,
        player_id=daemon_player_id,
        unit_instance_id=unit.unit_instance_id,
        battle_shocked_unit_ids=battle_shocked_unit_ids,
    )


def _daemonic_terror_applies(
    *,
    state: GameState,
    daemon_army: ArmyDefinition,
    target_unit: UnitInstance,
    battle_shocked_unit_ids: tuple[str, ...],
) -> bool:
    return _unit_within_shadow(
        state=state,
        player_id=daemon_army.player_id,
        unit_instance_id=target_unit.unit_instance_id,
        battle_shocked_unit_ids=battle_shocked_unit_ids,
    ) or _unit_within_greater_daemon_terror(
        state=state,
        daemon_army=daemon_army,
        target_unit=target_unit,
    )


def _unit_within_shadow(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
    battle_shocked_unit_ids: tuple[str, ...],
) -> bool:
    regions = shadow_regions_for_player(
        state=state,
        player_id=player_id,
        battle_shocked_unit_ids=battle_shocked_unit_ids,
    )
    if ShadowRegion.OWN_DEPLOYMENT_ZONE in regions and _unit_intersects_deployment_zones(
        state=state,
        unit_instance_id=unit_instance_id,
        player_id=player_id,
        owner_zone=True,
    ):
        return True
    if ShadowRegion.OPPONENT_DEPLOYMENT_ZONE in regions and _unit_intersects_deployment_zones(
        state=state,
        unit_instance_id=unit_instance_id,
        player_id=player_id,
        owner_zone=False,
    ):
        return True
    if ShadowRegion.NO_MANS_LAND in regions and _unit_intersects_no_mans_land(
        state=state,
        unit_instance_id=unit_instance_id,
    ):
        return True
    return (
        _unit_within_greater_daemon_shadow_aura(
            state=state,
            player_id=player_id,
            unit_instance_id=unit_instance_id,
        )
        or _unit_within_semantic_shadow_aura(
            state=state,
            player_id=player_id,
            unit_instance_id=unit_instance_id,
        )
        or _unit_within_corrupted_realspace_shadow(
            state=state,
            player_id=player_id,
            unit_instance_id=unit_instance_id,
        )
    )


def _unit_within_corrupted_realspace_shadow(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
) -> bool:
    if state.mission_setup is None:
        raise GameLifecycleError("Corrupted Realspace Shadow check requires MissionSetup.")
    target_models = _unit_geometry_models(state=state, unit_instance_id=unit_instance_id)
    if not target_models:
        return False
    marker_by_id = {
        marker.objective_marker_id: marker.to_objective_marker()
        for marker in state.mission_setup.objective_markers
    }
    for sticky_state in state.sticky_objective_control_states:
        if sticky_state.player_id != player_id:
            continue
        if not isinstance(sticky_state.replay_payload, dict):
            raise GameLifecycleError("Corrupted Realspace sticky payload must be an object.")
        if sticky_state.replay_payload.get("effect_kind") != CORRUPTED_REALSPACE_STICKY_EFFECT_KIND:
            continue
        raw_aura_inches = sticky_state.replay_payload.get("shadow_of_chaos_aura_inches")
        if type(raw_aura_inches) not in (float, int):
            raise GameLifecycleError("Corrupted Realspace aura payload must contain inches.")
        aura_inches = float(cast(float | int, raw_aura_inches))
        if aura_inches <= 0:
            raise GameLifecycleError("Corrupted Realspace aura inches must be positive.")
        if not _objective_controlled_by_player(
            state=state,
            objective_id=sticky_state.objective_id,
            player_id=player_id,
        ):
            continue
        marker = marker_by_id.get(sticky_state.objective_id)
        if marker is None:
            raise GameLifecycleError("Corrupted Realspace objective marker is unknown.")
        marker_pose = Pose.at(marker.x_inches, marker.y_inches, marker.z_inches)
        if any(
            DistanceMeasurementContext.from_objective_marker_to_model(
                marker_id=marker.objective_marker_id,
                marker_pose=marker_pose,
                model=target_model,
                marker_diameter_inches=marker.marker_diameter_inches,
            ).horizontal_distance_inches()
            <= aura_inches
            for target_model in target_models
        ):
            return True
    return False


def _objective_controlled_by_player(
    *,
    state: GameState,
    objective_id: str,
    player_id: str,
) -> bool:
    if state.mission_setup is None:
        raise GameLifecycleError("Objective control lookup requires MissionSetup.")
    objective_context = ObjectiveControlContext.from_game_state(
        state,
        timing=ObjectiveControlTiming.PHASE_END,
        phase=state.current_battle_phase or BattlePhase.COMMAND,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
    )
    objective_record = apply_sticky_objective_control(
        record=resolve_objective_control(objective_context),
        states=tuple(state.sticky_objective_control_states),
    )
    result = objective_record.result_by_objective_id(
        _validate_identifier("objective_id", objective_id)
    )
    if result.status is ObjectiveControlStatus.UNSUPPORTED:
        raise GameLifecycleError("Shadow of Chaos cannot use unsupported objective control.")
    return (
        result.status is ObjectiveControlStatus.CONTROLLED
        and result.controlled_by_player_id == player_id
    )


def _unit_within_greater_daemon_shadow_aura(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
) -> bool:
    target_unit = _unit_by_id(state, unit_instance_id)
    daemon_army = _army_for_player(state=state, player_id=player_id)
    if not any(unit.unit_instance_id == target_unit.unit_instance_id for unit in daemon_army.units):
        return False
    if not _unit_has_faction_keyword(target_unit, LEGIONES_DAEMONICA):
        return False
    target_models = _unit_geometry_models(
        state=state,
        unit_instance_id=target_unit.unit_instance_id,
    )
    if not target_models:
        return False
    for source_unit in daemon_army.units:
        if source_unit.unit_instance_id == target_unit.unit_instance_id:
            continue
        aura_keyword = _greater_daemon_shadow_aura_keyword(source_unit)
        if aura_keyword is None:
            continue
        if not _unit_has_keyword(target_unit, aura_keyword):
            continue
        for source_model in _unit_geometry_models(
            state=state, unit_instance_id=source_unit.unit_instance_id
        ):
            if any(
                shapely_backend.base_footprint_distance(
                    source_model.base,
                    source_model.pose,
                    target_model.base,
                    target_model.pose,
                )
                <= 6.0
                for target_model in target_models
            ):
                return True
    return False


def _greater_daemon_shadow_aura_keyword(unit: UnitInstance) -> str | None:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Greater Daemon Shadow aura lookup requires UnitInstance.")
    for ability in unit.datasheet_abilities:
        if ability.source_kind is not CatalogAbilitySourceKind.DATASHEET:
            continue
        for source_id, keyword in GREATER_DAEMON_SHADOW_AURA_KEYWORDS_BY_SOURCE_ID:
            if ability.source_id == source_id:
                return keyword
    return None


def _unit_within_semantic_shadow_aura(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
) -> bool:
    target_unit = _unit_by_id(state, unit_instance_id)
    target_models = _unit_geometry_models(
        state=state,
        unit_instance_id=target_unit.unit_instance_id,
    )
    if not target_models:
        return False
    daemon_army = _army_for_player(state=state, player_id=player_id)
    for source_unit in daemon_army.units:
        if source_unit.unit_instance_id == target_unit.unit_instance_id:
            continue
        if not _unit_geometry_models(state=state, unit_instance_id=source_unit.unit_instance_id):
            continue
        for ability in source_unit.datasheet_abilities:
            if not _semantic_shadow_aura_ability_active(unit=source_unit, ability=ability):
                continue
            rule_ir = _semantic_rule_ir_for_ability(ability)
            if not _rule_ir_sets_shadow_of_chaos_status(rule_ir):
                continue
            result = execute_rule_ir(
                rule_ir=rule_ir,
                context=RuleExecutionContext(
                    game_id=state.game_id,
                    player_id=player_id,
                    battle_round=max(1, state.battle_round),
                    phase=BattlePhaseKind.COMMAND,
                    active_player_id=state.active_player_id,
                    timing_window_id="chaos-daemons-shadow-of-chaos-semantic-aura",
                    source_unit_instance_id=source_unit.unit_instance_id,
                    target_unit_instance_ids=(),
                    source_keywords=(
                        *source_unit.keywords,
                        *source_unit.faction_keywords,
                    ),
                    trigger_payload={
                        "source": "chaos_daemons_shadow_of_chaos_semantic_aura",
                        "target_unit_instance_id": target_unit.unit_instance_id,
                    },
                    state=state,
                ),
                registry=default_rule_execution_registry(),
            )
            if result.status is not RuleExecutionStatus.APPLIED:
                reason = result.reason
                if reason is None:
                    raise GameLifecycleError(
                        "Shadow of Chaos semantic aura returned a non-applied result."
                    )
                raise GameLifecycleError(
                    f"Shadow of Chaos semantic aura execution failed: {reason}."
                )
            if _execution_result_sets_shadow_status_for_unit(
                result,
                unit_instance_id=target_unit.unit_instance_id,
            ):
                return True
    return False


def _semantic_shadow_aura_ability_active(
    *,
    unit: UnitInstance,
    ability: DatasheetAbilityDescriptor,
) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Shadow of Chaos semantic aura requires a UnitInstance.")
    if type(ability) is not DatasheetAbilityDescriptor:
        raise GameLifecycleError(
            "Shadow of Chaos semantic aura requires DatasheetAbilityDescriptor values."
        )
    if ability.support is not CatalogAbilitySupport.GENERIC_RULE_IR:
        return False
    if ability.rule_ir_payload is None:
        raise GameLifecycleError("Shadow of Chaos semantic aura ability is missing RuleIR.")
    if ability.source_kind is CatalogAbilitySourceKind.DATASHEET:
        return any(model.is_alive for model in unit.own_models)
    if ability.source_kind is CatalogAbilitySourceKind.WARGEAR:
        source_wargear_id = ability.source_wargear_id
        if source_wargear_id is None:
            raise GameLifecycleError(
                "Shadow of Chaos semantic aura wargear ability is missing source_wargear_id."
            )
        return any(
            model.is_alive and source_wargear_id in model.wargear_ids for model in unit.own_models
        )
    return False


def _semantic_rule_ir_for_ability(ability: DatasheetAbilityDescriptor) -> RuleIR:
    if type(ability) is not DatasheetAbilityDescriptor:
        raise GameLifecycleError("Shadow of Chaos semantic aura requires ability descriptors.")
    if ability.rule_ir_payload is None:
        raise GameLifecycleError("Shadow of Chaos semantic aura ability is missing RuleIR.")
    try:
        return RuleIR.from_payload(cast(RuleIRPayload, ability.rule_ir_payload))
    except RuleIRError as exc:
        raise GameLifecycleError("Shadow of Chaos semantic aura RuleIR is invalid.") from exc


def _rule_ir_sets_shadow_of_chaos_status(rule_ir: RuleIR) -> bool:
    if type(rule_ir) is not RuleIR:
        raise GameLifecycleError("Shadow of Chaos semantic aura requires RuleIR.")
    return rule_ir.is_supported and any(
        _effect_sets_shadow_of_chaos_status(effect)
        for clause in rule_ir.clauses
        for effect in clause.effects
    )


def _effect_sets_shadow_of_chaos_status(effect: RuleEffectSpec) -> bool:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Shadow of Chaos semantic aura requires RuleEffectSpec values.")
    if effect.kind is not RuleEffectKind.SET_CONTEXTUAL_STATUS:
        return False
    parameters = parameter_payload(effect.parameters)
    return (
        parameters.get("status") == "within_shadow_of_chaos"
        and parameters.get("rules_context") == "shadow_of_chaos"
        and parameters.get("owner") == "your_army"
    )


def _execution_result_sets_shadow_status_for_unit(
    result: RuleExecutionResult,
    *,
    unit_instance_id: str,
) -> bool:
    if type(result) is not RuleExecutionResult:
        raise GameLifecycleError("Shadow of Chaos semantic aura requires execution results.")
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for payload in result.effect_payloads:
        target_ids = _payload_identifier_list(
            payload,
            key="target_unit_instance_ids",
        )
        if requested_unit_id not in target_ids:
            continue
        effect_payload = payload.get("effect")
        if not isinstance(effect_payload, dict):
            raise GameLifecycleError("Shadow of Chaos semantic aura payload is missing effect.")
        try:
            effect = RuleEffectSpec.from_payload(cast(RuleEffectSpecPayload, effect_payload))
        except RuleIRError as exc:
            raise GameLifecycleError(
                "Shadow of Chaos semantic aura effect payload is invalid."
            ) from exc
        if _effect_sets_shadow_of_chaos_status(effect):
            return True
    return False


def _payload_identifier_list(payload: dict[str, JsonValue], *, key: str) -> tuple[str, ...]:
    values = payload.get(key)
    if not isinstance(values, list):
        raise GameLifecycleError(f"Shadow of Chaos semantic aura payload requires {key}.")
    identifiers: list[str] = []
    for value in values:
        identifiers.append(_validate_identifier(key, value))
    return tuple(identifiers)


def _unit_intersects_deployment_zones(
    *,
    state: GameState,
    unit_instance_id: str,
    player_id: str,
    owner_zone: bool,
) -> bool:
    if state.mission_setup is None or state.battlefield_state is None:
        raise GameLifecycleError("Deployment-zone Shadow check requires battle setup.")
    zones = tuple(
        zone
        for zone in state.mission_setup.deployment_zones
        if (zone.player_id == player_id) is owner_zone
    )
    if not zones:
        raise GameLifecycleError("Deployment-zone Shadow check requires matching zones.")
    for geometry_model in _unit_geometry_models(state=state, unit_instance_id=unit_instance_id):
        if any(
            shapely_backend.base_footprint_intersects_deployment_zone(
                geometry_model.base,
                geometry_model.pose,
                zone,
            )
            for zone in zones
        ):
            return True
    return False


def _unit_intersects_no_mans_land(
    *,
    state: GameState,
    unit_instance_id: str,
) -> bool:
    if state.mission_setup is None:
        raise GameLifecycleError("No Man's Land Shadow check requires MissionSetup.")
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("No Man's Land Shadow check requires battlefield_state.")
    for geometry_model in _unit_geometry_models(state=state, unit_instance_id=unit_instance_id):
        if shapely_backend.base_footprint_intersects_no_mans_land(
            geometry_model.base,
            geometry_model.pose,
            battlefield_bounds=(
                0.0,
                0.0,
                battlefield_state.battlefield_width_inches,
                battlefield_state.battlefield_depth_inches,
            ),
            deployment_zones=state.mission_setup.deployment_zones,
        ):
            return True
    return False


def _unit_within_greater_daemon_terror(
    *,
    state: GameState,
    daemon_army: ArmyDefinition,
    target_unit: UnitInstance,
) -> bool:
    target_models = _unit_geometry_models(
        state=state,
        unit_instance_id=target_unit.unit_instance_id,
    )
    if not target_models:
        return False
    greater_daemon_unit_ids = tuple(
        unit.unit_instance_id for unit in daemon_army.units if _is_greater_daemon_terror_unit(unit)
    )
    for source_unit_id in greater_daemon_unit_ids:
        for source_model in _unit_geometry_models(state=state, unit_instance_id=source_unit_id):
            if any(
                shapely_backend.base_footprint_distance(
                    source_model.base,
                    source_model.pose,
                    target_model.base,
                    target_model.pose,
                )
                <= 6.0
                for target_model in target_models
            ):
                return True
    return False


def _unit_geometry_models(
    *,
    state: GameState,
    unit_instance_id: str,
) -> tuple[GeometryModel, ...]:
    if state.battlefield_state is None:
        raise GameLifecycleError("Unit geometry lookup requires battlefield_state.")
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    unit_placement = state.battlefield_state.unit_placement_or_none(unit_instance_id)
    if unit_placement is None:
        return ()
    return tuple(
        geometry_model_for_placement(
            model=scenario.model_instance_for_placement(model_placement),
            placement=model_placement,
        )
        for model_placement in unit_placement.model_placements
        if scenario.model_instance_for_placement(model_placement).is_alive
    )


def _no_mans_land_objective_ids(state: GameState) -> tuple[str, ...]:
    if state.mission_setup is None:
        raise GameLifecycleError("No Man's Land objective lookup requires MissionSetup.")
    return tuple(
        sorted(
            marker.objective_marker_id
            for marker in state.mission_setup.objective_markers
            if not any(
                zone.contains_point(marker.x_inches, marker.y_inches)
                for zone in state.mission_setup.deployment_zones
            )
        )
    )


def _opponent_deployment_objective_ids(
    state: GameState,
    *,
    player_id: str,
) -> tuple[str, ...]:
    if state.mission_setup is None:
        raise GameLifecycleError("Opponent deployment objective lookup requires MissionSetup.")
    requested_player_id = _validate_identifier("player_id", player_id)
    opponent_zones = tuple(
        zone
        for zone in state.mission_setup.deployment_zones
        if zone.player_id != requested_player_id
    )
    return tuple(
        sorted(
            marker.objective_marker_id
            for marker in state.mission_setup.objective_markers
            if any(zone.contains_point(marker.x_inches, marker.y_inches) for zone in opponent_zones)
        )
    )


def _controls_at_least_half(
    *,
    objective_record: ObjectiveControlRecord,
    objective_ids: tuple[str, ...],
    player_id: str,
) -> bool:
    if not objective_ids:
        return False
    controlled = 0
    for objective_id in objective_ids:
        result = objective_record.result_by_objective_id(objective_id)
        if result.status is ObjectiveControlStatus.UNSUPPORTED:
            raise GameLifecycleError("Shadow of Chaos cannot use unsupported objective control.")
        if (
            result.status is ObjectiveControlStatus.CONTROLLED
            and result.controlled_by_player_id == player_id
        ):
            controlled += 1
    return controlled * 2 >= len(objective_ids)


def _roll_d3(
    *,
    context: BattleShockOutcomeContext,
    reason: str,
    roll_type: str,
    actor_id: str,
) -> D3RollResult:
    roll_state = context.dice_manager.roll(
        DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason=reason,
            roll_type=roll_type,
            actor_id=actor_id,
        )
    )
    return D3RollResult.from_source_d6_result(roll_state.original_result)


def _placed_model_ids_for_unit(
    *,
    state: GameState,
    unit_instance_id: str,
) -> tuple[str, ...]:
    if state.battlefield_state is None:
        raise GameLifecycleError("Daemonic Manifestation healing requires battlefield_state.")
    return tuple(
        sorted(
            placement.model_instance_id
            for placement in state.battlefield_state.unit_placement_by_id(
                unit_instance_id
            ).model_placements
        )
    )


def _opposing_player_id(*, state: GameState, player_id: str) -> str:
    opponent_ids = tuple(sorted(player for player in state.player_ids if player != player_id))
    if len(opponent_ids) != 1:
        raise GameLifecycleError("Daemonic Manifestation healing requires one opposing player.")
    return opponent_ids[0]


def _emit_daemonic_manifestation_unsupported(
    *,
    context: BattleShockOutcomeContext,
    target_unit: UnitInstance,
    d3_result: D3RollResult,
    unsupported_reason: str,
) -> None:
    context.decisions.event_log.append(
        "chaos_daemons_daemonic_manifestation_unsupported",
        {
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "phase": context.phase.value,
            "source_rule_id": SOURCE_RULE_ID,
            "battle_shock_result_id": context.result.result_id,
            "unit_instance_id": target_unit.unit_instance_id,
            "unsupported_reason": _validate_identifier(
                "unsupported_reason",
                unsupported_reason,
            ),
            "d3_result": validate_json_value(d3_result.to_payload()),
        },
    )


def _emit_daemonic_manifestation_no_effect(
    *,
    context: BattleShockOutcomeContext,
    target_unit: UnitInstance,
    d3_result: D3RollResult,
    no_effect_reason: str,
) -> None:
    context.decisions.event_log.append(
        "chaos_daemons_daemonic_manifestation_no_effect",
        {
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "phase": context.phase.value,
            "source_rule_id": SOURCE_RULE_ID,
            "battle_shock_result_id": context.result.result_id,
            "unit_instance_id": target_unit.unit_instance_id,
            "no_effect_reason": _validate_identifier("no_effect_reason", no_effect_reason),
            "d3_result": validate_json_value(d3_result.to_payload()),
        },
    )


def _unit_has_feel_no_pain_choice(state: GameState, unit: UnitInstance) -> bool:
    return any(
        state.feel_no_pain_sources_for_model(model_instance_id=model.model_instance_id)
        or state.feel_no_pain_decline_allowed_for_model(model_instance_id=model.model_instance_id)
        for model in unit.own_models
        if model.is_alive
    )


def _destroyed_model_ids_for_unit(
    *,
    state: GameState,
    unit: UnitInstance,
) -> tuple[str, ...]:
    if state.battlefield_state is None:
        raise GameLifecycleError("Destroyed model lookup requires battlefield_state.")
    removed_ids = set(state.battlefield_state.removed_model_ids)
    return tuple(
        sorted(
            model.model_instance_id
            for model in unit.own_models
            if model.model_instance_id in removed_ids
        )
    )


def _is_greater_daemon_terror_unit(unit: UnitInstance) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Greater Daemon terror lookup requires UnitInstance.")
    return any(
        ability.source_kind is CatalogAbilitySourceKind.DATASHEET
        and ability.source_id in chaos_daemons_datasheets.GREATER_DAEMON_SHADOW_AURA_SOURCE_IDS
        for ability in unit.datasheet_abilities
    )


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    canonical = _canonical_keyword(keyword)
    return any(_canonical_keyword(stored) == canonical for stored in unit.keywords)


def _unit_has_faction_keyword(unit: UnitInstance, keyword: str) -> bool:
    canonical = _canonical_keyword(keyword)
    return any(_canonical_keyword(stored) == canonical for stored in unit.faction_keywords)


def _unit_by_id(state: GameState, unit_instance_id: str) -> UnitInstance:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit_id:
                return unit
    raise GameLifecycleError("Chaos Daemons army rule target unit is unknown.")


def _army_for_player(*, state: GameState, player_id: str) -> ArmyDefinition:
    requested_player_id = _validate_identifier("player_id", player_id)
    for army in state.army_definitions:
        if army.player_id == requested_player_id:
            return army
    raise GameLifecycleError("Chaos Daemons army rule player army is unknown.")


def _chaos_daemons_armies(state: GameState) -> tuple[ArmyDefinition, ...]:
    return tuple(
        army
        for army in state.army_definitions
        if army.detachment_selection.faction_id == CHAOS_DAEMONS_FACTION_ID
    )


def _validate_identifier_tuple(field_name: str, value: object) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for item in cast(tuple[object, ...], value):
        identifier = _validate_identifier(f"{field_name} value", item)
        if identifier in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        identifiers.append(identifier)
    return tuple(identifiers)


_validate_identifier = IdentifierValidator(GameLifecycleError)
