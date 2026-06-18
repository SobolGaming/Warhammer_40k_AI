from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    PlacementError,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.geometry.volume import Model as GeometryModel

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


TURN_START_ENGAGEMENT_SNAPSHOT_EFFECT_KIND = "turn_start_engagement_snapshot"
TURN_START_ENGAGEMENT_SNAPSHOT_SOURCE_RULE_ID = "core-rules:turn-start-engagement-snapshot"


class TurnStartEngagementPairPayload(TypedDict):
    friendly_unit_instance_id: str
    enemy_unit_instance_id: str


def record_turn_start_engagement_snapshot(
    *,
    state: GameState,
    player_id: str,
) -> PersistingEffect | None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Turn-start engagement snapshot requires a GameState.")
    active_player_id = _validate_identifier("player_id", player_id)
    effect_id = _snapshot_effect_id(
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id=active_player_id,
    )
    existing = _turn_start_engagement_snapshot_effect(
        state,
        player_id=active_player_id,
        battle_round=state.battle_round,
    )
    if existing is not None:
        return existing
    scenario = _battlefield_scenario(state)
    friendly_placements = _placed_unit_placements_for_player(
        scenario=scenario,
        player_id=active_player_id,
    )
    if not friendly_placements:
        return None
    enemy_placements = _enemy_unit_placements_for_player(
        scenario=scenario,
        player_id=active_player_id,
    )
    pairs = _engaged_unit_pairs(
        scenario=scenario,
        friendly_placements=friendly_placements,
        enemy_placements=enemy_placements,
        horizontal_inches=state.runtime_ruleset_descriptor().engagement_policy.horizontal_inches,
        vertical_inches=state.runtime_ruleset_descriptor().engagement_policy.vertical_inches,
    )
    effect = PersistingEffect(
        effect_id=effect_id,
        source_rule_id=TURN_START_ENGAGEMENT_SNAPSHOT_SOURCE_RULE_ID,
        owner_player_id=active_player_id,
        target_unit_instance_ids=tuple(
            placement.unit_instance_id for placement in friendly_placements
        ),
        started_battle_round=state.battle_round,
        started_phase=BattlePhase.COMMAND,
        expiration=EffectExpiration.end_turn(
            battle_round=state.battle_round,
            player_id=active_player_id,
        ),
        effect_payload=validate_json_value(
            {
                "effect_kind": TURN_START_ENGAGEMENT_SNAPSHOT_EFFECT_KIND,
                "battle_round": state.battle_round,
                "player_id": active_player_id,
                "engaged_pairs": list(pairs),
            }
        ),
    )
    state.record_persisting_effect(effect)
    return effect


def turn_start_enemy_unit_ids_for_friendly_unit(
    state: GameState,
    *,
    player_id: str,
    battle_round: int,
    friendly_unit_instance_id: str,
) -> tuple[str, ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Turn-start engagement lookup requires a GameState.")
    active_player_id = _validate_identifier("player_id", player_id)
    friendly_unit_id = _validate_identifier("friendly_unit_instance_id", friendly_unit_instance_id)
    round_number = _validate_positive_int("battle_round", battle_round)
    effect = _turn_start_engagement_snapshot_effect(
        state,
        player_id=active_player_id,
        battle_round=round_number,
    )
    if effect is None:
        return ()
    payload = effect.effect_payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Turn-start engagement snapshot payload must be an object.")
    pairs = payload.get("engaged_pairs")
    if not isinstance(pairs, list):
        raise GameLifecycleError("Turn-start engagement snapshot pairs must be a list.")
    target_ids: list[str] = []
    for pair in pairs:
        if not isinstance(pair, dict):
            raise GameLifecycleError("Turn-start engagement snapshot pair must be an object.")
        friendly_id = _validate_identifier(
            "friendly_unit_instance_id",
            pair.get("friendly_unit_instance_id"),
        )
        enemy_id = _validate_identifier(
            "enemy_unit_instance_id",
            pair.get("enemy_unit_instance_id"),
        )
        if friendly_id == friendly_unit_id:
            target_ids.append(enemy_id)
    return tuple(sorted(set(target_ids)))


def _turn_start_engagement_snapshot_effect(
    state: GameState,
    *,
    player_id: str,
    battle_round: int,
) -> PersistingEffect | None:
    active_player_id = _validate_identifier("player_id", player_id)
    round_number = _validate_positive_int("battle_round", battle_round)
    matches = tuple(
        effect
        for effect in state.persisting_effects
        if effect.owner_player_id == active_player_id
        and _effect_payload_kind(effect) == TURN_START_ENGAGEMENT_SNAPSHOT_EFFECT_KIND
        and _effect_payload_battle_round(effect) == round_number
    )
    if len(matches) > 1:
        raise GameLifecycleError("Multiple turn-start engagement snapshots exist for turn.")
    return matches[0] if matches else None


def _effect_payload_kind(effect: PersistingEffect) -> str | None:
    payload = effect.effect_payload
    if not isinstance(payload, dict):
        return None
    value = payload.get("effect_kind")
    return value if type(value) is str else None


def _effect_payload_battle_round(effect: PersistingEffect) -> int | None:
    payload = effect.effect_payload
    if not isinstance(payload, dict):
        return None
    value = payload.get("battle_round")
    return value if type(value) is int else None


def _snapshot_effect_id(*, game_id: str, battle_round: int, player_id: str) -> str:
    return (
        f"{TURN_START_ENGAGEMENT_SNAPSHOT_SOURCE_RULE_ID}:"
        f"{_validate_identifier('game_id', game_id)}:"
        f"round-{_validate_positive_int('battle_round', battle_round)}:"
        f"{_validate_identifier('player_id', player_id)}"
    )


def _battlefield_scenario(state: GameState) -> BattlefieldScenario:
    if state.battlefield_state is None:
        raise GameLifecycleError("Turn-start engagement snapshot requires battlefield_state.")
    return BattlefieldScenario(
        battlefield_state=state.battlefield_state,
        armies=tuple(state.army_definitions),
    )


def _placed_unit_placements_for_player(
    *,
    scenario: BattlefieldScenario,
    player_id: str,
) -> tuple[UnitPlacement, ...]:
    active_player_id = _validate_identifier("player_id", player_id)
    for placed_army in scenario.battlefield_state.placed_armies:
        if placed_army.player_id == active_player_id:
            return tuple(placed_army.unit_placements)
    return ()


def _enemy_unit_placements_for_player(
    *,
    scenario: BattlefieldScenario,
    player_id: str,
) -> tuple[UnitPlacement, ...]:
    active_player_id = _validate_identifier("player_id", player_id)
    enemy_placements: list[UnitPlacement] = []
    for placed_army in scenario.battlefield_state.placed_armies:
        if placed_army.player_id == active_player_id:
            continue
        enemy_placements.extend(placed_army.unit_placements)
    return tuple(enemy_placements)


def _engaged_unit_pairs(
    *,
    scenario: BattlefieldScenario,
    friendly_placements: tuple[UnitPlacement, ...],
    enemy_placements: tuple[UnitPlacement, ...],
    horizontal_inches: float,
    vertical_inches: float,
) -> tuple[TurnStartEngagementPairPayload, ...]:
    pairs: list[TurnStartEngagementPairPayload] = []
    for friendly_placement in friendly_placements:
        friendly_models = _geometry_models_for_unit_placement(
            scenario=scenario,
            unit_placement=friendly_placement,
        )
        for enemy_placement in enemy_placements:
            enemy_models = _geometry_models_for_unit_placement(
                scenario=scenario,
                unit_placement=enemy_placement,
            )
            if _model_groups_are_engaged(
                first_models=friendly_models,
                second_models=enemy_models,
                horizontal_inches=horizontal_inches,
                vertical_inches=vertical_inches,
            ):
                pairs.append(
                    {
                        "friendly_unit_instance_id": friendly_placement.unit_instance_id,
                        "enemy_unit_instance_id": enemy_placement.unit_instance_id,
                    }
                )
    return tuple(
        sorted(
            pairs,
            key=lambda pair: (
                pair["friendly_unit_instance_id"],
                pair["enemy_unit_instance_id"],
            ),
        )
    )


def _geometry_models_for_unit_placement(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
) -> tuple[GeometryModel, ...]:
    models: list[GeometryModel] = []
    for placement in unit_placement.model_placements:
        try:
            model = scenario.model_instance_for_placement(placement)
        except PlacementError as exc:
            raise GameLifecycleError("Turn-start engagement model placement is invalid.") from exc
        models.append(geometry_model_for_placement(model=model, placement=placement))
    return tuple(models)


def _model_groups_are_engaged(
    *,
    first_models: tuple[GeometryModel, ...],
    second_models: tuple[GeometryModel, ...],
    horizontal_inches: float,
    vertical_inches: float,
) -> bool:
    return any(
        first_model.is_within_engagement_range(
            second_model,
            horizontal_inches=horizontal_inches,
            vertical_inches=vertical_inches,
        )
        for first_model in first_models
        for second_model in second_models
    )


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an int.")
    if value <= 0:
        raise GameLifecycleError(f"{field_name} must be greater than zero.")
    return value


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return stripped
