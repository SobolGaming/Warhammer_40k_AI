"""Live session binding for an observed pre-roll Charge declaration."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from warhammer40k_core.engine.event_log import canonical_json
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.phases.charge_modifier_ignore import (
    SELECT_CHARGING_UNIT_DECISION_TYPE,
)

if TYPE_CHECKING:
    from warhammer40k_core.adapters.access_control import ViewerContext
    from warhammer40k_core.adapters.battlefield_projection import (
        BattlefieldAuthoritativeEntitiesPayload,
    )
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.charge_phase_state import ChargingUnitSelection
    from warhammer40k_core.engine.phase import LifecycleStatus


def _observation_digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class _ObservedGroundCharge:
    selection: ChargingUnitSelection
    request_id: str
    option_id: str
    observation_hash: str
    battlefield_hash: str


@dataclass(slots=True)
class ChargeDeclarationSession:
    """Capture provenance alongside a native local session for the opt-in caller."""

    session: LocalGameSession
    _observed_ground_charge: _ObservedGroundCharge | None = field(
        default=None, init=False, repr=False, compare=False
    )

    def submit_observed_charge_declaration(
        self,
        *,
        viewer: ViewerContext,
        request_id: str,
        option_id: str,
        result_id: str,
        expected_observation_hash: str,
    ) -> LifecycleStatus | None:
        """Submit a Charge declaration and capture its live view; None means stale."""
        view = self.session.view_for_context(viewer=viewer)
        pending = view["pending_decision"]
        battlefield = view["battlefield_view"]
        observation_hash = _observation_digest(view)
        if (
            pending is None
            or battlefield is None
            or pending["request_id"] != request_id
            or pending["decision_type"] != SELECT_CHARGING_UNIT_DECISION_TYPE
            or observation_hash != expected_observation_hash
        ):
            return None

        status = self.session.submit_viewer_option(
            viewer=viewer, request_id=request_id, option_id=option_id, result_id=result_id
        )
        state = self.session.lifecycle.state
        phase = None if state is None else state.charge_phase_state
        selection = None if phase is None else phase.active_selection
        if (
            status.status_kind is not LifecycleStatusKind.INVALID
            and selection is not None
            and not selection.take_to_the_skies
        ):
            self._observed_ground_charge = _ObservedGroundCharge(
                selection,
                request_id,
                option_id,
                observation_hash,
                _observation_digest(battlefield["authoritative"]),
            )
        return status

    def matches_observed_ground_charge(
        self,
        *,
        viewer: ViewerContext,
        request_id: str,
        option_id: str,
        observation_hash: str,
        battlefield: BattlefieldAuthoritativeEntitiesPayload,
    ) -> bool:
        """Check the session's accepted origin against the currently active selection."""
        origin = self._observed_ground_charge
        state = self.session.lifecycle.state
        phase = None if state is None else state.charge_phase_state
        return (
            origin is not None
            and phase is not None
            and origin.selection is phase.active_selection
            and viewer.policy.may_submit_decision
            and origin.selection.player_id == viewer.viewer_player_id
            and origin.request_id == request_id
            and origin.option_id == option_id
            and origin.observation_hash == observation_hash
            and origin.battlefield_hash == _observation_digest(battlefield)
        )
