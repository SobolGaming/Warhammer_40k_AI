"""Source-preserving Range and Attacks choices before weapon declarations."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.modifiers import Modifier
from warhammer40k_core.core.weapon_profiles import RangeProfile, WeaponProfile
from warhammer40k_core.engine.catalog_modifier_ignore import ModifierIgnoreKind
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.modifier_evaluation import ModifierEvaluationSubject, select_modifiers
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.weapon_selection_context import (
    WeaponSelectionContext,
    WeaponSelectionContextPayload,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.abilities import AbilityCatalogIndex
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.decision_request import DecisionRequest
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


KINDS = (ModifierIgnoreKind.RANGE_CHARACTERISTIC, ModifierIgnoreKind.ATTACKS_CHARACTERISTIC)


def _operations(profile: WeaponProfile, kind: ModifierIgnoreKind) -> tuple[Modifier, ...]:
    if kind is ModifierIgnoreKind.ATTACKS_CHARACTERISTIC:
        return profile.attack_profile.modifiers
    value = profile.range_profile
    if value.random_value is not None:
        return value.random_value.modifiers
    return () if value.modifier_trace is None else value.modifier_trace.modifiers


def _inventory(context: WeaponSelectionContext, kind: ModifierIgnoreKind) -> tuple[Modifier, ...]:
    operations: dict[str, Modifier] = {}
    for _, profile in context.target_profiles:
        for modifier in _operations(profile, kind):
            previous = operations.get(modifier.modifier_id)
            if previous is not None and previous != modifier:
                raise GameLifecycleError("Weapon modifier identity has conflicting operations.")
            operations[modifier.modifier_id] = modifier
    return tuple(operations[key] for key in sorted(operations))


def _selected_profile(
    profile: WeaponProfile, kind: ModifierIgnoreKind, ignored: tuple[str, ...]
) -> WeaponProfile:
    identifiers = {item.modifier_id for item in _operations(profile, kind)}
    selected = tuple(item for item in ignored if item in identifiers)
    if kind is ModifierIgnoreKind.ATTACKS_CHARACTERISTIC:
        attacks = profile.attack_profile
        return replace(
            profile,
            attack_profile=replace(
                attacks,
                ignored_modifier_ids=selected,
                fixed_attacks=None
                if attacks.fixed_attacks is None
                else attacks.resolve_value(attacks.fixed_attacks, ignored_modifier_ids=selected),
            ),
        )
    value = profile.range_profile
    if value.random_value is not None:
        random = value.random_value
        if random.evaluation_id is None:
            raise GameLifecycleError("Range modifier selection requires its selected weapon roll.")
        return replace(
            profile,
            range_profile=RangeProfile.random(
                random.evaluate(
                    raw=random.raw,
                    evaluation_id=random.evaluation_id,
                    target_id=profile.profile_id,
                    ignored_modifier_ids=selected,
                )
            ),
        )
    trace = value.modifier_trace
    if trace is None:
        return profile
    trace = replace(trace, ignored_modifier_ids=selected)
    return replace(
        profile,
        range_profile=replace(
            value,
            distance_inches=trace.resolve().final,
            modifier_trace=trace,
        ),
    )


def unselected_weapon_profile(profile: WeaponProfile) -> WeaponProfile:
    for kind in KINDS:
        if _operations(profile, kind):
            profile = _selected_profile(profile, kind, ())
    return profile


def prepare_weapon_modifier_context(
    *,
    state: GameState,
    decisions: DecisionController,
    ability_index: AbilityCatalogIndex,
    activation_id: str,
    unit_instance_id: str,
    model_instance_id: str,
    context: WeaponSelectionContext,
    kinds: tuple[ModifierIgnoreKind, ...] = KINDS,
) -> tuple[WeaponSelectionContext, LifecycleStatus | None]:
    """Choose each physical weapon's source operations once, before targets or A dice.

    Target-specific operations share the same per-weapon decision inventory. Each
    target profile subsequently consumes only the selected operations that apply
    to that target; a split allocation cannot manufacture a fresh Attacks choice.
    """
    for kind in kinds:
        operations = _inventory(context, kind)
        if not operations:
            continue
        source_profiles: list[JsonValue] = []
        for target, profile in context.target_profiles:
            source_profile = unselected_weapon_profile(profile)
            source_profiles.append(
                {
                    "target_unit_instance_id": target,
                    "profile": validate_json_value(
                        source_profile.attack_profile.to_payload()
                        if kind is ModifierIgnoreKind.ATTACKS_CHARACTERISTIC
                        else source_profile.range_profile.to_payload()
                    ),
                }
            )
        profile_id = context.target_profiles[0][1].profile_id
        selection = select_modifiers(
            state=state,
            decisions=decisions,
            ability_index=ability_index,
            occurrence_id=f"{activation_id}:weapon:{context.weapon_instance_id}:{profile_id}:{kind.value}",
            subject=ModifierEvaluationSubject(
                unit_instance_id=unit_instance_id,
                model_instance_id=model_instance_id,
                weapon_profile_id=profile_id,
                kind=kind,
            ),
            modifiers=operations,
            source_context={
                "boundary": "weapon-declaration",
                "activation_result_id": activation_id,
                "weapon_instance_id": context.weapon_instance_id,
                "target_profiles": source_profiles,
            },
        )
        if selection.pending_status is not None:
            return context, selection.pending_status
        context = replace(
            context,
            target_profiles=tuple(
                (target, _selected_profile(profile, kind, selection.ignored_modifier_ids))
                for target, profile in context.target_profiles
            ),
        )
    return context, None


def authenticated_weapon_modifier_context(
    current: WeaponSelectionContext,
    offered: WeaponSelectionContext,
) -> WeaponSelectionContext:
    """Carry accepted subsets only when every underlying source operation matches."""

    def cleared(context: WeaponSelectionContext) -> WeaponSelectionContext:
        return replace(
            context,
            target_profiles=tuple(
                (target, unselected_weapon_profile(profile))
                for target, profile in context.target_profiles
            ),
        )

    if cleared(current) != cleared(offered):
        raise GameLifecycleError("Weapon modifier source inventory drifted from its request.")
    return offered


def shooting_modifier_context_from_request(
    request: DecisionRequest,
    current: WeaponSelectionContext,
) -> WeaponSelectionContext:
    payload = _object(request.payload)
    proposal = _object(payload["proposal_request"])
    candidates = proposal["target_candidates"]
    if not isinstance(candidates, list):
        raise GameLifecycleError("Weapon modifier declaration candidates are missing.")
    for raw in candidates:
        candidate = _object(raw)
        if candidate["weapon_instance_id"] == current.weapon_instance_id:
            offered = WeaponSelectionContext.from_payload(
                cast(
                    WeaponSelectionContextPayload,
                    _object(candidate["weapon_ability_selection_context"]),
                )
            )
            if offered.target_profiles[0][1].profile_id == current.target_profiles[0][1].profile_id:
                return authenticated_weapon_modifier_context(current, offered)
    raise GameLifecycleError("Weapon modifier selection has no pending physical weapon.")


def prepare_melee_modifier_rows(
    *,
    state: GameState,
    decisions: DecisionController,
    registry: RuntimeModifierRegistry,
    activation_id: str,
    unit_instance_id: str,
    player_id: str,
    rows: tuple[JsonValue, ...],
) -> tuple[tuple[JsonValue, ...], LifecycleStatus | None]:
    selected_rows: list[JsonValue] = []
    for raw in rows:
        row = _object(raw)
        raw_context = row["weapon_ability_selection_context"]
        if raw_context is None:
            selected_rows.append(row)
            continue
        context = WeaponSelectionContext.from_payload(
            cast(
                WeaponSelectionContextPayload,
                _object(raw_context),
            )
        )
        context, status = prepare_weapon_modifier_context(
            state=state,
            decisions=decisions,
            ability_index=registry.modifier_permission_index(player_id),
            activation_id=activation_id,
            unit_instance_id=unit_instance_id,
            model_instance_id=_identifier(row["model_instance_id"]),
            context=context,
        )
        if status is not None:
            return rows, status
        selected_rows.append(melee_row_with_context(row, context))
    return tuple(selected_rows), None


def authenticated_melee_modifier_rows(
    current: tuple[JsonValue, ...],
    offered: tuple[JsonValue, ...],
) -> tuple[JsonValue, ...]:
    if len(current) != len(offered):
        raise GameLifecycleError("Melee modifier weapon inventory drifted.")
    selected: list[JsonValue] = []
    for raw, offered_raw in zip(current, offered, strict=True):
        row, expected = _object(raw), _object(offered_raw)
        current_context, offered_context = (
            row["weapon_ability_selection_context"],
            expected["weapon_ability_selection_context"],
        )
        if current_context is not None and offered_context is not None:
            context = authenticated_weapon_modifier_context(
                WeaponSelectionContext.from_payload(
                    cast(WeaponSelectionContextPayload, _object(current_context))
                ),
                WeaponSelectionContext.from_payload(
                    cast(WeaponSelectionContextPayload, _object(offered_context))
                ),
            )
            row = melee_row_with_context(row, context)
        if row != expected:
            raise GameLifecycleError("Melee modifier declaration inventory drifted.")
        selected.append(row)
    return tuple(selected)


def _object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Weapon modifier selection requires an object.")
    return value


def _identifier(value: JsonValue) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise GameLifecycleError("Weapon modifier selection identifier is invalid.")
    return value


def selected_melee_context_for_physical_targets(
    *,
    state: GameState | None,
    current: WeaponSelectionContext,
    offered_rows: tuple[JsonValue, ...],
) -> WeaponSelectionContext:
    """Preserve physical aliases carried by the accepted attached-unit inventory."""
    matching = tuple(
        _object(row)
        for row in offered_rows
        if _object(row)["weapon_instance_id"] == current.weapon_instance_id
        and _object(row)["weapon_profile_id"] == current.target_profiles[0][1].profile_id
    )
    if len(matching) != 1:
        raise GameLifecycleError("Melee modifier selection has no accepted physical weapon.")
    offered = WeaponSelectionContext.from_payload(
        cast(
            WeaponSelectionContextPayload,
            _object(matching[0]["weapon_ability_selection_context"]),
        )
    )
    return authenticated_weapon_modifier_context(current, offered)


def selected_melee_rows_for_physical_targets(
    *,
    state: GameState,
    current: tuple[JsonValue, ...],
    offered_rows: tuple[JsonValue, ...],
) -> tuple[JsonValue, ...]:
    rows: list[JsonValue] = []
    for raw in current:
        row = _object(raw)
        value = row["weapon_ability_selection_context"]
        if value is not None:
            context = selected_melee_context_for_physical_targets(
                state=state,
                current=WeaponSelectionContext.from_payload(
                    cast(WeaponSelectionContextPayload, _object(value))
                ),
                offered_rows=offered_rows,
            )
            row = melee_row_with_context(row, context)
        rows.append(row)
    return tuple(rows)


def melee_modifier_rows_from_history(
    *,
    decisions: DecisionController,
    activation_id: str,
    unit_instance_id: str,
    rows: tuple[JsonValue, ...],
) -> tuple[JsonValue, ...]:
    """Rebuild immutable commitment evidence without requesting a new choice."""
    from warhammer40k_core.engine.modifier_evaluation import selected_modifiers_for_occurrence

    output: list[JsonValue] = []
    for raw in rows:
        row = _object(raw)
        raw_context = row["weapon_ability_selection_context"]
        if raw_context is None:
            output.append(row)
            continue
        context = WeaponSelectionContext.from_payload(
            cast(WeaponSelectionContextPayload, _object(raw_context))
        )
        profile_id = context.target_profiles[0][1].profile_id
        for kind in KINDS:
            operations = _inventory(context, kind)
            if not operations:
                continue
            selected = selected_modifiers_for_occurrence(
                decision_records=decisions.records,
                occurrence_id=f"{activation_id}:weapon:{context.weapon_instance_id}:{profile_id}:{kind.value}",
                subject=ModifierEvaluationSubject(
                    unit_instance_id=unit_instance_id,
                    model_instance_id=_identifier(row["model_instance_id"]),
                    weapon_profile_id=profile_id,
                    kind=kind,
                ),
                modifiers=operations,
            )
            kept = {item.modifier_id for item in selected}
            ignored = tuple(item.modifier_id for item in operations if item.modifier_id not in kept)
            context = replace(
                context,
                target_profiles=tuple(
                    (target, _selected_profile(profile, kind, ignored))
                    for target, profile in context.target_profiles
                ),
            )
        output.append(melee_row_with_context(row, context))
    return tuple(output)


def retarget_weapon_modifier_context(
    *,
    state: GameState,
    decisions: DecisionController,
    ability_index: AbilityCatalogIndex,
    activation_id: str,
    unit_instance_id: str,
    model_instance_id: str,
    current: WeaponSelectionContext,
    committed: WeaponSelectionContext,
    request_choices: bool,
) -> tuple[WeaponSelectionContext, LifecycleStatus | None]:
    """Re-enter the same decision owner when reactions change Range or Attacks."""
    from hashlib import sha256

    from warhammer40k_core.engine.event_log import canonical_json
    from warhammer40k_core.engine.modifier_evaluation import selected_modifiers_for_occurrence

    for kind in KINDS:
        if not _inventory(current, kind) and not _inventory(committed, kind):
            continue

        def values(
            context: WeaponSelectionContext, selected_kind: ModifierIgnoreKind = kind
        ) -> list[JsonValue]:
            return [
                {
                    "target": target,
                    "value": validate_json_value(
                        unselected_weapon_profile(
                            context.raw_profile_for_target(target)
                        ).attack_profile.to_payload()
                        if selected_kind is ModifierIgnoreKind.ATTACKS_CHARACTERISTIC
                        else unselected_weapon_profile(
                            context.raw_profile_for_target(target)
                        ).range_profile.to_payload()
                    ),
                }
                for target, _ in context.target_profiles
            ]

        sources = values(current)
        if sources == values(committed):
            selected_profiles = dict(
                (*committed.target_profiles, *committed.resolved_target_profiles)
            )
            selected_pairs: list[tuple[str, WeaponProfile]] = []
            for target, profile in current.target_profiles:
                prior = selected_profiles[target]
                if kind is ModifierIgnoreKind.ATTACKS_CHARACTERISTIC:
                    ignored = prior.attack_profile.ignored_modifier_ids
                elif prior.range_profile.random_value is not None:
                    ignored = prior.range_profile.random_value.ignored_modifier_ids
                else:
                    trace = prior.range_profile.modifier_trace
                    ignored = () if trace is None else trace.ignored_modifier_ids
                selected_pairs.append((target, _selected_profile(profile, kind, ignored)))
            current = replace(current, target_profiles=tuple(selected_pairs))
            continue
        digest = sha256(canonical_json(sources).encode()).hexdigest()
        occurrence = f"{activation_id}:retarget:{digest}"
        if request_choices:
            current, status = prepare_weapon_modifier_context(
                state=state,
                decisions=decisions,
                ability_index=ability_index,
                activation_id=occurrence,
                unit_instance_id=unit_instance_id,
                model_instance_id=model_instance_id,
                context=current,
                kinds=(kind,),
            )
            if status is not None:
                return current, status
        else:
            operations = _inventory(current, kind)
            profile_id = current.target_profiles[0][1].profile_id
            selected = selected_modifiers_for_occurrence(
                decision_records=decisions.records,
                occurrence_id=f"{occurrence}:weapon:{current.weapon_instance_id}:{profile_id}:{kind.value}",
                subject=ModifierEvaluationSubject(
                    unit_instance_id=unit_instance_id,
                    model_instance_id=model_instance_id,
                    weapon_profile_id=profile_id,
                    kind=kind,
                ),
                modifiers=operations,
            )
            kept = {item.modifier_id for item in selected}
            ignored = tuple(item.modifier_id for item in operations if item.modifier_id not in kept)
            current = replace(
                current,
                target_profiles=tuple(
                    (target, _selected_profile(profile, kind, ignored))
                    for target, profile in current.target_profiles
                ),
            )
    return current, None


def melee_row_with_context(
    row: dict[str, JsonValue], context: WeaponSelectionContext
) -> dict[str, JsonValue]:
    profiles = tuple(profile.attack_profile for _, profile in context.target_profiles)
    fixed = {profile.fixed_attacks for profile in profiles}
    maximum: list[int] = []
    for profile in profiles:
        if profile.fixed_attacks is not None:
            maximum.append(profile.fixed_attacks)
        else:
            expression = profile.dice_expression
            if expression is None:
                raise GameLifecycleError("Melee count inventory lacks an expression.")
            maximum.append(
                profile.resolve_value(expression.quantity * expression.sides + expression.modifier)
            )
    return {
        **row,
        "weapon_ability_selection_context": validate_json_value(context.to_payload()),
        "maximum_declared_targets": max(maximum),
        "fixed_attacks": next(iter(fixed)) if len(fixed) == 1 else None,
    }
