from __future__ import annotations

import hashlib
from typing import TypedDict

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import BaseSizeDefinition, DatasheetAbilityDescriptor
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.decision_request import (
    DecisionOptionPayload,
    DecisionRequest,
)
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.objective_control import model_objective_control_characteristic
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance

PROJECTION_SCHEMA_VERSION = "game-view-v3-phase18a"
RULES_CATALOG_VIEW_SCHEMA_VERSION = "rules-catalog-view-v2"

_DATACARD_CHARACTERISTICS: tuple[tuple[Characteristic, str], ...] = (
    (Characteristic.MOVEMENT, "M"),
    (Characteristic.TOUGHNESS, "T"),
    (Characteristic.SAVE, "SV"),
    (Characteristic.INVULNERABLE_SAVE, "InSv"),
    (Characteristic.WOUNDS, "W"),
    (Characteristic.LEADERSHIP, "LD"),
    (Characteristic.OBJECTIVE_CONTROL, "OC"),
)


class DecisionRequestViewPayload(TypedDict):
    request_id: str
    decision_type: str
    actor_id: str | None
    payload: JsonValue
    options: list[DecisionOptionPayload]
    is_parameterized: bool


class RulesCatalogReferencePayload(TypedDict):
    projection_schema: str
    catalog_id: str
    ruleset_id: JsonValue
    source_package_id: str
    source_hash: str


class BaseSizeDisplayPayload(TypedDict):
    base_size_id: str
    kind: str
    diameter_mm: float | None
    length_mm: float | None
    width_mm: float | None


class DatasheetAbilityDisplayPayload(TypedDict):
    ability_id: str
    datasheet_id: str
    display_name: str
    source_id: str
    support: str
    timing_tags: list[str]
    parameter_tokens: list[str]
    profile: JsonValue


class DatasheetDisplayPayload(TypedDict):
    datasheet_id: str
    display_name: str
    content_scope: str
    keywords: list[str]
    faction_keywords: list[str]
    model_profile_ids: list[str]
    wargear_option_ids: list[str]
    abilities: list[DatasheetAbilityDisplayPayload]
    source_ids: list[str]


class ModelProfileDisplayPayload(TypedDict):
    model_profile_id: str
    datasheet_id: str
    display_name: str
    base_size_id: str
    base_characteristics: dict[str, JsonValue]
    source_ids: list[str]


class WeaponProfileDisplayPayload(TypedDict):
    weapon_profile_id: str
    wargear_id: str
    display_name: str
    profile: JsonValue


class WargearDisplayPayload(TypedDict):
    wargear_id: str
    display_name: str
    weapon_profile_ids: list[str]
    profile: JsonValue


class FactionDisplayPayload(TypedDict):
    faction_id: str
    display_name: str
    content_scope: str
    faction_keywords: list[str]
    army_rule_ids: list[str]
    source_ids: list[str]


class DetachmentDisplayPayload(TypedDict):
    detachment_id: str
    display_name: str
    faction_id: str
    content_scope: str
    enhancement_ids: list[str]
    stratagem_ids: list[str]
    source_ids: list[str]


class EnhancementDisplayPayload(TypedDict):
    enhancement_id: str
    display_name: str
    source_id: str
    content_scope: str
    points: int | None
    subtypes: list[str]


class WargearOptionDisplayPayload(TypedDict):
    option_id: str
    datasheet_id: str
    model_profile_id: str
    default_wargear_ids: list[str]
    allowed_wargear_ids: list[str]
    min_selections: int
    max_selections: int


class RulesCatalogViewPayload(TypedDict):
    projection_schema: str
    catalog_id: str
    ruleset_id: JsonValue
    source_package_id: str
    source_hash: str
    datasheet_display_by_id: dict[str, DatasheetDisplayPayload]
    model_profile_display_by_id: dict[str, ModelProfileDisplayPayload]
    wargear_display_by_id: dict[str, WargearDisplayPayload]
    weapon_profile_display_by_id: dict[str, WeaponProfileDisplayPayload]
    faction_display_by_id: dict[str, FactionDisplayPayload]
    detachment_display_by_id: dict[str, DetachmentDisplayPayload]
    enhancement_display_by_id: dict[str, EnhancementDisplayPayload]
    wargear_option_display_by_id: dict[str, WargearOptionDisplayPayload]
    base_size_display_by_id: dict[str, BaseSizeDisplayPayload]


class SourceMetadataDisplayPayload(TypedDict):
    catalog_id: str
    source_package_id: str
    source_ids: list[str]


class RedactionDisplayPayload(TypedDict):
    hidden: bool
    reason: str | None


class CharacteristicDisplayPayload(TypedDict):
    characteristic: str
    label: str
    value_kind: str
    raw: int | None
    base: int | None
    final: int | None
    display_value: str | None
    applied_modifier_ids: list[str]
    redaction: RedactionDisplayPayload


class ModifierTargetDisplayPayload(TypedDict):
    target_kind: str
    model_instance_id: str
    characteristic: str
    characteristic_label: str


class VisibleModifierDisplayPayload(TypedDict):
    modifier_id: str
    source_kind: str
    source_id: str
    target: ModifierTargetDisplayPayload
    applies_status: str
    public_label: str
    operation_text: str


class UnitDisplayPayload(TypedDict):
    unit_instance_id: str
    owner_player_id: str | None
    visible_status: str
    unit_display_name: str | None
    datasheet_id: str | None
    source_metadata: SourceMetadataDisplayPayload | None
    keywords: list[str]
    faction_keywords: list[str]
    model_instance_ids: list[str]
    selected_wargear_ids: list[str]
    redaction: RedactionDisplayPayload


class ModelDisplayPayload(TypedDict):
    model_instance_id: str
    unit_instance_id: str
    datasheet_id: str | None
    model_profile_id: str | None
    model_profile_name: str | None
    visible_status: str
    model_display_name: str | None
    wargear_ids: list[str]
    base_size: BaseSizeDisplayPayload | None
    geometry: JsonValue
    wounds_remaining: int | None
    starting_wounds: int | None
    base_characteristics: dict[str, CharacteristicDisplayPayload]
    current_characteristics: dict[str, CharacteristicDisplayPayload]
    visible_modifiers: list[VisibleModifierDisplayPayload]
    source_metadata: SourceMetadataDisplayPayload | None
    redaction: RedactionDisplayPayload


class GameViewPayload(TypedDict):
    projection_schema: str
    projection_state_hash: str
    rules_catalog: RulesCatalogReferencePayload
    viewer_player_id: str
    game_id: str
    stage: str
    battle_round: int
    active_player_id: str | None
    current_setup_step: str | None
    current_battle_phase: str | None
    player_ids: list[str]
    battlefield_state: JsonValue
    mission_setup: JsonValue
    public_secondary_mission_choices: list[JsonValue]
    public_secondary_mission_card_states: list[JsonValue]
    public_command_point_ledgers: list[JsonValue]
    public_victory_point_ledgers: list[JsonValue]
    public_stratagem_use_records: list[JsonValue]
    unit_display_by_id: dict[str, UnitDisplayPayload]
    model_display_by_id: dict[str, ModelDisplayPayload]
    pending_decision: DecisionRequestViewPayload | None
    pending_proposal: JsonValue
    event_count: int


def project_rules_catalog_view(*, catalog: ArmyCatalog) -> RulesCatalogViewPayload:
    if type(catalog) is not ArmyCatalog:
        raise GameLifecycleError("Rules catalog projection requires an ArmyCatalog.")
    base_size_display_by_id: dict[str, BaseSizeDisplayPayload] = {}
    model_profile_display_by_id: dict[str, ModelProfileDisplayPayload] = {}
    datasheet_display_by_id: dict[str, DatasheetDisplayPayload] = {}
    wargear_option_display_by_id: dict[str, WargearOptionDisplayPayload] = {}
    wargear_display_by_id: dict[str, WargearDisplayPayload] = {}
    weapon_profile_display_by_id: dict[str, WeaponProfileDisplayPayload] = {}

    for datasheet in catalog.datasheets:
        model_profile_ids: list[str] = []
        wargear_option_ids: list[str] = []
        for profile in datasheet.model_profiles:
            base_size_id = _base_size_id(profile.model_profile_id)
            model_profile_display: ModelProfileDisplayPayload = {
                "model_profile_id": profile.model_profile_id,
                "datasheet_id": datasheet.datasheet_id,
                "display_name": profile.name,
                "base_size_id": base_size_id,
                "base_characteristics": _datacard_characteristics(profile.characteristics),
                "source_ids": list(profile.source_ids),
            }
            _insert_unique(
                base_size_display_by_id,
                base_size_id,
                _base_size_display(base_size_id=base_size_id, base_size=profile.base_size),
                field_name="base_size_display_by_id",
            )
            _insert_unique(
                model_profile_display_by_id,
                profile.model_profile_id,
                model_profile_display,
                field_name="model_profile_display_by_id",
            )
            model_profile_ids.append(profile.model_profile_id)
        for option in datasheet.wargear_options:
            wargear_option_display: WargearOptionDisplayPayload = {
                "option_id": option.option_id,
                "datasheet_id": datasheet.datasheet_id,
                "model_profile_id": option.model_profile_id,
                "default_wargear_ids": list(option.default_wargear_ids),
                "allowed_wargear_ids": list(option.allowed_wargear_ids),
                "min_selections": option.min_selections,
                "max_selections": option.max_selections,
            }
            _insert_unique(
                wargear_option_display_by_id,
                option.option_id,
                wargear_option_display,
                field_name="wargear_option_display_by_id",
            )
            wargear_option_ids.append(option.option_id)
        datasheet_display_by_id[datasheet.datasheet_id] = {
            "datasheet_id": datasheet.datasheet_id,
            "display_name": datasheet.name,
            "content_scope": datasheet.content_scope.value,
            "keywords": list(datasheet.keywords.keywords),
            "faction_keywords": list(datasheet.keywords.faction_keywords),
            "model_profile_ids": sorted(model_profile_ids),
            "wargear_option_ids": sorted(wargear_option_ids),
            "abilities": [
                {
                    "ability_id": ability.ability_id,
                    "datasheet_id": datasheet.datasheet_id,
                    "display_name": ability.name,
                    "source_id": ability.source_id,
                    "support": ability.support.value,
                    "timing_tags": list(ability.timing_tags),
                    "parameter_tokens": list(ability.parameter_tokens),
                    "profile": validate_json_value(_datasheet_ability_display_profile(ability)),
                }
                for ability in datasheet.abilities
            ],
            "source_ids": list(datasheet.source_ids),
        }

    for item in catalog.wargear:
        wargear_display: WargearDisplayPayload = {
            "wargear_id": item.wargear_id,
            "display_name": item.name,
            "weapon_profile_ids": [profile.profile_id for profile in item.weapon_profiles],
            "profile": validate_json_value(item.to_payload()),
        }
        _insert_unique(
            wargear_display_by_id,
            item.wargear_id,
            wargear_display,
            field_name="wargear_display_by_id",
        )
        for weapon_profile in item.weapon_profiles:
            weapon_profile_display: WeaponProfileDisplayPayload = {
                "weapon_profile_id": weapon_profile.profile_id,
                "wargear_id": item.wargear_id,
                "display_name": weapon_profile.name,
                "profile": validate_json_value(weapon_profile.to_payload()),
            }
            _insert_unique(
                weapon_profile_display_by_id,
                weapon_profile.profile_id,
                weapon_profile_display,
                field_name="weapon_profile_display_by_id",
            )

    payload: RulesCatalogViewPayload = {
        "projection_schema": RULES_CATALOG_VIEW_SCHEMA_VERSION,
        "catalog_id": catalog.catalog_id,
        "ruleset_id": validate_json_value(catalog.ruleset_id.to_payload()),
        "source_package_id": catalog.source_package_id,
        "source_hash": _rules_catalog_source_hash(catalog),
        "datasheet_display_by_id": datasheet_display_by_id,
        "model_profile_display_by_id": model_profile_display_by_id,
        "wargear_display_by_id": wargear_display_by_id,
        "weapon_profile_display_by_id": weapon_profile_display_by_id,
        "faction_display_by_id": {
            faction.faction_id: {
                "faction_id": faction.faction_id,
                "display_name": faction.name,
                "content_scope": faction.content_scope.value,
                "faction_keywords": list(faction.faction_keywords),
                "army_rule_ids": list(faction.army_rule_ids),
                "source_ids": list(faction.source_ids),
            }
            for faction in catalog.factions
        },
        "detachment_display_by_id": {
            detachment.detachment_id: {
                "detachment_id": detachment.detachment_id,
                "display_name": detachment.name,
                "faction_id": detachment.faction_id,
                "content_scope": detachment.content_scope.value,
                "enhancement_ids": list(detachment.enhancement_ids),
                "stratagem_ids": list(detachment.stratagem_ids),
                "source_ids": list(detachment.source_ids),
            }
            for detachment in catalog.detachments
        },
        "enhancement_display_by_id": {
            enhancement.enhancement_id: {
                "enhancement_id": enhancement.enhancement_id,
                "display_name": enhancement.name,
                "source_id": enhancement.source_id,
                "content_scope": enhancement.content_scope.value,
                "points": enhancement.points,
                "subtypes": [subtype.value for subtype in enhancement.subtypes],
            }
            for enhancement in catalog.enhancements
        },
        "wargear_option_display_by_id": wargear_option_display_by_id,
        "base_size_display_by_id": base_size_display_by_id,
    }
    return payload


def project_game_view(
    *,
    lifecycle: GameLifecycle,
    viewer_player_id: str,
) -> GameViewPayload:
    if type(lifecycle) is not GameLifecycle:
        raise GameLifecycleError("Game projection requires a GameLifecycle.")
    state = lifecycle.state
    if state is None:
        raise GameLifecycleError("Game projection requires a started lifecycle.")
    catalog = lifecycle.config.army_catalog
    viewer = _validate_viewer(state=state, viewer_player_id=viewer_player_id)
    pending_request = _pending_request(lifecycle)
    secondary_mission_choices_revealed = state.secondary_mission_choices_are_revealed()
    battlefield_payload = (
        None if state.battlefield_state is None else state.battlefield_state.to_payload()
    )
    mission_payload = None if state.mission_setup is None else state.mission_setup.to_payload()
    setup_step = state.current_setup_step
    battle_phase = state.current_battle_phase
    rules_catalog = _rules_catalog_reference(catalog)
    unit_display_by_id, model_display_by_id = _live_display_maps(
        state=state,
        catalog=catalog,
        viewer_player_id=viewer,
    )
    event_count = len(lifecycle.decision_controller.event_log.records)
    payload: GameViewPayload = {
        "projection_schema": PROJECTION_SCHEMA_VERSION,
        "projection_state_hash": "",
        "rules_catalog": rules_catalog,
        "viewer_player_id": viewer,
        "game_id": state.game_id,
        "stage": state.stage.value,
        "battle_round": state.battle_round,
        "active_player_id": state.active_player_id,
        "current_setup_step": None if setup_step is None else setup_step.value,
        "current_battle_phase": None if battle_phase is None else battle_phase.value,
        "player_ids": list(state.player_ids),
        "battlefield_state": validate_json_value(battlefield_payload),
        "mission_setup": validate_json_value(mission_payload),
        "public_secondary_mission_choices": [
            validate_json_value(
                choice.to_public_payload(
                    viewer_player_id=viewer,
                    secondary_mission_choices_revealed=secondary_mission_choices_revealed,
                )
            )
            for choice in state.secondary_mission_choices
        ],
        "public_secondary_mission_card_states": [
            validate_json_value(card_state_payload)
            for card_state_payload in state.public_secondary_mission_card_states(
                viewer_player_id=viewer
            )
        ],
        "public_command_point_ledgers": [
            validate_json_value(ledger.to_payload()) for ledger in state.command_point_ledgers
        ],
        "public_victory_point_ledgers": [
            validate_json_value(
                ledger.to_public_payload(
                    viewer_player_id=viewer,
                    secondary_mission_choices_revealed=secondary_mission_choices_revealed,
                )
            )
            for ledger in state.victory_point_ledgers
        ],
        "public_stratagem_use_records": [
            validate_json_value(record.to_payload()) for record in state.stratagem_use_records
        ],
        "unit_display_by_id": unit_display_by_id,
        "model_display_by_id": model_display_by_id,
        "pending_decision": None
        if pending_request is None
        else _decision_request_view(pending_request, viewer_player_id=viewer),
        "pending_proposal": None
        if pending_request is None
        else _proposal_view(pending_request, viewer_player_id=viewer),
        "event_count": event_count,
    }
    payload["projection_state_hash"] = _projection_state_hash(payload)
    return payload


def _live_display_maps(
    *,
    state: GameState,
    catalog: ArmyCatalog,
    viewer_player_id: str,
) -> tuple[dict[str, UnitDisplayPayload], dict[str, ModelDisplayPayload]]:
    placed_unit_ids = _placed_unit_ids(state)
    unit_display_by_id: dict[str, UnitDisplayPayload] = {}
    model_display_by_id: dict[str, ModelDisplayPayload] = {}
    for army in state.army_definitions:
        for unit in army.units:
            if army.player_id != viewer_player_id and unit.unit_instance_id not in placed_unit_ids:
                continue
            visible = army.player_id == viewer_player_id or unit.unit_instance_id in placed_unit_ids
            unit_display_by_id[unit.unit_instance_id] = _unit_display_payload(
                state=state,
                catalog=catalog,
                army=army,
                unit=unit,
                visible=visible,
            )
            for model in unit.own_models:
                model_display_by_id[model.model_instance_id] = _model_display_payload(
                    state=state,
                    catalog=catalog,
                    unit=unit,
                    model=model,
                    visible=visible,
                )
    return unit_display_by_id, model_display_by_id


def _unit_display_payload(
    *,
    state: GameState,
    catalog: ArmyCatalog,
    army: ArmyDefinition,
    unit: UnitInstance,
    visible: bool,
) -> UnitDisplayPayload:
    if not visible:
        return {
            "unit_instance_id": unit.unit_instance_id,
            "owner_player_id": None,
            "visible_status": "hidden",
            "unit_display_name": None,
            "datasheet_id": None,
            "source_metadata": None,
            "keywords": [],
            "faction_keywords": [],
            "model_instance_ids": [],
            "selected_wargear_ids": [],
            "redaction": _redaction(reason="not_visible_to_viewer"),
        }
    return {
        "unit_instance_id": unit.unit_instance_id,
        "owner_player_id": army.player_id,
        "visible_status": "visible",
        "unit_display_name": unit.name,
        "datasheet_id": unit.datasheet_id,
        "source_metadata": _source_metadata(
            state=state,
            catalog=catalog,
            source_ids=unit.datasheet_source_ids,
        ),
        "keywords": list(unit.keywords),
        "faction_keywords": list(unit.faction_keywords),
        "model_instance_ids": [model.model_instance_id for model in unit.own_models],
        "selected_wargear_ids": [
            wargear_id
            for selection in unit.wargear_selections
            for wargear_id in selection.wargear_ids
        ],
        "redaction": _visible_redaction(),
    }


def _model_display_payload(
    *,
    state: GameState,
    catalog: ArmyCatalog,
    unit: UnitInstance,
    model: ModelInstance,
    visible: bool,
) -> ModelDisplayPayload:
    if not visible:
        unknown_characteristics = _unknown_datacard_characteristics(
            model_instance_id=model.model_instance_id
        )
        return {
            "model_instance_id": model.model_instance_id,
            "unit_instance_id": unit.unit_instance_id,
            "datasheet_id": None,
            "model_profile_id": None,
            "model_profile_name": None,
            "visible_status": "hidden",
            "model_display_name": None,
            "wargear_ids": [],
            "base_size": None,
            "geometry": None,
            "wounds_remaining": None,
            "starting_wounds": None,
            "base_characteristics": unknown_characteristics,
            "current_characteristics": unknown_characteristics,
            "visible_modifiers": [],
            "source_metadata": None,
            "redaction": _redaction(reason="not_visible_to_viewer"),
        }
    base_characteristics = _model_characteristic_display_map(
        state=state,
        unit=unit,
        model=model,
        use_base_values=True,
    )
    current_characteristics = _model_characteristic_display_map(
        state=state,
        unit=unit,
        model=model,
        use_base_values=False,
    )
    return {
        "model_instance_id": model.model_instance_id,
        "unit_instance_id": unit.unit_instance_id,
        "datasheet_id": model.datasheet_id,
        "model_profile_id": model.model_profile_id,
        "model_profile_name": model.name,
        "visible_status": "visible",
        "model_display_name": model.name,
        "wargear_ids": list(model.wargear_ids),
        "base_size": _base_size_display(
            base_size_id=_base_size_id(model.model_profile_id),
            base_size=model.base_size,
        ),
        "geometry": validate_json_value(model.geometry.to_payload()),
        "wounds_remaining": model.wounds_remaining,
        "starting_wounds": model.starting_wounds,
        "base_characteristics": base_characteristics,
        "current_characteristics": current_characteristics,
        "visible_modifiers": _visible_modifier_traces(
            model=model,
            current_characteristics=current_characteristics,
        ),
        "source_metadata": _source_metadata(
            state=state, catalog=catalog, source_ids=model.source_ids
        ),
        "redaction": _visible_redaction(),
    }


def _model_characteristic_display_map(
    *,
    state: GameState,
    unit: UnitInstance,
    model: ModelInstance,
    use_base_values: bool,
) -> dict[str, CharacteristicDisplayPayload]:
    by_characteristic = {value.characteristic: value for value in model.characteristics}
    payload: dict[str, CharacteristicDisplayPayload] = {}
    for characteristic, label in _DATACARD_CHARACTERISTICS:
        value = _model_display_characteristic(
            by_characteristic=by_characteristic,
            state=state,
            unit=unit,
            model=model,
            characteristic=characteristic,
            use_base_values=use_base_values,
        )
        payload[label] = _characteristic_display_payload(
            value=value,
            label=label,
            use_base_values=use_base_values,
        )
    return payload


def _model_display_characteristic(
    *,
    by_characteristic: dict[Characteristic, CharacteristicValue],
    state: GameState,
    unit: UnitInstance,
    model: ModelInstance,
    characteristic: Characteristic,
    use_base_values: bool,
) -> CharacteristicValue:
    if characteristic is Characteristic.OBJECTIVE_CONTROL:
        return model_objective_control_characteristic(
            model,
            battle_shocked=(
                False if use_base_values else unit.unit_instance_id in state.battle_shocked_unit_ids
            ),
        )
    value = by_characteristic.get(characteristic)
    if value is None:
        raise GameLifecycleError("Model display projection missing datacard characteristic.")
    return value


def _characteristic_display_payload(
    *,
    value: CharacteristicValue,
    label: str,
    use_base_values: bool,
) -> CharacteristicDisplayPayload:
    if type(value) is not CharacteristicValue:
        raise GameLifecycleError("Characteristic display requires CharacteristicValue.")
    final = value.base if use_base_values else value.final
    return {
        "characteristic": value.characteristic.value,
        "label": label,
        "value_kind": value.value_kind.value,
        "raw": value.raw,
        "base": value.base,
        "final": final,
        "display_value": _characteristic_display_value(
            characteristic=value.characteristic,
            value=final,
            is_dash=value.is_dash,
        ),
        "applied_modifier_ids": [] if use_base_values else list(value.applied_modifier_ids),
        "redaction": _visible_redaction(),
    }


def _unknown_datacard_characteristics(
    *,
    model_instance_id: str,
) -> dict[str, CharacteristicDisplayPayload]:
    _validate_identifier("model_instance_id", model_instance_id)
    return {
        label: {
            "characteristic": characteristic.value,
            "label": label,
            "value_kind": "unknown",
            "raw": None,
            "base": None,
            "final": None,
            "display_value": None,
            "applied_modifier_ids": [],
            "redaction": _redaction(reason="not_visible_to_viewer"),
        }
        for characteristic, label in _DATACARD_CHARACTERISTICS
    }


def _visible_modifier_traces(
    *,
    model: ModelInstance,
    current_characteristics: dict[str, CharacteristicDisplayPayload],
) -> list[VisibleModifierDisplayPayload]:
    traces: list[VisibleModifierDisplayPayload] = []
    for label in sorted(current_characteristics):
        characteristic = current_characteristics[label]
        for modifier_id in characteristic["applied_modifier_ids"]:
            traces.append(
                {
                    "modifier_id": modifier_id,
                    "source_kind": "engine_resolved_characteristic",
                    "source_id": modifier_id,
                    "target": {
                        "target_kind": "model_characteristic",
                        "model_instance_id": model.model_instance_id,
                        "characteristic": characteristic["characteristic"],
                        "characteristic_label": label,
                    },
                    "applies_status": "applied",
                    "public_label": modifier_id,
                    "operation_text": (
                        f"Engine-resolved modifier {modifier_id} applies to {label}."
                    ),
                }
            )
    return traces


def _datacard_characteristics(
    characteristics: tuple[CharacteristicValue, ...],
) -> dict[str, JsonValue]:
    by_characteristic = {value.characteristic: value for value in characteristics}
    payload: dict[str, JsonValue] = {}
    for characteristic, label in _DATACARD_CHARACTERISTICS:
        value = by_characteristic.get(characteristic)
        if value is None:
            raise GameLifecycleError("Catalog projection missing datacard characteristic.")
        payload[label] = validate_json_value(
            _characteristic_display_payload(
                value=value,
                label=label,
                use_base_values=True,
            )
        )
    return payload


def _datasheet_ability_display_profile(
    ability: DatasheetAbilityDescriptor,
) -> dict[str, JsonValue]:
    if type(ability) is not DatasheetAbilityDescriptor:
        raise GameLifecycleError("Ability display profile requires a datasheet ability descriptor.")
    return {
        "ability_id": ability.ability_id,
        "name": ability.name,
        "source_id": ability.source_id,
        "support": ability.support.value,
        "timing_tags": list(ability.timing_tags),
        "parameter_tokens": list(ability.parameter_tokens),
    }


def _characteristic_display_value(
    *,
    characteristic: Characteristic,
    value: int,
    is_dash: bool,
) -> str:
    if is_dash:
        return "-"
    if characteristic is Characteristic.MOVEMENT:
        return f'{value}"'
    if characteristic in {
        Characteristic.SAVE,
        Characteristic.INVULNERABLE_SAVE,
        Characteristic.LEADERSHIP,
    }:
        return f"{value}+"
    return str(value)


def _base_size_display(
    *,
    base_size_id: str,
    base_size: BaseSizeDefinition,
) -> BaseSizeDisplayPayload:
    if type(base_size) is not BaseSizeDefinition:
        raise GameLifecycleError("Base-size display requires BaseSizeDefinition.")
    return {
        "base_size_id": _validate_identifier("base_size_id", base_size_id),
        "kind": base_size.kind.value,
        "diameter_mm": base_size.diameter_mm,
        "length_mm": base_size.length_mm,
        "width_mm": base_size.width_mm,
    }


def _source_metadata(
    *,
    state: GameState,
    catalog: ArmyCatalog,
    source_ids: tuple[str, ...],
) -> SourceMetadataDisplayPayload:
    if type(state) is not GameState:
        raise GameLifecycleError("Source metadata display requires GameState.")
    if type(catalog) is not ArmyCatalog:
        raise GameLifecycleError("Source metadata display requires ArmyCatalog.")
    return {
        "catalog_id": catalog.catalog_id,
        "source_package_id": catalog.source_package_id,
        "source_ids": list(source_ids),
    }


def _placed_unit_ids(state: GameState) -> frozenset[str]:
    if state.battlefield_state is None:
        return frozenset()
    return frozenset(
        unit_placement.unit_instance_id
        for placed_army in state.battlefield_state.placed_armies
        for unit_placement in placed_army.unit_placements
    )


def _rules_catalog_reference(catalog: ArmyCatalog) -> RulesCatalogReferencePayload:
    if type(catalog) is not ArmyCatalog:
        raise GameLifecycleError("Rules catalog reference requires ArmyCatalog.")
    return {
        "projection_schema": RULES_CATALOG_VIEW_SCHEMA_VERSION,
        "catalog_id": catalog.catalog_id,
        "ruleset_id": validate_json_value(catalog.ruleset_id.to_payload()),
        "source_package_id": catalog.source_package_id,
        "source_hash": _rules_catalog_source_hash(catalog),
    }


def _rules_catalog_source_hash(catalog: ArmyCatalog) -> str:
    encoded = canonical_json(catalog.to_payload()).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _projection_state_hash(payload: GameViewPayload) -> str:
    hash_payload = {
        "projection_schema": payload["projection_schema"],
        "rules_catalog": payload["rules_catalog"],
        "viewer_player_id": payload["viewer_player_id"],
        "game_id": payload["game_id"],
        "stage": payload["stage"],
        "battle_round": payload["battle_round"],
        "active_player_id": payload["active_player_id"],
        "current_setup_step": payload["current_setup_step"],
        "current_battle_phase": payload["current_battle_phase"],
        "battlefield_state": payload["battlefield_state"],
        "unit_display_by_id": payload["unit_display_by_id"],
        "model_display_by_id": payload["model_display_by_id"],
        "event_count": payload["event_count"],
    }
    encoded = canonical_json(hash_payload).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _base_size_id(model_profile_id: str) -> str:
    return f"base-size:{_validate_identifier('model_profile_id', model_profile_id)}"


def _visible_redaction() -> RedactionDisplayPayload:
    return {"hidden": False, "reason": None}


def _redaction(*, reason: str) -> RedactionDisplayPayload:
    return {"hidden": True, "reason": _validate_identifier("redaction reason", reason)}


def _insert_unique[T](
    target: dict[str, T],
    key: str,
    value: T,
    *,
    field_name: str,
) -> None:
    if key in target:
        raise GameLifecycleError(f"{field_name} contains duplicate key: {key}.")
    target[key] = value


def _decision_request_view(
    request: DecisionRequest,
    *,
    viewer_player_id: str,
) -> DecisionRequestViewPayload:
    if _secret_request_hidden_from_viewer(request=request, viewer_player_id=viewer_player_id):
        return {
            "request_id": request.request_id,
            "decision_type": _redacted_decision_type(request.decision_type),
            "actor_id": request.actor_id,
            "payload": {
                "secret": True,
                "hidden": True,
            },
            "options": [],
            "is_parameterized": False,
        }
    return {
        "request_id": request.request_id,
        "decision_type": request.decision_type,
        "actor_id": request.actor_id,
        "payload": request.payload,
        "options": [option.to_payload() for option in request.options],
        "is_parameterized": request.is_parameterized_submission_request(),
    }


def _proposal_view(
    request: DecisionRequest,
    *,
    viewer_player_id: str,
) -> JsonValue:
    if _secret_request_hidden_from_viewer(request=request, viewer_player_id=viewer_player_id):
        return None
    if not request.is_parameterized_submission_request():
        return None
    if not isinstance(request.payload, dict):
        raise GameLifecycleError("Parameterized DecisionRequest payload must be an object.")
    proposal_request = request.payload.get("proposal_request")
    if not isinstance(proposal_request, dict):
        raise GameLifecycleError("Parameterized DecisionRequest payload missing proposal_request.")
    return validate_json_value(_metadata_bearing_proposal_request(request, proposal_request))


def _metadata_bearing_proposal_request(
    request: DecisionRequest,
    proposal_request: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    metadata: dict[str, JsonValue] = {
        "request_id": request.request_id,
        "decision_type": request.decision_type,
        "actor_id": request.actor_id,
    }
    for key, value in metadata.items():
        if key not in proposal_request:
            continue
        if proposal_request[key] != value:
            raise GameLifecycleError(
                "Parameterized proposal_request metadata must match DecisionRequest."
            )
    return {**metadata, **proposal_request}


def _pending_request(lifecycle: GameLifecycle) -> DecisionRequest | None:
    pending_requests = lifecycle.decision_controller.queue.pending_requests
    if not pending_requests:
        return None
    return pending_requests[0]


def _secret_request_hidden_from_viewer(
    *,
    request: DecisionRequest,
    viewer_player_id: str,
) -> bool:
    if request.actor_id == viewer_player_id:
        return False
    payload = request.payload
    if not isinstance(payload, dict):
        return False
    secret = payload.get("secret")
    if secret is None:
        return False
    if type(secret) is not bool:
        raise GameLifecycleError("Secret DecisionRequest payload flag must be a bool.")
    return secret


def _redacted_decision_type(decision_type: str) -> str:
    if decision_type in {
        "draw_tactical_secondary_missions",
        "discard_tactical_secondary_mission",
        "start_mission_action",
    }:
        return "hidden_decision"
    return decision_type


def _validate_viewer(*, state: GameState, viewer_player_id: object) -> str:
    if type(viewer_player_id) is not str:
        raise GameLifecycleError("viewer_player_id must be a string.")
    viewer = viewer_player_id.strip()
    if not viewer:
        raise GameLifecycleError("viewer_player_id must not be empty.")
    if viewer not in state.player_ids:
        raise GameLifecycleError("viewer_player_id must be a player in this game.")
    return viewer


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return stripped
