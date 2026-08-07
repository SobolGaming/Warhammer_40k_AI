from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.damage_allocation import model_owner_player_id
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import (
    current_rules_unit_views_for_identity,
    rules_unit_owner_player_id,
    rules_unit_view_by_id,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def resolve_non_attack_destruction_source_identity(
    *,
    state: GameState,
    source_rules_unit_instance_id: str | None,
    source_model_instance_id: str | None,
    destroying_player_id: str,
) -> tuple[str | None, str | None]:
    if source_rules_unit_instance_id is None:
        if source_model_instance_id is not None:
            raise GameLifecycleError("Rule destruction source model requires a source rules unit.")
        return None, None
    requested_destroying_player_id = _validate_identifier(
        "destroying_player_id",
        destroying_player_id,
    )
    requested_source_id = _validate_identifier(
        "source_rules_unit_instance_id",
        source_rules_unit_instance_id,
    )
    canonical_source_id = rules_unit_view_by_id(
        state=state,
        unit_instance_id=requested_source_id,
    ).unit_instance_id
    if (
        rules_unit_owner_player_id(
            state=state,
            unit_instance_id=canonical_source_id,
        )
        != requested_destroying_player_id
    ):
        raise GameLifecycleError(
            "Rule destruction source rules unit must belong to the destroying player."
        )
    if source_model_instance_id is None:
        return canonical_source_id, None
    requested_source_model_id = _validate_identifier(
        "source_model_instance_id",
        source_model_instance_id,
    )
    if (
        model_owner_player_id(
            state=state,
            model_instance_id=requested_source_model_id,
        )
        != requested_destroying_player_id
    ):
        raise GameLifecycleError(
            "Rule destruction source model must belong to the destroying player."
        )
    physical_source_id = state.unit_instance_id_for_model(requested_source_model_id)
    model_rules_unit_id = rules_unit_view_by_id(
        state=state,
        unit_instance_id=physical_source_id,
    ).unit_instance_id
    if model_rules_unit_id != canonical_source_id:
        raise GameLifecycleError("Rule destruction source model is not in the source rules unit.")
    return canonical_source_id, requested_source_model_id


def validate_non_attack_destruction_source_context(
    *,
    state: GameState,
    context: dict[str, JsonValue],
) -> None:
    if "source_model_instance_id" not in context:
        raise GameLifecycleError(
            "Rule destruction context requires source_model_instance_id attribution."
        )
    source_rules_unit_id = _optional_payload_identifier(
        context,
        "source_rules_unit_instance_id",
    )
    source_model_id = _optional_payload_identifier(context, "source_model_instance_id")
    if source_rules_unit_id is None:
        if source_model_id is not None:
            raise GameLifecycleError(
                "Rule destruction source model context requires a source rules unit."
            )
        return
    if source_model_id is None:
        return
    destroying_player_id = _payload_identifier(context, "destroying_player_id")
    if model_owner_player_id(state=state, model_instance_id=source_model_id) != (
        destroying_player_id
    ):
        raise GameLifecycleError("Rule destruction source model owner drift.")
    physical_source_id = state.unit_instance_id_for_model(source_model_id)
    current_source_views = current_rules_unit_views_for_identity(
        state=state,
        unit_instance_id=source_rules_unit_id,
    )
    if all(
        physical_source_id not in view.component_unit_instance_ids for view in current_source_views
    ):
        raise GameLifecycleError("Rule destruction source model rules-unit drift.")


def _payload_identifier(payload: dict[str, JsonValue], key: str) -> str:
    return _validate_identifier(key, payload.get(key))


def _optional_payload_identifier(
    payload: dict[str, JsonValue],
    key: str,
) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    return _validate_identifier(key, value)


_validate_identifier = IdentifierValidator(GameLifecycleError)
