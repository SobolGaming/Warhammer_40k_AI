"""Materialize native core occurrences without choosing a numeric winner."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.damage_allocation import (
    DestructionReactionKind,
    DestructionReactionSource,
    FeelNoPainSource,
)
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_abilities import (
    DeadlyDemiseAbilityProfile,
    FeelNoPainAbilityProfile,
    deadly_demise_profiles_for_unit,
    feel_no_pain_profiles_for_unit,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.unit_factory import UnitInstance

__all__ = (
    "_deadly_demise_mortal_wounds_payload",
    "_deadly_demise_source_for_model",
    "_deadly_demise_source_payload",
    "_feel_no_pain_source_for_model",
    "_record_model_destruction_reaction_source",
    "_record_model_feel_no_pain_source",
    "_record_static_persisting_effect",
    "_static_ability_started_battle_round",
)

DEADLY_DEMISE_TRIGGER_ROLL_THRESHOLD = 6
DEADLY_DEMISE_RANGE_INCHES = 6.0


def record_core_deadly_demise_sources_for_unit(
    *,
    state: GameState,
    unit: UnitInstance,
) -> tuple[tuple[str, DestructionReactionSource], ...]:
    from warhammer40k_core.engine.catalog_rule_consumption import (
        _validate_game_state,
        _validate_unit,
    )

    _validate_game_state(state)
    _validate_unit(unit)
    profiles = deadly_demise_profiles_for_unit(unit)
    recorded_sources: list[tuple[str, DestructionReactionSource]] = []
    for profile in profiles:
        for model in unit.own_models:
            source = _deadly_demise_source_for_model(
                profile=profile,
                model_instance_id=model.model_instance_id,
            )
            _record_model_destruction_reaction_source(
                state=state,
                model_instance_id=model.model_instance_id,
                source=source,
            )
            recorded_sources.append((model.model_instance_id, source))
    return tuple(sorted(recorded_sources, key=lambda binding: (binding[0], binding[1].source_id)))


def record_core_feel_no_pain_sources_for_unit(
    *,
    state: GameState,
    unit: UnitInstance,
) -> tuple[tuple[str, FeelNoPainSource], ...]:
    from warhammer40k_core.engine.catalog_rule_consumption import (
        _validate_game_state,
        _validate_unit,
    )

    _validate_game_state(state)
    _validate_unit(unit)
    profiles = feel_no_pain_profiles_for_unit(unit)
    recorded_sources: list[tuple[str, FeelNoPainSource]] = []
    for profile in profiles:
        for model in unit.own_models:
            source = _feel_no_pain_source_for_model(
                profile=profile,
                model_instance_id=model.model_instance_id,
            )
            _record_model_feel_no_pain_source(
                state=state,
                model_instance_id=model.model_instance_id,
                source=source,
            )
            recorded_sources.append((model.model_instance_id, source))
    return tuple(sorted(recorded_sources, key=lambda binding: (binding[0], binding[1].source_id)))


def record_core_fights_first_sources_for_unit(
    *,
    state: GameState,
    unit: UnitInstance,
) -> tuple[PersistingEffect, ...]:
    from warhammer40k_core.engine.catalog_rule_consumption import (
        _owner_player_id_for_unit,
        _validate_game_state,
        _validate_unit,
    )
    from warhammer40k_core.engine.fights_first_native import native_fights_first_sources

    _validate_game_state(state)
    _validate_unit(unit)
    effects = tuple(
        PersistingEffect(
            effect_id=source.effect_id,
            source_rule_id=source.source_rule_id,
            owner_player_id=_owner_player_id_for_unit(state=state, unit=unit),
            target_unit_instance_ids=(unit.unit_instance_id,),
            started_battle_round=_static_ability_started_battle_round(state),
            expiration=EffectExpiration.end_of_battle(),
            effect_payload=source.effect_payload(),
        )
        for source in native_fights_first_sources(unit)
    )
    for effect in effects:
        _record_static_persisting_effect(state=state, effect=effect)
    return effects


def _deadly_demise_source_for_model(
    *,
    profile: DeadlyDemiseAbilityProfile,
    model_instance_id: str,
) -> DestructionReactionSource:
    from warhammer40k_core.engine.catalog_rule_consumption import (
        _string_identifier,
    )

    if type(profile) is not DeadlyDemiseAbilityProfile:
        raise GameLifecycleError("Deadly Demise source registration requires an ability profile.")
    model_id = _string_identifier("Deadly Demise source model_instance_id", model_instance_id)
    return DestructionReactionSource(
        source_id=f"{profile.source_id}:{profile.ability_source.instance_id}:{model_id}:deadly-demise",
        reaction_kind=DestructionReactionKind.DEADLY_DEMISE,
        source_rule_id=profile.source_id,
        payload=_deadly_demise_source_payload(profile.mortal_wounds_token),
        optional=False,
    )


def _deadly_demise_source_payload(token: str) -> dict[str, JsonValue]:
    mortal_wounds = _deadly_demise_mortal_wounds_payload(token)
    return {
        "trigger_roll_threshold": DEADLY_DEMISE_TRIGGER_ROLL_THRESHOLD,
        "range_inches": DEADLY_DEMISE_RANGE_INCHES,
        "mortal_wounds": mortal_wounds,
    }


def _deadly_demise_mortal_wounds_payload(token: str) -> dict[str, JsonValue]:
    from warhammer40k_core.engine.catalog_rule_consumption import (
        _string_identifier,
    )

    normalized = _string_identifier("Deadly Demise mortal wounds token", token).upper()
    if normalized == "D3":
        return {"kind": "d3"}
    if normalized == "D6":
        return {"kind": "d6"}
    try:
        value = int(normalized)
    except ValueError as exc:
        raise GameLifecycleError("Unsupported Deadly Demise mortal-wound token.") from exc
    if value < 1:
        raise GameLifecycleError("Deadly Demise fixed mortal wounds must be positive.")
    return {"kind": "fixed", "value": value}


def _feel_no_pain_source_for_model(
    *,
    profile: FeelNoPainAbilityProfile,
    model_instance_id: str,
) -> FeelNoPainSource:
    from warhammer40k_core.engine.catalog_rule_consumption import (
        _string_identifier,
    )

    if type(profile) is not FeelNoPainAbilityProfile:
        raise GameLifecycleError("Feel No Pain source registration requires an ability profile.")
    model_id = _string_identifier("Feel No Pain source model_instance_id", model_instance_id)
    return FeelNoPainSource(
        source_id=f"{profile.source_id}:{profile.ability_source.instance_id}:{model_id}:feel-no-pain",
        threshold=profile.threshold,
    )


def _record_model_feel_no_pain_source(
    *,
    state: GameState,
    model_instance_id: str,
    source: FeelNoPainSource,
) -> None:
    existing_sources = state.feel_no_pain_sources_for_model(model_instance_id=model_instance_id)
    for existing_source in existing_sources:
        if existing_source.source_id != source.source_id:
            continue
        if existing_source != source:
            raise GameLifecycleError("Catalog Feel No Pain source conflicts with existing state.")
        return
    state.record_model_feel_no_pain_sources(
        model_instance_id=model_instance_id,
        sources=(*existing_sources, source),
        decline_allowed=state.feel_no_pain_decline_allowed_for_model(
            model_instance_id=model_instance_id
        ),
    )


def _record_static_persisting_effect(
    *,
    state: GameState,
    effect: PersistingEffect,
) -> None:
    for existing_effect in state.persisting_effects:
        if existing_effect.effect_id != effect.effect_id:
            continue
        if existing_effect != effect:
            raise GameLifecycleError("Core static persisting effect conflicts with existing state.")
        return
    state.record_persisting_effect(effect)


def _record_model_destruction_reaction_source(
    *,
    state: GameState,
    model_instance_id: str,
    source: DestructionReactionSource,
) -> None:
    existing_sources = state.destruction_reaction_sources_for_model(
        model_instance_id=model_instance_id
    )
    for existing_source in existing_sources:
        if existing_source.source_id != source.source_id:
            continue
        if existing_source != source:
            raise GameLifecycleError("Core Deadly Demise source conflicts with existing state.")
        return
    state.record_model_destruction_reaction_sources(
        model_instance_id=model_instance_id,
        sources=(*existing_sources, source),
    )


def _static_ability_started_battle_round(state: GameState) -> int:
    if type(state.battle_round) is not int:
        raise GameLifecycleError("Core static ability source requires an integer battle round.")
    if state.battle_round < 0:
        raise GameLifecycleError("Core static ability source requires a non-negative battle round.")
    return 1
