"""Armed positive controls for existing after-fought and retained-cleanup tests."""

from dataclasses import replace
from typing import cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.weapon_profiles import AttackProfile, DamageProfile
from warhammer40k_core.engine.attack_completion_authority import completed_attack_sequence
from warhammer40k_core.engine.fight_order_records import (
    FightActivationSelection,
    FightActivationSelectionPayload,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle


def armed_fight_control_catalog() -> ArmyCatalog:
    """Equip the ranged-only infantry fixture for real, low-damage melee."""
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    original = next(item for item in catalog.wargear if item.wargear_id == "core-leader-blade")
    infantry_weapon = replace(
        original,
        wargear_id="order102-positive-infantry-blade",
        weapon_profiles=tuple(
            replace(
                profile,
                profile_id="order102-positive-infantry-blade-profile",
                attack_profile=AttackProfile.fixed(1),
                skill=CharacteristicValue.from_raw(Characteristic.WEAPON_SKILL, 6),
                strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 1),
                damage_profile=DamageProfile.fixed(1),
            )
            for profile in original.weapon_profiles
        ),
    )
    return replace(
        catalog,
        datasheets=tuple(
            replace(
                row,
                wargear_options=tuple(
                    replace(
                        option,
                        default_wargear_ids=(infantry_weapon.wargear_id,),
                        allowed_wargear_ids=(infantry_weapon.wargear_id,),
                    )
                    for option in row.wargear_options
                ),
            )
            if row.datasheet_id == "core-intercessor-like-infantry"
            else row
            for row in catalog.datasheets
        ),
        wargear=(*catalog.wargear, infantry_weapon),
    )


def assert_completed_melee(
    lifecycle: GameLifecycle, *, unit_instance_id: str | None = None
) -> None:
    """Require a real completed executor and HIT attempt before the timing window."""
    events = lifecycle.decision_controller.event_log.records
    fought = [
        event
        for event in events
        if event.event_type == "unit_has_fought"
        and isinstance(event.payload, dict)
        and isinstance(event.payload["activation_selection"], dict)
        and (
            unit_instance_id is None
            or event.payload["activation_selection"]["unit_instance_id"] == unit_instance_id
        )
    ]
    assert fought
    payload = fought[-1].payload
    assert isinstance(payload, dict)
    activation = FightActivationSelection.from_payload(
        cast(FightActivationSelectionPayload, payload["activation_selection"])
    )
    sequence_id = payload["attack_sequence_id"]
    assert isinstance(sequence_id, str)
    sequence = completed_attack_sequence(event_records=events, sequence_id=sequence_id)
    assert sequence.attacking_unit_instance_id == activation.unit_instance_id
    assert any(
        event.event_type == "attack_sequence_step"
        and isinstance(event.payload, dict)
        and event.payload.get("sequence_id") == sequence_id
        and event.payload.get("step") == "hit"
        for event in events
    )
