"""Current rules-unit views and historical aliases of recorded partitions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_split_records import UnitSplitRecord

if TYPE_CHECKING:
    from warhammer40k_core.engine.army_mustering import ArmyDefinition
    from warhammer40k_core.engine.rules_units import RulesUnitComponentRole, RulesUnitView


def split_rules_unit_views(army: ArmyDefinition) -> tuple[RulesUnitView, ...]:
    from warhammer40k_core.engine.rules_units import RulesUnitComponent, RulesUnitView

    views: list[RulesUnitView] = []
    for record in army.unit_splits:
        for index in (0, 1):
            components: list[RulesUnitComponent] = []
            for origin in record.component_origins(index):
                role: RulesUnitComponentRole = "unit"
                formation = record.source_formation
                if formation is not None:
                    if origin.source_unit_instance_id == formation.bodyguard_unit_instance_id:
                        role = "bodyguard"
                    elif origin.source_unit_instance_id in formation.leader_unit_instance_ids:
                        role = "leader"
                    else:
                        role = "support"
                components.append(
                    RulesUnitComponent(
                        unit=army.unit_by_id(origin.unit_instance_id),
                        role=role,
                    )
                )
            views.append(
                RulesUnitView(
                    unit_instance_id=record.successor_id(index),
                    owner_player_id=army.player_id,
                    components=tuple(components),
                    split_record=record,
                    split_index=index,
                )
            )
    return tuple(views)


def record_has_historical_identity(record: UnitSplitRecord, identity: str) -> bool:
    return identity == record.source_unit_instance_id or any(
        identity == unit.unit_instance_id for unit in record.source_units
    )


def historical_split_successor_ids(
    *, armies: tuple[ArmyDefinition, ...], identity: str
) -> tuple[str, ...]:
    return tuple(
        record.successor_id(index)
        for army in armies
        for record in army.unit_splits
        if record_has_historical_identity(record, identity)
        for index in (0, 1)
        if identity == record.source_unit_instance_id
        or any(
            origin.source_unit_instance_id == identity for origin in record.component_origins(index)
        )
    )


def split_effect_predecessor_ids(
    *,
    armies: tuple[ArmyDefinition, ...],
    unit_instance_id: str,
) -> tuple[str, ...]:
    """Resolve an existing unit-bound effect without conflating successor identities."""
    for army in armies:
        for view in split_rules_unit_views(army):
            if unit_instance_id not in (view.unit_instance_id, *view.component_unit_instance_ids):
                continue
            record = view.split_record
            if record is None:
                raise GameLifecycleError("Split view is missing its source record.")
            return tuple(
                dict.fromkeys(
                    (
                        unit_instance_id,
                        record.source_unit_instance_id,
                        *(
                            component.unit.split_origin.source_unit_instance_id
                            for component in view.components
                            if component.unit.split_origin is not None
                            and (
                                unit_instance_id == view.unit_instance_id
                                or component.unit.unit_instance_id == unit_instance_id
                            )
                        ),
                    )
                )
            )
    return (unit_instance_id,)
