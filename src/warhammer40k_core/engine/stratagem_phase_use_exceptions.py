from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.stratagems import (
        StratagemDefinition,
        StratagemEligibilityContext,
        StratagemTargetBinding,
        StratagemUseRecord,
    )


PHASE_USE_EXCEPTION_PAYLOAD_KEY = "stratagem_phase_use_exception"
PHASE_PER_UNIT_FREQUENCY_SCOPE = "phase_per_unit"
PHASE_USE_EXCEPTION_FREQUENCY_VIOLATION = "source_ability_once_per_phase_per_unit"


@dataclass(frozen=True, slots=True)
class StratagemPhaseUseException:
    source_ability_id: str
    source_id: str
    eligible_datasheet_ids: tuple[str, ...]
    frequency_scope: str = PHASE_PER_UNIT_FREQUENCY_SCOPE
    bypass_same_stratagem_per_phase: bool = True
    does_not_block_other_units: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_ability_id",
            _validate_identifier("source_ability_id", self.source_ability_id),
        )
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        object.__setattr__(
            self,
            "eligible_datasheet_ids",
            _validate_identifier_tuple("eligible_datasheet_ids", self.eligible_datasheet_ids),
        )
        if not self.eligible_datasheet_ids:
            raise GameLifecycleError(
                "Stratagem phase-use exception requires eligible datasheet IDs."
            )
        if self.frequency_scope != PHASE_PER_UNIT_FREQUENCY_SCOPE:
            raise GameLifecycleError(
                "Stratagem phase-use exception frequency scope is unsupported."
            )
        if self.bypass_same_stratagem_per_phase is not True:
            raise GameLifecycleError(
                "Stratagem phase-use exception must bypass the same-phase restriction."
            )
        if self.does_not_block_other_units is not True:
            raise GameLifecycleError(
                "Stratagem phase-use exception must not block uses on other units."
            )

    def to_payload(self) -> JsonValue:
        return validate_json_value(
            {
                "source_ability_id": self.source_ability_id,
                "source_id": self.source_id,
                "eligible_datasheet_ids": list(self.eligible_datasheet_ids),
                "frequency_scope": self.frequency_scope,
                "bypass_same_stratagem_per_phase": self.bypass_same_stratagem_per_phase,
                "does_not_block_other_units": self.does_not_block_other_units,
            }
        )

    @classmethod
    def from_payload(cls, payload: JsonValue) -> StratagemPhaseUseException:
        if not isinstance(payload, dict):
            raise GameLifecycleError("Stratagem phase-use exception payload must be an object.")
        source_ability_id = payload.get("source_ability_id")
        source_id = payload.get("source_id")
        eligible_datasheet_ids = payload.get("eligible_datasheet_ids")
        frequency_scope = payload.get("frequency_scope")
        bypass_same_phase = payload.get("bypass_same_stratagem_per_phase")
        does_not_block = payload.get("does_not_block_other_units")
        if (
            type(source_ability_id) is not str
            or type(source_id) is not str
            or not isinstance(eligible_datasheet_ids, list)
            or type(frequency_scope) is not str
            or type(bypass_same_phase) is not bool
            or type(does_not_block) is not bool
        ):
            raise GameLifecycleError("Stratagem phase-use exception payload is malformed.")
        return cls(
            source_ability_id=source_ability_id,
            source_id=source_id,
            eligible_datasheet_ids=tuple(
                _validate_identifier("eligible_datasheet_ids entry", value)
                for value in cast(list[object], eligible_datasheet_ids)
            ),
            frequency_scope=frequency_scope,
            bypass_same_stratagem_per_phase=bypass_same_phase,
            does_not_block_other_units=does_not_block,
        )


def phase_use_exception_effect_payload(
    *,
    source_ability_id: str,
    source_id: str,
    eligible_datasheet_ids: tuple[str, ...],
) -> JsonValue:
    descriptor = StratagemPhaseUseException(
        source_ability_id=source_ability_id,
        source_id=source_id,
        eligible_datasheet_ids=eligible_datasheet_ids,
    )
    return validate_json_value({PHASE_USE_EXCEPTION_PAYLOAD_KEY: descriptor.to_payload()})


def stratagem_phase_use_exception(
    definition: StratagemDefinition,
) -> StratagemPhaseUseException | None:
    payload = definition.effect_payload
    if not isinstance(payload, dict) or PHASE_USE_EXCEPTION_PAYLOAD_KEY not in payload:
        return None
    return StratagemPhaseUseException.from_payload(payload[PHASE_USE_EXCEPTION_PAYLOAD_KEY])


def phase_use_exception_restriction_violation(
    *,
    state: GameState,
    player_id: str,
    definition: StratagemDefinition,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding | None,
    previous_uses: tuple[StratagemUseRecord, ...],
) -> str | None:
    same_phase_uses = tuple(
        use
        for use in previous_uses
        if use.stratagem_id == definition.stratagem_id
        and use.battle_round == context.battle_round
        and use.phase is context.phase
        and use.active_player_id == context.active_player_id
    )
    if not same_phase_uses:
        return None
    exception = stratagem_phase_use_exception(definition)
    if exception is None:
        return "same_stratagem_per_phase"
    if target_binding is None and _player_has_exception_unit(
        state=state,
        player_id=player_id,
        exception=exception,
    ):
        # A parameterized request may still contain an eligible exception target.
        # Defer the restriction to target-specific proposal validation.
        return None
    current_target_id = _target_unit_id(target_binding)
    current_is_exception = _unit_uses_exception(
        state=state,
        unit_instance_id=current_target_id,
        exception=exception,
    )
    if current_is_exception:
        if any(
            use.target_binding.target_unit_instance_id == current_target_id
            for use in same_phase_uses
        ):
            return PHASE_USE_EXCEPTION_FREQUENCY_VIOLATION
        return None
    if any(
        not _unit_uses_exception(
            state=state,
            unit_instance_id=use.target_binding.target_unit_instance_id,
            exception=exception,
        )
        for use in same_phase_uses
    ):
        return "same_stratagem_per_phase"
    return None


def _player_has_exception_unit(
    *,
    state: GameState,
    player_id: str,
    exception: StratagemPhaseUseException,
) -> bool:
    return any(
        unit.datasheet_id in exception.eligible_datasheet_ids
        for army in state.army_definitions
        if army.player_id == player_id
        for unit in army.units
    )


def _unit_uses_exception(
    *,
    state: GameState,
    unit_instance_id: str | None,
    exception: StratagemPhaseUseException,
) -> bool:
    if unit_instance_id is None:
        return False
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == unit_instance_id:
                return unit.datasheet_id in exception.eligible_datasheet_ids
    return False


def _target_unit_id(target_binding: StratagemTargetBinding | None) -> str | None:
    if target_binding is None:
        return None
    return target_binding.target_unit_instance_id


def _validate_identifier_tuple(field_name: str, value: object) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(f"Stratagem phase-use exception {field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for item in cast(tuple[object, ...], value):
        identifier = _validate_identifier(f"{field_name} entry", item)
        if identifier in seen:
            raise GameLifecycleError(f"Stratagem phase-use exception {field_name} must be unique.")
        seen.add(identifier)
        identifiers.append(identifier)
    return tuple(identifiers)


_validate_identifier = IdentifierValidator(GameLifecycleError)
