from __future__ import annotations

import json
from typing import cast

import pytest

from warhammer40k_core.core.attached_unit import AttachedUnit, AttachedUnitError
from warhammer40k_core.core.unit import MovementStatus, Unit, UnitError, UnitMember
from warhammer40k_core.core.unit_group import UnitGroup, UnitGroupPayload
from warhammer40k_core.engine.event_log import EventLog


def _member(model_id: str, wounds: int = 1) -> UnitMember:
    return UnitMember.ready(model_id=model_id, name=model_id.title(), wounds=wounds)


def _unit(unit_id: str, *model_ids: str) -> Unit:
    return Unit(
        unit_id=unit_id,
        name=unit_id.title(),
        own_models=tuple(_member(model_id) for model_id in model_ids),
    )


def test_leader_joins_bodyguard_as_attached_unit() -> None:
    bodyguard = _unit("intercessors", "intercessor-1", "intercessor-2")
    leader = _unit("captain", "captain-1")
    attached = AttachedUnit(
        attached_unit_id="captain-intercessors",
        bodyguard=bodyguard,
        leaders=(leader,),
    )
    group = UnitGroup.attached(attached)

    assert attached.stable_identity() == "attached-unit:captain-intercessors"
    assert group.stable_identity() == "unit-group:attached:captain-intercessors"
    assert group.unit_ids() == ("intercessors", "captain")
    assert group.all_model_ids() == ("intercessor-1", "intercessor-2", "captain-1")


def test_joined_support_units_are_included_in_group_model_views() -> None:
    bodyguard = _unit("bodyguard", "bodyguard-1")
    leader = _unit("leader", "leader-1")
    support = _unit("support-servitors", "servitor-1", "servitor-2")
    group = UnitGroup.attached(
        AttachedUnit(
            attached_unit_id="joined-group",
            bodyguard=bodyguard,
            leaders=(leader,),
            support_units=(support,),
        )
    )

    assert group.unit_ids() == ("bodyguard", "leader", "support-servitors")
    assert group.all_model_ids() == ("bodyguard-1", "leader-1", "servitor-1", "servitor-2")


def test_attached_unit_moves_as_one_rules_unit() -> None:
    group = UnitGroup.attached(
        AttachedUnit(
            attached_unit_id="move-group",
            bodyguard=_unit("bodyguard", "bodyguard-1", "bodyguard-2"),
            leaders=(_unit("leader", "leader-1"),),
        )
    )

    assert group.model_ids_for_movement() == ("bodyguard-1", "bodyguard-2", "leader-1")


def test_movement_model_ids_exclude_destroyed_models_across_attached_group() -> None:
    bodyguard = Unit(
        unit_id="bodyguard",
        name="Bodyguard",
        own_models=(
            UnitMember("bodyguard-1", "Bodyguard 1", starting_wounds=1, wounds_remaining=1),
            UnitMember("bodyguard-2", "Bodyguard 2", starting_wounds=1, wounds_remaining=0),
        ),
    )
    leader = _unit("leader", "leader-1")
    group = UnitGroup.attached(
        AttachedUnit(attached_unit_id="move-group", bodyguard=bodyguard, leaders=(leader,))
    )

    assert group.all_model_ids() == ("bodyguard-1", "bodyguard-2", "leader-1")
    assert group.model_ids_for_movement() == ("bodyguard-1", "leader-1")


def test_damage_allocation_sees_alive_models_across_attached_group() -> None:
    bodyguard = Unit(
        unit_id="bodyguard",
        name="Bodyguard",
        own_models=(
            _member("bodyguard-1"),
            UnitMember("bodyguard-2", "Bodyguard 2", starting_wounds=1, wounds_remaining=0),
        ),
    )
    leader = _unit("leader", "leader-1")
    group = UnitGroup.attached(
        AttachedUnit(attached_unit_id="damage-group", bodyguard=bodyguard, leaders=(leader,))
    )

    assert group.alive_model_ids() == ("bodyguard-1", "leader-1")
    assert group.model_ids_for_damage_allocation() == ("bodyguard-1", "leader-1")


def test_event_logging_uses_group_aware_payload() -> None:
    group = UnitGroup.attached(
        AttachedUnit(
            attached_unit_id="event-group",
            bodyguard=_unit("bodyguard", "bodyguard-1"),
            leaders=(_unit("leader", "leader-1"),),
        )
    )
    event_log = EventLog()

    record = event_log.append("unit_group_selected", group.event_subject_payload())
    blob = json.dumps(record.to_payload(), sort_keys=True)

    assert record.payload == {
        "unit_group_id": "unit-group:attached:event-group",
        "unit_ids": ["bodyguard", "leader"],
        "model_ids": ["bodyguard-1", "leader-1"],
        "alive_model_ids": ["bodyguard-1", "leader-1"],
        "movement_status": "ready",
    }
    assert "<" not in blob
    assert "object at 0x" not in blob


def test_line_of_sight_and_targeting_see_attached_group_models() -> None:
    group = UnitGroup.attached(
        AttachedUnit(
            attached_unit_id="target-group",
            bodyguard=_unit("bodyguard", "bodyguard-1"),
            leaders=(_unit("leader", "leader-1"),),
            support_units=(_unit("support", "support-1"),),
        )
    )

    assert group.model_ids_for_line_of_sight() == ("bodyguard-1", "leader-1", "support-1")
    assert group.targetable_model_ids() == ("bodyguard-1", "leader-1", "support-1")


def test_movement_status_applies_to_whole_attached_group() -> None:
    group = UnitGroup.attached(
        AttachedUnit(
            attached_unit_id="moved-group",
            bodyguard=_unit("bodyguard", "bodyguard-1"),
            leaders=(_unit("leader", "leader-1"),),
            support_units=(_unit("support", "support-1"),),
        )
    )

    moved = group.with_movement_status(MovementStatus.NORMAL_MOVE)

    assert moved.movement_status is MovementStatus.NORMAL_MOVE
    assert tuple(unit.movement_status for unit in moved.units()) == (
        MovementStatus.NORMAL_MOVE,
        MovementStatus.NORMAL_MOVE,
        MovementStatus.NORMAL_MOVE,
    )
    with pytest.raises(AttachedUnitError):
        AttachedUnit(
            attached_unit_id="bad-status",
            bodyguard=_unit("bodyguard", "bodyguard-1").with_movement_status(
                MovementStatus.NORMAL_MOVE
            ),
            leaders=(_unit("leader", "leader-1"),),
        )


def test_unit_group_payload_round_trips_without_object_reprs() -> None:
    group = UnitGroup.attached(
        AttachedUnit(
            attached_unit_id="payload-group",
            bodyguard=_unit("bodyguard", "bodyguard-1"),
            leaders=(_unit("leader", "leader-1"),),
        )
    )
    blob = json.dumps(group.to_payload(), sort_keys=True)

    assert "<" not in blob
    assert "object at 0x" not in blob
    assert (
        UnitGroup.from_payload(cast(UnitGroupPayload, json.loads(blob))).to_payload()
        == group.to_payload()
    )


def test_units_reject_ambiguous_or_duplicate_identity() -> None:
    with pytest.raises(UnitError):
        UnitMember.ready("model:bad", "Bad")
    with pytest.raises(UnitError):
        Unit(unit_id="unit:bad", name="Bad", own_models=(_member("bad-1"),))
    with pytest.raises(UnitError):
        Unit(unit_id="empty", name="Empty", own_models=())
    with pytest.raises(UnitError):
        Unit(
            unit_id="duplicate-models",
            name="Duplicate Models",
            own_models=(_member("model-1"), _member("model-1")),
        )
    with pytest.raises(AttachedUnitError):
        AttachedUnit(
            attached_unit_id="duplicate-units",
            bodyguard=_unit("bodyguard", "bodyguard-1"),
            leaders=(_unit("bodyguard", "leader-1"),),
        )
    with pytest.raises(AttachedUnitError):
        AttachedUnit(
            attached_unit_id="duplicate-group-models",
            bodyguard=_unit("bodyguard", "shared-model"),
            leaders=(_unit("leader", "shared-model"),),
        )
