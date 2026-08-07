from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.destruction_provenance import ModelDestructionAttribution
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import EventLog, JsonValue, validate_json_value
from warhammer40k_core.engine.generic_rule_effect_payloads import (
    generic_rule_effect_payload_grants_ability,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import (
    current_rules_unit_views_for_identity,
    rules_unit_owner_player_id,
    rules_unit_view_by_id,
)
from warhammer40k_core.engine.unit_destroyed_hooks import (
    UnitDestroyedContext,
    unit_destruction_completion_events_for_phase,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

DEADLY_DEMISE_MODIFIER_ABILITY = "deadly_demise_modifier"
DEADLY_DEMISE_DESTROYED_ENEMY_UNIT_CONDITION = "source_model_destroyed_enemy_unit_this_battle"
DEADLY_DEMISE_MODIFIER_CONDITION_EFFECT_KIND = "deadly_demise_modifier_condition_achieved"

_THIS_MODEL_TARGET_KIND = "this_model"
_DESTROYED_UNIT_RELATIONSHIP = "this_model_destroyed_unit"
_ENEMY_ALLEGIANCE = "enemy"
_THIS_BATTLE_TIME_SCOPE = "this_battle"


@dataclass(frozen=True, slots=True)
class DeadlyDemiseModifier:
    effect_id: str
    source_rule_id: str
    owner_player_id: str
    source_unit_instance_id: str
    source_model_instance_id: str
    trigger_roll_threshold: int
    conditional_mortal_wounds_kind: str
    conditional_mortal_wounds_modifier: int

    def __post_init__(self) -> None:
        for field_name in (
            "effect_id",
            "source_rule_id",
            "owner_player_id",
            "source_unit_instance_id",
            "source_model_instance_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _validate_identifier(field_name, getattr(self, field_name)),
            )
        if type(self.trigger_roll_threshold) is not int or not (
            1 <= self.trigger_roll_threshold <= 6
        ):
            raise GameLifecycleError(
                "Deadly Demise modifier trigger_roll_threshold must be on a D6."
            )
        if self.conditional_mortal_wounds_kind != "d3":
            raise GameLifecycleError(
                "Deadly Demise modifier mortal wounds must use the supported D3 kind."
            )
        if (
            type(self.conditional_mortal_wounds_modifier) is not int
            or self.conditional_mortal_wounds_modifier < 0
        ):
            raise GameLifecycleError(
                "Deadly Demise modifier mortal-wound modifier must be non-negative."
            )


def deadly_demise_modifier_for_model(
    *,
    state: GameState,
    model_instance_id: str,
    source_rule_id: str | None = None,
) -> DeadlyDemiseModifier | None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Deadly Demise modifier lookup requires GameState.")
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    requested_source_rule_id = (
        None if source_rule_id is None else _validate_identifier("source_rule_id", source_rule_id)
    )
    matches: list[DeadlyDemiseModifier] = []
    for persisting_effect in state.persisting_effects:
        effect_payload = persisting_effect.effect_payload
        if not isinstance(effect_payload, dict):
            continue
        if not generic_rule_effect_payload_grants_ability(
            effect_payload,
            ability=DEADLY_DEMISE_MODIFIER_ABILITY,
        ):
            continue
        if (
            requested_source_rule_id is not None
            and persisting_effect.source_rule_id != requested_source_rule_id
        ):
            continue
        modifier = _modifier_from_persisting_effect(
            state=state,
            persisting_effect=persisting_effect,
            effect_payload=effect_payload,
        )
        if modifier.source_model_instance_id == requested_model_id:
            matches.append(modifier)
    if len(matches) > 1:
        raise GameLifecycleError("A model cannot have multiple active Deadly Demise modifiers.")
    return None if not matches else matches[0]


def deadly_demise_modifier_condition_is_met(
    *,
    state: GameState,
    event_log: EventLog,
    modifier: DeadlyDemiseModifier,
) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Deadly Demise modifier condition requires GameState.")
    if type(event_log) is not EventLog:
        raise GameLifecycleError("Deadly Demise modifier condition requires EventLog.")
    if type(modifier) is not DeadlyDemiseModifier:
        raise GameLifecycleError("Deadly Demise modifier condition requires a modifier.")
    condition_effect_id = _condition_effect_id(modifier)
    stored = tuple(
        effect for effect in state.persisting_effects if effect.effect_id == condition_effect_id
    )
    if len(stored) > 1:
        raise GameLifecycleError("Deadly Demise modifier condition effect is duplicated.")
    if stored:
        _validate_condition_effect(effect=stored[0], modifier=modifier)
        return True
    current_phase = state.current_battle_phase
    if current_phase is None:
        return False
    return any(
        _destruction_matches_modifier(
            state=state,
            modifier=modifier,
            destroyed_unit_instance_id=_payload_identifier(
                payload,
                key="target_unit_instance_id",
            ),
            model_destroyed_payload=payload,
        )
        for _event_id, payload in unit_destruction_completion_events_for_phase(
            state=state,
            event_log=event_log,
            completed_phase=current_phase,
        )
    )


def record_deadly_demise_modifier_condition(
    *,
    context: UnitDestroyedContext,
    modifier: DeadlyDemiseModifier,
) -> bool:
    if type(context) is not UnitDestroyedContext:
        raise GameLifecycleError(
            "Deadly Demise modifier condition recording requires UnitDestroyedContext."
        )
    if type(modifier) is not DeadlyDemiseModifier:
        raise GameLifecycleError("Deadly Demise modifier condition recording requires a modifier.")
    if not _destruction_matches_modifier(
        state=context.state,
        modifier=modifier,
        destroyed_unit_instance_id=context.destroyed_unit_instance_id,
        model_destroyed_payload=context.model_destroyed_payload,
    ):
        return False
    effect_id = _condition_effect_id(modifier)
    existing = tuple(
        effect for effect in context.state.persisting_effects if effect.effect_id == effect_id
    )
    if len(existing) > 1:
        raise GameLifecycleError("Deadly Demise modifier condition effect is duplicated.")
    if existing:
        _validate_condition_effect(effect=existing[0], modifier=modifier)
        return False
    payload = validate_json_value(
        {
            "effect_kind": DEADLY_DEMISE_MODIFIER_CONDITION_EFFECT_KIND,
            "modifier_effect_id": modifier.effect_id,
            "source_rule_id": modifier.source_rule_id,
            "source_unit_instance_id": modifier.source_unit_instance_id,
            "source_model_instance_id": modifier.source_model_instance_id,
            "destroyed_unit_instance_id": context.destroyed_unit_instance_id,
            "model_destroyed_event_id": context.model_destroyed_event_id,
            "model_destroyed_payload": context.model_destroyed_payload,
        }
    )
    condition_effect = PersistingEffect(
        effect_id=effect_id,
        source_rule_id=modifier.source_rule_id,
        owner_player_id=modifier.owner_player_id,
        target_unit_instance_ids=(modifier.source_unit_instance_id,),
        started_battle_round=max(1, context.state.battle_round),
        started_phase=context.completed_phase,
        expiration=EffectExpiration.end_of_battle(),
        effect_payload=payload,
    )
    context.state.record_persisting_effect(condition_effect)
    context.decisions.event_log.append(
        "deadly_demise_modifier_condition_achieved",
        {
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "phase": context.completed_phase.value,
            "persisting_effect": condition_effect.to_payload(),
        },
    )
    return True


def _modifier_from_persisting_effect(
    *,
    state: GameState,
    persisting_effect: PersistingEffect,
    effect_payload: dict[str, JsonValue],
) -> DeadlyDemiseModifier:
    from warhammer40k_core.engine.generic_rule_attack_conditions import (
        generic_rule_parameters_from_effect_payload,
        generic_rule_source_model_instance_id_from_payload,
    )

    source_model_id = generic_rule_source_model_instance_id_from_payload(effect_payload)
    if source_model_id is None:
        raise GameLifecycleError("Deadly Demise modifier requires source_model_instance_id.")
    context_payload = _payload_object(effect_payload.get("context"), "context")
    source_unit_id = _payload_identifier(
        context_payload,
        key="source_unit_instance_id",
    )
    source_model_ids = _physical_unit_model_ids(
        state=state,
        unit_instance_id=source_unit_id,
    )
    if source_model_ids != (source_model_id,):
        raise GameLifecycleError("Deadly Demise modifier requires an exact single-model bearer.")
    if state.unit_instance_id_for_model(source_model_id) != source_unit_id:
        raise GameLifecycleError("Deadly Demise modifier source model identity drift.")
    if rules_unit_owner_player_id(state=state, unit_instance_id=source_unit_id) != (
        persisting_effect.owner_player_id
    ):
        raise GameLifecycleError("Deadly Demise modifier owner identity drift.")
    if persisting_effect.target_unit_instance_ids != (source_unit_id,):
        raise GameLifecycleError("Deadly Demise modifier must target only the bearer unit.")
    payload_source_id = _payload_identifier(effect_payload, key="source_id")
    if payload_source_id != persisting_effect.source_rule_id:
        raise GameLifecycleError("Deadly Demise modifier source rule identity drift.")
    target_payload = _payload_object(effect_payload.get("target"), "target")
    if target_payload.get("kind") != _THIS_MODEL_TARGET_KIND:
        raise GameLifecycleError("Deadly Demise modifier requires a this_model target.")
    effect = _payload_object(effect_payload.get("effect"), "effect")
    parameters = generic_rule_parameters_from_effect_payload(effect)
    expected_parameter_keys = {
        "ability",
        "trigger_roll_threshold",
        "conditional_mortal_wounds_kind",
        "conditional_mortal_wounds_modifier",
        "condition",
        "replaces_existing_deadly_demise",
    }
    if set(parameters) != expected_parameter_keys:
        raise GameLifecycleError("Deadly Demise modifier parameters are invalid.")
    if parameters["ability"] != DEADLY_DEMISE_MODIFIER_ABILITY:
        raise GameLifecycleError("Deadly Demise modifier ability identity drift.")
    if parameters["condition"] != DEADLY_DEMISE_DESTROYED_ENEMY_UNIT_CONDITION:
        raise GameLifecycleError("Deadly Demise modifier condition is unsupported.")
    if parameters["replaces_existing_deadly_demise"] is not True:
        raise GameLifecycleError("Deadly Demise modifier must replace the existing ability.")
    _validate_modifier_conditions(effect_payload)
    return DeadlyDemiseModifier(
        effect_id=persisting_effect.effect_id,
        source_rule_id=persisting_effect.source_rule_id,
        owner_player_id=persisting_effect.owner_player_id,
        source_unit_instance_id=source_unit_id,
        source_model_instance_id=source_model_id,
        trigger_roll_threshold=_positive_int(
            parameters["trigger_roll_threshold"],
            field_name="trigger_roll_threshold",
        ),
        conditional_mortal_wounds_kind=_string(
            parameters["conditional_mortal_wounds_kind"],
            field_name="conditional_mortal_wounds_kind",
        ),
        conditional_mortal_wounds_modifier=_non_negative_int(
            parameters["conditional_mortal_wounds_modifier"],
            field_name="conditional_mortal_wounds_modifier",
        ),
    )


def _validate_modifier_conditions(effect_payload: dict[str, JsonValue]) -> None:
    from warhammer40k_core.engine.generic_rule_attack_conditions import (
        generic_rule_conditions_from_payload,
    )

    conditions = generic_rule_conditions_from_payload(effect_payload)
    if len(conditions) != 1 or conditions[0].get("kind") != "target_constraint":
        raise GameLifecycleError("Deadly Demise modifier requires one target_constraint condition.")
    parameters = _payload_object(conditions[0].get("parameters"), "condition parameters")
    if parameters != {
        "relationship": _DESTROYED_UNIT_RELATIONSHIP,
        "target_allegiance": _ENEMY_ALLEGIANCE,
        "time_scope": _THIS_BATTLE_TIME_SCOPE,
    }:
        raise GameLifecycleError("Deadly Demise modifier condition parameters are invalid.")


def _destruction_matches_modifier(
    *,
    state: GameState,
    modifier: DeadlyDemiseModifier,
    destroyed_unit_instance_id: str,
    model_destroyed_payload: dict[str, JsonValue],
) -> bool:
    destroyed_unit_id = _validate_identifier(
        "destroyed_unit_instance_id",
        destroyed_unit_instance_id,
    )
    if (
        rules_unit_owner_player_id(
            state=state,
            unit_instance_id=destroyed_unit_id,
        )
        == modifier.owner_player_id
    ):
        return False
    attribution = ModelDestructionAttribution.from_model_destroyed_payload(model_destroyed_payload)
    if attribution.destroying_player_id != modifier.owner_player_id:
        return False
    attributed_source_id = attribution.source_rules_unit_instance_id
    if attributed_source_id is None:
        return False
    expected_rules_unit_id = rules_unit_view_by_id(
        state=state,
        unit_instance_id=modifier.source_unit_instance_id,
    ).unit_instance_id
    attributed_views = current_rules_unit_views_for_identity(
        state=state,
        unit_instance_id=attributed_source_id,
    )
    if all(view.unit_instance_id != expected_rules_unit_id for view in attributed_views):
        return False
    return attribution.source_model_instance_id == modifier.source_model_instance_id


def _physical_unit_model_ids(
    *,
    state: GameState,
    unit_instance_id: str,
) -> tuple[str, ...]:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    matches = tuple(
        unit
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id == requested_unit_id
    )
    if len(matches) != 1:
        raise GameLifecycleError("Deadly Demise modifier source unit is not unique.")
    return tuple(model.model_instance_id for model in matches[0].own_models)


def _condition_effect_id(modifier: DeadlyDemiseModifier) -> str:
    return _validate_identifier(
        "Deadly Demise modifier condition effect_id",
        f"{modifier.effect_id}:condition-achieved",
    )


def _validate_condition_effect(
    *,
    effect: PersistingEffect,
    modifier: DeadlyDemiseModifier,
) -> None:
    payload = _payload_object(effect.effect_payload, "condition effect payload")
    if payload.get("effect_kind") != DEADLY_DEMISE_MODIFIER_CONDITION_EFFECT_KIND:
        raise GameLifecycleError("Deadly Demise modifier condition effect kind drift.")
    if payload.get("modifier_effect_id") != modifier.effect_id:
        raise GameLifecycleError("Deadly Demise modifier condition source effect drift.")
    if payload.get("source_rule_id") != modifier.source_rule_id:
        raise GameLifecycleError("Deadly Demise modifier condition source rule drift.")
    if effect.source_rule_id != modifier.source_rule_id:
        raise GameLifecycleError("Deadly Demise modifier condition effect rule drift.")
    if payload.get("source_unit_instance_id") != modifier.source_unit_instance_id:
        raise GameLifecycleError("Deadly Demise modifier condition source unit drift.")
    if payload.get("source_model_instance_id") != modifier.source_model_instance_id:
        raise GameLifecycleError("Deadly Demise modifier condition source model drift.")
    if effect.owner_player_id != modifier.owner_player_id:
        raise GameLifecycleError("Deadly Demise modifier condition owner drift.")
    if effect.target_unit_instance_ids != (modifier.source_unit_instance_id,):
        raise GameLifecycleError("Deadly Demise modifier condition target drift.")


def _payload_object(value: JsonValue | None, field_name: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"Deadly Demise modifier {field_name} must be an object.")
    return value


def _payload_identifier(payload: dict[str, JsonValue], *, key: str) -> str:
    if key not in payload:
        raise GameLifecycleError(f"Deadly Demise modifier payload missing {key}.")
    return _validate_identifier(key, payload[key])


def _positive_int(value: JsonValue, *, field_name: str) -> int:
    if type(value) is not int or value < 1:
        raise GameLifecycleError(f"Deadly Demise modifier {field_name} must be a positive integer.")
    return value


def _non_negative_int(value: JsonValue, *, field_name: str) -> int:
    if type(value) is not int or value < 0:
        raise GameLifecycleError(
            f"Deadly Demise modifier {field_name} must be a non-negative integer."
        )
    return value


def _string(value: JsonValue, *, field_name: str) -> str:
    if type(value) is not str or not value:
        raise GameLifecycleError(f"Deadly Demise modifier {field_name} must be a string.")
    return value


_validate_identifier = IdentifierValidator(GameLifecycleError)
