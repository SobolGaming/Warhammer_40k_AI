"""Canonical Aircraft session shared by semantic and component checks."""

from dataclasses import replace

from tests.phase13b_shooting_declaration_helpers import shooting_lifecycle
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import BattlePhase


def aircraft_session(
    *, turn_owner: str = "player-b", fleet_size: int = 1, loaded_transport: bool = False
) -> LocalGameSession:
    aircraft_sheet = "core-transport" if loaded_transport else "core-vehicle-monster"
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    catalog = replace(
        catalog,
        datasheets=tuple(
            replace(
                sheet,
                model_profiles=tuple(
                    replace(
                        profile,
                        characteristics=tuple(
                            CharacteristicValue.source_dash(value.characteristic)
                            if value.characteristic
                            in {Characteristic.MOVEMENT, Characteristic.OBJECTIVE_CONTROL}
                            else value
                            for value in profile.characteristics
                        ),
                    )
                    for profile in sheet.model_profiles
                ),
                keywords=replace(
                    sheet.keywords,
                    keywords=(
                        *sheet.keywords.keywords,
                        "AIRCRAFT",
                        "FLY",
                        "HOVER",
                    ),
                ),
            )
            if sheet.datasheet_id == aircraft_sheet
            else sheet
            for sheet in catalog.datasheets
        ),
    )
    names = tuple(
        "aircraft" if index == 0 else f"aircraft-{index + 1}" for index in range(fleet_size)
    )
    lifecycle, _units = shooting_lifecycle(
        alpha_unit_ids=(*names, *(("passenger",) if loaded_transport else ())),
        game_id="order66-aircraft",
        alpha_datasheets=dict.fromkeys(names, (aircraft_sheet, aircraft_sheet, 1)),
        catalog=catalog,
    )
    state = lifecycle.state
    assert state is not None
    if loaded_transport:
        from warhammer40k_core.engine.transports import (
            TransportCapacityProfile,
            TransportCargoState,
        )

        assert state.battlefield_state is not None
        state.battlefield_state = state.battlefield_state.without_unit_placement(
            "army-alpha:passenger"
        )
        state.record_transport_cargo_state(
            TransportCargoState(
                player_id="player-a",
                transport_unit_instance_id="army-alpha:aircraft",
                capacity_profile=TransportCapacityProfile(
                    transport_datasheet_id=aircraft_sheet,
                    max_model_count=12,
                    allowed_keywords=("INFANTRY",),
                    source_id="test:order66:capacity",
                ),
                embarked_unit_instance_ids=("army-alpha:passenger",),
                phase_battle_round=1,
                started_phase_embarked_unit_instance_ids=("army-alpha:passenger",),
            )
        )
    state.active_player_id = turn_owner
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    return LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle.to_payload()))
