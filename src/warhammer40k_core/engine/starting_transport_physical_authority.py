"""Initial physical rows for cargo that never had a battlefield placement."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_mission_fight_on_death_physical_history import (
    PhysicalAuthorityState,
)
from warhammer40k_core.engine.transports import TransportCargoState, TransportCargoStatePayload

if TYPE_CHECKING:
    from warhammer40k_core.engine.event_log import EventRecord
    from warhammer40k_core.engine.game_state import GameState


def starting_transport_physical_authority(
    *, state: GameState, event_records: tuple[EventRecord, ...]
) -> dict[str, PhysicalAuthorityState]:
    """Bind setup cargo to its immutable roster manifest and starting wounds.

    Current cargo membership and current wounds cannot seed an earlier boundary:
    both may already have changed during destruction or disembarkation.
    """
    authority: dict[str, PhysicalAuthorityState] = {}
    seen: set[str] = set()
    for event in event_records:
        if event.event_type != "battle_formation_transport_manifest_recorded":
            continue
        payload = event.payload
        if not isinstance(payload, dict) or not isinstance(
            payload.get("transport_cargo_state"), dict
        ):
            raise GameLifecycleError("Starting cargo physical authority requires a manifest.")
        cargo = TransportCargoState.from_payload(
            cast(TransportCargoStatePayload, payload["transport_cargo_state"])
        )
        armies = tuple(a for a in state.army_definitions if a.army_id == payload.get("army_id"))
        if len(armies) != 1:
            raise GameLifecycleError("Starting cargo physical authority army drift.")
        army = armies[0]
        manifests = tuple(
            m
            for m in army.dedicated_transport_manifests
            if m.transport_unit_instance_id(army_id=army.army_id)
            == cargo.transport_unit_instance_id
        )
        if len(manifests) != 1:
            raise GameLifecycleError("Starting cargo physical authority lacks its roster manifest.")
        manifest = manifests[0]
        if (
            payload.get("game_id") != state.game_id
            or payload.get("player_id") != army.player_id
            or payload.get("setup_step") != "muster_armies"
            or payload.get("transport_unit_instance_id") != cargo.transport_unit_instance_id
            or cargo.player_id != army.player_id
            or cargo.capacity_profile.to_payload() != manifest.capacity_profile.to_payload()
            or cargo.embarked_unit_instance_ids
            != manifest.embarked_unit_instance_ids(army_id=army.army_id)
            or not cargo.embarked_unit_instance_ids
            or cargo.transport_unit_instance_id in seen
        ):
            raise GameLifecycleError("Starting cargo physical authority manifest drift.")
        seen.add(cargo.transport_unit_instance_id)
        for unit_id in cargo.embarked_unit_instance_ids:
            units = tuple(u for u in army.source_units() if u.unit_instance_id == unit_id)
            if len(units) != 1:
                raise GameLifecycleError("Starting cargo physical authority unit drift.")
            for model in units[0].own_models:
                if model.model_instance_id in authority:
                    raise GameLifecycleError("Starting cargo physical authority model duplicated.")
                authority[model.model_instance_id] = PhysicalAuthorityState(
                    presence="embarked", pose=None, wounds_remaining=model.initial_wounds
                )
    return authority
