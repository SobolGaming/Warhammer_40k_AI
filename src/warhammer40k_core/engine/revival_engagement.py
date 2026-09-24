"""Core revival eligibility uses enemy rules units at the pre-placement boundary."""

from __future__ import annotations

from typing import TypedDict, cast

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    ModelPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.physical_engagement import (
    geometry_models_are_physically_engaged,
    physical_geometry_models_for_rules_unit,
)
from warhammer40k_core.engine.rules_units import (
    rules_unit_view_from_armies,
    rules_unit_views_from_armies,
)
from warhammer40k_core.geometry.volume import Model
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_revival_2026_09 import (
    PACKAGE_HASH,
    REVIVAL_SOURCE_ID,
)


class RevivalEngagementPayload(TypedDict):
    rule_source_id: str
    source_package_hash: str
    target_unit_instance_id: str
    engaged_enemy_rules_unit_ids_before: list[str]
    returned_model_engaged_enemy_rules_unit_ids: list[str]


def validated_revival_engagement_payload(
    raw: JsonValue, *, target_unit_instance_id: str
) -> RevivalEngagementPayload:
    """Validate the closed evidence shape for source-specific healing consumers."""
    if not isinstance(raw, dict) or set(raw) != {
        "rule_source_id",
        "source_package_hash",
        "target_unit_instance_id",
        "engaged_enemy_rules_unit_ids_before",
        "returned_model_engaged_enemy_rules_unit_ids",
    }:
        raise GameLifecycleError("Revival engagement evidence shape is invalid.")
    sets: list[list[str]] = []
    for key in (
        "engaged_enemy_rules_unit_ids_before",
        "returned_model_engaged_enemy_rules_unit_ids",
    ):
        value = raw[key]
        if not isinstance(value, list) or any(type(item) is not str or not item for item in value):
            raise GameLifecycleError("Revival engagement requires canonical unit ID lists.")
        ids = cast(list[str], value)
        if ids != sorted(set(ids)):
            raise GameLifecycleError("Revival engagement unit IDs must be sorted and unique.")
        sets.append(ids)
    before, returned = sets
    expected = RevivalEngagementPayload(
        rule_source_id=REVIVAL_SOURCE_ID,
        source_package_hash=PACKAGE_HASH,
        target_unit_instance_id=target_unit_instance_id,
        engaged_enemy_rules_unit_ids_before=before,
        returned_model_engaged_enemy_rules_unit_ids=returned,
    )
    if raw != expected or set(returned) - set(before):
        raise GameLifecycleError("Revival engagement source or unit evidence drifted.")
    return expected


def revival_engagement_evidence(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    target_unit_instance_id: str,
    placement: ModelPlacement,
) -> RevivalEngagementPayload:
    target = rules_unit_view_from_armies(
        armies=scenario.armies, unit_instance_id=target_unit_instance_id
    )
    if target.unit_instance_id != target_unit_instance_id:
        raise GameLifecycleError("Revival engagement requires canonical rules-unit identity.")
    if (
        target.component_unit_id_for_model(placement.model_instance_id)
        != placement.unit_instance_id
    ):
        raise GameLifecycleError("Revival engagement model ownership drifted.")
    return validate_revival_engagement_geometry(
        target_unit_instance_id=target_unit_instance_id,
        existing_models=physical_geometry_models_for_rules_unit(
            scenario=scenario, unit_instance_id=target_unit_instance_id
        ),
        enemies={
            enemy.unit_instance_id: physical_geometry_models_for_rules_unit(
                scenario=scenario, unit_instance_id=enemy.unit_instance_id
            )
            for enemy in rules_unit_views_from_armies(armies=scenario.armies)
            if enemy.owner_player_id != target.owner_player_id
        },
        returned_model=geometry_model_for_placement(
            model=scenario.model_instance_for_placement(placement), placement=placement
        ),
        ruleset_descriptor=ruleset_descriptor,
    )


def validate_revival_engagement_geometry(
    *,
    target_unit_instance_id: str,
    existing_models: tuple[Model, ...],
    enemies: dict[str, tuple[Model, ...]],
    returned_model: Model,
    ruleset_descriptor: RulesetDescriptor,
) -> RevivalEngagementPayload:
    """Shared live/history predicate; retained bases are supplied by physical authority."""
    if returned_model.model_id in {model.model_id for model in existing_models}:
        raise GameLifecycleError("Revival engagement cannot authorize itself.")
    before = tuple(
        sorted(
            unit_id
            for unit_id, models in enemies.items()
            if geometry_models_are_physically_engaged(
                first_models=existing_models,
                second_models=models,
                ruleset_descriptor=ruleset_descriptor,
            )
        )
    )
    returned = tuple(
        sorted(
            unit_id
            for unit_id, models in enemies.items()
            if geometry_models_are_physically_engaged(
                first_models=(returned_model,),
                second_models=models,
                ruleset_descriptor=ruleset_descriptor,
            )
        )
    )
    if set(returned) - set(before):
        raise GameLifecycleError("Revived model engages a new enemy rules unit.")
    return RevivalEngagementPayload(
        rule_source_id=REVIVAL_SOURCE_ID,
        source_package_hash=PACKAGE_HASH,
        target_unit_instance_id=target_unit_instance_id,
        engaged_enemy_rules_unit_ids_before=list(before),
        returned_model_engaged_enemy_rules_unit_ids=list(returned),
    )
