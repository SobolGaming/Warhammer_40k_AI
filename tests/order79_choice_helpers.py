"""Existing source-backed generic reserve-choice consumer at a Core boundary."""

from tests.setup_completion_helpers import record_primary_turn_start_evidence_for_fixture
from tests.support.catalog_package_fixtures import (
    config_backed_flesh_hounds_armies,
    flesh_hounds_package,
)
from tests.support.catalog_runtime_fixtures import (
    battle_state_with_armies,
    flesh_hounds_battlefield_state,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.game_state import (
    GameConfig,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import BattlePhase


def reserve_choice_session() -> LocalGameSession:
    package = flesh_hounds_package()
    catalog, requests, armies = config_backed_flesh_hounds_armies(
        package=package, enemy_unit_selection_id="order79-opponent"
    )
    army, enemy = armies
    state = battle_state_with_armies(
        armies=armies,
        battlefield=flesh_hounds_battlefield_state(
            army=army,
            unit=army.units[0],
            enemy_army=enemy,
            enemy_unit=enemy.units[0],
            enemy_x=40.0,
        ),
        active_player_id=enemy.player_id,
        phase=BattlePhase.FIGHT,
    )
    config = GameConfig(
        game_id=state.game_id,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=catalog,
        army_muster_requests=requests,
        player_ids=state.player_ids,
        turn_order=state.turn_order,
        fixed_secondary_mission_ids=("assassination", "bring_it_down"),
        mission_setup=state.mission_setup,
        allow_legacy_non_strict_rosters=True,
        model_geometries=package.model_geometries,
    )
    for player_id in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player_id=player_id,
                mode=SecondaryMissionMode.FIXED,
                fixed_mission_ids=config.fixed_secondary_mission_ids,
            )
        )
    return LocalGameSession(
        lifecycle=GameLifecycle.from_payload(
            GameLifecycle(
                state=state,
                _config=config,
                decision_controller=record_primary_turn_start_evidence_for_fixture(state),
            ).to_payload()
        )
    )
