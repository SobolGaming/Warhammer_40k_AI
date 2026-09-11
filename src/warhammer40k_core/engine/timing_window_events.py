from __future__ import annotations

from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.timing_windows import TimingWindow


def timing_window_boundary_state(
    *,
    decisions: DecisionController,
    window: TimingWindow,
    resolution_order: tuple[str, ...] = (),
) -> tuple[bool, bool]:
    """Validate a boundary occurrence by identity before trusting its disposition."""
    expected = validate_json_value(
        {"timing_window": window.to_payload(), "resolution_order": list(resolution_order)}
    )
    opened = False
    completed = False
    for event in decisions.event_log.records:
        if event.event_type not in ("timing_window_opened", "timing_window_resolved"):
            continue
        payload = event.payload
        if not isinstance(payload, dict) or not isinstance(payload.get("timing_window"), dict):
            raise GameLifecycleError("Timing window boundary requires a window object.")
        window_payload = payload["timing_window"]
        if not isinstance(window_payload, dict):
            raise GameLifecycleError("Timing window boundary requires a window object.")
        if window_payload.get("window_id") != window.window_id:
            continue
        if payload != expected:
            raise GameLifecycleError("Timing window boundary identity or ordering drifted.")
        if event.event_type == "timing_window_opened":
            if opened or completed:
                raise GameLifecycleError("Timing window boundary is duplicated or out of order.")
            opened = True
        else:
            if not opened or completed:
                raise GameLifecycleError("Timing window completion lacks its unique opening.")
            completed = True
    return opened, completed


def record_timing_window_boundary(
    *,
    decisions: DecisionController,
    window: TimingWindow,
    completed: bool,
    resolution_order: tuple[str, ...] = (),
) -> None:
    opened, resolved = timing_window_boundary_state(
        decisions=decisions, window=window, resolution_order=resolution_order
    )
    if resolved if completed else opened:
        return
    if completed:
        if decisions.queue.pending_requests:
            raise GameLifecycleError("Timing window cannot finish with a pending rule decision.")
        if not opened:
            raise GameLifecycleError("Timing window completion requires its opening event.")
    decisions.event_log.append(
        "timing_window_resolved" if completed else "timing_window_opened",
        {"timing_window": window.to_payload(), "resolution_order": list(resolution_order)},
    )
