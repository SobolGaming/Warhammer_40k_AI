"""Physical source inventory for authenticating historical profile evaluations."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.army_mustering import muster_army
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_factory import ModelInstance, ModelInstancePayload

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameConfig, GameState


def historical_profile_models(
    *,
    state: GameState,
    config: GameConfig | None,
    requests: tuple[DecisionRequest, ...],
) -> tuple[dict[str, ModelInstance], dict[str, str], dict[str, str]]:
    models: dict[str, ModelInstance] = {}
    owners: dict[str, str] = {}
    physical_units: dict[str, str] = {}
    armies = tuple(state.army_definitions)
    if config is not None:
        armies = tuple(
            muster_army(
                catalog=config.army_catalog,
                request=request,
                model_geometries=config.model_geometries,
            )
            for request in config.army_muster_requests
        )
    for army in armies:
        for unit in army.units:
            for model in unit.own_models:
                models[model.model_instance_id] = model
                owners[model.model_instance_id] = army.player_id
                physical_units[model.model_instance_id] = unit.unit_instance_id
    original_ids: frozenset[str] = frozenset(models) if config is not None else frozenset()
    materialized: dict[str, ModelInstance] = {}
    for request in requests:
        if request.decision_type != "submit_catalog_model_materialization_placement":
            continue
        payload = request.payload
        if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
            raise GameLifecycleError("Materialized random profile inventory is malformed.")
        rows = payload["models"]
        if not isinstance(rows, list):
            raise GameLifecycleError("Materialized random profile inventory must be an array.")
        for row in rows:
            if not isinstance(row, dict):
                raise GameLifecycleError("Materialized random profile model is malformed.")
            model = ModelInstance.from_payload(cast(ModelInstancePayload, row))
            prior = materialized.get(model.model_instance_id)
            if model.model_instance_id in original_ids or (prior is not None and prior != model):
                raise GameLifecycleError("Materialized random profile model identity drifted.")
            materialized[model.model_instance_id] = model
            models[model.model_instance_id] = model
            if request.actor_id is None:
                raise GameLifecycleError("Materialized random profile model has no owner.")
            owners[model.model_instance_id] = request.actor_id
            physical_id = payload.get("source_unit_instance_id")
            if type(physical_id) is not str:
                raise GameLifecycleError("Materialized model physical owner is missing.")
            physical_units[model.model_instance_id] = physical_id
    return models, owners, physical_units
