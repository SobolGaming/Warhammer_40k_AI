"""Loaded catalog discounts exercised through real shooting submissions."""

from dataclasses import replace
from typing import cast

from tests.core_stratagem_helpers import _clear_terrain
from tests.phase13b_shooting_declaration_helpers import (
    _canonical_catalog,
    _compact_intercessor_catalog,
    _proposal_from_request,
    _shooting_lifecycle,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    CatalogJsonObject,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.core.weapon_profiles import AttackProfile, DamageProfile
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import LifecycleStatus
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.source_data import RuleSourceText


def discounted_attack_session(*, cp: int) -> tuple[LocalGameSession, LifecycleStatus]:
    catalog = _compact_intercessor_catalog(_canonical_catalog())
    source = RuleSourceText.from_raw(
        source_id="test:order49:automatic-discount",
        raw_text=(
            "Each time you target this model's unit with a Stratagem, reduce the CP cost "
            "of that use of that Stratagem by 1CP."
        ),
        objective_scope=ObjectiveRuleScope.CORE_RULES,
    )
    rule_ir = compile_rule_source_text(source, source_keyword_sequence_parts=("INFANTRY",)).rule_ir
    ability = DatasheetAbilityDescriptor(
        ability_id="order49-automatic-discount",
        name="Automatic discount fixture",
        source_id=source.source_id,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        effect_description=source.raw_text,
        rule_ir_payload=cast(CatalogJsonObject, rule_ir.to_payload()),
    )
    catalog = replace(
        catalog,
        datasheets=tuple(replace(s, abilities=(*s.abilities, ability)) for s in catalog.datasheets),
        wargear=tuple(
            replace(
                w,
                weapon_profiles=tuple(
                    replace(
                        p,
                        attack_profile=AttackProfile.fixed(24),
                        damage_profile=DamageProfile.dice(DiceExpression(quantity=1, sides=6)),
                    )
                    if p.range_profile.distance_inches is not None
                    else p
                    for p in w.weapon_profiles
                ),
            )
            for w in catalog.wargear
        ),
    )
    lifecycle, _ = _shooting_lifecycle(
        alpha_unit_ids=("shooter",),
        game_id="order49-discounted-attacks",
        catalog=catalog,
        alpha_unit_specs=(
            ("shooter", "core-intercessor-like-infantry", "core-intercessor-like", 1),
        ),
        enemy_pose=Pose.at(12, 10),
    )
    state = lifecycle.state
    assert state is not None
    _clear_terrain(state)
    for player in state.player_ids:
        current = state.command_point_total(player)
        if current:
            state.spend_command_points(
                player_id=player, amount=current, source_id="order49:reset-cp"
            )
        if cp:
            state.gain_command_points(
                player_id=player,
                amount=cp,
                source_id="order49:fixture-cp",
                source_kind=CommandPointSourceKind.OTHER,
                cap_exempt=True,
            )
    session = LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle.to_payload()))
    status = session.advance_until_decision_or_terminal()
    for option_id in ("army-alpha:shooter", "normal"):
        request = status.decision_request
        assert request is not None
        status = session.submit_option(
            request_id=request.request_id, option_id=option_id, result_id=f"order49:{option_id}"
        )
    request = status.decision_request
    assert request is not None
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order49:declare-shooting",
        payload=validate_json_value(
            _proposal_from_request(request=request, target_unit_id="army-beta:enemy").to_payload()
        ),
    )
    return session, status
