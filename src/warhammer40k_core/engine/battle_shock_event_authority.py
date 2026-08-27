from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.dice import (
    DiceExpression,
    RerollPermission,
)
from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.engine.battle_shock import (
    BattleShockResult,
    BattleShockResultPayload,
    BattleShockTestRequest,
    battle_shock_leadership_target_for_rules_unit,
)
from warhammer40k_core.engine.battle_shock_historical_authority import (
    HistoricalBattleShockAuthorityContext,
    historical_battle_shock_authority_context,
)
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockHookBinding,
    BattleShockModifierApplication,
    HistoricalBattleShockContribution,
    battle_shock_modifier_applications_from_modifiers,
)
from warhammer40k_core.engine.battle_shock_resolution_authority import (
    BattleShockRerollAuthority,
    BattleShockResolutionAuthority,
    parse_battle_shock_resolution_authority,
)
from warhammer40k_core.engine.battle_shock_source_family_authority import (
    validate_battle_shock_runtime_source_family_authority,
    validate_battle_shock_source_family_authority,
)
from warhammer40k_core.engine.catalog_selected_target_test_modifiers import (
    BATTLE_SHOCK_TEST_ROLL_TYPE,
    CATALOG_SELECTED_TARGET_TEST_MODIFIER_HOOK_ID,
    selected_target_test_roll_modifier_from_effect,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.effects import PersistingEffect, PersistingEffectPayload
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.mutation_decision_authority import (
    validate_mutation_decision_closure,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.stratagems_model import (
    GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
    StratagemUseRecord,
    StratagemUseRecordPayload,
)
from warhammer40k_core.engine.unit_move_completed_hooks import (
    UNIT_MOVE_COMPLETED_BATTLE_SHOCK_BASE_PAYLOAD_KEYS,
    UnitMoveCompletedBattleShockEffect,
    unit_move_completed_battle_shock_base_payload,
    unit_move_completed_battle_shock_effect_key,
    unit_move_completed_battle_shock_request_id,
)
from warhammer40k_core.engine.unit_state import BelowHalfStrengthContext

if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
    from warhammer40k_core.engine.game_state import GameState


_SELECTED_TARGET_EFFECT_EVENTS = frozenset(
    {
        "catalog_selected_target_effect_selected",
        "catalog_post_shoot_hit_target_effect_selected",
        "catalog_shooting_start_selected_target_effect_selected",
    }
)


@dataclass(frozen=True, slots=True)
class _RuntimeModifierAuthority:
    event_index: int
    payload: dict[str, JsonValue]
    phase_start_battle_shocked_unit_ids: tuple[str, ...]
    applications: tuple[BattleShockModifierApplication, ...]


def validate_battle_shock_resolution_event_authority(
    *,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    resolved_index: int,
    resolved_payload: dict[str, JsonValue],
    result: BattleShockResult,
) -> BattleShockResolutionAuthority:
    authority = parse_battle_shock_resolution_authority(
        event_records=event_records,
        decision_records=decision_records,
        resolved_index=resolved_index,
        resolved_payload=resolved_payload,
        result=result,
    )
    request_payload = cast(
        dict[str, JsonValue],
        validate_json_value(result.request.to_payload()),
    )
    validate_battle_shock_source_family_authority(
        event_records=event_records,
        decision_records=decision_records,
        resolved_index=resolved_index,
        request_payload=request_payload,
        request_context=authority.request_context,
        request_base=authority.base_payload,
        result=result,
    )
    return authority


def validate_battle_shock_runtime_content_authority(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    runtime_content_bundle: RuntimeContentBundle,
) -> None:
    """Bind historical Battle-shock producers to the restored runtime bundle."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Battle-shock runtime authority requires GameState.")
    if type(event_records) is not tuple or any(
        type(event) is not EventRecord for event in event_records
    ):
        raise GameLifecycleError("Battle-shock runtime authority requires event records.")
    if type(decision_records) is not tuple or any(
        type(record) is not DecisionRecord for record in decision_records
    ):
        raise GameLifecycleError("Battle-shock runtime authority requires decision records.")
    for resolved_index, event in enumerate(event_records):
        if event.event_type != "battle_shock_test_resolved":
            continue
        resolved_payload = _json_object(event.payload, context="resolved event")
        raw_result = _json_object(
            resolved_payload.get("battle_shock_result"),
            context="resolved result",
        )
        result = BattleShockResult.from_payload(cast(BattleShockResultPayload, raw_result))
        authority = validate_battle_shock_resolution_event_authority(
            event_records=event_records,
            decision_records=decision_records,
            resolved_index=resolved_index,
            resolved_payload=resolved_payload,
            result=result,
        )
        prior_events = event_records[:resolved_index]
        request_index = authority.request_event_index
        request_base = authority.base_payload
        modifier_authority = _RuntimeModifierAuthority(
            event_index=authority.modifier_event_index,
            payload=cast(
                dict[str, JsonValue],
                event_records[authority.modifier_event_index].payload,
            ),
            phase_start_battle_shocked_unit_ids=(authority.phase_start_battle_shocked_unit_ids),
            applications=authority.modifier_applications,
        )
        active_player_id = authority.active_player_id
        phase = authority.phase
        historical = historical_battle_shock_authority_context(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            boundary_event_index=modifier_authority.event_index,
            request=result.request,
            active_player_id=active_player_id,
            phase=phase,
            phase_start_battle_shocked_unit_ids=(
                modifier_authority.phase_start_battle_shocked_unit_ids
            ),
        )
        _validate_historical_request_semantics(
            historical=historical,
            prior_events=prior_events,
            request_index=request_index,
            request_base=request_base,
            result=result,
            active_player_id=active_player_id,
            phase=phase,
            phase_start_battle_shocked_unit_ids=(
                modifier_authority.phase_start_battle_shocked_unit_ids
            ),
            runtime_content_bundle=runtime_content_bundle,
        )
        _validate_loaded_modifier_applications(
            event_records=prior_events,
            decision_records=decision_records,
            modifier_event_index=modifier_authority.event_index,
            request_base=request_base,
            result=result,
            applications=modifier_authority.applications,
            historical=historical,
            active_player_id=active_player_id,
            phase=phase,
            phase_start_battle_shocked_unit_ids=(
                modifier_authority.phase_start_battle_shocked_unit_ids
            ),
            runtime_content_bundle=runtime_content_bundle,
        )
        if authority.reroll is not None:
            expected_permission = _historical_reroll_permission(
                historical=historical,
                runtime_content_bundle=runtime_content_bundle,
            )
            if expected_permission is None or authority.reroll.permission != expected_permission:
                raise GameLifecycleError(
                    "Completed Battle-shock reroll lacks loaded permission authority."
                )
        validate_battle_shock_runtime_source_family_authority(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            authority=authority,
            historical=historical,
            modifier_applications=modifier_authority.applications,
            runtime_content_bundle=runtime_content_bundle,
        )


def _validate_historical_request_semantics(
    *,
    historical: HistoricalBattleShockAuthorityContext,
    prior_events: tuple[EventRecord, ...],
    request_index: int,
    request_base: dict[str, JsonValue],
    result: BattleShockResult,
    active_player_id: str,
    phase: BattlePhase,
    phase_start_battle_shocked_unit_ids: tuple[str, ...],
    runtime_content_bundle: RuntimeContentBundle,
) -> None:
    request = result.request
    if request.game_id != historical.game_id or request.player_id not in historical.player_ids:
        raise GameLifecycleError("Battle-shock historical request occurrence drifted.")
    rules_unit = historical.rules_unit(request.unit_instance_id)
    if rules_unit.owner_player_id != request.player_id:
        raise GameLifecycleError("Battle-shock historical request owner drifted.")
    placed_model_ids = historical.placed_alive_model_ids(rules_unit.unit_instance_id)
    if not placed_model_ids:
        raise GameLifecycleError("Battle-shock historical request unit is not on battlefield.")
    if request_base.get("source_kind") == "command_battle_shock":
        _validate_command_candidate_model_authority(
            prior_events=prior_events,
            request_index=request_index,
            request=result.request,
            active_player_id=active_player_id,
            phase_start_battle_shocked_unit_ids=(phase_start_battle_shocked_unit_ids),
            placed_model_ids=placed_model_ids,
        )
    starting_strength = historical.starting_strength(rules_unit.unit_instance_id)
    expected_strength_context = BelowHalfStrengthContext.from_rules_unit(
        rules_unit=rules_unit,
        starting_strength=starting_strength,
        current_model_ids=placed_model_ids,
    )
    if request.below_half_strength_context != expected_strength_context:
        raise GameLifecycleError("Battle-shock historical request strength context drifted.")
    ability_index = runtime_content_bundle.ability_indexes_by_player_id.get(request.player_id)
    if ability_index is None:
        raise GameLifecycleError("Battle-shock request lacks loaded Leadership authority.")
    expected_leadership = battle_shock_leadership_target_for_rules_unit(
        rules_unit,
        current_model_ids=placed_model_ids,
        ability_index=ability_index,
        state=None,
    )
    characteristic_bindings = (
        runtime_content_bundle.runtime_modifier_registry.all_unit_characteristic_bindings()
    )
    for binding in characteristic_bindings:
        if binding.historical_leadership_handler is None:
            raise GameLifecycleError(
                "Loaded unit characteristic modifier lacks historical Leadership authority."
            )
        expected_leadership = binding.historical_leadership_handler(
            historical,
            expected_leadership,
        )
    if request.leadership_target != expected_leadership:
        raise GameLifecycleError("Battle-shock request Leadership lacks exact authority.")
    expected_expression = _historical_dice_expression(
        historical=historical,
        runtime_content_bundle=runtime_content_bundle,
    )
    if request.spec.expression != expected_expression:
        raise GameLifecycleError(
            "Battle-shock request dice expression lacks exact runtime authority."
        )


def _historical_contributions(
    *,
    historical: HistoricalBattleShockAuthorityContext,
    runtime_content_bundle: RuntimeContentBundle,
) -> tuple[tuple[BattleShockHookBinding, HistoricalBattleShockContribution], ...]:
    contributions: list[tuple[BattleShockHookBinding, HistoricalBattleShockContribution]] = []
    for binding in runtime_content_bundle.battle_shock_hook_registry.all_bindings():
        requires_authority = (
            binding.dice_expression_handler is not None
            or (
                binding.modifier_handler is not None and not binding.modifier_source_effect_evidence
            )
            or binding.reroll_permission_handler is not None
        )
        handler = binding.historical_contribution_handler
        if handler is None:
            if requires_authority:
                raise GameLifecycleError(
                    "Loaded Battle-shock hook lacks event-bound historical authority."
                )
            continue
        contribution = handler(historical)
        if type(contribution) is not HistoricalBattleShockContribution:
            raise GameLifecycleError(
                "Historical Battle-shock provider returned an invalid contribution."
            )
        if contribution.dice_expression is not None and binding.dice_expression_handler is None:
            raise GameLifecycleError("Historical Battle-shock dice provider drifted.")
        if contribution.modifiers and binding.modifier_handler is None:
            raise GameLifecycleError("Historical Battle-shock modifier provider drifted.")
        if contribution.reroll_permission is not None and (
            binding.reroll_permission_handler is None
        ):
            raise GameLifecycleError("Historical Battle-shock reroll provider drifted.")
        contributions.append((binding, contribution))
    return tuple(contributions)


def _historical_dice_expression(
    *,
    historical: HistoricalBattleShockAuthorityContext,
    runtime_content_bundle: RuntimeContentBundle,
) -> DiceExpression:
    expression = DiceExpression(quantity=2, sides=6)
    seen_override = False
    for _binding, contribution in _historical_contributions(
        historical=historical,
        runtime_content_bundle=runtime_content_bundle,
    ):
        candidate = contribution.dice_expression
        if candidate is None:
            continue
        if seen_override and candidate != expression:
            raise GameLifecycleError(
                "Historical Battle-shock dice providers produced conflicting overrides."
            )
        expression = candidate
        seen_override = True
    return expression


def _historical_modifier_applications(
    *,
    historical: HistoricalBattleShockAuthorityContext,
    runtime_content_bundle: RuntimeContentBundle,
) -> tuple[BattleShockModifierApplication, ...]:
    applications: list[BattleShockModifierApplication] = []
    for raw_binding, contribution in _historical_contributions(
        historical=historical,
        runtime_content_bundle=runtime_content_bundle,
    ):
        if not contribution.modifiers:
            continue
        applications.extend(
            battle_shock_modifier_applications_from_modifiers(
                provider_id=raw_binding.hook_id,
                modifiers=contribution.modifiers,
            )
        )
    return tuple(sorted(applications, key=lambda value: (value.hook_id, value.source_id)))


def _historical_reroll_permission(
    *,
    historical: HistoricalBattleShockAuthorityContext,
    runtime_content_bundle: RuntimeContentBundle,
) -> RerollPermission | None:
    permissions = tuple(
        contribution.reroll_permission
        for _binding, contribution in _historical_contributions(
            historical=historical,
            runtime_content_bundle=runtime_content_bundle,
        )
        if contribution.reroll_permission is not None
    )
    if len(permissions) > 1:
        raise GameLifecycleError(
            "Multiple historical Battle-shock reroll permissions are available."
        )
    return permissions[0] if permissions else None


def _validate_command_candidate_model_authority(
    *,
    prior_events: tuple[EventRecord, ...],
    request_index: int,
    request: BattleShockTestRequest,
    active_player_id: str,
    phase_start_battle_shocked_unit_ids: tuple[str, ...],
    placed_model_ids: tuple[str, ...],
) -> None:
    from warhammer40k_core.engine.command_battle_shock_candidates import (
        CommandBattleShockCandidate,
        CommandBattleShockCandidatePayload,
    )

    if type(request) is not BattleShockTestRequest:
        raise GameLifecycleError("Command Battle-shock candidate authority requires request.")
    snapshots = tuple(
        event
        for event in prior_events[:request_index]
        if event.event_type == "battle_shock_step_snapshot_created"
        and isinstance(event.payload, dict)
        and event.payload.get("game_id") == request.game_id
        and event.payload.get("battle_round") == request.battle_round
        and event.payload.get("active_player_id") == active_player_id
        and event.payload.get("phase") == BattlePhase.COMMAND.value
    )
    if len(snapshots) != 1:
        raise GameLifecycleError("Command Battle-shock candidate authority is ambiguous.")
    payload = cast(dict[str, JsonValue], snapshots[0].payload)
    raw_candidates = payload.get("battle_shock_candidate_inventory")
    if not isinstance(raw_candidates, list) or any(
        not isinstance(value, dict) for value in raw_candidates
    ):
        raise GameLifecycleError("Command Battle-shock candidate authority is invalid.")
    candidates = tuple(
        CommandBattleShockCandidate.from_payload(cast(CommandBattleShockCandidatePayload, value))
        for value in raw_candidates
        if isinstance(value, dict)
    )
    matching = tuple(
        candidate
        for candidate in candidates
        if candidate.unit_instance_id == request.unit_instance_id
    )
    if (
        len(matching) != 1
        or matching[0].placed_alive_model_instance_ids != placed_model_ids
        or matching[0].below_half_strength_context != request.below_half_strength_context
        or payload.get("battle_shock_phase_start_unit_ids")
        != list(phase_start_battle_shocked_unit_ids)
    ):
        raise GameLifecycleError("Command Battle-shock candidate model authority drifted.")


def _validate_loaded_modifier_applications(
    *,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    modifier_event_index: int,
    request_base: dict[str, JsonValue],
    result: BattleShockResult,
    applications: tuple[BattleShockModifierApplication, ...],
    historical: HistoricalBattleShockAuthorityContext,
    active_player_id: str,
    phase: BattlePhase,
    phase_start_battle_shocked_unit_ids: tuple[str, ...],
    runtime_content_bundle: RuntimeContentBundle,
) -> None:
    bindings = runtime_content_bundle.battle_shock_hook_registry.all_bindings()
    binding_hook_ids = frozenset(binding.hook_id for binding in bindings)
    state_recomputed_hook_ids = frozenset(
        binding.hook_id
        for binding in bindings
        if binding.modifier_handler is not None and not binding.modifier_source_effect_evidence
    )
    source_effect_hook_ids = frozenset(
        binding.hook_id
        for binding in bindings
        if binding.modifier_handler is not None and binding.modifier_source_effect_evidence
    )
    source_kind = request_base.get("source_kind")
    if source_kind != "stratagem_battle_shock" and any(
        application.hook_id not in binding_hook_ids for application in applications
    ):
        raise GameLifecycleError("Battle-shock modifier hook lacks loaded runtime authority.")
    expected_loaded_applications = _historical_modifier_applications(
        historical=historical,
        runtime_content_bundle=runtime_content_bundle,
    )
    presented_loaded_applications = tuple(
        application
        for application in applications
        if application.hook_id in state_recomputed_hook_ids
    )
    expected_state_applications = tuple(
        application
        for application in expected_loaded_applications
        if application.hook_id in state_recomputed_hook_ids
    )
    if presented_loaded_applications != expected_state_applications:
        raise GameLifecycleError(
            "Battle-shock modifier applications are incomplete or context-invalid."
        )
    expected_source_effect_applications = _expected_source_effect_modifier_applications(
        event_records=event_records,
        decision_records=decision_records,
        modifier_event_index=modifier_event_index,
        result=result,
    )
    presented_source_effect_applications = tuple(
        application for application in applications if application.hook_id in source_effect_hook_ids
    )
    if presented_source_effect_applications != expected_source_effect_applications:
        raise GameLifecycleError(
            "Battle-shock source-effect applications are incomplete or context-invalid."
        )
    for application in applications:
        matches = tuple(binding for binding in bindings if binding.hook_id == application.hook_id)
        if not matches:
            if source_kind != "stratagem_battle_shock":
                raise GameLifecycleError(
                    "Battle-shock modifier hook lacks loaded runtime authority."
                )
            _validate_stratagem_modifier_application(
                event_records=event_records,
                decision_records=decision_records,
                request_base=request_base,
                result=result,
                application=application,
                runtime_content_bundle=runtime_content_bundle,
            )
            continue
        if len(matches) != 1 or matches[0].modifier_handler is None:
            raise GameLifecycleError("Battle-shock modifier hook authority is ambiguous.")
        binding = matches[0]
        if (
            not binding.modifier_source_effect_evidence
            and binding.historical_contribution_handler is None
        ):
            raise GameLifecycleError("Battle-shock modifier hook lacks an authority validator.")


def _expected_source_effect_modifier_applications(
    *,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    modifier_event_index: int,
    result: BattleShockResult,
) -> tuple[BattleShockModifierApplication, ...]:
    if type(modifier_event_index) is not int or not 0 <= modifier_event_index < len(event_records):
        raise GameLifecycleError("Battle-shock source-effect boundary is invalid.")
    request_payload = result.request.to_payload()
    matches: list[tuple[int, dict[str, JsonValue]]] = []
    for event_index, event in enumerate(event_records[:modifier_event_index]):
        if (
            event.event_type == "battle_shock_test_requested"
            and isinstance(event.payload, dict)
            and event.payload.get("battle_shock_test_request") == request_payload
        ):
            matches.append((event_index, event.payload))
    if len(matches) != 1:
        raise GameLifecycleError("Battle-shock source-effect request authority is ambiguous.")
    request_index, request_context = matches[0]
    raw_effects = request_context.get("selected_target_recorded_effects_before_battle_shock")
    if raw_effects is None:
        return ()
    if not isinstance(raw_effects, list):
        raise GameLifecycleError("Battle-shock source-effect evidence is invalid.")
    selected_result = request_context.get("selected_target_decision_result")
    if not isinstance(selected_result, dict):
        raise GameLifecycleError("Battle-shock source-effect decision is missing.")
    request_id = selected_result.get("request_id")
    result_id = selected_result.get("result_id")
    if type(request_id) is not str or type(result_id) is not str:
        raise GameLifecycleError("Battle-shock source-effect decision identity is invalid.")
    validate_mutation_decision_closure(
        event_records=event_records,
        decision_records=decision_records,
        mutation_index=request_index,
        request_id=request_id,
        result_id=result_id,
    )
    active_effects: list[PersistingEffect] = []
    seen_effect_ids: set[str] = set()
    for raw_effect in raw_effects:
        if not _looks_like_persisting_effect(raw_effect):
            continue
        effect = PersistingEffect.from_payload(cast(PersistingEffectPayload, raw_effect))
        if effect.effect_id in seen_effect_ids:
            raise GameLifecycleError("Battle-shock source-effect evidence is duplicated.")
        seen_effect_ids.add(effect.effect_id)
        if result.request.unit_instance_id not in effect.target_unit_instance_ids:
            continue
        if (
            selected_target_test_roll_modifier_from_effect(
                effect=effect,
                roll_type=BATTLE_SHOCK_TEST_ROLL_TYPE,
            )
            is not None
        ):
            active_effects.append(effect)
    modifiers = tuple(
        sorted(
            (
                modifier
                for effect in active_effects
                if (
                    modifier := selected_target_test_roll_modifier_from_effect(
                        effect=effect,
                        roll_type=BATTLE_SHOCK_TEST_ROLL_TYPE,
                    )
                )
                is not None
            ),
            key=lambda value: value.modifier_id,
        )
    )
    return battle_shock_modifier_applications_from_modifiers(
        provider_id=CATALOG_SELECTED_TARGET_TEST_MODIFIER_HOOK_ID,
        modifiers=modifiers,
    )


def _has_exact_source_effect_modifier_authority(
    *,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    result: BattleShockResult,
    application: BattleShockModifierApplication,
) -> bool:
    from warhammer40k_core.engine.catalog_selected_target_test_modifiers import (
        BATTLE_SHOCK_TEST_ROLL_TYPE,
        selected_target_test_roll_modifier_from_effect,
    )

    request_payload = result.request.to_payload()
    matches: list[tuple[int, str, str]] = []
    for event_index, event in enumerate(event_records):
        if not isinstance(event.payload, dict):
            continue
        authority_request_id: JsonValue
        authority_result_id: JsonValue
        if event.event_type in _SELECTED_TARGET_EFFECT_EVENTS:
            raw_effects = event.payload.get("persisting_effects")
            authority_request_id = event.payload.get("request_id")
            authority_result_id = event.payload.get("result_id")
        elif (
            event.event_type == "battle_shock_test_requested"
            and event.payload.get("battle_shock_test_request") == request_payload
        ):
            raw_effects = event.payload.get("selected_target_recorded_effects_before_battle_shock")
            selected_result = event.payload.get("selected_target_decision_result")
            if not isinstance(selected_result, dict):
                continue
            authority_request_id = selected_result.get("request_id")
            authority_result_id = selected_result.get("result_id")
        else:
            continue
        if not isinstance(raw_effects, list):
            continue
        derived: list[RollModifier] = []
        for raw_effect in raw_effects:
            if not _looks_like_persisting_effect(raw_effect):
                continue
            effect = PersistingEffect.from_payload(cast(PersistingEffectPayload, raw_effect))
            if result.request.unit_instance_id not in effect.target_unit_instance_ids:
                continue
            modifier = selected_target_test_roll_modifier_from_effect(
                effect=effect,
                roll_type=BATTLE_SHOCK_TEST_ROLL_TYPE,
            )
            if modifier is not None:
                derived.append(modifier)
        if tuple(sorted(derived, key=lambda modifier: modifier.modifier_id)) == (
            application.modifiers
        ):
            if type(authority_request_id) is not str or type(authority_result_id) is not str:
                raise GameLifecycleError("Battle-shock source-effect decision identity is invalid.")
            matches.append((event_index, authority_request_id, authority_result_id))
    if len(matches) != 1:
        return False
    event_index, request_id, result_id = matches[0]
    validate_mutation_decision_closure(
        event_records=event_records,
        decision_records=decision_records,
        mutation_index=event_index,
        request_id=request_id,
        result_id=result_id,
    )
    return True


def _looks_like_persisting_effect(value: JsonValue) -> bool:
    return isinstance(value, dict) and {
        "effect_id",
        "source_rule_id",
        "owner_player_id",
        "target_unit_instance_ids",
        "started_battle_round",
        "started_phase",
        "expiration",
        "effect_payload",
    }.issubset(value)


def _validate_stratagem_modifier_application(
    *,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    request_base: dict[str, JsonValue],
    result: BattleShockResult,
    application: BattleShockModifierApplication,
    runtime_content_bundle: RuntimeContentBundle,
) -> None:
    use = _validated_stratagem_use_and_provider(
        request_base=request_base,
        result=result,
        runtime_content_bundle=runtime_content_bundle,
    )
    provider_id = use.handler_id
    if application.hook_id != provider_id:
        raise GameLifecycleError("Battle-shock Stratagem modifier provider drifted.")
    if _has_exact_source_effect_modifier_authority(
        event_records=event_records,
        decision_records=decision_records,
        result=result,
        application=application,
    ):
        return
    if application.source_id != use.source_id:
        raise GameLifecycleError("Battle-shock Stratagem modifier source drifted.")
    if use.handler_id != GENERIC_RULE_IR_STRATAGEM_HANDLER_ID:
        return
    effect = _json_object(
        request_base.get("generic_rule_effect"),
        context="generic Stratagem effect",
    )
    source_id = effect.get("source_id")
    operand = _generic_rule_effect_parameter(effect, key="modifier_if_destroyed_target")
    suffix = _generic_rule_effect_parameter(effect, key="modifier_source_suffix")
    if (
        source_id != application.source_id
        or type(operand) is not int
        or (suffix is not None and type(suffix) is not str)
    ):
        raise GameLifecycleError("Battle-shock generic Stratagem modifier source drifted.")
    expected_id = f"{use.use_id}:{suffix or 'battle-shock-modifier'}"
    if len(application.modifiers) != 1:
        raise GameLifecycleError("Battle-shock generic Stratagem modifier count drifted.")
    modifier = application.modifiers[0]
    if modifier.modifier_id != expected_id or modifier.operand != operand:
        raise GameLifecycleError("Battle-shock generic Stratagem modifier operand drifted.")


def _validated_stratagem_use_and_provider(
    *,
    request_base: dict[str, JsonValue],
    result: BattleShockResult,
    runtime_content_bundle: RuntimeContentBundle,
) -> StratagemUseRecord:
    raw_use = _json_object(
        request_base.get("source_stratagem_use"),
        context="source Stratagem use",
    )
    use = StratagemUseRecord.from_payload(cast(StratagemUseRecordPayload, raw_use))
    index = runtime_content_bundle.stratagem_indexes_by_player_id.get(use.player_id)
    if index is None:
        raise GameLifecycleError("Battle-shock Stratagem lacks a loaded player index.")
    records = tuple(
        record
        for record in index.all_records()
        if record.definition.stratagem_id == use.stratagem_id
    )
    if len(records) != 1:
        raise GameLifecycleError("Battle-shock Stratagem catalog authority is ambiguous.")
    record = records[0]
    if (
        record.disabled
        or record.definition.source_id != use.source_id
        or record.definition.handler_id != use.handler_id
    ):
        raise GameLifecycleError("Battle-shock Stratagem catalog authority drifted.")
    if use.handler_id != GENERIC_RULE_IR_STRATAGEM_HANDLER_ID and not (
        runtime_content_bundle.stratagem_handler_registry.has_handler(use.handler_id)
    ):
        raise GameLifecycleError("Battle-shock Stratagem handler lacks loaded authority.")
    expected_request_id = f"{use.use_id}:battle-shock:{result.request.unit_instance_id}"
    if result.request.request_id != expected_request_id:
        raise GameLifecycleError("Battle-shock Stratagem request identity drifted.")
    return use


def _generic_rule_effect_parameter(
    effect_payload: dict[str, JsonValue],
    *,
    key: str,
) -> JsonValue:
    effect = _json_object(effect_payload.get("effect"), context="generic rule effect")
    parameters = effect.get("parameters")
    if not isinstance(parameters, list):
        raise GameLifecycleError("Battle-shock generic rule effect parameters are invalid.")
    matches = tuple(
        parameter.get("value")
        for parameter in parameters
        if isinstance(parameter, dict) and parameter.get("key") == key
    )
    if len(matches) > 1:
        raise GameLifecycleError("Battle-shock generic rule effect parameter is duplicated.")
    return None if not matches else matches[0]


def validate_unit_move_completed_battle_shock_request_authority(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    request_event_index: int,
    request_base: dict[str, JsonValue],
    request: BattleShockTestRequest,
    active_player_id: str,
    phase: BattlePhase,
    phase_start_battle_shocked_unit_ids: tuple[str, ...],
    runtime_content_bundle: RuntimeContentBundle,
) -> None:
    from warhammer40k_core.engine.catalog_unit_move_completed_battle_shock_runtime import (
        historical_catalog_unit_move_completed_battle_shock_effects,
    )
    from warhammer40k_core.engine.charge_move_event_authority import (
        validate_charge_move_completed_event_authority,
    )

    if type(request_event_index) is not int or not 0 <= request_event_index < len(event_records):
        raise GameLifecycleError("Battle-shock move-completed request index is invalid.")
    if type(request) is not BattleShockTestRequest:
        raise GameLifecycleError("Battle-shock move-completed authority requires a request.")
    if type(active_player_id) is not str or not active_player_id:
        raise GameLifecycleError("Battle-shock move-completed active player is invalid.")
    if type(phase) is not BattlePhase:
        raise GameLifecycleError("Battle-shock move-completed phase is invalid.")
    if frozenset(request_base) != UNIT_MOVE_COMPLETED_BATTLE_SHOCK_BASE_PAYLOAD_KEYS:
        raise GameLifecycleError("Battle-shock move-completed source schema drifted.")
    request_event = event_records[request_event_index]
    request_payload = cast(dict[str, JsonValue], validate_json_value(request.to_payload()))
    if request_event.event_type != "battle_shock_test_requested" or request_event.payload != {
        **request_base,
        "battle_shock_test_request": request_payload,
    }:
        raise GameLifecycleError("Battle-shock move-completed request occurrence drifted.")
    matching_request_indexes = tuple(
        index
        for index, event in enumerate(event_records)
        if event.event_type == "battle_shock_test_requested"
        and isinstance(event.payload, dict)
        and event.payload.get("battle_shock_test_request") == request_payload
    )
    if matching_request_indexes != (request_event_index,):
        raise GameLifecycleError("Battle-shock move-completed request occurrence is ambiguous.")
    hook_id = request_base.get("hook_id")
    trigger_event_id = request_base.get("trigger_event_id")
    source_rule_id = request_base.get("source_rule_id")
    target_unit_id = request_base.get("target_unit_instance_id")
    target_player_id = request_base.get("target_player_id")
    replay_payload = request_base.get("replay_payload")
    if not all(
        type(value) is str
        for value in (
            hook_id,
            trigger_event_id,
            source_rule_id,
            target_unit_id,
            target_player_id,
        )
    ) or not isinstance(replay_payload, dict):
        raise GameLifecycleError("Battle-shock move-completed source payload is invalid.")
    hook = cast(str, hook_id)
    trigger_id = cast(str, trigger_event_id)
    source_rule = cast(str, source_rule_id)
    target_unit = cast(str, target_unit_id)
    target_player = cast(str, target_player_id)
    triggers = tuple(
        (index, event) for index, event in enumerate(event_records) if event.event_id == trigger_id
    )
    if (
        len(triggers) != 1
        or triggers[0][0] >= request_event_index
        or triggers[0][1].event_type != "charge_move_completed"
    ):
        raise GameLifecycleError("Battle-shock move-completed trigger type drifted.")
    trigger_payload = _json_object(
        triggers[0][1].payload,
        context="move-completed trigger",
    )
    trigger_index = triggers[0][0]
    trigger_authority = validate_charge_move_completed_event_authority(
        event_records=event_records,
        decision_records=decision_records,
        event_index=trigger_index,
        payload=trigger_payload,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
    )
    triggering_unit_id = _required_identifier(
        trigger_payload.get("unit_instance_id"),
        context="move-completed triggering unit",
    )
    triggering_player_id = _required_identifier(
        trigger_payload.get("active_player_id"),
        context="move-completed triggering player",
    )
    if (
        request.game_id != request_base.get("game_id")
        or request.battle_round != request_base.get("battle_round")
        or active_player_id != triggering_player_id
        or active_player_id != request_base.get("active_player_id")
        or phase is not BattlePhase.CHARGE
        or request_base.get("phase") != BattlePhase.CHARGE.value
        or request_base.get("movement_action") != "charge_move"
        or trigger_payload.get("game_id") != request.game_id
        or trigger_payload.get("battle_round") != request.battle_round
        or trigger_payload.get("phase") != BattlePhase.CHARGE.value
        or trigger_authority.proposal.movement_phase_action != "charge_move"
    ):
        raise GameLifecycleError("Battle-shock move-completed trigger context drifted.")
    historical_before_trigger = historical_battle_shock_authority_context(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        boundary_event_index=trigger_index,
        request=request,
        active_player_id=active_player_id,
        phase=phase,
        phase_start_battle_shocked_unit_ids=phase_start_battle_shocked_unit_ids,
    )
    source_rules_unit = historical_before_trigger.rules_unit(triggering_unit_id)
    placed_source_model_ids = historical_before_trigger.placed_alive_model_ids(
        source_rules_unit.unit_instance_id
    )
    physical_rows = {
        row.model_instance_id: row for row in historical_before_trigger.physical_models
    }
    if (
        source_rules_unit.owner_player_id != triggering_player_id
        or trigger_authority.witness.model_ids() != placed_source_model_ids
        or any(
            physical_rows[model_id].pose != trigger_authority.witness.poses_for_model(model_id)[0]
            for model_id in placed_source_model_ids
        )
    ):
        raise GameLifecycleError("Battle-shock move-completed trigger model authority drifted.")
    historical = historical_battle_shock_authority_context(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        boundary_event_index=request_event_index,
        request=request,
        active_player_id=active_player_id,
        phase=phase,
        phase_start_battle_shocked_unit_ids=phase_start_battle_shocked_unit_ids,
    )
    bindings = tuple(
        binding
        for binding in (
            runtime_content_bundle.unit_move_completed_battle_shock_hook_registry.all_bindings()
        )
        if binding.hook_id == hook
    )
    if len(bindings) != 1:
        raise GameLifecycleError("Battle-shock move-completed hook lacks loaded authority.")
    binding = bindings[0]
    effect = UnitMoveCompletedBattleShockEffect(
        hook_id=hook,
        source_id=binding.source_id,
        source_rule_id=source_rule,
        target_unit_instance_id=target_unit,
        target_player_id=target_player,
        trigger_event_id=trigger_id,
        reason=request.reason,
        replay_payload=replay_payload,
    )
    historical_effects = historical_catalog_unit_move_completed_battle_shock_effects(
        historical=historical,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        trigger_event_id=trigger_id,
        triggering_unit_instance_id=triggering_unit_id,
        triggering_player_id=triggering_player_id,
        movement_action="charge_move",
        ability_indexes_by_player_id=runtime_content_bundle.ability_indexes_by_player_id,
    )
    if (
        historical_effects.count(effect) != 1
        or request_base
        != unit_move_completed_battle_shock_base_payload(
            game_id=request.game_id,
            battle_round=request.battle_round,
            active_player_id=active_player_id,
            completed_phase=phase,
            movement_action="charge_move",
            effect=effect,
        )
        or request_base.get("effect_key") != unit_move_completed_battle_shock_effect_key(effect)
        or request.request_id
        != unit_move_completed_battle_shock_request_id(
            battle_round=request.battle_round,
            effect=effect,
        )
        or request.unit_instance_id != target_unit
        or request.player_id != target_player
    ):
        raise GameLifecycleError("Battle-shock move-completed effect identity drifted.")


def _json_object(value: JsonValue, *, context: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"Battle-shock {context} must be an object.")
    return value


def _required_identifier(value: JsonValue, *, context: str) -> str:
    if type(value) is not str or not value:
        raise GameLifecycleError(f"Battle-shock {context} must be an identifier.")
    return value


__all__ = (
    "BattleShockRerollAuthority",
    "BattleShockResolutionAuthority",
    "validate_battle_shock_resolution_event_authority",
    "validate_battle_shock_runtime_content_authority",
    "validate_unit_move_completed_battle_shock_request_authority",
)
