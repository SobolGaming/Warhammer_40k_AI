"""Translate numerical admission failures at the engine's public boundary."""

from __future__ import annotations

from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.geometry.numerical_identity import NumericalIdentity
from warhammer40k_core.geometry.numerical_identity import (
    validate_numerical_identity as validate_geometry_identity,
)
from warhammer40k_core.geometry.pose import GeometryError


def numerical_identity_from_payload(payload: object) -> NumericalIdentity:
    try:
        return NumericalIdentity.from_payload(payload)
    except GeometryError as exc:
        raise GameLifecycleError(str(exc)) from exc


def validate_numerical_identity(value: object) -> NumericalIdentity:
    try:
        return validate_geometry_identity(value)
    except GeometryError as exc:
        raise GameLifecycleError(str(exc)) from exc
