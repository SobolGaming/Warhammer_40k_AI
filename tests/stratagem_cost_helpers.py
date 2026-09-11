"""Real catalog CP operations loaded through the canonical lifecycle bundle."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from tests.core_stratagem_helpers import _battle_lifecycle, _config
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    CatalogJsonObject,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.stratagem_catalog import eleventh_edition_core_stratagem_index
from warhammer40k_core.engine.stratagems import (
    FIRE_OVERWATCH_TRIGGER_CONTEXT_KEY,
    StratagemEligibilityContext,
    StratagemTargetProposal,
    request_stratagem_target_proposal,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.source_data import RuleSourceText


def cost_session(
    *, available_cp: int, optional_increases: bool = True, discount: int = 0
) -> LocalGameSession:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    sheet = catalog.datasheet_by_id("core-intercessor-like-infantry")
    texts = [
        "Once per turn, when your opponent targets a unit from their army "
        'within 12" of this model with a Stratagem, '
        "you can use this ability. If you do, increase the CP cost of that use of that "
        "Stratagem by 1CP."
        if optional_increases
        else "Each time your opponent targets a unit from their army "
        'within 12" of this model with a Stratagem, '
        "increase the CP cost of that use of that Stratagem by 1CP."
    ]
    if discount:
        texts.append(
            "Each time you target this model's unit with a Stratagem, reduce the CP cost "
            f"of that use of that Stratagem by {discount}CP."
        )
    abilities: list[DatasheetAbilityDescriptor] = []
    for i, text in enumerate(texts):
        source = RuleSourceText.from_raw(
            source_id=f"test:order37:cost-{i}",
            raw_text=text,
            objective_scope=ObjectiveRuleScope.CORE_RULES,
        )
        rule_ir = compile_rule_source_text(
            source, source_keyword_sequence_parts=("INFANTRY",)
        ).rule_ir
        abilities.append(
            DatasheetAbilityDescriptor(
                ability_id=f"order37-cost-{i}",
                name=f"Cost operation fixture {i}",
                source_id=source.source_id,
                support=CatalogAbilitySupport.GENERIC_RULE_IR,
                source_kind=CatalogAbilitySourceKind.DATASHEET,
                effect_description=source.raw_text,
                rule_ir_payload=cast(CatalogJsonObject, rule_ir.to_payload()),
            )
        )
    catalog = replace(
        catalog,
        datasheets=tuple(
            replace(s, abilities=(*s.abilities, *abilities))
            if s.datasheet_id == sheet.datasheet_id
            else s
            for s in catalog.datasheets
        ),
    )
    config = _config(catalog=catalog, beta_unit_selection_ids=("reserve-0",))
    lifecycle = _battle_lifecycle(
        config,
        battle_round=1,
        pose_replacements=(
            ("army-alpha:intercessor-unit-1", tuple(Pose.at(x=10 + i, y=10) for i in range(5))),
            ("army-beta:reserve-0", tuple(Pose.at(x=18 + i, y=10) for i in range(5))),
        ),
        clear_terrain=True,
    )
    state = lifecycle.state
    assert state is not None
    total = state.command_point_total("player-b")
    if total:
        state.spend_command_points(player_id="player-b", amount=total, source_id="order37:reset")
    if available_cp:
        state.gain_command_points(
            player_id="player-b",
            amount=available_cp,
            source_id="order37:fixture",
            source_kind=CommandPointSourceKind.OTHER,
            cap_exempt=True,
        )
    context = StratagemEligibilityContext.from_state(
        state=state,
        player_id="player-b",
        trigger_kind=TimingTriggerKind.END_PHASE,
        trigger_payload={
            FIRE_OVERWATCH_TRIGGER_CONTEXT_KEY: "army-alpha:intercessor-unit-1",
            "movement_phase_action": "normal_move",
            "movement_payload": {
                "unit_instance_id": "army-alpha:intercessor-unit-1",
                "movement_phase_action": "normal_move",
            },
        },
    )
    record = next(
        r
        for r in eleventh_edition_core_stratagem_index().all_records()
        if r.definition.stratagem_id == "fire-overwatch"
    )
    status = request_stratagem_target_proposal(
        state=state,
        decisions=lifecycle.decision_controller,
        proposal_request=StratagemTargetProposal.for_request(
            context=context, catalog_record=record
        ),
        stratagem_cost_modifier_registry=(
            lifecycle._require_runtime_content_bundle().stratagem_cost_modifier_registry  # pyright: ignore[reportPrivateUsage]
        ),
    )
    assert status.decision_request is not None, status
    return LocalGameSession(lifecycle=lifecycle)
