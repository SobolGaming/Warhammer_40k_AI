from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from itertools import combinations
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.catalog_modifier_ignore import (
    CatalogModifierIgnorePermission,
    ModifierIgnoreKind,
)
from warhammer40k_core.engine.decision_request import DecisionOption
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


MODIFIER_IGNORE_CONTEXT_KEY = "modifier_ignore_context"
MODIFIER_IGNORE_SELECTION_EFFECT_KIND = "modifier_ignore_selection"
_MAX_ENUMERATED_MODIFIERS = 10


@dataclass(frozen=True, slots=True)
class ModifierIgnoreSnapshot:
    kind: ModifierIgnoreKind
    modifier_id: str
    source_id: str | None
    model_instance_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", _modifier_ignore_kind(self.kind))
        object.__setattr__(
            self,
            "modifier_id",
            _validate_identifier("modifier-ignore modifier_id", self.modifier_id),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_optional_identifier("modifier-ignore source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_optional_identifier(
                "modifier-ignore model_instance_id",
                self.model_instance_id,
            ),
        )
        if (
            self.kind is ModifierIgnoreKind.MOVEMENT_CHARACTERISTIC
            and self.model_instance_id is None
        ):
            raise GameLifecycleError(
                "Movement-characteristic modifier snapshots require model_instance_id."
            )
        if (
            self.kind is not ModifierIgnoreKind.MOVEMENT_CHARACTERISTIC
            and self.model_instance_id is not None
        ):
            raise GameLifecycleError("Roll modifier snapshots must not carry model_instance_id.")

    @classmethod
    def for_roll_modifier(
        cls,
        *,
        kind: ModifierIgnoreKind,
        modifier: RollModifier,
    ) -> ModifierIgnoreSnapshot:
        if kind not in {ModifierIgnoreKind.ADVANCE_ROLL, ModifierIgnoreKind.CHARGE_ROLL}:
            raise GameLifecycleError("Roll modifier snapshot requires a roll modifier kind.")
        if type(modifier) is not RollModifier:
            raise GameLifecycleError("Roll modifier snapshot requires RollModifier.")
        return cls(
            kind=kind,
            modifier_id=modifier.modifier_id,
            source_id=modifier.source_id,
        )

    def identity(self) -> tuple[str, str, str]:
        return (self.kind.value, self.model_instance_id or "", self.modifier_id)

    def to_payload(self) -> dict[str, JsonValue]:
        return {
            "kind": self.kind.value,
            "modifier_id": self.modifier_id,
            "source_id": self.source_id,
            "model_instance_id": self.model_instance_id,
        }

    @classmethod
    def from_payload(cls, payload: object) -> ModifierIgnoreSnapshot:
        if not isinstance(payload, dict):
            raise GameLifecycleError("Modifier-ignore snapshot payload must be an object.")
        mapped_payload = cast(dict[str, object], payload)
        if set(mapped_payload) != {"kind", "modifier_id", "source_id", "model_instance_id"}:
            raise GameLifecycleError("Modifier-ignore snapshot payload fields drifted.")
        return cls(
            kind=_modifier_ignore_kind(_required_string(mapped_payload, "kind")),
            modifier_id=_required_string(mapped_payload, "modifier_id"),
            source_id=_optional_string(mapped_payload, "source_id"),
            model_instance_id=_optional_string(mapped_payload, "model_instance_id"),
        )


def options_with_modifier_ignore_choices(
    *,
    option: DecisionOption,
    unit_instance_id: str,
    permissions: tuple[CatalogModifierIgnorePermission, ...],
    available_modifiers: tuple[ModifierIgnoreSnapshot, ...],
) -> tuple[DecisionOption, ...]:
    if type(option) is not DecisionOption:
        raise GameLifecycleError("Modifier-ignore expansion requires DecisionOption.")
    unit_id = _validate_identifier("modifier-ignore unit_instance_id", unit_instance_id)
    if type(permissions) is not tuple or any(
        type(permission) is not CatalogModifierIgnorePermission for permission in permissions
    ):
        raise GameLifecycleError("Modifier-ignore expansion requires typed permissions.")
    if type(available_modifiers) is not tuple or any(
        type(snapshot) is not ModifierIgnoreSnapshot for snapshot in available_modifiers
    ):
        raise GameLifecycleError("Modifier-ignore expansion requires typed modifier snapshots.")
    permitted_kinds = {kind for permission in permissions for kind in permission.modifier_kinds}
    snapshots = tuple(
        sorted(
            (snapshot for snapshot in available_modifiers if snapshot.kind in permitted_kinds),
            key=ModifierIgnoreSnapshot.identity,
        )
    )
    identities = tuple(snapshot.identity() for snapshot in snapshots)
    if len(set(identities)) != len(identities):
        raise GameLifecycleError("Modifier-ignore snapshot identities must be unique.")
    if not snapshots:
        return (option,)
    if len(snapshots) > _MAX_ENUMERATED_MODIFIERS:
        raise GameLifecycleError("Modifier-ignore choice exceeds the finite enumeration limit.")
    if not isinstance(option.payload, dict):
        raise GameLifecycleError("Modifier-ignore option payload must be an object.")
    expanded: list[DecisionOption] = []
    for ignored_count in range(len(snapshots) + 1):
        for ignored in combinations(snapshots, ignored_count):
            context = validate_json_value(
                {
                    "unit_instance_id": unit_id,
                    "permissions": [permission.to_payload() for permission in permissions],
                    "available_modifiers": [snapshot.to_payload() for snapshot in snapshots],
                    "ignored_modifiers": [snapshot.to_payload() for snapshot in ignored],
                }
            )
            if not isinstance(context, dict):
                raise GameLifecycleError("Modifier-ignore context must be an object.")
            payload = validate_json_value({**option.payload, MODIFIER_IGNORE_CONTEXT_KEY: context})
            suffix = _modifier_ignore_option_suffix(ignored)
            expanded.append(
                DecisionOption(
                    option_id=(
                        option.option_id if not ignored else f"{option.option_id}:ignore:{suffix}"
                    ),
                    label=(
                        option.label
                        if not ignored
                        else f"{option.label} (ignore {len(ignored)} modifier"
                        f"{'s' if len(ignored) != 1 else ''})"
                    ),
                    payload=payload,
                )
            )
    return tuple(expanded)


def record_modifier_ignore_selection(
    *,
    state: GameState,
    result: DecisionResult,
    unit_instance_id: str,
    phase: BattlePhaseKind,
) -> PersistingEffect | None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Modifier-ignore selection requires GameState.")
    if type(result) is not DecisionResult:
        raise GameLifecycleError("Modifier-ignore selection requires DecisionResult.")
    unit_id = _validate_identifier("modifier-ignore unit_instance_id", unit_instance_id)
    if type(phase) is not BattlePhaseKind:
        raise GameLifecycleError("Modifier-ignore selection requires BattlePhaseKind.")
    payload = result.payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Modifier-ignore result payload must be an object.")
    raw_context = payload.get(MODIFIER_IGNORE_CONTEXT_KEY)
    if raw_context is None:
        return None
    context = _validated_context(raw_context, expected_unit_instance_id=unit_id)
    actor_id = _validate_identifier("modifier-ignore actor_id", result.actor_id)
    effect = PersistingEffect(
        effect_id=f"{result.result_id}:modifier-ignore-selection",
        source_rule_id="core:modifier-ignore-selection",
        owner_player_id=actor_id,
        target_unit_instance_ids=(unit_id,),
        started_battle_round=state.battle_round,
        expiration=EffectExpiration.end_phase(
            battle_round=state.battle_round,
            phase=phase,
            player_id=actor_id,
        ),
        effect_payload=validate_json_value(
            {
                "effect_kind": MODIFIER_IGNORE_SELECTION_EFFECT_KIND,
                "phase": phase.value,
                "source_decision_request_id": result.request_id,
                "source_decision_result_id": result.result_id,
                MODIFIER_IGNORE_CONTEXT_KEY: context,
            }
        ),
    )
    for existing in state.persisting_effects:
        if existing.effect_id != effect.effect_id:
            continue
        if existing != effect:
            raise GameLifecycleError("Modifier-ignore selection conflicts with state.")
        return existing
    state.record_persisting_effect(effect)
    return effect


def ignored_modifier_ids_for_context(
    *,
    state: GameState,
    unit_instance_id: str,
    kind: ModifierIgnoreKind,
    model_instance_id: str | None = None,
) -> tuple[str, ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Modifier-ignore lookup requires GameState.")
    unit_id = _validate_identifier("modifier-ignore unit_instance_id", unit_instance_id)
    requested_kind = _modifier_ignore_kind(kind)
    model_id = _validate_optional_identifier(
        "modifier-ignore model_instance_id",
        model_instance_id,
    )
    if requested_kind is ModifierIgnoreKind.MOVEMENT_CHARACTERISTIC and model_id is None:
        raise GameLifecycleError("Movement modifier-ignore lookup requires model_instance_id.")
    if requested_kind is not ModifierIgnoreKind.MOVEMENT_CHARACTERISTIC and model_id is not None:
        raise GameLifecycleError("Roll modifier-ignore lookup must not carry model_instance_id.")
    matching_contexts: list[dict[str, JsonValue]] = []
    for effect in state.persisting_effects_for_unit(unit_id):
        effect_payload = effect.effect_payload
        if not isinstance(effect_payload, dict):
            continue
        if effect_payload.get("effect_kind") != MODIFIER_IGNORE_SELECTION_EFFECT_KIND:
            continue
        raw_context = effect_payload.get(MODIFIER_IGNORE_CONTEXT_KEY)
        matching_contexts.append(_validated_context(raw_context, expected_unit_instance_id=unit_id))
    if len(matching_contexts) > 1:
        raise GameLifecycleError("Modifier-ignore selection is ambiguous for unit.")
    if not matching_contexts:
        return ()
    ignored = _snapshot_tuple(matching_contexts[0], key="ignored_modifiers")
    return tuple(
        snapshot.modifier_id
        for snapshot in ignored
        if snapshot.kind is requested_kind and snapshot.model_instance_id == model_id
    )


def _validated_context(
    payload: object,
    *,
    expected_unit_instance_id: str,
) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Modifier-ignore context must be an object.")
    mapped_payload = cast(dict[str, object], payload)
    if set(mapped_payload) != {
        "unit_instance_id",
        "permissions",
        "available_modifiers",
        "ignored_modifiers",
    }:
        raise GameLifecycleError("Modifier-ignore context fields drifted.")
    if _required_string(mapped_payload, "unit_instance_id") != expected_unit_instance_id:
        raise GameLifecycleError("Modifier-ignore context unit drifted.")
    raw_permissions = mapped_payload.get("permissions")
    if not isinstance(raw_permissions, list) or not raw_permissions:
        raise GameLifecycleError("Modifier-ignore context requires permissions.")
    permission_ids: set[str] = set()
    permission_provenance: set[tuple[str, str, str, str]] = set()
    permitted_kinds: set[ModifierIgnoreKind] = set()
    for raw_permission in cast(list[object], raw_permissions):
        if not isinstance(raw_permission, dict):
            raise GameLifecycleError("Modifier-ignore permission payload must be an object.")
        mapped_permission = cast(dict[str, object], raw_permission)
        if set(mapped_permission) != {
            "permission_id",
            "record_id",
            "source_id",
            "rule_ir_hash",
            "clause_id",
            "modifier_kinds",
        }:
            raise GameLifecycleError("Modifier-ignore permission payload fields drifted.")
        permission_id = _validate_identifier(
            "permission_id",
            _required_string(mapped_permission, "permission_id"),
        )
        provenance = (
            _validate_identifier("record_id", _required_string(mapped_permission, "record_id")),
            _validate_identifier("source_id", _required_string(mapped_permission, "source_id")),
            _validate_identifier(
                "rule_ir_hash", _required_string(mapped_permission, "rule_ir_hash")
            ),
            _validate_identifier("clause_id", _required_string(mapped_permission, "clause_id")),
        )
        if permission_id in permission_ids:
            raise GameLifecycleError("Modifier-ignore permission IDs are duplicated.")
        if provenance in permission_provenance:
            raise GameLifecycleError("Modifier-ignore permission provenance is duplicated.")
        permission_ids.add(permission_id)
        permission_provenance.add(provenance)
        raw_kinds = mapped_permission.get("modifier_kinds")
        if not isinstance(raw_kinds, list) or not raw_kinds:
            raise GameLifecycleError("Modifier-ignore permission kinds must be a list.")
        raw_kind_values = cast(list[object], raw_kinds)
        if any(type(value) is not str for value in raw_kind_values):
            raise GameLifecycleError("Modifier-ignore permission kinds must be strings.")
        kinds = tuple(_modifier_ignore_kind(value) for value in cast(list[str], raw_kind_values))
        if len(set(kinds)) != len(kinds):
            raise GameLifecycleError("Modifier-ignore permission kinds are duplicated.")
        permitted_kinds.update(kinds)
    available = _snapshot_tuple(mapped_payload, key="available_modifiers")
    ignored = _snapshot_tuple(mapped_payload, key="ignored_modifiers")
    if any(snapshot.kind not in permitted_kinds for snapshot in available):
        raise GameLifecycleError("Modifier-ignore available modifier kind is not permitted.")
    available_identities = {snapshot.identity() for snapshot in available}
    if len(available_identities) != len(available):
        raise GameLifecycleError("Modifier-ignore available modifiers are duplicated.")
    ignored_identities = {snapshot.identity() for snapshot in ignored}
    if len(ignored_identities) != len(ignored):
        raise GameLifecycleError("Modifier-ignore ignored modifiers are duplicated.")
    if not ignored_identities.issubset(available_identities):
        raise GameLifecycleError("Ignored modifier is not in the available snapshot.")
    validated = validate_json_value(cast(JsonValue, mapped_payload))
    if not isinstance(validated, dict):
        raise GameLifecycleError("Modifier-ignore context must remain an object.")
    return validated


def _snapshot_tuple(
    payload: Mapping[str, object],
    *,
    key: str,
) -> tuple[ModifierIgnoreSnapshot, ...]:
    raw_values = payload.get(key)
    if not isinstance(raw_values, list):
        raise GameLifecycleError(f"Modifier-ignore {key} must be a list.")
    return tuple(
        ModifierIgnoreSnapshot.from_payload(value) for value in cast(list[object], raw_values)
    )


def _modifier_ignore_option_suffix(
    ignored: tuple[ModifierIgnoreSnapshot, ...],
) -> str:
    payload = cast(JsonValue, [snapshot.to_payload() for snapshot in ignored])
    return sha256(canonical_json(payload).encode("utf-8")).hexdigest()[:16]


def _required_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value:
        raise GameLifecycleError(f"Modifier-ignore {key} must be a non-empty string.")
    return value


def _optional_string(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if type(value) is not str or not value:
        raise GameLifecycleError(f"Modifier-ignore {key} must be a string or null.")
    return value


def _validate_optional_identifier(field_name: str, value: object) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _modifier_ignore_kind(value: object) -> ModifierIgnoreKind:
    if type(value) is ModifierIgnoreKind:
        return value
    if type(value) is not str:
        raise GameLifecycleError("Modifier-ignore kind must be a string.")
    try:
        return ModifierIgnoreKind(value)
    except ValueError as exc:
        raise GameLifecycleError("Modifier-ignore kind is unsupported.") from exc


_validate_identifier = IdentifierValidator(GameLifecycleError)
