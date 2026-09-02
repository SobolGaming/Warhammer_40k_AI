from __future__ import annotations

from dataclasses import replace
from typing import cast

from warhammer40k_core.core.objectives import ObjectiveMarker
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    PlacementError,
    UnitPlacement,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.hazard import (
    CORE_HAZARD_ROLLS_RULE_ID,
    HAZARD_ROLL_FAILURE_THRESHOLD,
    hazard_mortal_wounds_per_failed_roll,
    hazard_roll_failed,
    hazard_roll_spec,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.transports import (
    EMERGENCY_DISEMBARK_MOVE_SOURCE_ID,
    TRANSPORT_HAZARD_MORTAL_WOUNDS_SOURCE_KIND,
    CombatDisembark,
    CombatDisembarkPayload,
    DestroyedTransportDisembark,
    DestroyedTransportDisembarkPayload,
    DestroyedTransportHazardRolls,
    DestroyedTransportHazardRollsPayload,
    DestroyedTransportModelRoll,
    DisembarkModeKind,
    DisembarkSelection,
    TransportCargoState,
    TransportHazardMortalWounds,
    TransportMovementStatus,
    disembark_mode_for_hazard,
    disembark_mode_kind_from_token,
    emit_transport_hazard_mortal_wounds_resolved,
    resolve_disembark_internal,
    transport_hazard_source_context,
    validate_destroyed_transport_roll_tuple,
    validate_transport_identifier,
    validate_transport_positive_int,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition


def validate_destroyed_transport_hazard_rolls(
    hazard_rolls: DestroyedTransportHazardRolls,
) -> None:
    object.__setattr__(
        hazard_rolls,
        "source_rule_id",
        validate_transport_identifier(
            "DestroyedTransportHazardRolls source_rule_id",
            hazard_rolls.source_rule_id,
        ),
    )
    if hazard_rolls.source_rule_id != EMERGENCY_DISEMBARK_MOVE_SOURCE_ID:
        raise GameLifecycleError("DestroyedTransportHazardRolls source rule drift.")
    object.__setattr__(
        hazard_rolls,
        "player_id",
        validate_transport_identifier(
            "DestroyedTransportHazardRolls player_id",
            hazard_rolls.player_id,
        ),
    )
    object.__setattr__(
        hazard_rolls,
        "battle_round",
        validate_transport_positive_int(
            "DestroyedTransportHazardRolls battle_round",
            hazard_rolls.battle_round,
        ),
    )
    object.__setattr__(
        hazard_rolls,
        "unit_instance_id",
        validate_transport_identifier(
            "DestroyedTransportHazardRolls unit_instance_id",
            hazard_rolls.unit_instance_id,
        ),
    )
    object.__setattr__(
        hazard_rolls,
        "transport_unit_instance_id",
        validate_transport_identifier(
            "DestroyedTransportHazardRolls transport_unit_instance_id",
            hazard_rolls.transport_unit_instance_id,
        ),
    )
    object.__setattr__(
        hazard_rolls,
        "disembark_mode",
        disembark_mode_kind_from_token(hazard_rolls.disembark_mode),
    )
    if hazard_rolls.disembark_mode not in {
        DisembarkModeKind.DESTROYED_TRANSPORT,
        DisembarkModeKind.EMERGENCY_DISEMBARK,
    }:
        raise GameLifecycleError(
            "DestroyedTransportHazardRolls requires destroyed Transport timing."
        )
    object.__setattr__(
        hazard_rolls,
        "roll_threshold",
        validate_transport_positive_int(
            "DestroyedTransportHazardRolls roll_threshold",
            hazard_rolls.roll_threshold,
        ),
    )
    if hazard_rolls.roll_threshold != HAZARD_ROLL_FAILURE_THRESHOLD:
        raise GameLifecycleError("DestroyedTransportHazardRolls threshold drift.")
    object.__setattr__(
        hazard_rolls,
        "model_rolls",
        validate_destroyed_transport_roll_tuple(
            "DestroyedTransportHazardRolls model_rolls",
            hazard_rolls.model_rolls,
        ),
    )
    if not hazard_rolls.model_rolls:
        raise GameLifecycleError("DestroyedTransportHazardRolls requires cargo models.")
    wounds_per_failed_roll = validate_transport_positive_int(
        "DestroyedTransportHazardRolls mortal_wounds_per_failed_roll",
        hazard_rolls.mortal_wounds_per_failed_roll,
    )
    if wounds_per_failed_roll not in {1, 3}:
        raise GameLifecycleError(
            "DestroyedTransportHazardRolls mortal_wounds_per_failed_roll drift."
        )
    object.__setattr__(
        hazard_rolls,
        "mortal_wounds_per_failed_roll",
        wounds_per_failed_roll,
    )
    for roll in hazard_rolls.model_rolls:
        if roll.mortal_wound_inflicted != hazard_roll_failed(roll.roll_state):
            raise GameLifecycleError("DestroyedTransportHazardRolls roll result drift.")


def destroyed_transport_hazard_rolls_to_payload(
    hazard_rolls: DestroyedTransportHazardRolls,
) -> DestroyedTransportHazardRollsPayload:
    return {
        "source_rule_id": hazard_rolls.source_rule_id,
        "player_id": hazard_rolls.player_id,
        "battle_round": hazard_rolls.battle_round,
        "unit_instance_id": hazard_rolls.unit_instance_id,
        "transport_unit_instance_id": hazard_rolls.transport_unit_instance_id,
        "disembark_mode": hazard_rolls.disembark_mode.value,
        "roll_threshold": hazard_rolls.roll_threshold,
        "mortal_wounds_per_failed_roll": hazard_rolls.mortal_wounds_per_failed_roll,
        "model_rolls": [roll.to_payload() for roll in hazard_rolls.model_rolls],
        "mortal_wound_count": hazard_rolls.mortal_wound_count,
    }


def destroyed_transport_hazard_rolls_from_payload(
    payload: DestroyedTransportHazardRollsPayload,
) -> DestroyedTransportHazardRolls:
    result = DestroyedTransportHazardRolls(
        source_rule_id=payload["source_rule_id"],
        player_id=payload["player_id"],
        battle_round=payload["battle_round"],
        unit_instance_id=payload["unit_instance_id"],
        transport_unit_instance_id=payload["transport_unit_instance_id"],
        disembark_mode=disembark_mode_kind_from_token(payload["disembark_mode"]),
        roll_threshold=payload["roll_threshold"],
        mortal_wounds_per_failed_roll=payload["mortal_wounds_per_failed_roll"],
        model_rolls=tuple(
            DestroyedTransportModelRoll.from_payload(roll) for roll in payload["model_rolls"]
        ),
    )
    if result.mortal_wound_count != payload["mortal_wound_count"]:
        raise GameLifecycleError("DestroyedTransportHazardRolls mortal wound drift.")
    return result


def resolve_destroyed_transport_hazard_rolls_service(
    *,
    cargo_state: TransportCargoState,
    unit: UnitInstance,
    dice_manager: DiceRollManager,
    battle_round: int,
    disembark_mode: DisembarkModeKind,
) -> DestroyedTransportHazardRolls:
    if type(cargo_state) is not TransportCargoState:
        raise GameLifecycleError("Destroyed Transport hazard rolls require cargo state.")
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Destroyed Transport hazard rolls require UnitInstance.")
    if type(dice_manager) is not DiceRollManager:
        raise GameLifecycleError("Destroyed Transport hazard rolls require DiceRollManager.")
    if not cargo_state.contains_unit(unit.unit_instance_id):
        raise GameLifecycleError("Destroyed Transport hazard unit is not embarked.")
    model_ids = tuple(
        sorted(model.model_instance_id for model in unit.own_models if model.is_alive)
    )
    if not model_ids:
        raise GameLifecycleError("Destroyed Transport hazard rolls require living cargo models.")
    model_rolls = tuple(
        DestroyedTransportModelRoll(
            model_instance_id=model_instance_id,
            roll_state=(
                roll_state := dice_manager.roll(
                    hazard_roll_spec(
                        reason=(f"Emergency Disembark hazard roll for {model_instance_id}"),
                        roll_type="destroyed_transport_disembark",
                        actor_id=model_instance_id,
                    )
                )
            ),
            mortal_wound_inflicted=hazard_roll_failed(roll_state),
        )
        for model_instance_id in model_ids
    )
    return DestroyedTransportHazardRolls(
        player_id=cargo_state.player_id,
        battle_round=battle_round,
        unit_instance_id=unit.unit_instance_id,
        transport_unit_instance_id=cargo_state.transport_unit_instance_id,
        disembark_mode=disembark_mode,
        roll_threshold=HAZARD_ROLL_FAILURE_THRESHOLD,
        model_rolls=model_rolls,
        mortal_wounds_per_failed_roll=hazard_mortal_wounds_per_failed_roll(unit),
    )


def resolve_destroyed_transport_disembark_service(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    cargo_state: TransportCargoState,
    selection: DisembarkSelection,
    unit: UnitInstance,
    transport_placement: UnitPlacement,
    hazard_rolls: DestroyedTransportHazardRolls,
    battlefield_width_inches: float,
    battlefield_depth_inches: float,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
    objective_markers: tuple[ObjectiveMarker, ...],
) -> DestroyedTransportDisembark:
    if type(hazard_rolls) is not DestroyedTransportHazardRolls:
        raise GameLifecycleError(
            "Destroyed Transport disembark requires pre-placement hazard rolls."
        )
    if selection.disembark_mode not in {
        DisembarkModeKind.DESTROYED_TRANSPORT,
        DisembarkModeKind.EMERGENCY_DISEMBARK,
    }:
        raise GameLifecycleError(
            "Destroyed Transport disembark requires destroyed or emergency mode."
        )
    emergency = selection.disembark_mode is DisembarkModeKind.EMERGENCY_DISEMBARK
    if (
        hazard_rolls.player_id != selection.player_id
        or hazard_rolls.battle_round != selection.battle_round
        or hazard_rolls.unit_instance_id != selection.unit_instance_id
        or hazard_rolls.transport_unit_instance_id != selection.transport_unit_instance_id
        or hazard_rolls.disembark_mode is not selection.disembark_mode
    ):
        raise GameLifecycleError("Destroyed Transport hazard context drift.")
    placement = resolve_disembark_internal(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        cargo_state=cargo_state,
        selection=replace(
            selection,
            transport_movement_status=TransportMovementStatus.NOT_MOVED,
        ),
        unit=unit,
        transport_placement=transport_placement,
        require_started_phase_embarked=False,
        battlefield_width_inches=battlefield_width_inches,
        battlefield_depth_inches=battlefield_depth_inches,
        terrain_features=terrain_features,
        objective_markers=objective_markers,
    )
    expected_model_ids = {model.model_instance_id for model in unit.own_models}
    if any(not model.is_alive for model in unit.own_models):
        raise GameLifecycleError(
            "Destroyed Transport placement unit must contain only living survivors."
        )
    hazard_model_ids = set(hazard_rolls.model_instance_ids)
    if not expected_model_ids <= hazard_model_ids:
        raise GameLifecycleError("Destroyed Transport survivor snapshot drift.")
    placed_model_ids = {
        model_placement.model_instance_id
        for model_placement in selection.attempted_placement.model_placements
    }
    destroyed_model_ids = tuple(sorted(expected_model_ids - placed_model_ids)) if emergency else ()
    return DestroyedTransportDisembark(
        player_id=selection.player_id,
        battle_round=selection.battle_round,
        unit_instance_id=selection.unit_instance_id,
        transport_unit_instance_id=selection.transport_unit_instance_id,
        disembark_mode=selection.disembark_mode,
        placement=placement,
        roll_threshold=hazard_rolls.roll_threshold,
        model_rolls=hazard_rolls.model_rolls,
        mortal_wounds_per_failed_roll=hazard_rolls.mortal_wounds_per_failed_roll,
        destroyed_model_instance_ids=destroyed_model_ids,
        hazard_destroyed_model_instance_ids=tuple(sorted(hazard_model_ids - expected_model_ids)),
        source_rule_id=hazard_rolls.source_rule_id,
    )


def apply_transport_hazard_mortal_wounds_service(
    *,
    state: object,
    decisions: DecisionController,
    disembark: CombatDisembark | DestroyedTransportDisembark | DestroyedTransportHazardRolls,
    dice_manager: DiceRollManager,
) -> TransportHazardMortalWounds:
    from warhammer40k_core.engine.damage_allocation import (
        continue_mortal_wound_application,
    )
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.mortal_wound_application_progress import (
        start_hazardous_mortal_wound_application,
    )
    from warhammer40k_core.engine.mortal_wound_target_lineage import (
        MortalWoundTargetLineage,
    )

    if type(state) is not GameState:
        raise GameLifecycleError("Transport hazard mortal wounds require GameState.")
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Transport hazard mortal wounds require DecisionController.")
    if type(disembark) not in {
        CombatDisembark,
        DestroyedTransportDisembark,
        DestroyedTransportHazardRolls,
    }:
        raise GameLifecycleError(
            "Transport hazard mortal wounds require a transport hazard disembark."
        )
    if type(dice_manager) is not DiceRollManager:
        raise GameLifecycleError("Transport hazard mortal wounds require DiceRollManager.")
    if state.battle_round != disembark.battle_round:
        raise GameLifecycleError("Transport hazard mortal wounds battle_round drift.")
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Transport hazard mortal wounds require battlefield_state.")
    pre_placement = type(disembark) is DestroyedTransportHazardRolls
    target_lineage = None
    if pre_placement:
        hazard_rolls = cast(
            DestroyedTransportHazardRolls,
            disembark,
        )  # pyright: ignore[reportUnnecessaryCast]
        cargo_state = state.transport_cargo_state_for_transport(
            hazard_rolls.transport_unit_instance_id
        )
        if (
            cargo_state is None
            or cargo_state.player_id != hazard_rolls.player_id
            or not cargo_state.contains_unit(hazard_rolls.unit_instance_id)
        ):
            raise GameLifecycleError(
                "Pre-placement Transport hazard requires embarked cargo authority."
            )
        if any(
            battlefield.model_placement_or_none(model_id) is not None
            or model_id in set(battlefield.removed_model_ids)
            for model_id in hazard_rolls.model_instance_ids
        ):
            raise GameLifecycleError(
                "Pre-placement Transport hazard cargo must be living and unplaced."
            )
        target_lineage = MortalWoundTargetLineage.freeze_embarked(
            state=state,
            target_unit_instance_id=hazard_rolls.unit_instance_id,
            owner_player_id=hazard_rolls.player_id,
        )
        alive_models, _ = target_lineage.alive_models_for_policy(state=state)
        if tuple(model.model_instance_id for model in alive_models) != (
            hazard_rolls.model_instance_ids
        ):
            raise GameLifecycleError("Pre-placement Transport hazard cargo snapshot drift.")
    else:
        placed_disembark = cast(
            CombatDisembark | DestroyedTransportDisembark,
            disembark,
        )
        if not placed_disembark.placement.is_valid:
            raise GameLifecycleError(
                "Transport hazard mortal wounds require a valid disembark placement."
            )
        try:
            battlefield.unit_placement_by_id(placed_disembark.unit_instance_id)
        except PlacementError as exc:
            raise GameLifecycleError(
                "Transport hazard mortal wounds require the disembarked unit to be placed."
            ) from exc

    mortal_wounds = disembark.mortal_wound_count
    if mortal_wounds == 0:
        resolved = TransportHazardMortalWounds(
            source_rule_id=CORE_HAZARD_ROLLS_RULE_ID,
            source_kind=TRANSPORT_HAZARD_MORTAL_WOUNDS_SOURCE_KIND,
            disembark=disembark,
        )
        emit_transport_hazard_mortal_wounds_resolved(
            decisions=decisions,
            result=resolved,
        )
        return resolved

    progress = start_hazardous_mortal_wound_application(
        state=state,
        application_id=(
            f"{disembark.unit_instance_id}:{disembark_mode_for_hazard(disembark).value}:"
            f"transport-hazard-mortal-wounds:r{disembark.battle_round}"
        ),
        source_rule_id=CORE_HAZARD_ROLLS_RULE_ID,
        source_context=transport_hazard_source_context(
            disembark=disembark,
            mortal_wounds=mortal_wounds,
        ),
        target_unit_instance_id=disembark.unit_instance_id,
        destroying_player_id=disembark.player_id,
        mortal_wounds=mortal_wounds,
        source_step="transport_hazard_mortal_wounds",
        target_lineage=target_lineage,
    )
    routed = continue_mortal_wound_application(
        state=state,
        decisions=decisions,
        request_id=state.next_decision_request_id(),
        progress=progress,
        dice_manager=dice_manager,
        remove_destroyed_models=not pre_placement,
    )
    if routed.request is not None:
        decisions.request_decision(routed.request)
        return TransportHazardMortalWounds(
            source_rule_id=CORE_HAZARD_ROLLS_RULE_ID,
            source_kind=TRANSPORT_HAZARD_MORTAL_WOUNDS_SOURCE_KIND,
            disembark=disembark,
            pending_mortal_wound_request=routed.request,
        )
    if routed.application is None:
        raise GameLifecycleError("Transport hazard mortal wounds did not produce application.")
    resolved = TransportHazardMortalWounds(
        source_rule_id=CORE_HAZARD_ROLLS_RULE_ID,
        source_kind=TRANSPORT_HAZARD_MORTAL_WOUNDS_SOURCE_KIND,
        disembark=disembark,
        mortal_wound_application=routed.application,
    )
    emit_transport_hazard_mortal_wounds_resolved(
        decisions=decisions,
        result=resolved,
    )
    return resolved


def transport_hazard_disembark_from_source_context(
    source_context: JsonValue,
) -> CombatDisembark | DestroyedTransportDisembark | DestroyedTransportHazardRolls:
    if not isinstance(source_context, dict):
        raise GameLifecycleError("Transport hazard source context is invalid.")
    if source_context.get("source_kind") != TRANSPORT_HAZARD_MORTAL_WOUNDS_SOURCE_KIND:
        raise GameLifecycleError("Transport hazard source kind is invalid.")
    if source_context.get("source_rule_id") != CORE_HAZARD_ROLLS_RULE_ID:
        raise GameLifecycleError("Transport hazard source_rule_id is invalid.")
    mode = disembark_mode_kind_from_token(source_context.get("disembark_mode"))
    disembark_payload = source_context.get("disembark")
    if not isinstance(disembark_payload, dict):
        raise GameLifecycleError("Transport hazard disembark payload is invalid.")
    if mode is DisembarkModeKind.COMBAT_DISEMBARK:
        disembark: CombatDisembark | DestroyedTransportDisembark | DestroyedTransportHazardRolls = (
            CombatDisembark.from_payload(cast(CombatDisembarkPayload, disembark_payload))
        )
    elif mode in {
        DisembarkModeKind.DESTROYED_TRANSPORT,
        DisembarkModeKind.EMERGENCY_DISEMBARK,
    }:
        if "placement" in disembark_payload:
            disembark = DestroyedTransportDisembark.from_payload(
                cast(DestroyedTransportDisembarkPayload, disembark_payload)
            )
        else:
            disembark = DestroyedTransportHazardRolls.from_payload(
                cast(DestroyedTransportHazardRollsPayload, disembark_payload)
            )
    else:
        raise GameLifecycleError("Transport hazard source mode is invalid.")
    if source_context.get("player_id") != disembark.player_id:
        raise GameLifecycleError("Transport hazard source player drift.")
    if source_context.get("battle_round") != disembark.battle_round:
        raise GameLifecycleError("Transport hazard source battle_round drift.")
    if source_context.get("unit_instance_id") != disembark.unit_instance_id:
        raise GameLifecycleError("Transport hazard source unit drift.")
    if source_context.get("transport_unit_instance_id") != disembark.transport_unit_instance_id:
        raise GameLifecycleError("Transport hazard source transport drift.")
    if source_context.get("mortal_wounds") != disembark.mortal_wound_count:
        raise GameLifecycleError("Transport hazard source mortal wound drift.")
    return disembark
