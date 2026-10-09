"""Canonical embarked infantry with one deliberately oversized catalog base."""

from dataclasses import replace

from tests.core_stratagem_helpers import _replace_unit_poses
from tests.disembark_eligibility_helpers import PASSENGER_ID, disembark_session
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.datasheet import BaseSizeDefinition, UnitCompositionDefinition
from warhammer40k_core.engine.battlefield_state import ModelPlacement, UnitPlacement
from warhammer40k_core.engine.damage_allocation import unit_by_id
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.transports import DisembarkModeKind
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.geometry.pose import Pose


def large_disembark_session(
    *, diameter: float = 5, modes: tuple[DisembarkModeKind, ...] = ()
) -> LocalGameSession:
    return disembark_session(modes, oversized_base_diameter_inches=diameter)


def large_disembark_config(config: GameConfig, *, diameter: float) -> GameConfig:
    catalog = config.army_catalog
    sheet = catalog.datasheet_by_id("core-intercessor-like-infantry")
    large = replace(
        sheet.model_profiles[0],
        model_profile_id="order55-large",
        base_size=BaseSizeDefinition.circular(diameter * 25.4),
    )
    small = replace(sheet.model_profiles[0], model_profile_id="order55-small")
    sheet = replace(
        sheet,
        datasheet_id="order55-passengers",
        model_profiles=(large, small),
        composition=(
            UnitCompositionDefinition(
                model_profile_id=large.model_profile_id, min_models=1, max_models=1
            ),
            UnitCompositionDefinition(
                model_profile_id=small.model_profile_id, min_models=4, max_models=4
            ),
        ),
        wargear_options=(),
    )
    catalog = replace(
        catalog,
        datasheets=(*catalog.datasheets, sheet),
        detachments=tuple(
            replace(d, unit_datasheet_ids=(*d.unit_datasheet_ids, sheet.datasheet_id))
            if d.detachment_id == "core-combined-arms"
            else d
            for d in catalog.detachments
        ),
    )
    alpha, beta = config.army_muster_requests
    selections = tuple(
        replace(
            selection,
            datasheet_id=sheet.datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(model_profile_id=large.model_profile_id, model_count=1),
                ModelProfileSelection(model_profile_id=small.model_profile_id, model_count=4),
            ),
        )
        if selection.unit_selection_id == "intercessor-unit-1"
        else selection
        for selection in alpha.unit_selections
    )
    return replace(
        config,
        army_catalog=catalog,
        army_muster_requests=(replace(alpha, unit_selections=selections), beta),
    )


def prepare_large_disembark_state(state: GameState) -> None:
    other_units = [
        u
        for army in state.army_definitions
        for u in army.units
        if u.unit_instance_id not in {PASSENGER_ID, "army-alpha:transport"}
    ]
    for index, other in enumerate(other_units):
        _replace_unit_poses(
            state,
            unit_instance_id=other.unit_instance_id,
            poses=tuple(
                Pose.at(30 + 2 * j, 25 + 4 * index) for j, _ in enumerate(other.own_models)
            ),
        )


def large_disembark_placement(session: LocalGameSession, *, gap: float = 0.5) -> UnitPlacement:
    state = session.lifecycle.state
    assert state is not None
    unit = unit_by_id(state=state, unit_instance_id=PASSENGER_ID)
    diameter = unit.own_models[0].base_size.diameter_mm
    assert diameter is not None
    poses = (
        Pose.at(10, 10 + 50 / 25.4 + diameter / 50.8 + gap),
        Pose.at(7, 11.5),
        Pose.at(7, 9),
        Pose.at(9, 7),
        Pose.at(11, 7),
    )
    return UnitPlacement(
        army_id="army-alpha",
        player_id="player-a",
        unit_instance_id=PASSENGER_ID,
        model_placements=tuple(
            ModelPlacement(
                army_id="army-alpha",
                player_id="player-a",
                unit_instance_id=PASSENGER_ID,
                model_instance_id=model.model_instance_id,
                pose=pose,
            )
            for model, pose in zip(unit.own_models, poses, strict=True)
        ),
    )
