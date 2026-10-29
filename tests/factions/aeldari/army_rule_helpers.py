from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from tests.deployment_submission_helpers import submit_all_deployments_if_pending
from tests.fight_on_death_helpers import retain_destroyed_model_for_fixture
from tests.movement_submission_helpers import (
    straight_line_witness_for_unit,
    submit_movement_proposal,
)
from tests.phase13b_shooting_declaration_helpers import proposal_from_request
from tests.phase15c_fight_order_helpers import fight_lifecycle
from warhammer40k_core.adapters.contracts import ParameterizedSubmission
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    CatalogJsonObject,
    DatasheetAbilityDescriptor,
    DatasheetDefinition,
    DatasheetKeywordSet,
    DatasheetWargearOption,
)
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    ConsolidationModeKind,
    FightEligibilityKind,
    FightOrderingBandKind,
    FightPhaseStepKind,
    FightTypeKind,
    MovementMode,
    RulesetDescriptor,
)
from warhammer40k_core.core.wargear import Wargear
from warhammer40k_core.core.wargear_selection_limits import DatasheetWargearSelectionLimit
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.advance_hooks import (
    DECLINE_MOVEMENT_ACTION_GRANT_OPTION_ID,
    SELECT_MOVEMENT_ACTION_GRANT_DECISION_TYPE,
)
from warhammer40k_core.engine.army_mustering import (
    ArmyMusteringError,
    ArmyMusterRequest,
    muster_army,
)
from warhammer40k_core.engine.attack_sequence import (
    attack_sequence_hit_roll_spec,
    attack_sequence_wound_roll_spec,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldTransitionBatch,
    ModelDisplacementKind,
    ModelDisplacementRecord,
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.charge_declaration_hooks import ChargeDeclarationContext
from warhammer40k_core.engine.damage_allocation import (
    DamageKind,
    apply_damage_to_model,
    unit_by_id,
)
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionError, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice_result_override_descriptors import (
    ASPECT_SHRINE_TOKEN_RESOURCE_KIND,
)
from warhammer40k_core.engine.dice_result_overrides import (
    DICE_RESULT_OVERRIDE_DECISION_TYPE,
    DICE_RESULT_OVERRIDE_EVENT_TYPE,
    UNIT_RESOURCE_SPENT_EVENT_TYPE,
    apply_dice_result_override_decision,
    request_dice_result_override_if_available,
)
from warhammer40k_core.engine.effects import EffectExpirationKind, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.aeldari import army_rule
from warhammer40k_core.engine.fight_activation_abilities import (
    FIGHT_ACTIVATION_ABILITY_DECISION_TYPE,
    FIGHT_ACTIVATION_MOVEMENT_DISTANCE_EFFECT_KIND,
    FightActivationAbilityContext,
)
from warhammer40k_core.engine.fight_order import (
    FIGHT_ACTIVATION_DECISION_TYPE,
    FightActivationSelection,
    FightMovementStepState,
    fight_activation_option_id,
)
from warhammer40k_core.engine.fight_resolution import (
    CONSOLIDATE_ACTION,
    SUBMIT_MELEE_DECLARATION_DECISION_TYPE,
    FightMovementProposal,
    MeleeDeclarationProposalRequest,
    fight_movement_maximum_distance_inches,
)
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.list_validation_errors import ListValidationError
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.movement_end_surge_hooks import (
    MovementEndSurgeContext,
    MovementEndSurgeGrant,
)
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    ProposalKind,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.movement import (
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    MovementPhaseActionKind,
)
from warhammer40k_core.engine.phases.shooting import (
    SELECT_SHOOTING_TYPE_DECISION_TYPE,
    SELECT_SHOOTING_UNIT_DECISION_TYPE,
    SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
    ShootingPhaseHandler,
)
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.stratagems import (
    DECLINE_STRATAGEM_WINDOW_OPTION_ID,
    STRATAGEM_DECISION_TYPE,
)
from warhammer40k_core.engine.unit_resource_state import (
    spend_unit_resource,
    unit_resource_starting_total,
    unit_resource_total,
)
from warhammer40k_core.engine.unit_resources import UnitResourceStatus
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
    WargearSelection,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.source_data import RuleSourceText

_AELDARI_UNIT_ID = "army-alpha:aeldari-vehicle"


_AELDARI_UNIT_SELECTION_ID = "aeldari-vehicle"


_AELDARI_DATASHEET_ID = "phase17g-aeldari-star-engine-vehicle"


_AELDARI_ASPECT_DATASHEET_ID = "phase17g-aeldari-aspect-warriors"


_AELDARI_ASPECT_MODEL_PROFILE_ID = "core-intercessor-like"


_AELDARI_FIGHT_DATASHEET_ID = "phase17g-aeldari-sudden-strike-fighter"


_AELDARI_FIGHT_SQUAD_DATASHEET_ID = "phase17g-aeldari-sudden-strike-fight-squad"


_AELDARI_DETACHMENT_ID = "warhost"


_OTHER_AELDARI_DETACHMENT_ID = "guardian-battlehost"


_ASPECT_SHRINE_TOKEN_WARGEAR_ID = f"{_AELDARI_ASPECT_DATASHEET_ID}:aspect-shrine-token"


_ASPECT_SHRINE_TOKEN_OPTION_ID = f"{_AELDARI_ASPECT_DATASHEET_ID}:aspect-shrine-token:option-1"


_ASPECT_SHRINE_TOKEN_OPTION_SOURCE_ID = "source:aeldari:datasheets-options:aspect-shrine-token"


_ENEMY_UNIT_SELECTION_ID = "enemy-unit"


_ENEMY_UNIT_ID = f"army-beta:{_ENEMY_UNIT_SELECTION_ID}"


def _wahapedia_aeldari_battle_focus_row() -> dict[str, JsonValue]:
    path = (
        Path("data/source_snapshots/wahapedia")
        / ("1" + "0th-edition")
        / "2026-06-14"
        / "json"
        / "Abilities.json"
    )
    artifact = json.loads(path.read_text(encoding="utf-8"))
    rows = cast(list[JsonValue], artifact["rows"])
    for row in rows:
        payload = cast(dict[str, JsonValue], row)
        fields = cast(dict[str, JsonValue], payload["fields"])
        if fields["name"] == "Battle Focus" and fields["faction_id"] == "AE":
            return payload
    raise AssertionError("missing Aeldari Battle Focus source row")


def _aeldari_config(
    *,
    aeldari_datasheet_id: str = _AELDARI_DATASHEET_ID,
    aeldari_model_profile_id: str = "core-vehicle-monster",
    aeldari_model_count: int = 1,
    aspect_shrine_token_count: int = 0,
) -> GameConfig:
    catalog = _aeldari_catalog(include_aspect_shrine_token=aspect_shrine_token_count > 0)
    selected_model_count = max(aeldari_model_count, aspect_shrine_token_count * 5)
    selected_datasheet_id = aeldari_datasheet_id
    selected_model_profile_id = aeldari_model_profile_id
    if aspect_shrine_token_count > 0:
        selected_datasheet_id = _AELDARI_ASPECT_DATASHEET_ID
        selected_model_profile_id = _AELDARI_ASPECT_MODEL_PROFILE_ID
    return GameConfig(
        game_id="phase17g-aeldari-star-engines",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-phase17g-aeldari-test"
        ),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                army_id="army-alpha",
                player_id="player-a",
                faction_id=army_rule.AELDARI_FACTION_ID,
                detachment_id=_AELDARI_DETACHMENT_ID,
                unit_selection_id=_AELDARI_UNIT_SELECTION_ID,
                datasheet_id=selected_datasheet_id,
                model_profile_id=selected_model_profile_id,
                model_count=selected_model_count,
                wargear_selections=(
                    ()
                    if aspect_shrine_token_count == 0
                    else (
                        WargearSelection(
                            option_id=_ASPECT_SHRINE_TOKEN_OPTION_ID,
                            model_profile_id=selected_model_profile_id,
                            wargear_ids=(_ASPECT_SHRINE_TOKEN_WARGEAR_ID,),
                            selection_count=aspect_shrine_token_count,
                        ),
                    )
                ),
            ),
            _army_muster_request(
                catalog=catalog,
                army_id="army-beta",
                player_id="player-b",
                faction_id="core-marine-force",
                detachment_id="core-combined-arms",
                unit_selection_id=_ENEMY_UNIT_SELECTION_ID,
                datasheet_id="core-intercessor-like-infantry",
                model_profile_id="core-intercessor-like",
                model_count=5,
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=_mission_setup(),
    )


def _aeldari_catalog(*, include_aspect_shrine_token: bool = False) -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    aeldari_vehicle = _aeldari_vehicle_datasheet(
        base_catalog.datasheet_by_id("core-vehicle-monster")
    )
    aeldari_fighter = _aeldari_fight_datasheet(
        base_catalog.datasheet_by_id("core-character-leader")
    )
    aeldari_fight_squad = replace(
        base_catalog.datasheet_by_id("core-intercessor-like-infantry"),
        datasheet_id=_AELDARI_FIGHT_SQUAD_DATASHEET_ID,
        name="Sudden Strike Test Fight Squad",
        keywords=DatasheetKeywordSet(
            keywords=("Infantry",),
            faction_keywords=("Asuryani",),
        ),
        attachment_eligibilities=(),
        wargear_options=tuple(
            replace(
                option,
                default_wargear_ids=("core-leader-blade",),
                allowed_wargear_ids=("core-leader-blade",),
            )
            for option in base_catalog.datasheet_by_id(
                "core-intercessor-like-infantry"
            ).wargear_options
        ),
        source_ids=("phase17g:test:aeldari:sudden-strike-fight-squad",),
    )
    aeldari_aspect_warriors = _aeldari_aspect_datasheet(
        base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    )
    return replace(
        base_catalog,
        datasheets=(
            *base_catalog.datasheets,
            aeldari_vehicle,
            aeldari_fighter,
            aeldari_fight_squad,
            *((aeldari_aspect_warriors,) if include_aspect_shrine_token else ()),
        ),
        wargear=(
            (
                *base_catalog.wargear,
                Wargear(
                    wargear_id=_ASPECT_SHRINE_TOKEN_WARGEAR_ID,
                    name="Aspect Shrine Token",
                    source_ids=(_ASPECT_SHRINE_TOKEN_OPTION_SOURCE_ID,),
                ),
            )
            if include_aspect_shrine_token
            else base_catalog.wargear
        ),
        factions=(
            *base_catalog.factions,
            FactionDefinition(
                faction_id=army_rule.AELDARI_FACTION_ID,
                name="Aeldari",
                faction_keywords=("Asuryani",),
                source_ids=("gw-11e-faction-detachments-2026-27:faction:aeldari",),
            ),
        ),
        detachments=(
            *base_catalog.detachments,
            DetachmentDefinition(
                canonical_detachment_id=_AELDARI_DETACHMENT_ID,
                detachment_id=_AELDARI_DETACHMENT_ID,
                name="Warhost",
                faction_id=army_rule.AELDARI_FACTION_ID,
                detachment_point_cost=3,
                unit_datasheet_ids=(
                    _AELDARI_DATASHEET_ID,
                    _AELDARI_FIGHT_DATASHEET_ID,
                    _AELDARI_FIGHT_SQUAD_DATASHEET_ID,
                    *((_AELDARI_ASPECT_DATASHEET_ID,) if include_aspect_shrine_token else ()),
                ),
                force_disposition_ids=("phase17g-force", "take-and-hold"),
                source_ids=("gw-11e-faction-detachments-2026-27:detachment:aeldari:warhost",),
            ),
            DetachmentDefinition(
                canonical_detachment_id=_OTHER_AELDARI_DETACHMENT_ID,
                detachment_id=_OTHER_AELDARI_DETACHMENT_ID,
                name="Guardian Battlehost",
                faction_id=army_rule.AELDARI_FACTION_ID,
                detachment_point_cost=3,
                unit_datasheet_ids=(
                    _AELDARI_DATASHEET_ID,
                    _AELDARI_FIGHT_DATASHEET_ID,
                    _AELDARI_FIGHT_SQUAD_DATASHEET_ID,
                    *((_AELDARI_ASPECT_DATASHEET_ID,) if include_aspect_shrine_token else ()),
                ),
                force_disposition_ids=("phase17g-force", "take-and-hold"),
                source_ids=(
                    "gw-11e-faction-detachments-2026-27:detachment:aeldari:guardian-battlehost",
                ),
            ),
        ),
    )


def _aeldari_vehicle_datasheet(
    base_datasheet: DatasheetDefinition,
) -> DatasheetDefinition:
    return replace(
        base_datasheet,
        datasheet_id=_AELDARI_DATASHEET_ID,
        name="Star Engines Test Vehicle",
        keywords=DatasheetKeywordSet(
            keywords=("Vehicle",),
            faction_keywords=("Asuryani",),
        ),
        attachment_eligibilities=(),
        source_ids=("phase17g:test:aeldari:star-engines-vehicle",),
    )


def _aeldari_aspect_datasheet(base_datasheet: DatasheetDefinition) -> DatasheetDefinition:
    return replace(
        base_datasheet,
        datasheet_id=_AELDARI_ASPECT_DATASHEET_ID,
        name="Aspect Warrior Test Unit",
        keywords=DatasheetKeywordSet(
            keywords=("Infantry", "Aspect Warrior"),
            faction_keywords=("Asuryani",),
        ),
        attachment_eligibilities=(),
        wargear_options=(
            *(
                replace(
                    option,
                    default_wargear_ids=("core-heavy-cannon",),
                    allowed_wargear_ids=("core-heavy-cannon",),
                )
                for option in base_datasheet.wargear_options
            ),
            _aspect_shrine_token_wargear_option(),
        ),
        abilities=(*base_datasheet.abilities, _aspect_shrine_token_ability()),
        source_ids=("phase17g:test:aeldari:aspect-warriors",),
    )


def _aeldari_fight_datasheet(base_datasheet: DatasheetDefinition) -> DatasheetDefinition:
    return replace(
        base_datasheet,
        datasheet_id=_AELDARI_FIGHT_DATASHEET_ID,
        name="Sudden Strike Test Fighter",
        keywords=DatasheetKeywordSet(
            keywords=base_datasheet.keywords.keywords,
            faction_keywords=("Asuryani",),
        ),
        attachment_eligibilities=(),
        source_ids=("phase17g:test:aeldari:sudden-strike-fighter",),
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    army_id: str,
    player_id: str,
    faction_id: str,
    detachment_id: str,
    unit_selection_id: str,
    datasheet_id: str,
    model_profile_id: str,
    model_count: int,
    wargear_selections: tuple[WargearSelection, ...] = (),
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=faction_id,
            detachment_ids=(detachment_id,),
        ),
        force_disposition_id=(
            "purge-the-foe" if faction_id == "core-marine-force" else "take-and-hold"
        ),
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id=datasheet_id,
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id=model_profile_id,
                        model_count=model_count,
                    ),
                ),
                wargear_selections=wargear_selections,
            ),
        ),
    )


def _aspect_shrine_token_wargear_option() -> DatasheetWargearOption:
    return DatasheetWargearOption(
        option_id=_ASPECT_SHRINE_TOKEN_OPTION_ID,
        model_profile_id=_AELDARI_ASPECT_MODEL_PROFILE_ID,
        default_wargear_ids=(),
        allowed_wargear_ids=(_ASPECT_SHRINE_TOKEN_WARGEAR_ID,),
        min_selections=0,
        max_selections=1,
        source_ids=(_ASPECT_SHRINE_TOKEN_OPTION_SOURCE_ID,),
        selection_limit=DatasheetWargearSelectionLimit(
            selection_group_id=f"{_AELDARI_ASPECT_DATASHEET_ID}:aspect-shrine-token",
            models_per_increment=5,
            max_group_selections_per_increment=1,
            max_option_selections_per_increment=1,
            unit_resource_kind=ASPECT_SHRINE_TOKEN_RESOURCE_KIND,
            unit_resource_amount_per_selection=1,
        ),
    )


def _aspect_shrine_token_ability(*, replacement_value: int = 6) -> DatasheetAbilityDescriptor:
    compiled = compile_rule_source_text(
        RuleSourceText.from_raw(
            objective_scope=ObjectiveRuleScope.CORE_RULES,
            source_id="source:aeldari:aspect-shrine-token",
            raw_text=(
                "Once per battle for each Aspect Shrine token this unit has, you can change "
                "the result of one Hit roll or one Wound roll made for a model in this unit "
                f"(excluding CHARACTER models) to an unmodified {replacement_value}."
            ),
        ),
        source_keyword_sequence_parts=("CHARACTER",),
    )
    return DatasheetAbilityDescriptor(
        ability_id="aspect-shrine-token",
        name="Aspect Shrine Token",
        source_id="source:aeldari:aspect-shrine-token",
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.WARGEAR,
        effect_description="Aspect Shrine Token dice result override.",
        source_wargear_id=_ASPECT_SHRINE_TOKEN_WARGEAR_ID,
        rule_ir_payload=cast(CatalogJsonObject, compiled.rule_ir.to_payload()),
    )


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )


def _advance_to_movement_unit_selection(
    config: GameConfig,
    *,
    session: LocalGameSession | None = None,
) -> tuple[GameLifecycle, LifecycleStatus]:
    if session is None:
        lifecycle = GameLifecycle()
        lifecycle.start(config)
        status = lifecycle.advance_until_decision_or_terminal()
    else:
        lifecycle = session.lifecycle
        session.start(config)
        status = session.advance_until_decision_or_terminal()
    secondary_index = 1
    while (
        status.decision_request is not None
        and status.decision_request.decision_type == SECONDARY_MISSION_DECISION_TYPE
    ):
        status = lifecycle.submit_decision(
            DecisionResult.for_request(
                result_id=f"phase17g-aeldari-secondary-{secondary_index:06d}",
                request=_decision_request(status),
                selected_option_id="fixed:assassination:bring_it_down",
            )
        )
        secondary_index += 1
    status = submit_all_deployments_if_pending(
        lifecycle,
        status,
        result_id_prefix="phase17g-aeldari-deploy",
        pose_factory=_aeldari_shooting_reachable_deployment_pose,
    )
    request = _decision_request(status)
    assert request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    return lifecycle, status


def _decline_stratagem_window_if_present(
    lifecycle: GameLifecycle,
    status: LifecycleStatus,
    *,
    result_id: str,
) -> LifecycleStatus:
    request = _decision_request(status)
    if request.decision_type != STRATAGEM_DECISION_TYPE:
        return status
    return lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id=result_id,
            request=request,
            selected_option_id=DECLINE_STRATAGEM_WINDOW_OPTION_ID,
        )
    )


def _select_aeldari_vehicle_for_movement(
    lifecycle: GameLifecycle,
    movement_status: LifecycleStatus,
) -> DecisionRequest:
    action_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-aeldari-select-vehicle",
            request=_decision_request(movement_status),
            selected_option_id=_AELDARI_UNIT_ID,
        )
    )
    action_status = _decline_stratagem_window_if_present(
        lifecycle,
        action_status,
        result_id="phase17g-aeldari-decline-selected-to-move",
    )
    action_request = _decision_request(action_status)
    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE
    return action_request


def _aeldari_vehicle_is_selectable_to_shoot(
    *,
    state: GameState,
    config: GameConfig,
) -> bool:
    shooting_state = _state_at_phase(state, BattlePhase.SHOOTING)
    handler = ShootingPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
    )
    decisions = DecisionController()
    status = handler.begin_phase(state=shooting_state, decisions=decisions)
    if status.status_kind is not LifecycleStatusKind.WAITING_FOR_DECISION:
        return False
    request = _decision_request(status)
    if request.decision_type != SELECT_SHOOTING_UNIT_DECISION_TYPE:
        return False
    return _AELDARI_UNIT_ID in {option.option_id for option in request.options}


def _shooting_declaration_request_for_aeldari_vehicle(
    *,
    state: GameState,
    config: GameConfig,
) -> DecisionRequest:
    shooting_state = _state_at_phase(state, BattlePhase.SHOOTING)
    handler = ShootingPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
    )
    decisions = DecisionController()
    status = handler.begin_phase(state=shooting_state, decisions=decisions)
    unit_request = _decision_request(status)
    assert unit_request.decision_type == SELECT_SHOOTING_UNIT_DECISION_TYPE
    assert _AELDARI_UNIT_ID in {option.option_id for option in unit_request.options}

    handler.apply_decision(
        state=shooting_state,
        decisions=decisions,
        result=DecisionResult.for_request(
            result_id="phase17g-aeldari-select-shooting-unit",
            request=unit_request,
            selected_option_id=_AELDARI_UNIT_ID,
        ),
    )
    type_status = handler.begin_phase(state=shooting_state, decisions=decisions)
    type_request = _decision_request(type_status)
    assert type_request.decision_type == SELECT_SHOOTING_TYPE_DECISION_TYPE
    assert tuple(option.option_id for option in type_request.options) == (
        ShootingType.ASSAULT.value,
    )

    handler.apply_decision(
        state=shooting_state,
        decisions=decisions,
        result=DecisionResult.for_request(
            result_id="phase17g-aeldari-select-assault-shooting",
            request=type_request,
            selected_option_id=ShootingType.ASSAULT.value,
        ),
    )
    declaration_status = handler.begin_phase(state=shooting_state, decisions=decisions)
    return _decision_request(declaration_status)


def _aspect_shrine_lifecycle_override_request(
    *, replacement_value: int = 6, twin_linked: bool = False
) -> tuple[GameLifecycle, DecisionRequest]:
    config = _aeldari_config(aspect_shrine_token_count=1)
    # Exercise the generic descriptor with alternate source-fixture values;
    # this does not change or claim the real Aspect Shrine rule's assigned six.
    if replacement_value != 6:
        ability = _aspect_shrine_token_ability(replacement_value=replacement_value)
        catalog = replace(
            config.army_catalog,
            datasheets=tuple(
                replace(
                    row,
                    abilities=tuple(
                        ability if value.ability_id == ability.ability_id else value
                        for value in row.abilities
                    ),
                )
                if row.datasheet_id == _AELDARI_ASPECT_DATASHEET_ID
                else row
                for row in config.army_catalog.datasheets
            ),
        )
        config = replace(config, army_catalog=catalog)
    if twin_linked:
        config = replace(
            config,
            army_catalog=replace(
                config.army_catalog,
                wargear=tuple(
                    replace(
                        row,
                        weapon_profiles=tuple(
                            replace(
                                profile, keywords=(*profile.keywords, WeaponKeyword.TWIN_LINKED)
                            )
                            for profile in row.weapon_profiles
                        ),
                    )
                    for row in config.army_catalog.wargear
                ),
            ),
        )
    lifecycle, movement_status = _advance_to_movement_unit_selection(config)
    if twin_linked:
        from tests.twin_linked_helpers import submit_next

        # Preserve the real phase-boundary history for checkpoint/replay checks.
        movement_session = LocalGameSession(lifecycle)
        for _ in range(50):
            if _state(lifecycle).current_battle_phase is BattlePhase.SHOOTING:
                break
            movement_request = _decision_request(movement_status)
            if movement_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE:
                movement_status = movement_session.submit_option(
                    request_id=movement_request.request_id,
                    option_id=MovementPhaseActionKind.REMAIN_STATIONARY.value,
                    result_id=f"{movement_request.request_id}:order96-stationary",
                )
            else:
                submit_next(movement_session, movement_request)
                movement_status = movement_session.advance_until_decision_or_terminal()
            assert movement_status.status_kind is not LifecycleStatusKind.INVALID
        assert _state(lifecycle).current_battle_phase is BattlePhase.SHOOTING
    else:
        _advance_lifecycle_state_to_phase(lifecycle, BattlePhase.SHOOTING)
        lifecycle = _rehydrate_lifecycle_with_empty_decisions(lifecycle)

    unit_request = _decision_request(
        _decline_stratagem_window_if_present(
            lifecycle,
            lifecycle.advance_until_decision_or_terminal(),
            result_id="aspect-token-decline-shooting-start-window",
        )
    )
    assert unit_request.decision_type == SELECT_SHOOTING_UNIT_DECISION_TYPE
    type_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="aspect-token-select-shooting-unit",
            request=unit_request,
            selected_option_id=_AELDARI_UNIT_ID,
        )
    )
    type_status = _decline_stratagem_window_if_present(
        lifecycle,
        type_status,
        result_id="aspect-token-decline-selected-to-shoot-window",
    )
    type_request = _decision_request(type_status)
    assert type_request.decision_type == SELECT_SHOOTING_TYPE_DECISION_TYPE
    declaration_request = _decision_request(
        lifecycle.submit_decision(
            DecisionResult.for_request(
                result_id="aspect-token-select-shooting-type",
                request=type_request,
                selected_option_id=ShootingType.NORMAL.value,
            )
        )
    )
    assert declaration_request.decision_type == SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE
    proposal = proposal_from_request(
        request=declaration_request,
        target_unit_id=_ENEMY_UNIT_ID,
    )
    declaration = proposal.declarations[0]
    declaration_result_id = "aspect-token-shooting-declaration"
    attack_context_id = f"attack-sequence:{declaration_result_id}:pool-001:attack-001"
    manager = DiceRollManager(
        _state(lifecycle).game_id,
        event_log=lifecycle.decision_controller.event_log,
    )
    manager.roll_fixed(
        attack_sequence_hit_roll_spec(
            weapon_profile_id=declaration.weapon_profile_id,
            attack_context_id=attack_context_id,
            attacker_player_id="player-a",
        ),
        [6] if twin_linked else [2] if replacement_value == 1 else [1],
    )
    manager.roll_fixed(
        attack_sequence_wound_roll_spec(
            weapon_profile_id=declaration.weapon_profile_id,
            attack_context_id=attack_context_id,
            attacker_player_id="player-a",
        ),
        [1] if twin_linked else [6],
    )
    status = lifecycle.submit_decision(
        DecisionResult(
            result_id=declaration_result_id,
            request_id=declaration_request.request_id,
            decision_type=declaration_request.decision_type,
            actor_id=declaration_request.actor_id,
            selected_option_id="submit_parameterized_payload",
            payload=validate_json_value(proposal.to_payload()),
        )
    )
    status = _decline_stratagem_window_if_present(
        lifecycle,
        status,
        result_id="aspect-token-decline-hit-command-reroll",
    )
    hit_assignment_count = 0
    while (
        twin_linked
        and _decision_request(status).decision_type == DICE_RESULT_OVERRIDE_DECISION_TYPE
    ):
        hit_assignment = _decision_request(status)
        assert isinstance(hit_assignment.payload, dict)
        assert hit_assignment.payload["roll_spec_type"] == "attack_sequence.hit"
        hit_assignment_count += 1
        status = lifecycle.submit_decision(
            DecisionResult.for_request(
                result_id=(
                    "order96:decline-hit-assignment"
                    if hit_assignment_count == 1
                    else f"order96:decline-hit-assignment:{hit_assignment.request_id}"
                ),
                request=hit_assignment,
                selected_option_id="decline",
            )
        )
        status = _decline_stratagem_window_if_present(
            lifecycle,
            status,
            result_id=f"order96:decline-wound-command-reroll:{hit_assignment_count}",
        )
    request = _decision_request(status)
    assert request.decision_type == (
        "select_dice_reroll" if twin_linked else DICE_RESULT_OVERRIDE_DECISION_TYPE
    )
    return lifecycle, request


def _aeldari_shooting_reachable_deployment_pose(
    index: int,
    player_id: str,
    model_instance_id: str,
) -> Pose:
    unit_instance_id = model_instance_id.rsplit(":", 2)[0]
    if unit_instance_id == _AELDARI_UNIT_ID:
        if _AELDARI_ASPECT_MODEL_PROFILE_ID not in model_instance_id:
            return Pose.at(15.5, 17.0, 0.0, facing_degrees=0.0)
        return Pose.at(
            15.5 - ((index % 2) * 2.0),
            17.0 + ((index // 2) * 2.0),
            0.0,
            facing_degrees=0.0,
        )
    if unit_instance_id == f"army-beta:{_ENEMY_UNIT_SELECTION_ID}":
        return Pose.at(43.5, 17.0 + (index * 1.8), 0.0, facing_degrees=180.0)
    if player_id == "player-b":
        return Pose.at(57.0, 24.0 + (index * 1.8), 0.0, facing_degrees=180.0)
    return Pose.at(3.0, 24.0 + (index * 1.8), 0.0, facing_degrees=0.0)


def _state_at_phase(state: GameState, phase: BattlePhase) -> GameState:
    phase_state = GameState.from_payload(state.to_payload())
    while phase_state.current_battle_phase is not phase:
        if phase_state.current_battle_phase is None:
            raise AssertionError("battle state ended before expected phase")
        phase_state.advance_to_next_battle_phase()
    return phase_state


def _prepared_aeldari_state_at_phase(phase: BattlePhase) -> GameState:
    lifecycle, _status = _advance_to_movement_unit_selection(_aeldari_config())
    return _state_at_phase(_state(lifecycle), phase)


def _advance_lifecycle_state_to_phase(lifecycle: GameLifecycle, phase: BattlePhase) -> None:
    state = _state(lifecycle)
    while state.current_battle_phase is not phase:
        if state.current_battle_phase is None:
            raise AssertionError("battle state ended before expected phase")
        state.advance_to_next_battle_phase()


def _rehydrate_lifecycle_with_empty_decisions(lifecycle: GameLifecycle) -> GameLifecycle:
    payload = lifecycle.to_payload()
    payload["decisions"]["queue"] = DecisionController().to_payload()["queue"]
    return GameLifecycle.from_payload(payload)


def _drain_fight_movement_requests(
    lifecycle: GameLifecycle,
    status: LifecycleStatus,
) -> LifecycleStatus:
    current = status
    while (
        current.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
        and current.decision_request is not None
        and current.decision_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    ):
        request = current.decision_request
        proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
        assert proposal_request.proposal_kind in {
            ProposalKind.PILE_IN,
            ProposalKind.CONSOLIDATE,
        }
        context = cast(dict[str, JsonValue], proposal_request.context)
        current = lifecycle.submit_decision(
            ParameterizedSubmission(
                request_id=request.request_id,
                result_id=f"{request.request_id}:phase17g-aeldari-no-move",
                payload=cast(
                    JsonValue,
                    {
                        "proposal_request_id": proposal_request.request_id,
                        "proposal_kind": proposal_request.proposal_kind.value,
                        "unit_instance_id": proposal_request.unit_instance_id,
                        "movement_phase_action": proposal_request.movement_phase_action,
                        "movement_mode": context["movement_mode"],
                    },
                ),
            ).to_result(request)
        )
    return current


def _place_unit_poses(
    state: GameState,
    *,
    unit_instance_id: str,
    poses: tuple[Pose, ...],
) -> None:
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield_state")
    placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    state.replace_battlefield_state(
        state.battlefield_state.with_unit_placement(_with_model_poses(placement, poses=poses))
    )


def _unit_line_poses(*, x: float, y: float) -> tuple[Pose, ...]:
    return tuple(Pose.at(x, y + index * 1.8, 0.0) for index in range(5))


def _with_model_poses(
    unit_placement: UnitPlacement,
    *,
    poses: tuple[Pose, ...],
) -> UnitPlacement:
    if len(poses) != len(unit_placement.model_placements):
        raise AssertionError("test pose fixture must match unit model count")
    return UnitPlacement(
        army_id=unit_placement.army_id,
        player_id=unit_placement.player_id,
        unit_instance_id=unit_placement.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id=placement.army_id,
                player_id=placement.player_id,
                unit_instance_id=placement.unit_instance_id,
                model_instance_id=placement.model_instance_id,
                pose=pose,
            )
            for placement, pose in zip(unit_placement.model_placements, poses, strict=True)
        ),
    )


def _displacement_batch_for_unit(
    *,
    state: GameState,
    unit_instance_id: str,
    start_poses: tuple[Pose, ...],
    end_poses: tuple[Pose, ...],
) -> BattlefieldTransitionBatch:
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield_state")
    placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    if len(start_poses) != len(placement.model_placements):
        raise AssertionError("test start poses must match unit model count")
    if len(end_poses) != len(placement.model_placements):
        raise AssertionError("test end poses must match unit model count")
    return BattlefieldTransitionBatch(
        displacements=tuple(
            ModelDisplacementRecord(
                model_instance_id=model_placement.model_instance_id,
                displacement_kind=ModelDisplacementKind.FALL_BACK,
                start_pose=start_pose,
                end_pose=end_pose,
                source_phase=BattlePhase.MOVEMENT.value,
                source_step="move_units",
                source_event_id="phase17g-aeldari-enemy-fall-back-event",
            )
            for model_placement, start_pose, end_pose in zip(
                placement.model_placements,
                start_poses,
                end_poses,
                strict=True,
            )
        )
    )


def _single_persisting_effect_for_unit_by_kind(
    state: GameState,
    unit_instance_id: str,
    effect_kind: str,
) -> PersistingEffect:
    effects = _persisting_effects_for_unit_by_kind(state, unit_instance_id, effect_kind)
    assert len(effects) == 1
    return effects[0]


def _persisting_effects_for_unit_by_kind(
    state: GameState,
    unit_instance_id: str,
    effect_kind: str,
) -> tuple[PersistingEffect, ...]:
    effects: list[PersistingEffect] = []
    for effect in state.persisting_effects_for_unit(unit_instance_id):
        payload = cast(dict[str, JsonValue], effect.effect_payload)
        if payload.get("effect_kind") == effect_kind:
            effects.append(effect)
    return tuple(effects)


def _runtime_content_bundle(lifecycle: GameLifecycle) -> RuntimeContentBundle:
    require_runtime_content_bundle = cast(
        Callable[[], RuntimeContentBundle],
        object.__getattribute__(lifecycle, "_require_runtime_content_bundle"),
    )
    return require_runtime_content_bundle()


def _event_payload(lifecycle: GameLifecycle, event_type: str) -> dict[str, JsonValue]:
    for event in lifecycle.decision_controller.event_log.records:
        if event.event_type == event_type:
            return cast(dict[str, JsonValue], event.payload)
    raise AssertionError(f"missing event {event_type}")


def _last_event_payload(lifecycle: GameLifecycle, event_type: str) -> dict[str, JsonValue]:
    for event in reversed(lifecycle.decision_controller.event_log.records):
        if event.event_type == event_type:
            return cast(dict[str, JsonValue], event.payload)
    raise AssertionError(f"missing event {event_type}")


def _decision_request(status: LifecycleStatus) -> DecisionRequest:
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request


def _state(lifecycle: GameLifecycle) -> GameState:
    assert lifecycle.state is not None
    return lifecycle.state


__all__ = [
    "ASPECT_SHRINE_TOKEN_RESOURCE_KIND",
    "CONSOLIDATE_ACTION",
    "DECLINE_MOVEMENT_ACTION_GRANT_OPTION_ID",
    "DECLINE_STRATAGEM_WINDOW_OPTION_ID",
    "DICE_RESULT_OVERRIDE_DECISION_TYPE",
    "DICE_RESULT_OVERRIDE_EVENT_TYPE",
    "FIGHT_ACTIVATION_ABILITY_DECISION_TYPE",
    "FIGHT_ACTIVATION_DECISION_TYPE",
    "FIGHT_ACTIVATION_MOVEMENT_DISTANCE_EFFECT_KIND",
    "MOVEMENT_PROPOSAL_DECISION_TYPE",
    "SECONDARY_MISSION_DECISION_TYPE",
    "SELECT_MOVEMENT_ACTION_DECISION_TYPE",
    "SELECT_MOVEMENT_ACTION_GRANT_DECISION_TYPE",
    "SELECT_MOVEMENT_UNIT_DECISION_TYPE",
    "SELECT_SHOOTING_TYPE_DECISION_TYPE",
    "SELECT_SHOOTING_UNIT_DECISION_TYPE",
    "STRATAGEM_DECISION_TYPE",
    "SUBMIT_MELEE_DECLARATION_DECISION_TYPE",
    "SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE",
    "UNIT_RESOURCE_SPENT_EVENT_TYPE",
    "_AELDARI_ASPECT_DATASHEET_ID",
    "_AELDARI_ASPECT_MODEL_PROFILE_ID",
    "_AELDARI_DATASHEET_ID",
    "_AELDARI_DETACHMENT_ID",
    "_AELDARI_FIGHT_DATASHEET_ID",
    "_AELDARI_FIGHT_SQUAD_DATASHEET_ID",
    "_AELDARI_UNIT_ID",
    "_AELDARI_UNIT_SELECTION_ID",
    "_ASPECT_SHRINE_TOKEN_OPTION_ID",
    "_ASPECT_SHRINE_TOKEN_OPTION_SOURCE_ID",
    "_ASPECT_SHRINE_TOKEN_WARGEAR_ID",
    "_ENEMY_UNIT_ID",
    "_ENEMY_UNIT_SELECTION_ID",
    "_OTHER_AELDARI_DETACHMENT_ID",
    "ArmyCatalog",
    "ArmyMusterRequest",
    "ArmyMusteringError",
    "BattlePhase",
    "BattlePhaseKind",
    "BattlefieldTransitionBatch",
    "Callable",
    "CatalogAbilitySourceKind",
    "CatalogAbilitySupport",
    "CatalogJsonObject",
    "ChargeDeclarationContext",
    "ConsolidationModeKind",
    "DamageKind",
    "DatasheetAbilityDescriptor",
    "DatasheetDefinition",
    "DatasheetKeywordSet",
    "DatasheetWargearOption",
    "DatasheetWargearSelectionLimit",
    "DecisionController",
    "DecisionError",
    "DecisionRequest",
    "DecisionResult",
    "DetachmentDefinition",
    "DetachmentSelection",
    "DiceExpression",
    "DiceRollManager",
    "DiceRollSpec",
    "EffectExpirationKind",
    "FactionDefinition",
    "FightActivationAbilityContext",
    "FightActivationSelection",
    "FightEligibilityKind",
    "FightMovementProposal",
    "FightMovementStepState",
    "FightOrderingBandKind",
    "FightPhaseStepKind",
    "FightTypeKind",
    "GameConfig",
    "GameLifecycle",
    "GameLifecycleError",
    "GameLifecyclePayload",
    "GameState",
    "JsonValue",
    "LifecycleStatus",
    "LifecycleStatusKind",
    "ListValidationError",
    "LocalGameSession",
    "MeleeDeclarationProposalRequest",
    "MissionSetup",
    "ModelDisplacementKind",
    "ModelDisplacementRecord",
    "ModelPlacement",
    "ModelProfileSelection",
    "MovementEndSurgeContext",
    "MovementEndSurgeGrant",
    "MovementMode",
    "MovementPhaseActionKind",
    "MovementProposalRequest",
    "ObjectiveRuleScope",
    "ParameterizedSubmission",
    "Path",
    "PersistingEffect",
    "Pose",
    "ProposalKind",
    "RuleSourceText",
    "RulesetDescriptor",
    "RuntimeContentBundle",
    "ShootingPhaseHandler",
    "ShootingType",
    "UnitMusterSelection",
    "UnitPlacement",
    "UnitResourceStatus",
    "Wargear",
    "WargearSelection",
    "WeaponKeyword",
    "_advance_lifecycle_state_to_phase",
    "_advance_to_movement_unit_selection",
    "_aeldari_aspect_datasheet",
    "_aeldari_catalog",
    "_aeldari_config",
    "_aeldari_fight_datasheet",
    "_aeldari_shooting_reachable_deployment_pose",
    "_aeldari_vehicle_datasheet",
    "_aeldari_vehicle_is_selectable_to_shoot",
    "_army_muster_request",
    "_aspect_shrine_lifecycle_override_request",
    "_aspect_shrine_token_ability",
    "_aspect_shrine_token_wargear_option",
    "_decision_request",
    "_decline_stratagem_window_if_present",
    "_displacement_batch_for_unit",
    "_drain_fight_movement_requests",
    "_event_payload",
    "_last_event_payload",
    "_mission_setup",
    "_persisting_effects_for_unit_by_kind",
    "_place_unit_poses",
    "_prepared_aeldari_state_at_phase",
    "_rehydrate_lifecycle_with_empty_decisions",
    "_runtime_content_bundle",
    "_select_aeldari_vehicle_for_movement",
    "_shooting_declaration_request_for_aeldari_vehicle",
    "_single_persisting_effect_for_unit_by_kind",
    "_state",
    "_state_at_phase",
    "_unit_line_poses",
    "_wahapedia_aeldari_battle_focus_row",
    "_with_model_poses",
    "apply_damage_to_model",
    "apply_dice_result_override_decision",
    "army_rule",
    "attack_sequence_hit_roll_spec",
    "attack_sequence_wound_roll_spec",
    "cast",
    "chapter_approved_2026_27_mission_pack",
    "compile_rule_source_text",
    "fight_activation_option_id",
    "fight_lifecycle",
    "fight_movement_maximum_distance_inches",
    "json",
    "muster_army",
    "proposal_from_request",
    "pytest",
    "replace",
    "request_dice_result_override_if_available",
    "retain_destroyed_model_for_fixture",
    "spend_unit_resource",
    "straight_line_witness_for_unit",
    "submit_all_deployments_if_pending",
    "submit_movement_proposal",
    "unit_by_id",
    "unit_resource_starting_total",
    "unit_resource_total",
    "validate_json_value",
]
