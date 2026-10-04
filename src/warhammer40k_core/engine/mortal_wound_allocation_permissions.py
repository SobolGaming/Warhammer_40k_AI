"""Core allocation permissions; named source providers own eligibility and choices."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from warhammer40k_core.engine.damage_allocation import FeelNoPainSource
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.timing_windows import TimingTriggerKind

MORTAL_WOUND_ALLOCATION_PERMISSION_KIND = "mortal_wound_allocation_permission"
MORTAL_WOUND_ALLOCATION_PREVENTION_RULE_KIND = "grant_mortal_feel_no_pain"
MORTAL_WOUND_ALLOCATION_RULE_APPLIED_EVENT_TYPE = "mortal_wound_allocation_rule_applied"


@dataclass(frozen=True, slots=True)
class MortalWoundAllocationPrevention:
    permission: PersistingEffect
    source: FeelNoPainSource
    decline_allowed: bool

    def __post_init__(self) -> None:
        payload = validate_mortal_wound_allocation_permission(self.permission)
        expected = FeelNoPainSource(
            source_id=f"{self.permission.effect_id}:mortal-allocation-feel-no-pain",
            threshold=cast(int, payload["threshold"]),
        )
        if (
            type(self.source) is not FeelNoPainSource
            or type(self.decline_allowed) is not bool
            or self.source != expected
            or self.decline_allowed != payload["decline_allowed"]
        ):
            raise GameLifecycleError("Mortal wound allocation prevention descriptor drift.")


def mortal_wound_allocation_permission_effect(
    *,
    state: GameState,
    effect_id: str,
    source_rule_id: str,
    target_unit_instance_id: str,
    occasion_id: str,
    threshold: int,
    decline_allowed: bool = False,
) -> PersistingEffect:
    """Freeze a provider-authorized living cohort; only the engine records the effect."""
    if type(state) is not GameState:
        raise GameLifecycleError("Mortal wound allocation permission requires GameState.")
    target = rules_unit_view_by_id(state=state, unit_instance_id=target_unit_instance_id)
    phase, turn_player_id = state.current_battle_phase, state.active_player_id
    if phase is None or turn_player_id is None:
        raise GameLifecycleError("Mortal wound allocation permission requires a phase and turn.")
    model_ids = tuple(sorted(model.model_instance_id for model in target.alive_models()))
    effect = PersistingEffect(
        effect_id=effect_id,
        source_rule_id=source_rule_id,
        owner_player_id=target.owner_player_id,
        target_unit_instance_ids=(target.unit_instance_id,),
        started_battle_round=state.battle_round,
        started_phase=phase,
        expiration=EffectExpiration.end_phase(
            battle_round=state.battle_round, phase=phase, player_id=turn_player_id
        ),
        effect_payload={
            "effect_kind": MORTAL_WOUND_ALLOCATION_PERMISSION_KIND,
            "trigger_kind": TimingTriggerKind.MORTAL_WOUND_ALLOCATED.value,
            "rule_kind": MORTAL_WOUND_ALLOCATION_PREVENTION_RULE_KIND,
            "occasion_id": occasion_id,
            "target_model_instance_ids": list(model_ids),
            "threshold": threshold,
            "decline_allowed": decline_allowed,
            "turn_player_id": turn_player_id,
        },
    )
    validate_mortal_wound_allocation_permission(effect)
    return effect


def validate_mortal_wound_allocation_permission(effect: PersistingEffect) -> dict[str, JsonValue]:
    if type(effect) is not PersistingEffect:
        raise GameLifecycleError("Mortal wound allocation permission requires a typed effect.")
    payload = effect.effect_payload
    keys = {
        "effect_kind",
        "trigger_kind",
        "rule_kind",
        "occasion_id",
        "target_model_instance_ids",
        "threshold",
        "decline_allowed",
        "turn_player_id",
    }
    if (
        not isinstance(payload, dict)
        or set(payload) != keys
        or payload["effect_kind"] != MORTAL_WOUND_ALLOCATION_PERMISSION_KIND
        or payload["trigger_kind"] != TimingTriggerKind.MORTAL_WOUND_ALLOCATED.value
        or payload["rule_kind"] != MORTAL_WOUND_ALLOCATION_PREVENTION_RULE_KIND
        or type(payload["threshold"]) is not int
        or not 2 <= payload["threshold"] <= 6
        or type(payload["decline_allowed"]) is not bool
        or len(effect.target_unit_instance_ids) != 1
        or effect.started_phase is None
    ):
        raise GameLifecycleError("Mortal wound allocation permission schema drift.")
    for key in ("occasion_id", "turn_player_id"):
        value = payload[key]
        if type(value) is not str or not value.strip() or value != value.strip():
            raise GameLifecycleError(f"Mortal wound allocation permission {key} is invalid.")
    models = payload["target_model_instance_ids"]
    if (
        not isinstance(models, list)
        or not models
        or any(type(m) is not str or not m.strip() or m != m.strip() for m in models)
        or models != sorted(set(cast(list[str], models)))
    ):
        raise GameLifecycleError("Mortal wound allocation permission model cohort is invalid.")
    if effect.expiration != EffectExpiration.end_phase(
        battle_round=effect.started_battle_round,
        phase=effect.started_phase,
        player_id=cast(str, payload["turn_player_id"]),
    ):
        raise GameLifecycleError("Mortal wound allocation permission duration drift.")
    return payload


def mortal_wound_allocation_preventions(
    *, state: GameState, model_instance_id: str
) -> tuple[MortalWoundAllocationPrevention, ...]:
    unit_id = state.unit_instance_id_for_model(model_instance_id)
    owner = rules_unit_view_by_id(state=state, unit_instance_id=unit_id).owner_player_id
    bindings: list[MortalWoundAllocationPrevention] = []
    for effect in state.persisting_effects:
        payload = effect.effect_payload
        if not isinstance(payload, dict) or payload.get("effect_kind") != (
            MORTAL_WOUND_ALLOCATION_PERMISSION_KIND
        ):
            continue
        payload = validate_mortal_wound_allocation_permission(effect)
        models = cast(list[str], payload["target_model_instance_ids"])
        for model_id in models:
            component_id = state.unit_instance_id_for_model(model_id)
            if (
                rules_unit_view_by_id(state=state, unit_instance_id=component_id).owner_player_id
                != effect.owner_player_id
            ):
                raise GameLifecycleError("Mortal wound allocation permission ownership drift.")
        if (
            model_instance_id not in models
            or effect.owner_player_id != owner
            or effect.started_battle_round != state.battle_round
            or effect.started_phase is not state.current_battle_phase
            or payload["turn_player_id"] != state.active_player_id
        ):
            continue
        bindings.append(
            MortalWoundAllocationPrevention(
                permission=effect,
                source=FeelNoPainSource(
                    source_id=f"{effect.effect_id}:mortal-allocation-feel-no-pain",
                    threshold=cast(int, payload["threshold"]),
                ),
                decline_allowed=cast(bool, payload["decline_allowed"]),
            )
        )
    return tuple(sorted(bindings, key=lambda binding: binding.permission.effect_id))
