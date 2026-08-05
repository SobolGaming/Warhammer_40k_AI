from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.dice import (
    RerollComponentSelectionPolicy,
    RerollPermission,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.effects import GENERIC_RULE_EFFECT_KIND, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import (
    RulesUnitIdentityReconciliation,
    reconcile_rules_unit_identity,
    rules_unit_identity_ids,
)
from warhammer40k_core.rules.rule_ir import (
    RuleDuration,
    RuleDurationKind,
    RuleDurationPayload,
    RuleEffectKind,
    RuleEffectSpec,
    RuleEffectSpecPayload,
    RuleIRError,
    RuleTargetKind,
    RuleTargetSpec,
    RuleTargetSpecPayload,
    parameter_payload,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


@dataclass(frozen=True, slots=True)
class _SelectedTargetChargeEffect:
    persisting_effect: PersistingEffect
    historical_source_unit_instance_id: str
    selected_target: RulesUnitIdentityReconciliation


@dataclass(frozen=True, slots=True)
class SelectedTargetChargeConstraint:
    reroll_allowed: bool
    required_target_unit_instance_ids: tuple[str, ...]
    source_effect_ids: tuple[str, ...]
    selected_target_identity_ids: tuple[str, ...]
    unavailable_target_identity_ids: tuple[str, ...]
    destroyed_target_identity_ids: tuple[str, ...]
    source_lineages: tuple[RulesUnitIdentityReconciliation, ...]
    target_lineages: tuple[RulesUnitIdentityReconciliation, ...]

    def is_satisfied_by(self, target_unit_instance_ids: tuple[str, ...]) -> bool:
        candidate_ids = frozenset(
            _validate_identifier_tuple(
                "target_unit_instance_ids",
                target_unit_instance_ids,
            )
        )
        return not self.unavailable_target_identity_ids and set(
            self.required_target_unit_instance_ids
        ).issubset(candidate_ids)

    def to_payload(self) -> dict[str, JsonValue]:
        return cast(
            dict[str, JsonValue],
            validate_json_value(
                {
                    "reroll_allowed": self.reroll_allowed,
                    "required_target_unit_instance_ids": list(
                        self.required_target_unit_instance_ids
                    ),
                    "source_effect_ids": list(self.source_effect_ids),
                    "selected_target_identity_ids": list(self.selected_target_identity_ids),
                    "unavailable_target_identity_ids": list(self.unavailable_target_identity_ids),
                    "destroyed_target_identity_ids": list(self.destroyed_target_identity_ids),
                    "source_lineages": [lineage.to_payload() for lineage in self.source_lineages],
                    "target_lineages": [lineage.to_payload() for lineage in self.target_lineages],
                }
            ),
        )


def selected_target_charge_constraint_for_unit(
    *,
    state: GameState,
    unit_instance_id: str,
) -> SelectedTargetChargeConstraint | None:
    contexts = _selected_target_charge_effects_for_unit(
        state=state,
        unit_instance_id=unit_instance_id,
    )
    if not contexts:
        return None
    source_lineages_by_identity = {
        context.historical_source_unit_instance_id: reconcile_rules_unit_identity(
            state=state,
            unit_instance_id=context.historical_source_unit_instance_id,
        )
        for context in contexts
    }
    lineages_by_identity: dict[str, RulesUnitIdentityReconciliation] = {}
    for context in contexts:
        lineage = context.selected_target
        prior = lineages_by_identity.get(lineage.historical_unit_instance_id)
        if prior is not None and prior != lineage:
            raise GameLifecycleError("Selected-target Charge lineage reconciliation drifted.")
        lineages_by_identity[lineage.historical_unit_instance_id] = lineage
    lineages = tuple(
        lineages_by_identity[identity_id] for identity_id in sorted(lineages_by_identity)
    )
    return SelectedTargetChargeConstraint(
        reroll_allowed=True,
        required_target_unit_instance_ids=tuple(
            sorted(
                {unit_id for lineage in lineages for unit_id in lineage.surviving_unit_instance_ids}
            )
        ),
        source_effect_ids=tuple(
            sorted(context.persisting_effect.effect_id for context in contexts)
        ),
        selected_target_identity_ids=tuple(
            lineage.historical_unit_instance_id for lineage in lineages
        ),
        unavailable_target_identity_ids=tuple(
            lineage.historical_unit_instance_id
            for lineage in lineages
            if lineage.is_destroyed
            or lineage.placed_surviving_unit_instance_ids != lineage.surviving_unit_instance_ids
        ),
        destroyed_target_identity_ids=tuple(
            lineage.historical_unit_instance_id for lineage in lineages if lineage.is_destroyed
        ),
        source_lineages=tuple(
            source_lineages_by_identity[identity_id]
            for identity_id in sorted(source_lineages_by_identity)
        ),
        target_lineages=lineages,
    )


def catalog_selected_target_charge_reroll_permission_for_unit(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
) -> RerollPermission | None:
    requested_player_id = _validate_identifier("player_id", player_id)
    contexts = _selected_target_charge_effects_for_unit(
        state=state,
        unit_instance_id=unit_instance_id,
    )
    if any(
        context.persisting_effect.owner_player_id != requested_player_id for context in contexts
    ):
        raise GameLifecycleError("Selected-target Charge effect owner drifted.")
    constraint = selected_target_charge_constraint_for_unit(
        state=state,
        unit_instance_id=unit_instance_id,
    )
    if constraint is None:
        return None
    return RerollPermission(
        source_id=f"catalog-selected-target-charge:{unit_instance_id}",
        timing_window="after_charge_roll",
        owning_player_id=requested_player_id,
        eligible_roll_type="charge_roll",
        component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
    )


def catalog_selected_target_required_charge_target_unit_instance_ids(
    *,
    state: GameState,
    unit_instance_id: str,
) -> tuple[str, ...]:
    constraint = selected_target_charge_constraint_for_unit(
        state=state,
        unit_instance_id=unit_instance_id,
    )
    return () if constraint is None else constraint.required_target_unit_instance_ids


def _selected_target_charge_effects_for_unit(
    *,
    state: GameState,
    unit_instance_id: str,
) -> tuple[_SelectedTargetChargeEffect, ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Selected-target Charge effect lookup requires GameState.")
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    contexts: list[_SelectedTargetChargeEffect] = []
    for persisting_effect in state.persisting_effects_for_unit(requested_unit_id):
        payload = persisting_effect.effect_payload
        if not isinstance(payload, dict) or payload.get("effect_kind") != GENERIC_RULE_EFFECT_KIND:
            continue
        rule_effect = _rule_effect_from_payload(payload)
        parameters = parameter_payload(rule_effect.parameters)
        if (
            rule_effect.kind is not RuleEffectKind.REROLL_PERMISSION
            or parameters.get("roll_type") != "charge"
            or parameters.get("target_reference") != "selected_unit"
        ):
            continue
        if (
            frozenset(parameters)
            != frozenset(
                {
                    "must_end_charge_move_engaged_with_selected_unit",
                    "roll_type",
                    "selected_target_unit_instance_id",
                    "target_reference",
                }
            )
            or parameters.get("must_end_charge_move_engaged_with_selected_unit") is not True
        ):
            raise GameLifecycleError("Selected-target Charge effect parameters drifted.")
        selected_target_id = _validate_identifier(
            "selected_target_unit_instance_id",
            parameters.get("selected_target_unit_instance_id"),
        )
        historical_source_id = _validate_selected_target_charge_context(
            state=state,
            payload=payload,
            persisting_effect=persisting_effect,
            requested_unit_id=requested_unit_id,
            selected_target_id=selected_target_id,
        )
        contexts.append(
            _SelectedTargetChargeEffect(
                persisting_effect=persisting_effect,
                historical_source_unit_instance_id=historical_source_id,
                selected_target=reconcile_rules_unit_identity(
                    state=state,
                    unit_instance_id=selected_target_id,
                ),
            )
        )
    return tuple(sorted(contexts, key=lambda context: context.persisting_effect.effect_id))


def _validate_selected_target_charge_context(
    *,
    state: GameState,
    payload: Mapping[str, JsonValue],
    persisting_effect: PersistingEffect,
    requested_unit_id: str,
    selected_target_id: str,
) -> str:
    target = _rule_target_from_payload(payload)
    duration = _rule_duration_from_payload(payload)
    selected_context = payload.get("catalog_selected_target")
    if not isinstance(selected_context, dict):
        raise GameLifecycleError("Selected-target Charge effect requires selection context.")
    historical_source_ids = _payload_identifier_list(payload, key="target_unit_instance_ids")
    if len(historical_source_ids) != 1:
        raise GameLifecycleError("Selected-target Charge effect requires one historical source.")
    historical_source_id = historical_source_ids[0]
    source_lineage = reconcile_rules_unit_identity(
        state=state,
        unit_instance_id=historical_source_id,
    )
    execution_context = payload.get("context")
    if not isinstance(execution_context, dict):
        raise GameLifecycleError("Selected-target Charge effect requires execution context.")
    execution_source_id = _validate_identifier(
        "context.source_unit_instance_id",
        execution_context.get("source_unit_instance_id"),
    )
    execution_target_ids = _payload_identifier_list(
        execution_context,
        key="target_unit_instance_ids",
    )
    selected_context_source_id = _validate_identifier(
        "catalog_selected_target.source_unit_instance_id",
        selected_context.get("source_unit_instance_id"),
    )
    historical_source_identity_ids = set(
        rules_unit_identity_ids(
            state=state,
            unit_instance_id=historical_source_id,
        )
    )
    if (
        target.kind is not RuleTargetKind.THIS_UNIT
        or target.parameters
        or duration.kind is not RuleDurationKind.UNTIL_TIMING_ENDPOINT
        or parameter_payload(duration.parameters) != {"boundary": "end", "endpoint": "turn"}
        or requested_unit_id not in persisting_effect.target_unit_instance_ids
        or not set(source_lineage.surviving_unit_instance_ids).issubset(
            persisting_effect.target_unit_instance_ids
        )
        or not set(persisting_effect.target_unit_instance_ids).issubset(
            source_lineage.current_unit_instance_ids
        )
        or payload.get("source_id") != persisting_effect.source_rule_id
        or execution_target_ids != (historical_source_id,)
        or execution_source_id != selected_context_source_id
        or execution_source_id not in historical_source_identity_ids
        or selected_context.get("selected_target_unit_instance_id") != selected_target_id
    ):
        raise GameLifecycleError("Selected-target Charge effect context drifted.")
    _validate_selected_target_trigger_payload(
        execution_context=execution_context,
        selected_target_id=selected_target_id,
    )
    return historical_source_id


def _validate_selected_target_trigger_payload(
    *,
    execution_context: Mapping[str, JsonValue],
    selected_target_id: str,
) -> None:
    trigger_payload = execution_context.get("trigger_payload")
    if not isinstance(trigger_payload, dict):
        raise GameLifecycleError("Selected-target Charge effect requires trigger payload.")
    selected_ids = _payload_identifier_list(
        trigger_payload,
        key="selected_target_unit_instance_ids",
    )
    if trigger_payload.get(
        "selected_target_unit_instance_id"
    ) != selected_target_id or selected_ids != (selected_target_id,):
        raise GameLifecycleError("Selected-target Charge trigger target drifted.")


def _rule_effect_from_payload(payload: Mapping[str, JsonValue]) -> RuleEffectSpec:
    raw_effect = payload.get("effect")
    if not isinstance(raw_effect, dict):
        raise GameLifecycleError("Generic RuleIR Charge effect requires effect payload.")
    try:
        return RuleEffectSpec.from_payload(cast(RuleEffectSpecPayload, raw_effect))
    except RuleIRError as exc:
        raise GameLifecycleError("Generic RuleIR Charge effect payload is invalid.") from exc


def _rule_target_from_payload(payload: Mapping[str, JsonValue]) -> RuleTargetSpec:
    raw_target = payload.get("target")
    if not isinstance(raw_target, dict):
        raise GameLifecycleError("Generic RuleIR Charge effect requires target payload.")
    try:
        return RuleTargetSpec.from_payload(cast(RuleTargetSpecPayload, raw_target))
    except RuleIRError as exc:
        raise GameLifecycleError("Generic RuleIR Charge target payload is invalid.") from exc


def _rule_duration_from_payload(payload: Mapping[str, JsonValue]) -> RuleDuration:
    raw_duration = payload.get("duration")
    if not isinstance(raw_duration, dict):
        raise GameLifecycleError("Generic RuleIR Charge effect requires duration payload.")
    try:
        return RuleDuration.from_payload(cast(RuleDurationPayload, raw_duration))
    except RuleIRError as exc:
        raise GameLifecycleError("Generic RuleIR Charge duration payload is invalid.") from exc


def _payload_identifier_list(
    payload: Mapping[str, JsonValue],
    *,
    key: str,
) -> tuple[str, ...]:
    raw_values = payload.get(key)
    if not isinstance(raw_values, list):
        raise GameLifecycleError(f"{key} must be a list.")
    return _validate_identifier_tuple(key, tuple(cast(list[object], raw_values)))


def _validate_identifier_tuple(field_name: str, values: tuple[object, ...]) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    validated = tuple(_validate_identifier(field_name, value) for value in values)
    if len(set(validated)) != len(validated):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    return validated


_validate_identifier = IdentifierValidator(GameLifecycleError)
