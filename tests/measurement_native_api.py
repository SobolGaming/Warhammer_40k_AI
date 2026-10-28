"""Owner-approved native Shooting API dispatch only for exact-base benchmarks.

Ordinary fixtures keep the strict current native call. The measurement wrapper
sets an explicit role and native source root; both arms use these identical
fixture bytes and retain their independent source/dependency pre/post checks.
Only native method selection is cached, never gameplay results or payloads.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
from functools import cache
from inspect import Parameter, signature
from pathlib import Path
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.phases.shooting import ShootingPhaseState

if TYPE_CHECKING:
    from warhammer40k_core.engine.attack_sequence import AttackSequence
    from warhammer40k_core.engine.decision_request import DecisionRequest

_MODE = "WARHAMMER_BENCHMARK_SHOOTING_API"
_SOURCE = "WARHAMMER_BENCHMARK_NATIVE_SRC"
_NATIVE_PATH = "warhammer40k_core/engine/phases/shooting_model.py"
_NATIVE_SHA256 = {
    "base-5f509724": "a5c9e8d74aacd6df1088df91882f20499ef1a763f5581d72fd3d5b9cb49798b5",
    "head-current": "ae3c0e81bd916cde958aea22c7269e4846ada5fb4e2385b1760ac5f77d81ace2",
}


@cache
def _benchmark_method(role: str, source: str) -> Callable[..., ShootingPhaseState]:
    """Bind one declared native API once per process, outside payload work."""
    if role not in _NATIVE_SHA256 or not source:
        raise ValueError("Unknown benchmark Shooting API role or native source root.")
    root = Path(source).resolve(strict=True)
    path = (root / _NATIVE_PATH).resolve(strict=True)
    method = ShootingPhaseState.with_attack_sequence_update
    names: tuple[str, ...] = ("self", "attack_sequence", "allocated_model_ids_this_phase")
    if role == "head-current":
        names += ("pending_decision_requests",)
    parameters = tuple(signature(method).parameters.values())
    if (
        Path(method.__code__.co_filename).resolve(strict=True) != path
        or hashlib.sha256(path.read_bytes()).hexdigest() != _NATIVE_SHA256[role]
        or tuple(parameter.name for parameter in parameters) != names
        or parameters[0].kind is not Parameter.POSITIONAL_OR_KEYWORD
        or any(parameter.kind is not Parameter.KEYWORD_ONLY for parameter in parameters[1:])
        or any(parameter.default is not Parameter.empty for parameter in parameters)
    ):
        raise ValueError("Unknown benchmark native Shooting source or signature.")
    return cast("Callable[..., ShootingPhaseState]", method)


def benchmark_shooting_update(
    phase: ShootingPhaseState,
    *,
    attack_sequence: AttackSequence | None,
    allocated_model_ids_this_phase: tuple[str, ...],
    pending_decision_requests: tuple[DecisionRequest, ...],
) -> ShootingPhaseState:
    """Call the real selected native method once with its supported arguments."""
    role = os.environ.get(_MODE)
    if role is None:
        return phase.with_attack_sequence_update(
            attack_sequence=attack_sequence,
            allocated_model_ids_this_phase=allocated_model_ids_this_phase,
            pending_decision_requests=pending_decision_requests,
        )
    method = _benchmark_method(role, os.environ.get(_SOURCE, ""))
    if type(phase) is not ShootingPhaseState:
        raise ValueError("Benchmark Shooting state is not the selected native domain type.")
    if role == "base-5f509724":
        return method(
            phase,
            attack_sequence=attack_sequence,
            allocated_model_ids_this_phase=allocated_model_ids_this_phase,
        )
    return method(
        phase,
        attack_sequence=attack_sequence,
        allocated_model_ids_this_phase=allocated_model_ids_this_phase,
        pending_decision_requests=pending_decision_requests,
    )


# Public benchmark controls expose these exact existing objects, not new adapters.
benchmark_shooting_method = _benchmark_method
BENCHMARK_SHOOTING_API_ENV = _MODE
BENCHMARK_NATIVE_SRC_ENV = _SOURCE
