from __future__ import annotations

# The movement phase's selection and mutation owners share these typed helpers.
# pyright: reportPrivateUsage=false
from collections import defaultdict
from dataclasses import replace
from functools import partial
from typing import cast

from warhammer40k_core.core.descriptor_hash import canonical_payload_sha256
from warhammer40k_core.engine.advance_hooks import (
    SELECT_MOVEMENT_ACTION_GRANT_DECISION_TYPE,
    AdvanceMoveContext,
    AdvanceMoveGrant,
    AdvanceMoveGrantPayload,
    AdvanceMoveHookRegistry,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.phases.movement_model import PendingMovementActionSelection
from warhammer40k_core.engine.sequencing import SequencingParticipant, SequencingRequirement
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate


def movement_grant_candidates(
    *,
    state: GameState,
    decisions: DecisionController,
    pending: PendingMovementActionSelection,
    registry: AdvanceMoveHookRegistry,
) -> tuple[TimingRuleCandidate, ...]:
    grants = registry.grants_for(
        AdvanceMoveContext(
            state=state,
            player_id=pending.player_id,
            battle_round=pending.battle_round,
            unit_instance_id=pending.unit_instance_id,
            movement_phase_action=pending.movement_phase_action.value,
            movement_request_id=pending.request_id,
            movement_result_id=pending.result_id,
            event_log=decisions.event_log,
        )
    )
    groups: dict[tuple[str, str], list[AdvanceMoveGrant]] = defaultdict(list)
    for grant in grants:
        # Alternative uses of one optional source (e.g. Agile Manoeuvres) remain
        # one rule's internal choice. Independent mandatory grants each resolve.
        groups[(grant.source_id, grant.hook_id if grant.automatic else "optional")].append(grant)
    completed = {
        cast(str, event.payload["timing_participant_id"])
        for event in decisions.event_log.records
        if event.event_type
        in ("advance_move_grants_auto_selected", "movement_action_grant_decision_resolved")
        and isinstance(event.payload, dict)
        and type(event.payload.get("timing_participant_id")) is str
    }
    candidates: list[TimingRuleCandidate] = []
    for (source_id, group_id), values in sorted(groups.items()):
        group = tuple(values)
        identity = "movement-grant:" + canonical_payload_sha256(
            {"action_result_id": pending.result_id, "source_id": source_id, "group_id": group_id}
        )
        if identity in completed:
            continue
        automatic = group[0].automatic
        template = None if automatic else _grant_request(state.game_id, pending, group, identity)
        candidates.append(
            TimingRuleCandidate(
                participant=SequencingParticipant(
                    participant_id=identity,
                    player_id=pending.player_id,
                    source_rule_id=source_id,
                    requirement=SequencingRequirement.MANDATORY
                    if automatic
                    else SequencingRequirement.OPTIONAL,
                    payload={
                        "movement_action_result_id": pending.result_id,
                        "grant_group_id": group_id,
                    },
                ),
                activate=partial(
                    _activate_grants,
                    state=state,
                    decisions=decisions,
                    pending=pending,
                    grants=group,
                    identity=identity,
                    template=template,
                ),
                request_template=template,
            )
        )
    return tuple(candidates)


def _grant_request(
    game_id: str,
    pending: PendingMovementActionSelection,
    grants: tuple[AdvanceMoveGrant, ...],
    identity: str,
) -> DecisionRequest:
    from warhammer40k_core.engine.phases.movement_action_decisions import (
        _advance_move_grant_option,
        _decline_advance_move_grant_option,
    )

    return DecisionRequest(
        request_id=identity,
        decision_type=SELECT_MOVEMENT_ACTION_GRANT_DECISION_TYPE,
        actor_id=pending.player_id,
        payload={
            "game_id": game_id,
            "battle_round": pending.battle_round,
            "phase": BattlePhase.MOVEMENT.value,
            "active_player_id": pending.player_id,
            "unit_instance_id": pending.unit_instance_id,
            "movement_phase_action": pending.movement_phase_action.value,
            "movement_mode": pending.movement_mode.value,
            "source_decision_request_id": pending.request_id,
            "source_decision_result_id": pending.result_id,
            "available_grants": validate_json_value([grant.to_payload() for grant in grants]),
            "timing_participant_id": identity,
        },
        options=(
            _decline_advance_move_grant_option(pending_action=pending),
            *(_advance_move_grant_option(pending_action=pending, grant=grant) for grant in grants),
        ),
    )


def _activate_grants(
    *,
    state: GameState,
    decisions: DecisionController,
    pending: PendingMovementActionSelection,
    grants: tuple[AdvanceMoveGrant, ...],
    identity: str,
    template: DecisionRequest | None,
) -> LifecycleStatus | None:
    if template is not None:
        request = replace(template, request_id=state.next_decision_request_id())
        decisions.request_decision(request)
        if not isinstance(request.payload, dict):
            raise GameLifecycleError("Movement grant request requires an object payload.")
        decisions.event_log.append(
            "advance_move_grant_decision_requested",
            {**request.payload, "request_id": request.request_id},
        )
        return LifecycleStatus.waiting_for_decision(
            stage=state.stage,
            decision_request=request,
            payload={"phase_body_status": "movement_action_grant_decision_pending"},
        )
    from warhammer40k_core.engine.phases.movement_action_decisions import (
        _record_movement_action_grant_effects,
    )

    effects = tuple(
        effect
        for grant in grants
        for effect in _record_movement_action_grant_effects(
            state=state,
            decisions=decisions,
            player_id=pending.player_id,
            unit_instance_id=pending.unit_instance_id,
            source_request_id=pending.request_id,
            source_result_id=pending.result_id,
            grant=grant,
        )
    )
    decisions.event_log.append(
        "advance_move_grants_auto_selected",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": pending.player_id,
            "phase": BattlePhase.MOVEMENT.value,
            "unit_instance_id": pending.unit_instance_id,
            "movement_phase_action": pending.movement_phase_action.value,
            "source_decision_request_id": pending.request_id,
            "source_decision_result_id": pending.result_id,
            "timing_participant_id": identity,
            "selected_grants": validate_json_value([grant.to_payload() for grant in grants]),
            "persisting_effects": validate_json_value([effect.to_payload() for effect in effects]),
        },
    )
    return None


def selected_movement_grants(
    decisions: DecisionController,
    pending: PendingMovementActionSelection,
) -> tuple[AdvanceMoveGrant, ...]:
    grants: list[AdvanceMoveGrant] = []
    for event in decisions.event_log.records:
        if event.event_type not in (
            "advance_move_grants_auto_selected",
            "movement_action_grant_decision_resolved",
        ):
            continue
        payload = event.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Movement grant resolution requires an object payload.")
        if payload.get("source_decision_result_id") != pending.result_id:
            continue
        raw_grants = payload.get("selected_grants")
        if not isinstance(raw_grants, list):
            raise GameLifecycleError("Movement grant resolution requires selected grants.")
        for raw in raw_grants:
            if not isinstance(raw, dict):
                raise GameLifecycleError("Movement grant resolution requires a typed grant.")
            grants.append(AdvanceMoveGrant.from_payload(cast(AdvanceMoveGrantPayload, raw)))
    if len({grant.hook_id for grant in grants}) != len(grants):
        raise GameLifecycleError("Movement grant resolved more than once for its action.")
    return tuple(grants)


def invalid_movement_grant_request(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    registry: AdvanceMoveHookRegistry,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.movement_start_sequencing import move_start_context
    from warhammer40k_core.engine.timing_request_candidates import (
        selected_timing_request_is_current,
    )

    movement = state.movement_phase_state
    if movement is None or movement.pending_action is None:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Movement grant lost its action.",
            payload={"invalid_reason": "movement_grant_source_request_drift"},
        )
    pending = movement.pending_action
    if selected_timing_request_is_current(
        decisions=decisions,
        context=move_start_context(state, pending),
        request=request,
        candidates=movement_grant_candidates(
            state=state, decisions=decisions, pending=pending, registry=registry
        ),
    ):
        return None
    return LifecycleStatus.invalid(
        stage=state.stage,
        message="Movement grant source request drifted.",
        payload={"invalid_reason": "movement_grant_source_request_drift"},
    )
