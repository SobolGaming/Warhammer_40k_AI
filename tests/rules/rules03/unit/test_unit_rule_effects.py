from __future__ import annotations

from typing import cast

from tests.shared.category_migration.unit_rule_effects import (
    GENERIC_RULE_EFFECT_KIND,
    BattlePhase,
    EffectExpiration,
    GameLifecycleError,
    JsonValue,
    PersistingEffect,
    _effect,
    _generic_rule_effect,
    charge_transit_through_non_vehicle_monster_models_allowed,
    embark_transport_forbidden_by_effects,
    embark_transport_forbidden_effect_source_ids,
    fire_overwatch_forbidden_by_effects,
    movement_bonus_inches_from_effects,
    movement_model_transit_permissions_from_effects,
    movement_transit_through_terrain_features_allowed,
    pytest,
)


def test_unit_rule_effect_helpers_sum_filter_and_validate_simple_effect_payloads() -> None:
    movement_effects = (
        _effect(
            "movement-a",
            owner_player_id="player-a",
            payload={"movement_bonus_inches": 2},
        ),
        _effect(
            "movement-b",
            owner_player_id="player-a",
            payload={"movement_bonus_inches": 3},
        ),
        _effect(
            "movement-ignored-owner",
            owner_player_id="player-b",
            payload={"movement_bonus_inches": 9},
        ),
        _effect("movement-missing", owner_player_id="player-a", payload={}),
    )
    assert (
        movement_bonus_inches_from_effects(
            movement_effects,
            owner_player_id="player-a",
        )
        == 5
    )
    assert (
        movement_bonus_inches_from_effects(
            movement_effects,
            owner_player_id="player-b",
        )
        == 9
    )

    with pytest.raises(GameLifecycleError, match="tuple of effects"):
        movement_bonus_inches_from_effects(
            cast(tuple[PersistingEffect, ...], []),
            owner_player_id="player-a",
        )
    with pytest.raises(GameLifecycleError, match="PersistingEffect values"):
        movement_bonus_inches_from_effects(
            cast(tuple[PersistingEffect, ...], (object(),)),
            owner_player_id="player-a",
        )
    with pytest.raises(GameLifecycleError, match="payload must be an object"):
        movement_bonus_inches_from_effects(
            (_effect("movement-non-object", payload="bad"),),
            owner_player_id="player-a",
        )
    with pytest.raises(GameLifecycleError, match="must be an int"):
        movement_bonus_inches_from_effects(
            (_effect("movement-string", payload={"movement_bonus_inches": "2"}),),
            owner_player_id="player-a",
        )
    with pytest.raises(GameLifecycleError, match="must not be negative"):
        movement_bonus_inches_from_effects(
            (_effect("movement-negative", payload={"movement_bonus_inches": -1}),),
            owner_player_id="player-a",
        )


def test_model_transit_effects_expose_exclusions_engagement_and_auto_pass() -> None:
    effects = (
        _generic_rule_effect(
            "model-transit",
            parameters=(
                ("permission", "move_through_models"),
                ("movement_modes", ["normal", "advance", "fall_back"]),
                ("model_allegiance", "any"),
                ("excluded_model_keyword_any", ["TITANIC"]),
                ("enemy_engagement_range_transit", True),
                ("enemy_engagement_range_end_allowed", False),
                ("desperate_escape_tests_auto_passed", True),
            ),
        ),
        _generic_rule_effect(
            "model-transit-other-owner",
            owner_player_id="player-b",
            parameters=(
                ("permission", "move_through_models"),
                ("movement_modes", ["fall_back"]),
                ("model_allegiance", "any"),
                ("excluded_model_keyword_any", []),
            ),
        ),
    )

    permissions = movement_model_transit_permissions_from_effects(
        effects,
        owner_player_id="player-a",
        movement_mode="fall_back",
        model_allegiance="enemy",
    )

    assert len(permissions) == 1
    assert permissions[0].movement_modes == ("normal", "advance", "fall_back")
    assert permissions[0].model_allegiance == "any"
    assert permissions[0].excluded_model_keyword_any == ("TITANIC",)
    assert permissions[0].enemy_engagement_range_transit
    assert not permissions[0].enemy_engagement_range_end_allowed
    assert permissions[0].desperate_escape_tests_auto_passed
    assert (
        movement_model_transit_permissions_from_effects(
            effects,
            owner_player_id="player-a",
            movement_mode="charge",
            model_allegiance="enemy",
        )
        == ()
    )
    with pytest.raises(GameLifecycleError, match="must be a bool"):
        movement_model_transit_permissions_from_effects(
            (
                _generic_rule_effect(
                    "model-transit-bad-bool",
                    parameters=(
                        ("permission", "move_through_models"),
                        ("movement_modes", ["normal"]),
                        ("model_allegiance", "enemy"),
                        ("excluded_model_keyword_any", []),
                        ("desperate_escape_tests_auto_passed", "yes"),
                    ),
                ),
            ),
            owner_player_id="player-a",
            movement_mode="normal",
            model_allegiance="enemy",
        )


__all__: list[str] = []
__all__ += ["GENERIC_RULE_EFFECT_KIND", "BattlePhase", "EffectExpiration", "JsonValue"]
__all__ += ["charge_transit_through_non_vehicle_monster_models_allowed"]
__all__ += ["embark_transport_forbidden_by_effects"]
__all__ += ["embark_transport_forbidden_effect_source_ids", "fire_overwatch_forbidden_by_effects"]
__all__ += ["movement_transit_through_terrain_features_allowed"]
