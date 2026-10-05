"""Real catalog redeployment fixtures using the ordinary setup facade."""

from __future__ import annotations

# pyright: reportPrivateUsage=false
from dataclasses import replace
from functools import lru_cache

from tools.generate_ability_support_matrix import _ability_support_catalog_package

from tests.deployment_submission_helpers import submit_all_deployments_if_pending
from tests.phase11c_command_phase_helpers import (
    default_unit_selection,
    mission_setup,
    phase11c_config,
    unit_selection,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest
from warhammer40k_core.engine.battlefield_state import ModelPlacement
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.list_validation import (
    AttachmentDeclaration,
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_state_validation import (
    runtime_ruleset_descriptor_for_mission_setup,
)
from warhammer40k_core.engine.prebattle import (
    PreBattlePlacementProposal,
    PreBattleProposalRequest,
)
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27 as faction_detachment_source,
)

RANGERS = "000000592"
YRIEL = "000004193"


@lru_cache(maxsize=1)
def redeploy_catalog() -> ArmyCatalog:
    package = _ability_support_catalog_package(datasheet_ids=(RANGERS, YRIEL))
    catalog = package.army_catalog
    row = next(
        row
        for row in faction_detachment_source.detachment_rows()
        if row.faction_id == "aeldari" and row.detachment_id == "corsair-coterie"
    )
    detachment = DetachmentDefinition(
        canonical_detachment_id=row.detachment_id,
        detachment_id=row.detachment_id,
        name=row.name,
        faction_id="AE",
        detachment_point_cost=row.detachment_point_cost,
        unit_datasheet_ids=(RANGERS, YRIEL),
        force_disposition_ids=("take-and-hold", "purge-the-foe"),
        source_ids=row.source_ids,
    )
    return replace(catalog, detachments=(detachment,))


def redeploy_session(
    *, player_id: str = "player-a", target: str = "rangers", enemy_midfield: bool = False
) -> tuple[LocalGameSession, DecisionRequest]:
    catalog = redeploy_catalog()
    mission = mission_setup()
    selections = tuple(
        UnitMusterSelection(
            unit_selection_id=selection_id,
            datasheet_id=datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(
                    catalog.datasheet_by_id(datasheet_id).model_profiles[0].model_profile_id, count
                ),
            ),
        )
        for selection_id, datasheet_id, count in (("rangers", RANGERS, 5), ("yriel", YRIEL, 1))
    )
    config = GameConfig(
        game_id="order127-catalog-redeploy",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=runtime_ruleset_descriptor_for_mission_setup(
            mission, rules_overlay_ids=()
        ),
        army_catalog=catalog,
        army_muster_requests=tuple(
            ArmyMusterRequest(
                army_id=army_id,
                player_id=owner,
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id="AE", detachment_ids=("corsair-coterie",)
                ),
                force_disposition_id=disposition,
                unit_selections=selections,
            )
            for owner, army_id, disposition in (
                ("player-a", "army-alpha", "take-and-hold"),
                ("player-b", "army-beta", "purge-the-foe"),
            )
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down"),
        mission_setup=mission,
    )
    return _start_redeploy(
        config, player_id=player_id, target=target, enemy_midfield=enemy_midfield
    )


def canonical_attached_redeploy_session(
    *, all_infiltrators: bool
) -> tuple[LocalGameSession, DecisionRequest]:
    """Supplement the real catalog consumer with canonical whole-group controls."""
    config = phase11c_config(
        game_id="order127-attached-redeploy",
        player_a_units=(
            default_unit_selection("bodyguard"),
            unit_selection(
                unit_selection_id="leader",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
        ),
        player_a_attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="leader", bodyguard_unit_selection_id="bodyguard"
            ),
        ),
    )
    catalog = replace(
        config.army_catalog,
        datasheets=tuple(
            replace(
                sheet,
                keywords=replace(
                    sheet.keywords, keywords=(*sheet.keywords.keywords, "REDEPLOY", "INFILTRATORS")
                ),
            )
            if sheet.datasheet_id == "core-intercessor-like-infantry"
            or (all_infiltrators and sheet.datasheet_id == "core-character-leader")
            else replace(
                sheet,
                keywords=replace(sheet.keywords, keywords=(*sheet.keywords.keywords, "REDEPLOY")),
            )
            if sheet.datasheet_id == "core-character-leader"
            else sheet
            for sheet in config.army_catalog.datasheets
        ),
    )
    config = replace(config, army_catalog=catalog)
    return _start_redeploy(config, player_id="player-a", target="attached", enemy_midfield=False)


def _start_redeploy(
    config: GameConfig, *, player_id: str, target: str, enemy_midfield: bool
) -> tuple[LocalGameSession, DecisionRequest]:
    session = LocalGameSession()
    session.start(config)
    for index in range(2):
        status = session.advance_until_decision_or_terminal()
        request = status.decision_request
        assert request is not None, status.to_payload()
        session.submit_option(
            request_id=request.request_id,
            option_id="fixed:assassination:bring_it_down",
            result_id=f"secondary:{index}",
        )
    status = submit_all_deployments_if_pending(
        session.lifecycle,
        session.advance_until_decision_or_terminal(),
        result_id_prefix="order127-deploy",
        pose_factory=lambda index, owner, model_id: (
            Pose.at(31, 3 + index * 1.8)
            if enemy_midfield and owner != player_id and ":rangers:" in model_id
            else Pose.at(
                3 + (index // 3) * 1.8 if owner == "player-a" else 57 - (index // 3) * 1.8,
                (34 if ":yriel:" in model_id else 24) + (index % 3) * 1.8,
            )
        ),
    )
    request = status.decision_request
    assert request is not None, status.to_payload()
    while request.decision_type == "resolve_sequencing_order":
        status = session.submit_option(
            request_id=request.request_id,
            option_id=request.options[0].option_id,
            result_id=f"sequence:{session.decision_record_count()}",
        )
        request = status.decision_request
        assert request is not None, status.to_payload()
    if request.actor_id != player_id:
        status = session.submit_option(
            request_id=request.request_id,
            option_id="complete_redeploys",
            result_id="complete-other-redeploys",
        )
        request = status.decision_request
        assert request is not None, status.to_payload()
    assert request.actor_id == player_id
    army_id = "army-alpha" if player_id == "player-a" else "army-beta"
    option_id = (
        next(
            option.option_id
            for option in request.options
            if option.option_id.startswith("redeploy:") and "attached" in option.option_id
        )
        if target == "attached"
        else f"redeploy:{army_id}:{target}"
    )
    status = session.submit_option(
        request_id=request.request_id,
        option_id=option_id,
        result_id="select-redeploy",
    )
    request = status.decision_request
    assert request is not None, status.to_payload()
    return session, request


def redeploy_payload(
    session: LocalGameSession, request: DecisionRequest, poses: tuple[Pose, ...]
) -> dict[str, JsonValue]:
    context = PreBattleProposalRequest.from_decision_request_payload(request.payload)
    state = session.lifecycle.state
    assert state is not None
    assert context.placement_kind is not None
    assert len(poses) == len(context.model_instance_ids)
    placements: list[ModelPlacement] = []
    for model_id, pose in zip(context.model_instance_ids, poses, strict=True):
        army, unit = next(
            (army, unit)
            for army in state.army_definitions
            for unit in army.units
            if any(model.model_instance_id == model_id for model in unit.own_models)
        )
        placements.append(
            ModelPlacement(
                army_id=army.army_id,
                player_id=army.player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model_id,
                pose=pose,
            )
        )
    proposal = PreBattlePlacementProposal(
        proposal_request_id=context.request_id,
        proposal_kind=context.proposal_kind,
        game_id=context.game_id,
        ruleset_descriptor_hash=context.ruleset_descriptor_hash,
        setup_step=context.setup_step,
        player_id=context.player_id,
        unit_instance_id=context.unit_instance_id,
        action_kind=context.action_kind,
        source_rule_id=context.source_rule_id,
        placement_kind=context.placement_kind,
        model_placements=tuple(placements),
    )
    payload = validate_json_value(proposal.to_payload())
    assert isinstance(payload, dict)
    return payload
