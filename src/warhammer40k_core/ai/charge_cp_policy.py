"""Opt-in resource choice for an already fixed Charge across a certified Dense wall."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.ai.charge_flight_admission import (
    ChargeFlightRollBound,
    ChargeFlightUnresolved,
    ChargeFlightUnresolvedReason,
    ProvenChargeFlightAdvantage,
    choose_proven_charge_flight_mode,
)
from warhammer40k_core.ai.player_policy import PolicyError, PolicyRoute, payload_digest
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.charge_move_resolution import resolve_charge_move
from warhammer40k_core.engine.charge_movement_source import charge_movement_placement
from warhammer40k_core.engine.effects import generic_rule_persisting_effect
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.phases.charge import charge_move_violation_code
from warhammer40k_core.engine.phases.charge_modifier_ignore import (
    SELECT_CHARGING_UNIT_DECISION_TYPE,
)
from warhammer40k_core.engine.rule_duration_execution import expiration_for_clause_effect
from warhammer40k_core.engine.rule_execution import (
    RuleExecutionContext,
    generic_rule_effect_payload,
    scoped_rule_ir_from_execution_payload,
)
from warhammer40k_core.engine.stratagems_model import (
    STRATAGEM_DECISION_TYPE,
    StratagemCatalogIndex,
    StratagemEligibilityContext,
)
from warhammer40k_core.engine.stratagems_requests import (
    POST_ROLL_MOVEMENT_ACTION_KEY,
    post_roll_movement_stratagem_records,
    stratagem_use_options_from_index,
    stratagem_window_context_from_request,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.rules.rule_ir import RuleEffectKind
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_blood_legion_ir_support_2026_27 import (  # noqa: E501
    GORE_HUNGRY_ONSLAUGHT_SOURCE_ID,
    GORE_HUNGRY_ONSLAUGHT_STRATAGEM_ID,
)

if TYPE_CHECKING:
    from warhammer40k_core.adapters.battlefield_projection import (
        BattlefieldAuthoritativeEntitiesPayload,
    )
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.ai.player_policy import PlayerDecisionContext, PolicyAction
    from warhammer40k_core.engine.decision_request import DecisionOption
    from warhammer40k_core.engine.effects import PersistingEffect
    from warhammer40k_core.engine.event_log import JsonValue
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.phase import LifecycleStatus
    from warhammer40k_core.engine.phases.charge import ChargePhaseHandler
    from warhammer40k_core.engine.stratagems_model import StratagemDefinition
    from warhammer40k_core.geometry.pathing import PathWitness


_ONSLAUGHT_CP_COST = 1


@dataclass(frozen=True, slots=True)
class DenseWallChargeChoice:
    game_id: str
    no_spend: ProvenChargeFlightAdvantage
    declaration: PolicyAction
    # These rolls complete and each costs 1 CP only if the native offer is used.
    conditional_ground: ChargeFlightRollBound | None


def choose_dense_wall_charge(
    session: LocalGameSession,
    context: PlayerDecisionContext,
    *,
    unit_id: str,
    target_id: str,
    witness: PathWitness,
    allow_late_onslaught: bool = False,
) -> DenseWallChargeChoice | ChargeFlightUnresolved:
    """Return a read-only mode choice on the caller's fixed unit, target and witness."""
    if type(allow_late_onslaught) is not bool:
        raise PolicyError("allow_late_onslaught requires a Boolean.")
    proof = choose_proven_charge_flight_mode(
        session, context, unit_id=unit_id, target_id=target_id, witness=witness
    )
    if isinstance(proof, ChargeFlightUnresolved):
        return proof
    state = session.lifecycle.state
    if not isinstance(proof, ProvenChargeFlightAdvantage) or state is None:
        return ChargeFlightUnresolved(ChargeFlightUnresolvedReason.UNSUPPORTED_PROOF_CONTEXT)

    save = DenseWallChargeChoice(state.game_id, proof, proof.action, None)
    if not allow_late_onslaught:
        return save

    actor = context.route.actor_id
    handler = session.lifecycle._charge_phase_handler  # pyright: ignore[reportPrivateUsage]
    eligibility = StratagemEligibilityContext.from_state(
        state=state, player_id=actor, trigger_kind=TimingTriggerKind.DURING_PHASE
    )
    # An eligibility query at declaration is only a current affordability and
    # eligibility check. The actual late window must come from the engine.
    onslaught = _eligible_onslaught(state, handler, eligibility, unit_id)
    ruleset = handler.ruleset_descriptor
    if onslaught is None or ruleset is None:
        return save
    _, definition = onslaught
    effect = _conditional_grant(eligibility, definition, unit_id)
    if effect is None:
        return save

    scenario = battlefield_scenario_for_state(state=state)
    placement = charge_movement_placement(scenario=scenario, unit_instance_id=unit_id)
    abilities = handler.ability_index_for_player(actor)
    reachable = tuple(
        roll for roll in range(2, 13) if roll >= proof.offer.target_filter_distance_inches
    )
    # Compare against the native target-filter ceiling for flight, as well as
    # retaining the original no-spend certificate. Prefer keeping CP on ties.
    if not any(
        roll - proof.offer.flight_penalty_inches < proof.offer.target_filter_distance_inches
        for roll in reachable
    ):
        return save

    def violation(budget: int, effects: tuple[PersistingEffect, ...]) -> str | None:
        result = resolve_charge_move(
            scenario=scenario,
            ruleset_descriptor=ruleset,
            unit_placement=placement,
            selected_target_unit_instance_ids=(target_id,),
            maximum_distance_inches=budget,
            path_witness=witness,
            unit_persisting_effects=effects,
            ability_index=abilities,
        )
        return charge_move_violation_code(
            resolution=result, ruleset_descriptor=ruleset, maximum_distance_inches=budget
        )

    # Spend only if this witness needs transit and works with the grant at
    # every budget that can open the window. Other ground paths are unsearched.
    if any(
        violation(roll, (effect,)) is not None
        or (roll in proof.ground_upper_bound.rolls and violation(roll, ()) is None)
        for roll in reachable
    ):
        return save

    if payload_digest(session.view_for_context(viewer=ViewerContext.for_player(actor))) != (
        context.observation_hash
    ):
        return ChargeFlightUnresolved(ChargeFlightUnresolvedReason.OBSERVATION_DRIFT)
    paid = ChargeFlightRollBound(reachable, sum(6 - abs(7 - roll) for roll in reachable))
    return DenseWallChargeChoice(
        state.game_id, proof, context.select_option(proof.offer.ground_option_id), paid
    )


def submit_dense_wall_charge(
    session: LocalGameSession, *, choice: DenseWallChargeChoice
) -> LifecycleStatus:
    """Submit the issued mode while the exact qualifying player observation is current."""
    action = choice.declaration
    viewer = ViewerContext.for_player(action.actor_id)
    view = session.view_for_context(viewer=viewer)
    battlefield = view["battlefield_view"]
    if (
        battlefield is None
        or action.option_id is None
        or payload_digest(view) != action.observation_hash
    ):
        raise PolicyError("Dense-wall Charge declaration no longer matches its observation.")
    return session.submit_viewer_option(
        viewer=viewer,
        request_id=action.request_id,
        option_id=action.option_id,
        result_id=_declaration_result_id(choice, battlefield["authoritative"]),
    )


def _declaration_result_id(
    choice: DenseWallChargeChoice, battlefield: BattlefieldAuthoritativeEntitiesPayload
) -> str:
    action = choice.declaration
    return "dense-wall-charge:" + payload_digest(
        [
            choice.game_id,
            action.actor_id,
            action.request_id,
            action.observation_hash,
            action.option_id,
            choice.no_spend.offer.target_id,
            choice.no_spend.witness_sha256,
            battlefield,
        ]
    )


def _recorded_ground_declaration(
    session: LocalGameSession,
    viewer: ViewerContext,
    action: PolicyAction,
    result_id: JsonValue,
) -> bool:
    events = session.events_since_for_context(EventStreamCursor(), viewer=viewer)["events"]
    for event in reversed(events):
        if event["event_type"] != "decision_recorded":
            continue
        payload = event["payload"]
        if not isinstance(payload, dict):
            continue
        result = payload.get("result")
        if isinstance(result, dict) and result.get("request_id") == action.request_id:
            return (
                result.get("result_id") == result_id
                and result.get("actor_id") == action.actor_id
                and result.get("decision_type") == SELECT_CHARGING_UNIT_DECISION_TYPE
                and result.get("selected_option_id") == action.option_id
            )
    return False


def select_late_onslaught(
    session: LocalGameSession, context: PlayerDecisionContext, *, choice: DenseWallChargeChoice
) -> PolicyAction | None:
    """Select the live 1 CP option for this ground declaration when the engine issues it."""
    declaration = choice.declaration
    actor = declaration.actor_id
    offer = choice.no_spend.offer
    if (
        choice.conditional_ground is None
        or declaration.request_id != offer.request_id
        or declaration.observation_hash != offer.observation_hash
        or declaration.option_id != offer.ground_option_id
        or context.route
        != PolicyRoute(actor, STRATAGEM_DECISION_TYPE, "battle", None, "charge", None)
    ):
        return None
    lifecycle = session.lifecycle
    viewer = ViewerContext.for_player(actor)
    state = lifecycle.state
    request = lifecycle.pending_decision_request()
    if (
        state is None
        or state.game_id != choice.game_id
        or request is None
        or request.decision_type != STRATAGEM_DECISION_TYPE
        or request.actor_id != actor
    ):
        return None
    view = session.view_for_context(viewer=viewer)
    battlefield = view["battlefield_view"]
    if battlefield is None or payload_digest(view) != context.observation_hash:
        return None

    phase = state.charge_phase_state
    if phase is None or phase.interruption is not None:
        return None
    selection = phase.active_selection
    distance = phase.move_pending_distance_state()
    # Compare the declaration through the existing viewer identity mapping.
    identities = session._viewer_history_identities(  # pyright: ignore[reportPrivateUsage]
        viewer=viewer
    )
    if (
        selection is None
        or selection.player_id != actor
        or identities.project(selection.request_id, key="request_id") != offer.request_id
        or selection.unit_instance_id != offer.unit_id
        or selection.take_to_the_skies
        or distance is None
        or offer.target_id not in distance.roll_result.reachable_target_distances_inches
    ):
        return None
    # Result aliases are local to the viewer. Match the native accepted result
    # against the commitment from the exact pre-roll view and unchanged board.
    result_id = identities.project(
        _declaration_result_id(choice, battlefield["authoritative"]), key="result_id"
    )
    if not _recorded_ground_declaration(session, viewer, declaration, result_id):
        return None

    eligibility = stratagem_window_context_from_request(request)
    action_id = distance.roll_result.request.request_id
    if (
        eligibility.timing_window_id != f"charge-post-roll:{action_id}"
        or eligibility.trigger_payload != {POST_ROLL_MOVEMENT_ACTION_KEY: action_id}
    ):
        return None

    handler = lifecycle._charge_phase_handler  # pyright: ignore[reportPrivateUsage]
    onslaught = _eligible_onslaught(state, handler, eligibility, offer.unit_id)
    if onslaught is None or onslaught[0] not in request.options:
        return None
    option, _ = onslaught
    option_id = identities.project(option.option_id, key="option_id")
    if not isinstance(option_id, str) or not any(
        row["option_id"] == option_id for row in context.request["options"]
    ):
        return None
    return context.select_option(option_id)


def _eligible_onslaught(
    state: GameState,
    handler: ChargePhaseHandler,
    context: StratagemEligibilityContext,
    unit_id: str,
) -> tuple[DecisionOption, StratagemDefinition] | None:
    if handler.stratagem_cost_modifier_registry.bindings:
        return None
    records = tuple(
        record
        for record in post_roll_movement_stratagem_records(
            handler.stratagem_index, BattlePhase.CHARGE
        )
        if record.definition.stratagem_id == GORE_HUNGRY_ONSLAUGHT_STRATAGEM_ID
        and record.definition.source_id == GORE_HUNGRY_ONSLAUGHT_SOURCE_ID
        and record.definition.command_point_cost == _ONSLAUGHT_CP_COST
    )
    if len(records) != 1:
        return None
    options = stratagem_use_options_from_index(
        state=state, index=StratagemCatalogIndex.from_records(records), context=context
    )
    matches: list[DecisionOption] = []
    for option in options:
        payload = option.payload
        if (
            isinstance(payload, dict)
            and isinstance(binding := payload.get("target_binding"), dict)
            and binding.get("target_unit_instance_id") == unit_id
        ):
            matches.append(option)
    return (matches[0], records[0].definition) if len(matches) == 1 else None


def _conditional_grant(
    eligibility: StratagemEligibilityContext, definition: StratagemDefinition, unit_id: str
) -> PersistingEffect | None:
    rule_ir = scoped_rule_ir_from_execution_payload(definition.effect_payload)
    if (
        not rule_ir.is_supported
        or rule_ir.source_id != GORE_HUNGRY_ONSLAUGHT_SOURCE_ID
        or len(rule_ir.clauses) != 1
    ):
        return None
    (clause,) = rule_ir.clauses
    if (
        clause.conditions
        or len(clause.effects) != 1
        or clause.effects[0].kind is not RuleEffectKind.MOVEMENT_TRANSIT_PERMISSION
    ):
        return None
    (effect,) = clause.effects
    context = RuleExecutionContext(
        game_id=eligibility.game_id,
        player_id=eligibility.player_id,
        battle_round=eligibility.battle_round,
        phase=eligibility.phase,
        active_player_id=eligibility.active_player_id,
        source_unit_instance_id=unit_id,
        target_unit_instance_ids=(unit_id,),
        target_player_id=eligibility.player_id,
    )
    expiration = expiration_for_clause_effect(clause=clause, effect=effect, context=context)
    if expiration is None:
        return None
    # This value is only an input to the pure native movement validator.
    return generic_rule_persisting_effect(
        effect_id="conditional-charge-terrain-transit",
        source_rule_id=rule_ir.source_id,
        owner_player_id=context.player_id,
        target_unit_instance_ids=(unit_id,),
        started_battle_round=context.battle_round,
        started_phase=context.phase,
        expiration=expiration,
        effect_payload=generic_rule_effect_payload(
            rule_ir=rule_ir, clause=clause, effect=effect, context=context
        ),
    )
