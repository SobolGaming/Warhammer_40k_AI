"""Facade kernel at Movement: real selected units and config, without executing setup."""

from collections import Counter

from tests.support.section02_fixtures import Section02Definitions

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import UnitMusterSelection
from warhammer40k_core.engine.phases.movement_handler import MovementPhaseHandler
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection


def movement_session(definitions: Section02Definitions, state: GameState) -> LocalGameSession:
    # Explicit non-roster kernel: metadata reconstructs native selections only;
    # no list validation/mustering is run or certified by this clause-level fixture.
    requests = tuple(
        ArmyMusterRequest(
            army_id=a.army_id,
            player_id=a.player_id,
            catalog_id=a.catalog_id,
            source_package_id=a.source_package_id,
            ruleset_id=a.ruleset_id,
            detachment_selection=a.detachment_selection,
            force_disposition_id=a.force_disposition_id,
            unit_selections=tuple(
                UnitMusterSelection(
                    unit_selection_id=u.unit_instance_id.split(":", 1)[1],
                    datasheet_id=u.datasheet_id,
                    model_profile_selections=tuple(
                        ModelProfileSelection(k, v)
                        for k, v in Counter(m.model_profile_id for m in u.own_models).items()
                    ),
                    wargear_selections=u.wargear_selections,
                )
                for u in a.units
            ),
        )
        for a in state.army_definitions
    )
    config = GameConfig(
        game_id=state.game_id,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        army_catalog=definitions.package.army_catalog,
        army_muster_requests=requests,
        player_ids=state.player_ids,
        turn_order=state.turn_order,
        fixed_secondary_mission_ids=("assassination", "bring-it-down"),
        allow_legacy_non_strict_rosters=True,
        model_geometries=definitions.package.model_geometries,
    )
    handler = MovementPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor, army_catalog=config.army_catalog
    )
    return LocalGameSession(
        GameLifecycle(state=state, _config=config, _movement_phase_handler=handler)
    )
