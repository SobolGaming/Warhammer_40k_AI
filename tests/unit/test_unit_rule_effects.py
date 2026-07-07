from __future__ import annotations

from typing import cast

import pytest

from warhammer40k_core.engine.effects import (
    GENERIC_RULE_EFFECT_KIND,
    EffectExpiration,
    PersistingEffect,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.unit_rule_effects import (
    charge_transit_through_non_vehicle_monster_models_allowed,
    embark_transport_forbidden_by_effects,
    embark_transport_forbidden_effect_source_ids,
    fire_overwatch_forbidden_by_effects,
    movement_bonus_inches_from_effects,
    movement_model_transit_permissions_from_effects,
    movement_transit_through_terrain_features_allowed,
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


def test_fire_overwatch_and_embark_effect_helpers_return_source_backed_results() -> None:
    assert not fire_overwatch_forbidden_by_effects(
        (
            _effect("overwatch-missing", payload={}),
            _effect(
                "overwatch-other-owner",
                owner_player_id="player-b",
                payload={"fire_overwatch_forbidden": True},
            ),
        ),
        owner_player_id="player-a",
    )
    assert fire_overwatch_forbidden_by_effects(
        (
            _effect("overwatch-false", payload={"fire_overwatch_forbidden": False}),
            _effect("overwatch-true", payload={"fire_overwatch_forbidden": True}),
        ),
        owner_player_id="player-a",
    )

    with pytest.raises(GameLifecycleError, match="Fire Overwatch effect payload must be an object"):
        fire_overwatch_forbidden_by_effects(
            (_effect("overwatch-non-object", payload="bad"),),
            owner_player_id="player-a",
        )
    with pytest.raises(GameLifecycleError, match="effect value must be a bool"):
        fire_overwatch_forbidden_by_effects(
            (_effect("overwatch-string", payload={"fire_overwatch_forbidden": "yes"}),),
            owner_player_id="player-a",
        )

    embark_effects = (
        _effect(
            "embark-b", source_rule_id="source-b", payload={"embark_transport_forbidden": True}
        ),
        _effect(
            "embark-a", source_rule_id="source-a", payload={"embark_transport_forbidden": True}
        ),
        _effect(
            "embark-other-owner",
            owner_player_id="player-b",
            source_rule_id="source-other",
            payload={"embark_transport_forbidden": True},
        ),
        _effect("embark-false", payload={"embark_transport_forbidden": False}),
        _effect("embark-missing", payload={}),
    )
    assert embark_transport_forbidden_effect_source_ids(
        embark_effects,
        owner_player_id="player-a",
    ) == ("source-a", "source-b")
    assert embark_transport_forbidden_by_effects(embark_effects, owner_player_id="player-a")

    with pytest.raises(GameLifecycleError, match="Embark restriction effect payload"):
        embark_transport_forbidden_effect_source_ids(
            (_effect("embark-non-object", payload="bad"),),
            owner_player_id="player-a",
        )
    with pytest.raises(GameLifecycleError, match="effect value must be a bool"):
        embark_transport_forbidden_effect_source_ids(
            (_effect("embark-string", payload={"embark_transport_forbidden": "yes"}),),
            owner_player_id="player-a",
        )


def test_charge_transit_through_non_vehicle_monster_models_requires_supported_rule_effect() -> None:
    assert charge_transit_through_non_vehicle_monster_models_allowed(
        (
            _generic_rule_effect(
                "charge-transit",
                parameters=(
                    ("permission", "move_through_models"),
                    ("movement_modes", ["normal", "charge"]),
                    ("model_allegiance", "enemy"),
                    ("excluded_model_keyword_any", ["MONSTER", "VEHICLE"]),
                ),
            ),
        ),
        owner_player_id="player-a",
    )
    assert not charge_transit_through_non_vehicle_monster_models_allowed(
        (
            _generic_rule_effect(
                "charge-transit-other-owner",
                owner_player_id="player-b",
                parameters=(
                    ("permission", "move_through_models"),
                    ("movement_modes", ["charge"]),
                    ("model_allegiance", "enemy"),
                    ("excluded_model_keyword_any", ["MONSTER", "VEHICLE"]),
                ),
            ),
            _generic_rule_effect(
                "charge-transit-wrong-permission",
                parameters=(
                    ("permission", "move_through_terrain"),
                    ("movement_modes", ["charge"]),
                    ("model_allegiance", "enemy"),
                    ("excluded_model_keyword_any", ["MONSTER", "VEHICLE"]),
                ),
            ),
            _generic_rule_effect(
                "charge-transit-no-charge",
                parameters=(
                    ("permission", "move_through_models"),
                    ("movement_modes", ["normal"]),
                    ("model_allegiance", "enemy"),
                    ("excluded_model_keyword_any", ["MONSTER", "VEHICLE"]),
                ),
            ),
            _generic_rule_effect(
                "charge-transit-wrong-allegiance",
                parameters=(
                    ("permission", "move_through_models"),
                    ("movement_modes", ["charge"]),
                    ("model_allegiance", "friendly"),
                    ("excluded_model_keyword_any", ["MONSTER", "VEHICLE"]),
                ),
            ),
            _generic_rule_effect(
                "charge-transit-missing-keyword",
                parameters=(
                    ("permission", "move_through_models"),
                    ("movement_modes", ["charge"]),
                    ("model_allegiance", "any"),
                    ("excluded_model_keyword_any", ["MONSTER"]),
                ),
            ),
        ),
        owner_player_id="player-a",
    )

    malformed_cases: tuple[tuple[str, JsonValue, str], ...] = (
        ("non-object", "bad", "Movement transit effect payload must be an object"),
        ("wrong-effect-kind", {"effect_kind": "other", "effect": {}}, ""),
        (
            "missing-effect-object",
            {"effect_kind": GENERIC_RULE_EFFECT_KIND, "effect": "bad"},
            "requires effect object",
        ),
        (
            "missing-parameters-list",
            {
                "effect_kind": GENERIC_RULE_EFFECT_KIND,
                "effect": {"kind": "movement_transit_permission"},
            },
            "parameters must be a list",
        ),
        (
            "parameter-not-object",
            {
                "effect_kind": GENERIC_RULE_EFFECT_KIND,
                "effect": {
                    "kind": "movement_transit_permission",
                    "parameters": ["bad"],
                },
            },
            "parameter must be an object",
        ),
        (
            "parameter-key-invalid",
            {
                "effect_kind": GENERIC_RULE_EFFECT_KIND,
                "effect": {
                    "kind": "movement_transit_permission",
                    "parameters": [{"key": 1, "value": "move_through_models"}],
                },
            },
            "parameter key is invalid",
        ),
        (
            "movement-modes-not-list",
            {
                "effect_kind": GENERIC_RULE_EFFECT_KIND,
                "effect": {
                    "kind": "movement_transit_permission",
                    "parameters": [
                        {"key": "permission", "value": "move_through_models"},
                        {"key": "movement_modes", "value": "charge"},
                    ],
                },
            },
            "movement_modes must be a list",
        ),
        (
            "movement-mode-not-string",
            {
                "effect_kind": GENERIC_RULE_EFFECT_KIND,
                "effect": {
                    "kind": "movement_transit_permission",
                    "parameters": [
                        {"key": "permission", "value": "move_through_models"},
                        {"key": "movement_modes", "value": [1]},
                    ],
                },
            },
            "movement_modes entries must be strings",
        ),
    )
    for effect_id, payload, message in malformed_cases:
        if not message:
            assert not charge_transit_through_non_vehicle_monster_models_allowed(
                (_effect(effect_id, payload=payload),),
                owner_player_id="player-a",
            )
            continue
        with pytest.raises(GameLifecycleError, match=message):
            charge_transit_through_non_vehicle_monster_models_allowed(
                (_effect(effect_id, payload=payload),),
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


def test_terrain_transit_effects_validate_modes_keywords_and_required_keyword_gate() -> None:
    base_parameters: tuple[tuple[str, JsonValue], ...] = (
        ("permission", "move_horizontally_through_terrain_features"),
        ("movement_modes", ["normal", "advance"]),
        ("terrain_features", True),
    )
    assert movement_transit_through_terrain_features_allowed(
        (
            _generic_rule_effect(
                "terrain-transit",
                parameters=(*base_parameters, ("required_keyword", "INFANTRY")),
            ),
        ),
        owner_player_id="player-a",
        movement_mode="normal",
        unit_keywords=("INFANTRY",),
    )
    assert not movement_transit_through_terrain_features_allowed(
        (
            _generic_rule_effect(
                "terrain-transit-other-owner",
                owner_player_id="player-b",
                parameters=base_parameters,
            ),
            _effect(
                "terrain-transit-wrong-effect-kind",
                payload={"effect_kind": "other", "effect": {}},
            ),
            _generic_rule_effect(
                "terrain-transit-wrong-kind",
                effect_kind="different_kind",
                parameters=base_parameters,
            ),
            _generic_rule_effect(
                "terrain-transit-wrong-permission",
                parameters=(
                    ("permission", "move_through_models"),
                    ("movement_modes", ["normal"]),
                    ("terrain_features", True),
                ),
            ),
            _generic_rule_effect(
                "terrain-transit-missing-keyword",
                parameters=(*base_parameters, ("required_keyword", "INFANTRY")),
            ),
            _generic_rule_effect(
                "terrain-transit-wrong-mode",
                parameters=base_parameters,
            ),
            _generic_rule_effect(
                "terrain-transit-flag-false",
                parameters=(
                    ("permission", "move_horizontally_through_terrain_features"),
                    ("movement_modes", ["normal"]),
                    ("terrain_features", False),
                ),
            ),
        ),
        owner_player_id="player-a",
        movement_mode="charge",
        unit_keywords=("BEAST",),
    )
    assert movement_transit_through_terrain_features_allowed(
        (_generic_rule_effect("terrain-transit-no-required-keyword", parameters=base_parameters),),
        owner_player_id="player-a",
        movement_mode="normal",
        unit_keywords=("BEAST",),
    )
    assert movement_transit_through_terrain_features_allowed(
        (
            _generic_rule_effect(
                "terrain-transit-direct-permission",
                parameters=(
                    ("permission", "move_through_terrain_features"),
                    ("movement_modes", ["fall_back"]),
                    ("terrain_features", True),
                ),
            ),
        ),
        owner_player_id="player-a",
        movement_mode="fall_back",
        unit_keywords=("BEAST",),
    )

    with pytest.raises(GameLifecycleError, match="Rule effect keyword helpers require a tuple"):
        movement_transit_through_terrain_features_allowed(
            (),
            owner_player_id="player-a",
            movement_mode="normal",
            unit_keywords=cast(tuple[str, ...], ["INFANTRY"]),
        )
    with pytest.raises(GameLifecycleError, match="keyword helper entries must be strings"):
        movement_transit_through_terrain_features_allowed(
            (),
            owner_player_id="player-a",
            movement_mode="normal",
            unit_keywords=cast(tuple[str, ...], (1,)),
        )
    with pytest.raises(GameLifecycleError, match="required_keyword must be a string"):
        movement_transit_through_terrain_features_allowed(
            (
                _generic_rule_effect(
                    "terrain-transit-bad-required-keyword",
                    parameters=(*base_parameters, ("required_keyword", 1)),
                ),
            ),
            owner_player_id="player-a",
            movement_mode="normal",
            unit_keywords=("INFANTRY",),
        )


def _effect(
    effect_id: str,
    *,
    payload: JsonValue,
    owner_player_id: str = "player-a",
    source_rule_id: str = "source-rule",
) -> PersistingEffect:
    return PersistingEffect(
        effect_id=f"effect:{effect_id}",
        source_rule_id=source_rule_id,
        owner_player_id=owner_player_id,
        target_unit_instance_ids=("unit-a",),
        started_battle_round=1,
        started_phase=BattlePhase.MOVEMENT,
        expiration=EffectExpiration.end_phase(
            battle_round=1,
            phase=BattlePhase.MOVEMENT,
            player_id=owner_player_id,
        ),
        effect_payload=payload,
    )


def _generic_rule_effect(
    effect_id: str,
    *,
    owner_player_id: str = "player-a",
    effect_kind: str = "movement_transit_permission",
    parameters: tuple[tuple[str, JsonValue], ...],
) -> PersistingEffect:
    return _effect(
        effect_id,
        owner_player_id=owner_player_id,
        payload={
            "effect_kind": GENERIC_RULE_EFFECT_KIND,
            "effect": {
                "kind": effect_kind,
                "parameters": [{"key": key, "value": value} for key, value in parameters],
            },
        },
    )
