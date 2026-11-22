"""Opt-in unit selection for the native Cavalcade opening."""

import json
from dataclasses import dataclass

from warhammer40k_core.ai.finite_candidates import FiniteCandidateSet
from warhammer40k_core.ai.player_policy import (
    CandidateExhaustedError,
    PlayerDecisionContext,
    PolicyAction,
    PolicyError,
    PolicyRegistration,
    PolicyRoute,
)
from warhammer40k_core.engine.phases.movement_model import (
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    MovementUnitLocationKind,
)

OPENING_MOVEMENT_UNIT_POLICY_ID = "opening-movement-unit-battlefield-size-v1"
_OPENING_ROUTE = PolicyRoute(
    "player-a", SELECT_MOVEMENT_UNIT_DECISION_TYPE, "battle", None, "movement", None
)


@dataclass(frozen=True, slots=True)
class OpeningMovementUnitPolicy:
    """Prefer the largest issued battlefield unit, keeping issued order on ties."""

    request_id: str

    def choose(self, context: PlayerDecisionContext) -> PolicyAction:
        view = context.observation
        request = context.request
        if (
            context.route != _OPENING_ROUTE
            or view["battle_round"] != 1
            or view["active_player_id"] != _OPENING_ROUTE.actor_id
            or request["request_id"] != self.request_id
        ):
            raise PolicyError("Opening Movement requires the bound Player A round-one request.")

        candidates = FiniteCandidateSet.from_context(context)
        selected_id: str | None = None
        largest = 0
        for candidate in candidates.candidates:
            option = candidate.option
            payload = option["payload"]
            if not isinstance(payload, dict) or payload.get("unit_location") not in tuple(
                MovementUnitLocationKind
            ):
                raise PolicyError("Opening Movement requires an issued unit location.")
            if payload["unit_location"] != MovementUnitLocationKind.BATTLEFIELD:
                continue
            models = payload.get("model_instance_ids")
            if not isinstance(models, list) or not models:
                raise PolicyError("Opening Movement requires the issued rules-unit model IDs.")
            if len(models) > largest:
                selected_id = option["option_id"]
                largest = len(models)
        if selected_id is None:
            raise CandidateExhaustedError("Opening Movement requires an issued battlefield unit.")
        return candidates.select(context, selected_id)


def opening_movement_unit_registration(request_id: str) -> PolicyRegistration:
    """Bind to the first actor-view request observed after both opening Shadow Forms."""
    if type(request_id) is not str or not request_id.strip():
        raise PolicyError("Opening Movement requires an issued viewer request ID.")
    return PolicyRegistration(
        _OPENING_ROUTE,
        OPENING_MOVEMENT_UNIT_POLICY_ID,
        json.dumps({"battle_round": 1, "request_id": request_id}),
        OpeningMovementUnitPolicy(request_id),
    )
