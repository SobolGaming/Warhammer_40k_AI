"""Canonical facade attacks against attached ability sources, with real choices."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from tests.phase13b_shooting_declaration_helpers import (
    _canonical_catalog,
    _compact_intercessor_catalog,
    _proposal_from_request,
    _shooting_lifecycle,
)
from tests.phase15c_fight_order_helpers import fight_lifecycle
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request
from tests.support.ability_presence_fixtures import compiled_ability_rule
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    CatalogJsonObject,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.core.weapon_profiles import AttackProfile, DamageProfile, WeaponKeyword
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.ability_catalog import catalog_ability_records_from_catalog
from warhammer40k_core.engine.catalog_rule_consumption import CatalogWeaponKeywordGrantRuntime
from warhammer40k_core.engine.damage_allocation import FeelNoPainSource, model_by_id
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import canonical_json, validate_json_value
from warhammer40k_core.engine.fight_resolution import MeleeDeclarationProposalRequest
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import WeaponProfileModifierContext
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.rule_ir import RuleIR


def source_retention_session(
    phase: BattlePhase,
    *,
    source_role: str = "bodyguard",
    source_wargear: bool = False,
    optional_fnp: bool = True,
    ability_text: str = (
        "Ranged weapons equipped by models in this unit have the [LETHAL HITS] ability."
    ),
    ability_rule_ir: RuleIR | None = None,
) -> tuple[LocalGameSession, str]:
    catalog = _compact_intercessor_catalog(_canonical_catalog())
    source_sheet = {
        "bodyguard": "core-intercessor-like-infantry",
        "leader": "core-character-leader",
        "support": "core-character-support",
    }[source_role]
    text = ability_text
    ir = (
        compiled_ability_rule(text, source_id="test:order118:unit-weapon-grant")
        if ability_rule_ir is None
        else ability_rule_ir
    )
    descriptor = DatasheetAbilityDescriptor(
        ability_id="order118:grant",
        name="Source lifetime fixture",
        source_id=ir.source_id,
        source_kind=CatalogAbilitySourceKind.WARGEAR
        if source_wargear
        else CatalogAbilitySourceKind.DATASHEET,
        source_wargear_id="core-bolt-rifle" if source_wargear else None,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        effect_description=text,
        rule_ir_payload=cast(CatalogJsonObject, ir.to_payload()),
    )
    catalog = replace(
        catalog,
        datasheets=tuple(
            replace(
                sheet,
                abilities=(*sheet.abilities, descriptor)
                if sheet.datasheet_id == source_sheet
                else sheet.abilities,
                wargear_options=tuple(
                    replace(
                        option,
                        default_wargear_ids=(*option.default_wargear_ids, "core-leader-blade"),
                        allowed_wargear_ids=(*option.allowed_wargear_ids, "core-leader-blade"),
                        max_selections=option.max_selections + 1,
                    )
                    for option in sheet.wargear_options
                )
                if sheet.datasheet_id == "core-intercessor-like-infantry"
                else sheet.wargear_options,
            )
            for sheet in catalog.datasheets
        ),
        wargear=tuple(
            replace(
                row,
                weapon_profiles=tuple(
                    replace(
                        weapon,
                        keywords=(WeaponKeyword.PRECISION,),
                        abilities=(),
                        attack_profile=AttackProfile.fixed(6),
                        damage_profile=DamageProfile.fixed(1),
                        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 20),
                        skill=CharacteristicValue.from_raw(weapon.skill.characteristic, 2),
                        armor_penetration=CharacteristicValue.from_raw(
                            Characteristic.ARMOR_PENETRATION, -10
                        ),
                    )
                    for weapon in row.weapon_profiles
                ),
            )
            for row in catalog.wargear
        ),
    )
    specs = (
        ("enemy", "core-intercessor-like-infantry", "core-intercessor-like", 1),
        ("leader", "core-character-leader", "core-character-leader", 1),
        ("support", "core-character-support", "core-character-support", 1),
        ("other", "core-character-leader", "core-character-leader", 1),
    )
    attachments = tuple(
        AttachmentDeclaration(source_unit_selection_id=key, bodyguard_unit_selection_id="enemy")
        for key in ("leader", "support")
    )
    if phase is BattlePhase.SHOOTING:
        lifecycle, units = _shooting_lifecycle(
            alpha_unit_ids=("attacker",),
            alpha_unit_specs=(
                ("attacker", "core-intercessor-like-infantry", "core-intercessor-like", 2),
            ),
            enemy_unit_specs=specs,
            enemy_attachment_declarations=attachments,
            game_id="order118-shooting",
            catalog=catalog,
            enemy_pose=Pose.at(30, 35),
        )
        # The canonical shooting fixture spaces separate units; an attached rules
        # unit needs its physical components next to one another.
        from tests.phase15c_fight_order_helpers import unit_placement_at

        state = lifecycle.state
        assert state is not None
        assert state.battlefield_state is not None
        battlefield = state.battlefield_state
        for index, key in enumerate(("enemy", "leader", "support", "other")):
            battlefield = battlefield.with_unit_placement(
                unit_placement_at(
                    units[key],
                    army_id="army-beta",
                    player_id="player-b",
                    poses=(Pose.at(30, 35 + index * 1.65),),
                )
            )
        state.replace_battlefield_state(battlefield)
    else:
        lifecycle, units = fight_lifecycle(
            alpha_unit_ids=("attacker",),
            enemy_unit_ids=("enemy", "leader", "support", "other"),
            origins={
                "attacker": Pose.at(10, 10),
                "enemy": Pose.at(11.65, 10),
                "leader": Pose.at(11.65, 11.65),
                "support": Pose.at(11.65, 13.3),
                "other": Pose.at(8.35, 11.65),
            },
            game_id="order118-fight",
            model_count=1,
            catalog=catalog,
            alpha_unit_specs={
                "attacker": ("core-intercessor-like-infantry", "core-intercessor-like", 2)
            },
            enemy_unit_specs={key: (sheet, profile, count) for key, sheet, profile, count in specs},
            enemy_attachment_declarations=attachments,
            fights_first_unit_keys=("attacker",),
            poses_by_unit_key={
                "attacker": (Pose.at(10, 10), Pose.at(10, 11.65)),
                "enemy": (Pose.at(11.65, 10),),
                "leader": (Pose.at(11.65, 11.65),),
                "support": (Pose.at(11.65, 13.3),),
                "other": (Pose.at(8.35, 11.65),),
            },
        )
    state = lifecycle.state
    assert state is not None
    view = rules_unit_view_by_id(state=state, unit_instance_id=units["enemy"].unit_instance_id)
    prevention_models = (
        (*view.alive_models(), *units["other"].alive_own_models()) if optional_fnp else ()
    )
    for model in prevention_models:
        state.record_model_feel_no_pain_sources(
            model_instance_id=model.model_instance_id,
            sources=(FeelNoPainSource(source_id="order118:optional-prevention", threshold=6),),
            decline_allowed=True,
        )
    source = units["enemy" if source_role == "bodyguard" else source_role].own_models[0]
    # Begin with an ordinarily wounded source, so its death leaves attacks and
    # living teammates for the source-lifetime assertion in every component case.
    state.army_definitions = [
        replace(
            army,
            units=tuple(
                replace(
                    unit,
                    own_models=tuple(
                        replace(model, wounds_remaining=1)
                        if model.model_instance_id == source.model_instance_id
                        else model
                        for model in unit.own_models
                    ),
                )
                for unit in army.units
            ),
        )
        for army in state.army_definitions
    ]
    return LocalGameSession(
        lifecycle=GameLifecycle.from_payload(lifecycle.to_payload())
    ), source.model_instance_id


def source_grant_active(session: LocalGameSession) -> bool:
    state = session.lifecycle.state
    assert state is not None
    config_payload = session.lifecycle.to_payload()["config"]
    assert config_payload is not None
    config = GameConfig.from_payload(config_payload)
    records = catalog_ability_records_from_catalog(config.army_catalog)
    runtime = CatalogWeaponKeywordGrantRuntime(
        {player: AbilityCatalogIndex.from_records(records) for player in state.player_ids},
        tuple(state.army_definitions),
    )
    view = rules_unit_view_by_id(state=state, unit_instance_id="army-beta:enemy")
    # A casualty never becomes a legal attacking model. Inspect its surviving
    # teammate's weapon through the actual catalog consumer.
    bearer = view.alive_models()[0]
    profile = next(
        row for row in config.army_catalog.wargear if row.wargear_id == "core-bolt-rifle"
    ).weapon_profiles[0]
    context = WeaponProfileModifierContext(
        state=state,
        source_phase=BattlePhase.SHOOTING,
        attacking_unit_instance_id=view.unit_instance_id,
        attacker_model_instance_id=bearer.model_instance_id,
        target_unit_instance_id="army-alpha:attacker",
        weapon_profile=profile,
    )
    return WeaponKeyword.LETHAL_HITS in runtime.weapon_profile_modifier(context).keywords


def submit_source_choice(
    session: LocalGameSession, request: DecisionRequest, *, source_model_id: str
) -> None:
    if request.decision_type == "submit_shooting_declaration":
        proposal = _proposal_from_request(
            request=request, target_unit_id="attached-unit:army-beta:enemy"
        )
        available = cast(dict[str, object], request.payload)["proposal_request"]
        weapons = cast(
            list[dict[str, object]], cast(dict[str, object], available)["available_weapons"]
        )
        first = proposal.declarations[0]
        other = next(
            row
            for row in weapons
            if row["model_instance_id"] != first.attacker_model_instance_id
            and row["weapon_profile_id"] == first.weapon_profile_id
        )
        proposal = replace(
            proposal,
            declarations=(
                *proposal.declarations,
                replace(
                    first,
                    attacker_model_instance_id=cast(str, other["model_instance_id"]),
                    weapon_instance_id=cast(str, other["weapon_instance_id"]),
                    target_unit_instance_id="army-beta:other",
                ),
            ),
        )
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id=f"{request.request_id}:fixture-choice",
            payload=validate_json_value(proposal.to_payload()),
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status
        return
    if request.decision_type == "submit_melee_declaration":
        melee = MeleeDeclarationProposalRequest.from_decision_request(request)
        declarations: list[dict[str, object]] = []
        models: set[str] = set()
        for weapon in melee.available_weapons:
            row = cast(dict[str, object], weapon)
            model_id = cast(str, row["model_instance_id"])
            if model_id in models or row["is_extra_attacks"] is True:
                continue
            targets = cast(list[str], row["engaged_target_unit_instance_ids"])
            if not targets:
                continue
            target = "attached-unit:army-beta:enemy" if not models else "army-beta:other"
            assert target in targets
            models.add(model_id)
            declarations.append(
                {
                    "attacker_model_instance_id": model_id,
                    "wargear_id": row["wargear_id"],
                    "weapon_profile_id": row["weapon_profile_id"],
                    "target_allocations": [{"target_unit_instance_id": target}],
                }
            )
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id=f"{request.request_id}:fixture-choice",
            payload=validate_json_value(
                {
                    "proposal_request_id": melee.request_id,
                    "proposal_kind": melee.proposal_kind,
                    "player_id": melee.actor_id,
                    "battle_round": melee.battle_round,
                    "unit_instance_id": melee.unit_instance_id,
                    "source_decision_request_id": melee.source_decision_request_id,
                    "source_decision_result_id": melee.source_decision_result_id,
                    "declarations": declarations,
                }
            ),
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status
        return
    if request.decision_type in {
        "select_precision_allocation",
        "select_damage_allocation_model",
        "select_fight_activation",
        "select_resolve_target_unit",
    }:
        option = next(
            (
                option
                for option in request.options
                if source_model_id in canonical_json(option.payload)
                or (
                    request.decision_type == "select_fight_activation"
                    and "army-alpha:attacker" in canonical_json(option.payload)
                )
                or (
                    request.decision_type == "select_resolve_target_unit"
                    and "attached-unit:army-beta:enemy" in canonical_json(option.payload)
                )
            ),
            next(
                (option for option in request.options if "decline_precision" in option.option_id),
                request.options[0],
            ),
        )
        status = session.submit_option(
            request_id=request.request_id,
            result_id=f"{request.request_id}:fixture-choice",
            option_id=option.option_id,
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status
        return
    submit_fixture_request(session, request)


def reach_source_casualty(session: LocalGameSession, *, source_model_id: str) -> DecisionRequest:
    for _ in range(150):
        request = pending_request(session)
        state = session.lifecycle.state
        assert state is not None
        if not model_by_id(state=state, model_instance_id=source_model_id).is_alive:
            return request
        submit_source_choice(session, request, source_model_id=source_model_id)
    raise AssertionError("Source casualty was not reached.")
