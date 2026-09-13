"""Shared 04.03.03 choice authority; action owners supply current legal target sets.

This module owns no geometry, dice, attack resolution or movement. Its closed
context binds a previously accepted selection to a current engine observation.
Only a fresh, matching DecisionResult can select replacement targets.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import msgspec

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.decision_request import DecisionError, DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_target_replacement_2026_09 as source_data,
)

TARGET_REPLACEMENT_SOURCE_ID = source_data.TARGET_REPLACEMENT_SOURCE_ID

SELECT_TARGET_REPLACEMENT_DECISION_TYPE = "select_target_replacement"
DECLINE_TARGET_REPLACEMENT_OPTION_ID = "decline_target_replacement"

_identifier = IdentifierValidator(GameLifecycleError)


def _identifiers(name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{name} must be a tuple.")
    validated = tuple(_identifier(name, value) for value in values)
    if len(set(validated)) != len(validated):
        raise GameLifecycleError(f"{name} contains duplicate identities.")
    return tuple(sorted(validated))


@dataclass(frozen=True, slots=True)
class TargetReplacementOption:
    option_id: str
    target_ids: tuple[str, ...]
    selection_payload: JsonValue = None
    label: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "option_id", _identifier("option_id", self.option_id))
        object.__setattr__(self, "target_ids", _identifiers("target_ids", self.target_ids))
        object.__setattr__(self, "selection_payload", validate_json_value(self.selection_payload))
        if self.label is not None and (type(self.label) is not str or not self.label.strip()):
            raise GameLifecycleError("Replacement label must be non-empty text.")
        if not self.target_ids or self.option_id == DECLINE_TARGET_REPLACEMENT_OPTION_ID:
            raise GameLifecycleError("A replacement option requires targets and a distinct ID.")


@dataclass(frozen=True, slots=True)
class TargetReplacementContext:
    action_id: str
    selection_id: str
    actor_id: str
    source_unit_instance_id: str
    original_target_ids: tuple[str, ...]
    invalid_target_ids: tuple[str, ...]
    source_context_hash: str
    options: tuple[TargetReplacementOption, ...]

    def __post_init__(self) -> None:
        for name in ("action_id", "selection_id", "actor_id", "source_unit_instance_id"):
            object.__setattr__(self, name, _identifier(name, getattr(self, name)))
        for name in ("original_target_ids", "invalid_target_ids"):
            object.__setattr__(self, name, _identifiers(name, getattr(self, name)))
        if not self.invalid_target_ids or not set(self.invalid_target_ids).issubset(
            self.original_target_ids
        ):
            raise GameLifecycleError("Replacement requires a previously selected invalid target.")
        digest = self.source_context_hash
        if (
            type(digest) is not str
            or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
        ):
            raise GameLifecycleError("Replacement context requires a SHA-256 commitment.")
        if type(self.options) is not tuple or any(
            type(option) is not TargetReplacementOption for option in self.options
        ):
            raise GameLifecycleError("Replacement options must be typed engine target sets.")
        if len({option.option_id for option in self.options}) != len(self.options):
            raise GameLifecycleError("Replacement option IDs must be unique.")
        if len(
            {
                (option.target_ids, canonical_json(option.selection_payload))
                for option in self.options
            }
        ) != len(self.options):
            raise GameLifecycleError("Replacement target sets must be unique.")
        if any(
            set(option.target_ids).intersection(self.invalid_target_ids) for option in self.options
        ):
            raise GameLifecycleError("Replacement options cannot retain an invalid target.")
        object.__setattr__(self, "options", tuple(sorted(self.options, key=lambda o: o.option_id)))

    def to_payload(self) -> dict[str, JsonValue]:
        return cast(
            dict[str, JsonValue],
            validate_json_value(
                {
                    "source_rule_id": TARGET_REPLACEMENT_SOURCE_ID,
                    "action_id": self.action_id,
                    "selection_id": self.selection_id,
                    "actor_id": self.actor_id,
                    "source_unit_instance_id": self.source_unit_instance_id,
                    "original_target_ids": list(self.original_target_ids),
                    "invalid_target_ids": list(self.invalid_target_ids),
                    "target_replacement_authority_sha256": self.source_context_hash,
                    "options": [
                        {
                            "option_id": o.option_id,
                            "target_ids": list(o.target_ids),
                            "selection_payload": o.selection_payload,
                            "label": o.label,
                        }
                        for o in self.options
                    ],
                }
            ),
        )

    @classmethod
    def from_payload(cls, payload: object) -> TargetReplacementContext:
        try:
            parsed = msgspec.convert(payload, type=_ContextPayload, strict=True)
        except msgspec.ValidationError as exc:
            raise GameLifecycleError("Target replacement context schema is invalid.") from exc
        if parsed.source_rule_id != TARGET_REPLACEMENT_SOURCE_ID:
            raise GameLifecycleError("Target replacement source identity drift.")
        return cls(
            action_id=parsed.action_id,
            selection_id=parsed.selection_id,
            actor_id=parsed.actor_id,
            source_unit_instance_id=parsed.source_unit_instance_id,
            original_target_ids=parsed.original_target_ids,
            invalid_target_ids=parsed.invalid_target_ids,
            source_context_hash=parsed.target_replacement_authority_sha256,
            options=tuple(
                TargetReplacementOption(
                    o.option_id, o.target_ids, validate_json_value(o.selection_payload), o.label
                )
                for o in parsed.options
            ),
        )


class _OptionPayload(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    option_id: str
    target_ids: tuple[str, ...]
    selection_payload: object
    label: str | None


class _ContextPayload(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    source_rule_id: str
    action_id: str
    selection_id: str
    actor_id: str
    source_unit_instance_id: str
    original_target_ids: tuple[str, ...]
    invalid_target_ids: tuple[str, ...]
    target_replacement_authority_sha256: str
    options: tuple[_OptionPayload, ...]


def replacement_request(*, request_id: str, context: TargetReplacementContext) -> DecisionRequest:
    payload = context.to_payload()
    return DecisionRequest(
        request_id=request_id,
        decision_type=SELECT_TARGET_REPLACEMENT_DECISION_TYPE,
        actor_id=context.actor_id,
        payload=payload,
        options=(
            *(
                DecisionOption(
                    option_id=o.option_id,
                    label=", ".join(o.target_ids) if o.label is None else o.label,
                    payload={
                        "context": payload,
                        "target_ids": list(o.target_ids),
                        "selection_payload": o.selection_payload,
                    },
                )
                for o in context.options
            ),
            DecisionOption(
                option_id=DECLINE_TARGET_REPLACEMENT_OPTION_ID,
                label="Decline replacement",
                payload={"context": payload, "target_ids": None},
            ),
        ),
    )


def replacement_selection(
    *,
    request: DecisionRequest,
    result: DecisionResult,
    current: TargetReplacementContext,
) -> tuple[str, ...] | None:
    expected = replacement_request(request_id=request.request_id, context=current)
    if expected != request:
        raise DecisionError("Target replacement request or current target context drift.")
    result.validate_for_request(expected)
    if result.selected_option_id == DECLINE_TARGET_REPLACEMENT_OPTION_ID:
        return None
    return next(o.target_ids for o in current.options if o.option_id == result.selected_option_id)
