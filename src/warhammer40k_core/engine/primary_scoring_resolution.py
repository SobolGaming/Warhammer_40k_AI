from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from warhammer40k_core.core.missions import MissionScoringResolutionMode
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError

PrimaryScoringResolutionMode = MissionScoringResolutionMode


@dataclass(frozen=True, slots=True)
class PrimaryScoringResolutionCandidate:
    """One achieved source rule before card-level grammar is resolved."""

    rule_id: str
    amount: int
    resolution_mode: PrimaryScoringResolutionMode
    resolution_group_id: str | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "rule_id",
            _validate_identifier("Primary scoring resolution rule_id", self.rule_id),
        )
        if type(self.amount) is not int or self.amount < 1:
            raise GameLifecycleError(
                "Primary scoring resolution candidate amount must be a positive integer."
            )
        mode = primary_scoring_resolution_mode_from_token(self.resolution_mode)
        object.__setattr__(self, "resolution_mode", mode)
        group_id = _validate_optional_identifier(
            "Primary scoring resolution group_id",
            self.resolution_group_id,
        )
        if mode is PrimaryScoringResolutionMode.INDEPENDENT:
            if group_id is not None:
                raise GameLifecycleError(
                    "Independent Primary scoring resolution must not have a group ID."
                )
        elif group_id is None:
            raise GameLifecycleError("Grouped Primary scoring resolution requires a group ID.")
        object.__setattr__(self, "resolution_group_id", group_id)


@dataclass(frozen=True, slots=True)
class ResolvedPrimaryScoringCandidate:
    """A selected award candidate plus deterministic card-grammar audit evidence."""

    candidate: PrimaryScoringResolutionCandidate
    achieved_rule_ids: tuple[str, ...]
    selected_rule_ids: tuple[str, ...]
    suppressed_rule_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.candidate) is not PrimaryScoringResolutionCandidate:
            raise GameLifecycleError(
                "Resolved Primary scoring candidate requires a typed candidate."
            )
        achieved = _validate_identifier_tuple(
            "Resolved Primary scoring achieved_rule_ids",
            self.achieved_rule_ids,
            min_length=1,
        )
        selected = _validate_identifier_tuple(
            "Resolved Primary scoring selected_rule_ids",
            self.selected_rule_ids,
            min_length=1,
        )
        suppressed = _validate_identifier_tuple(
            "Resolved Primary scoring suppressed_rule_ids",
            self.suppressed_rule_ids,
        )
        if set(selected) | set(suppressed) != set(achieved):
            raise GameLifecycleError(
                "Resolved Primary scoring selected and suppressed rules must partition achieved "
                "rules."
            )
        if set(selected).intersection(suppressed):
            raise GameLifecycleError(
                "Resolved Primary scoring rules cannot be selected and suppressed."
            )
        if self.candidate.rule_id not in selected:
            raise GameLifecycleError("Resolved Primary scoring candidate must be a selected rule.")
        object.__setattr__(self, "achieved_rule_ids", achieved)
        object.__setattr__(self, "selected_rule_ids", selected)
        object.__setattr__(self, "suppressed_rule_ids", suppressed)

    def metadata(self) -> dict[str, JsonValue]:
        return {
            "primary_scoring_resolution_mode": self.candidate.resolution_mode.value,
            "primary_scoring_resolution_group_id": self.candidate.resolution_group_id,
            "primary_scoring_achieved_rule_ids": list(self.achieved_rule_ids),
            "primary_scoring_selected_rule_ids": list(self.selected_rule_ids),
            "primary_scoring_suppressed_rule_ids": list(self.suppressed_rule_ids),
        }


def resolve_primary_scoring_candidates(
    candidates: tuple[PrimaryScoringResolutionCandidate, ...],
) -> tuple[ResolvedPrimaryScoringCandidate, ...]:
    """Apply independent, cumulative, and exclusive-highest card grammar."""

    validated = _validate_candidates(candidates)
    groups: dict[str, list[PrimaryScoringResolutionCandidate]] = {}
    group_modes: dict[str, PrimaryScoringResolutionMode] = {}
    for candidate in validated:
        group_key = _candidate_group_key(candidate)
        groups.setdefault(group_key, []).append(candidate)
        if candidate.resolution_group_id is None:
            continue
        existing_mode = group_modes.get(candidate.resolution_group_id)
        if existing_mode is not None and existing_mode is not candidate.resolution_mode:
            raise GameLifecycleError(
                "Primary scoring resolution group must use one resolution mode."
            )
        group_modes[candidate.resolution_group_id] = candidate.resolution_mode

    resolved: list[ResolvedPrimaryScoringCandidate] = []
    for group_key in sorted(groups):
        group = tuple(sorted(groups[group_key], key=lambda candidate: candidate.rule_id))
        mode = group[0].resolution_mode
        achieved_rule_ids = tuple(candidate.rule_id for candidate in group)
        if mode in {
            PrimaryScoringResolutionMode.INDEPENDENT,
            PrimaryScoringResolutionMode.CUMULATIVE,
        }:
            selected = group
        elif mode is PrimaryScoringResolutionMode.EXCLUSIVE_HIGHEST:
            selected = (min(group, key=lambda candidate: (-candidate.amount, candidate.rule_id)),)
        else:
            raise GameLifecycleError("Unsupported Primary scoring resolution mode.")
        selected_rule_ids = tuple(candidate.rule_id for candidate in selected)
        suppressed_rule_ids = tuple(
            rule_id for rule_id in achieved_rule_ids if rule_id not in selected_rule_ids
        )
        resolved.extend(
            ResolvedPrimaryScoringCandidate(
                candidate=candidate,
                achieved_rule_ids=achieved_rule_ids,
                selected_rule_ids=selected_rule_ids,
                suppressed_rule_ids=suppressed_rule_ids,
            )
            for candidate in selected
        )
    return tuple(sorted(resolved, key=lambda result: result.candidate.rule_id))


def primary_scoring_resolution_mode_from_token(
    token: object,
) -> PrimaryScoringResolutionMode:
    if type(token) is PrimaryScoringResolutionMode:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Primary scoring resolution mode token must be a string.")
    try:
        return PrimaryScoringResolutionMode(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported Primary scoring resolution mode: {token}.") from exc


def _validate_candidates(
    values: object,
) -> tuple[PrimaryScoringResolutionCandidate, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("Primary scoring resolution candidates must be a tuple.")
    validated: list[PrimaryScoringResolutionCandidate] = []
    seen_rule_ids: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not PrimaryScoringResolutionCandidate:
            raise GameLifecycleError("Primary scoring resolution requires typed candidates.")
        if value.rule_id in seen_rule_ids:
            raise GameLifecycleError(
                "Primary scoring resolution candidates must not duplicate rule IDs."
            )
        seen_rule_ids.add(value.rule_id)
        validated.append(value)
    return tuple(validated)


def _candidate_group_key(candidate: PrimaryScoringResolutionCandidate) -> str:
    if candidate.resolution_mode is PrimaryScoringResolutionMode.INDEPENDENT:
        return f"independent:{candidate.rule_id}"
    if candidate.resolution_group_id is None:
        raise GameLifecycleError("Grouped Primary scoring resolution requires a group ID.")
    return f"group:{candidate.resolution_group_id}"


def _validate_identifier_tuple(
    field_name: str,
    values: object,
    *,
    min_length: int = 0,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        identifiers.append(identifier)
    if len(identifiers) < min_length:
        raise GameLifecycleError(f"{field_name} must contain at least {min_length} values.")
    return tuple(sorted(identifiers))


def _validate_optional_identifier(field_name: str, value: object) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


_validate_identifier = IdentifierValidator(GameLifecycleError)


__all__ = (
    "PrimaryScoringResolutionCandidate",
    "PrimaryScoringResolutionMode",
    "ResolvedPrimaryScoringCandidate",
    "primary_scoring_resolution_mode_from_token",
    "resolve_primary_scoring_candidates",
)
