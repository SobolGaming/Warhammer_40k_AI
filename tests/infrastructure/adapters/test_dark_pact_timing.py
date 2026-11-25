"""Native selected-to-shoot/fight Dark Pacts and exact current replay."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from tests.core_stratagem_helpers import _clear_terrain
from tests.fire_overwatch_helpers import finish_overwatch, pending_overwatch
from tests.phase13b_shooting_declaration_helpers import (
    _compact_intercessor_catalog,
    _proposal_from_request,
)
from tests.phase15c_fight_order_helpers import (
    drain_fight_movement_requests,
    fight_config,
    fight_lifecycle,
)
from tests.phase17n_primary_mission_helpers import append_authenticated_normal_move
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request
from tests.setup_completion_helpers import record_primary_turn_start_evidence_for_fixture
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attachment_eligibility import AttachmentTargetEligibility
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
    DatasheetKeywordSet,
    DatasheetWargearOption,
    UnitCompositionDefinition,
)
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.faction_aliases import (
    CHAOS_DAEMONS_FACTION_ID,
    CHAOS_SPACE_MARINES_FACTION_ID,
)
from warhammer40k_core.core.ruleset_descriptor import FightTypeKind
from warhammer40k_core.core.weapon_profiles import RangeProfile, WeaponKeyword
from warhammer40k_core.engine.battle_formation_hooks import BattleFormationRequestContext
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.damage_allocation import FeelNoPainSource
from warhammer40k_core.engine.decision_request import DecisionError, DecisionRequest
from warhammer40k_core.engine.effects import EffectExpiration
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_space_marines import (
    army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.drukhari import army_rule as pain
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.drukhari import (
    power_from_pain,
)
from warhammer40k_core.engine.fight_order import fight_activation_option_id
from warhammer40k_core.engine.fight_resolution import MeleeDeclarationProposalRequest
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleStage,
    LifecycleStatusKind,
    SetupStep,
)
from warhammer40k_core.engine.phases.movement import MovementPhaseState
from warhammer40k_core.engine.phases.shooting_model import COMPLETE_SHOOTING_PHASE_OPTION_ID
from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.stratagems import (
    StratagemTargetBinding,
    StratagemTargetKind,
    StratagemTargetProposal,
    StratagemTargetProposalPayload,
)
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool, RangedAttackPoolPayload
from warhammer40k_core.geometry.pose import Pose

ACTOR = "army-alpha:attacker"
TARGET = "army-beta:enemy"
DATASHEET = "pact-test-marine"
LEADER = "army-alpha:leader"
LEADER_SHEET = "core-character-leader"
PAIN_DETACHMENT = "pain-reaction-fixture"
MODEL = "core-intercessor-like"
RESOLVED = "chaos_space_marines_dark_pact_resolved"


def _catalog(case: str, *, faction: str, detachment: str, attached: bool) -> ArmyCatalog:
    catalog = _compact_intercessor_catalog(ArmyCatalog.phase9a_canonical_content_pack())
    base = catalog.datasheet_by_id("core-intercessor-like-infantry")
    (model,) = base.model_profiles
    leadership = 2 if case in {"pass", "decline"} else 12
    profiles = tuple(
        replace(
            model,
            model_profile_id=model_id,
            characteristics=tuple(
                CharacteristicValue.from_raw(value.characteristic, leadership)
                if value.characteristic is Characteristic.LEADERSHIP
                else CharacteristicValue.from_raw(value.characteristic, wounds)
                if value.characteristic is Characteristic.WOUNDS
                else value
                for value in model.characteristics
            ),
        )
        for model_id, wounds in (
            ("special-marine", 1 if case in {"casualty", "wipe", "only-gun"} else 6),
            ("standard-marine", 6),
        )
    )
    rifle = next(item for item in catalog.wargear if item.wargear_id == "core-bolt-rifle")
    (ranged,) = rifle.weapon_profiles
    armed = tuple(
        replace(
            rifle,
            wargear_id=f"{prefix}-arms",
            weapon_profiles=(
                *(
                    ()
                    if prefix == "standard" and case == "only-gun"
                    else (replace(ranged, profile_id=f"{prefix}-ranged"),)
                ),
                replace(
                    ranged,
                    profile_id=f"{prefix}-melee",
                    range_profile=RangeProfile.melee(),
                    skill=CharacteristicValue.from_raw(Characteristic.WEAPON_SKILL, 3),
                ),
            ),
        )
        for prefix in ("unique", "standard")
    )
    daemons = faction == CHAOS_DAEMONS_FACTION_ID
    faction_keyword = {
        CHAOS_DAEMONS_FACTION_ID: "Legiones Daemonica",
        CHAOS_SPACE_MARINES_FACTION_ID: "Heretic Astartes",
        power_from_pain.DRUKHARI_FACTION_ID: "Drukhari",
    }[faction]
    faction_name = {
        CHAOS_DAEMONS_FACTION_ID: "Chaos Daemons",
        CHAOS_SPACE_MARINES_FACTION_ID: "Chaos Space Marines",
        power_from_pain.DRUKHARI_FACTION_ID: "Drukhari",
    }[faction]
    marine = replace(
        base,
        datasheet_id=DATASHEET,
        name="Be'lakor" if daemons else "Dark Pact test marine",
        keywords=DatasheetKeywordSet(
            keywords=(*base.keywords.keywords, "Undivided") if daemons else base.keywords.keywords,
            faction_keywords=(faction_keyword,),
        ),
        model_profiles=profiles,
        composition=(
            UnitCompositionDefinition(
                model_profile_id="special-marine", min_models=1, max_models=1
            ),
            UnitCompositionDefinition(
                model_profile_id="standard-marine",
                min_models=0,
                max_models=1,
                allows_zero_models=True,
            ),
        ),
        wargear_options=tuple(
            DatasheetWargearOption(
                option_id=f"{profile.model_profile_id}-arms",
                model_profile_id=profile.model_profile_id,
                default_wargear_ids=(weapon.wargear_id,),
                allowed_wargear_ids=(weapon.wargear_id,),
                min_selections=1,
                max_selections=1,
            )
            for profile, weapon in zip(profiles, armed, strict=True)
        ),
    )
    if faction == power_from_pain.DRUKHARI_FACTION_ID:
        marine = replace(
            marine,
            abilities=(
                DatasheetAbilityDescriptor(
                    ability_id="fixture-hatred-eternal",
                    name="Hatred Eternal (Pain)",
                    source_id="fixture:hatred-eternal",
                    support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
                    source_kind=CatalogAbilitySourceKind.DATASHEET,
                    parameter_tokens=(power_from_pain.HATRED_ETERNAL_ABILITY_KEY,),
                    effect_description="When empowered, this unit can re-roll hit rolls.",
                ),
            ),
        )
    datasheets = catalog.datasheets
    if attached:
        leader = catalog.datasheet_by_id(LEADER_SHEET)
        leader = replace(
            leader,
            keywords=replace(leader.keywords, faction_keywords=(faction_keyword,)),
            attachment_eligibilities=tuple(
                replace(
                    eligibility,
                    targets=(AttachmentTargetEligibility(DATASHEET, ("fixture:leader",)),),
                )
                for eligibility in leader.attachment_eligibilities
            ),
            model_profiles=tuple(
                replace(
                    profile,
                    characteristics=tuple(
                        CharacteristicValue.from_raw(value.characteristic, leadership)
                        if value.characteristic is Characteristic.LEADERSHIP
                        else value
                        for value in profile.characteristics
                    ),
                )
                for profile in leader.model_profiles
            ),
        )
        datasheets = tuple(
            leader if sheet.datasheet_id == LEADER_SHEET else sheet for sheet in datasheets
        )
    return replace(
        catalog,
        datasheets=(*datasheets, marine),
        factions=(
            *catalog.factions,
            FactionDefinition(
                faction_id=faction,
                name=faction_name,
                faction_keywords=(faction_keyword,),
                source_ids=(army_rule.SOURCE_RULE_ID,),
            ),
        ),
        detachments=(
            *catalog.detachments,
            DetachmentDefinition(
                canonical_detachment_id=detachment,
                detachment_id=detachment,
                name=detachment,
                faction_id=faction,
                detachment_point_cost=1,
                unit_datasheet_ids=(DATASHEET, LEADER_SHEET) if attached else (DATASHEET,),
                force_disposition_ids=("purge-the-foe",),
                source_ids=(army_rule.SOURCE_RULE_ID,),
            ),
        ),
        wargear=(*catalog.wargear, *armed),
    )


def _session(
    phase: BattlePhase, case: str, *, detachment: str = "pactbound-zealots", attached: bool = False
) -> tuple[LocalGameSession, str]:
    faction = {
        "pactbound-zealots": CHAOS_SPACE_MARINES_FACTION_ID,
        "shadow-legion": CHAOS_DAEMONS_FACTION_ID,
        "blood-legion": CHAOS_DAEMONS_FACTION_ID,
        PAIN_DETACHMENT: power_from_pain.DRUKHARI_FACTION_ID,
    }[detachment]
    catalog = _catalog(case, faction=faction, detachment=detachment, attached=attached)
    game_id = "dark-pact-native-fixture-6"
    alpha_ids = ("attacker", "leader") if attached else ("attacker",)
    alpha_specs = {"attacker": (DATASHEET, "special-marine", 1)}
    if attached:
        alpha_specs["leader"] = (LEADER_SHEET, LEADER_SHEET, 1)
    config = fight_config(
        game_id=game_id,
        catalog=catalog,
        alpha_unit_ids=alpha_ids,
        enemy_unit_ids=("enemy",),
        datasheet_id="core-intercessor-like-infantry",
        model_profile_id=MODEL,
        model_count=1,
        alpha_unit_specs=alpha_specs,
        alpha_attachment_declarations=(AttachmentDeclaration("leader", "attacker"),)
        if attached
        else (),
        alpha_faction_id=faction,
        alpha_detachment_ids=(detachment,),
    )
    poses: tuple[Pose, ...] = (Pose.at(10, 10),)
    if case in {"casualty", "only-gun"}:
        attacker, defender = config.army_muster_requests
        (selection,) = attacker.unit_selections
        selection = replace(
            selection,
            model_profile_selections=(
                *selection.model_profile_selections,
                ModelProfileSelection("standard-marine", 1),
            ),
        )
        config = replace(
            config, army_muster_requests=(replace(attacker, unit_selections=(selection,)), defender)
        )
        poses = (*poses, Pose.at(10, 11.45))
    enemy = Pose.at(11.75, 10.7) if phase is BattlePhase.FIGHT else Pose.at(25, 10)
    placements = {"attacker": poses, "enemy": (enemy,)}
    if attached:
        placements["leader"] = (Pose.at(11.6, 12.55),)
    lifecycle, units = fight_lifecycle(
        game_id=game_id,
        config=config,
        alpha_unit_ids=alpha_ids,
        enemy_unit_ids=("enemy",),
        origins={key: unit_poses[0] for key, unit_poses in placements.items()},
        poses_by_unit_key=placements,
        charge_fights_first_unit_keys=("attacker",) if phase is BattlePhase.FIGHT else (),
        battle_phase=phase,
        record_deployment=True,
    )
    bundle = lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    if detachment == "shadow-legion":
        state = lifecycle.state
        assert state is not None
        state.stage = GameLifecycleStage.SETUP
        state.setup_step_index = state.setup_sequence.index(SetupStep.DECLARE_BATTLE_FORMATIONS)
        formation = BattleFormationRequestContext(
            state=state,
            decisions=lifecycle.decision_controller,
            config=config,
        )
        for binding in bundle.battle_formation_hook_registry.all_bindings():
            if binding.request_handler is not None:
                assert binding.request_handler(formation) is None
        state.setup_step_index = None
        state.stage = GameLifecycleStage.BATTLE
    special = next(
        model
        for model in units["attacker"].own_models
        if model.model_profile_id == "special-marine"
    )
    return LocalGameSession(lifecycle), special.model_instance_id


def _choose(session: LocalGameSession, request: DecisionRequest, option_id: str) -> None:
    status = session.submit_option(
        request_id=request.request_id,
        option_id=option_id,
        result_id=f"{request.request_id}:dark-pact-fixture",
    )
    assert status.status_kind not in {LifecycleStatusKind.INVALID, LifecycleStatusKind.UNSUPPORTED}


def _select(session: LocalGameSession, phase: BattlePhase, *, actor: str = ACTOR) -> None:
    status = session.advance_until_decision_or_terminal()
    if phase is BattlePhase.FIGHT:
        status = drain_fight_movement_requests(session.lifecycle, status)
    request = status.decision_request
    assert request is not None
    assert request.decision_type == (
        "select_fight_activation" if phase is BattlePhase.FIGHT else "select_shooting_unit"
    )
    _choose(
        session,
        request,
        fight_activation_option_id(unit_instance_id=actor, fight_type=FightTypeKind.NORMAL)
        if phase is BattlePhase.FIGHT
        else actor,
    )


def _events(session: LocalGameSession, event_type: str) -> list[dict[str, JsonValue]]:
    return [
        event.payload
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type == event_type and isinstance(event.payload, dict)
    ]


def _pact_rolls(session: LocalGameSession) -> list[str]:
    rolls: list[str] = []
    for payload in _events(session, "dice_rolled"):
        spec = payload.get("spec")
        if isinstance(spec, dict):
            roll_type = spec.get("roll_type")
            if isinstance(roll_type, str) and roll_type.startswith(
                "chaos_space_marines.dark_pact_"
            ):
                rolls.append(roll_type)
    return rolls


def _declared_weapons(request: DecisionRequest, phase: BattlePhase) -> list[dict[str, JsonValue]]:
    if phase is BattlePhase.FIGHT:
        return [
            cast(dict[str, JsonValue], row)
            for row in MeleeDeclarationProposalRequest.from_decision_request(
                request
            ).available_weapons
        ]
    assert isinstance(request.payload, dict)
    proposal = request.payload["proposal_request"]
    assert isinstance(proposal, dict)
    return cast(list[dict[str, JsonValue]], proposal["available_weapons"])


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
@pytest.mark.parametrize("case", ["decline", "pass", "survive", "casualty", "wipe", "fnp"])
def test_dark_pact_selection_resolves_before_attacks(phase: BattlePhase, case: str) -> None:
    session, special_model_id = _session(phase, case)
    if case == "fnp":
        state = session.lifecycle.state
        assert state is not None
        state.record_model_feel_no_pain_sources(
            model_instance_id=special_model_id,
            sources=(
                FeelNoPainSource(source_id="test:pact-fnp-5", threshold=5),
                FeelNoPainSource(source_id="test:pact-fnp-6", threshold=6),
            ),
        )
    initial = session.lifecycle.to_payload()
    _select(session, phase)
    commitment = pending_request(session)
    assert [option.label for option in commitment.options] == [
        "Decline Dark Pact",
        "Make a Dark Pact",
    ]
    assert _pact_rolls(session) == []
    assert _events(session, RESOLVED) == []

    # A future effect ID cannot be submitted at the commitment window.
    with pytest.raises(DecisionError, match="finite action space"):
        session.submit_option(
            request_id=commitment.request_id,
            option_id=army_rule.SHOOTING_LETHAL_HITS_HOOK_ID,
            result_id="invented-early-effect",
        )
    assert pending_request(session) == commitment
    assert _pact_rolls(session) == []

    if case == "decline":
        _choose(session, commitment, commitment.options[0].option_id)
        assert _pact_rolls(session) == []
        assert _events(session, RESOLVED) == []
    else:
        _choose(session, commitment, commitment.options[1].option_id)
        while (request := pending_request(session)).decision_type == "select_mortal_wound_model":
            option = next(
                (
                    option
                    for option in request.options
                    if isinstance(option.payload, dict)
                    and option.payload.get("selected_model_id") == special_model_id
                ),
                request.options[0],
            )
            _choose(session, request, option.option_id)
        if case == "fnp":
            choices = 0
            while (request := pending_request(session)).decision_type == "select_feel_no_pain":
                assert _events(session, RESOLVED) == []
                assert len(_pact_rolls(session)) == 2
                _choose(session, request, "test:pact-fnp-5")
                choices += 1
            assert choices > 0
        (resolution,) = _events(session, RESOLVED)
        assert resolution["passed"] is (case == "pass"), resolution
        assert len(_pact_rolls(session)) == (1 if case == "pass" else 2)
        state = session.lifecycle.state
        assert state is not None
        survivors = rules_unit_view_by_id(state=state, unit_instance_id=ACTOR).alive_models()
        if case in {"casualty", "wipe"}:
            assert all(model.model_instance_id != special_model_id for model in survivors)
        if case == "wipe":
            assert not survivors
        else:
            request = pending_request(session)
            assert {option.label for option in request.options} == {
                "Dark Pacts: Lethal Hits",
                "Dark Pacts: Sustained Hits 1",
            }
            assert not _events(session, "shooting_declaration_accepted")
            assert not _events(session, "melee_declaration_accepted")
            _choose(session, request, request.options[1 if case == "survive" else 0].option_id)

    ordinary_pact = None
    if case == "pass" and phase is BattlePhase.SHOOTING:
        state = session.lifecycle.state
        assert state is not None
        ordinary_pact = army_rule.active_dark_pact_effect_for_unit(
            state, unit_instance_id=ACTOR, phase=phase
        )
        assert ordinary_pact is not None
        assert ordinary_pact.expiration == EffectExpiration.end_phase(
            battle_round=1, phase=phase, player_id="player-a"
        )

    attack_event = (
        "shooting_declaration_accepted"
        if phase is BattlePhase.SHOOTING
        else "melee_declaration_accepted"
    )
    if case != "wipe":
        if phase is BattlePhase.SHOOTING:
            request = pending_request(session)
            assert request.decision_type == "select_shooting_type"
            _choose(session, request, "normal")
        request = pending_request(session)
        assert request.decision_type in {"submit_shooting_declaration", "submit_melee_declaration"}
        weapons = _declared_weapons(request, phase)
        assert weapons
        if case == "casualty":
            assert all(row["model_instance_id"] != special_model_id for row in weapons)
            assert all(not str(row["weapon_profile_id"]).startswith("unique-") for row in weapons)
        else:
            assert any(str(row["weapon_profile_id"]).startswith("unique-") for row in weapons)
        if phase is BattlePhase.SHOOTING:
            proposal = _proposal_from_request(request=request, target_unit_id=TARGET)
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id="accepted-attacks",
                payload=validate_json_value(proposal.to_payload()),
            )
            assert status.status_kind not in {
                LifecycleStatusKind.INVALID,
                LifecycleStatusKind.UNSUPPORTED,
            }
        else:
            submit_fixture_request(session, request)
        for _ in range(20):
            if any(
                "attack_sequence.hit" in str(payload.get("spec", {}))
                for payload in _events(session, "dice_rolled")
            ):
                break
            submit_fixture_request(session, pending_request(session))
        else:
            pytest.fail("The surviving selected unit never rolled for an attack.")
        (declaration,) = _events(session, attack_event)
        if phase is BattlePhase.FIGHT:
            accepted = declaration["proposal"]
            assert isinstance(accepted, dict)
            submitted = accepted["declarations"]
        else:
            submitted = declaration["attack_pools"]
        assert isinstance(submitted, list)
        assert submitted
        if case == "casualty":
            assert all(
                isinstance(row, dict) and row["attacker_model_instance_id"] != special_model_id
                for row in submitted
            )
    else:
        assert pending_request(session).decision_type not in {
            "submit_shooting_declaration",
            "submit_melee_declaration",
        }
        assert not _events(session, attack_event)
        assert not any("attack_sequence.hit" in str(row) for row in _events(session, "dice_rolled"))

    if ordinary_pact is not None:
        state = session.lifecycle.state
        assert state is not None
        for _ in range(40):
            next_status = session.advance_until_decision_or_terminal()
            if state.current_battle_phase is not phase:
                break
            next_request = next_status.decision_request
            assert next_request is not None
            if next_request.decision_type == "select_shooting_unit":
                _choose(session, next_request, COMPLETE_SHOOTING_PHASE_OPTION_ID)
            else:
                submit_fixture_request(session, next_request)
        else:
            pytest.fail("Ordinary Shooting did not reach phase end.")
        assert ordinary_pact not in state.persisting_effects

    artifact = ReplayArtifact.capture(
        artifact_id=f"dark-pact-{phase.value}-{case}",
        initial_lifecycle_payload=initial,
        final_lifecycle=session.lifecycle,
    )
    replay = ReplayRunner(ReplayArtifact.from_payload(artifact.to_payload())).run()
    assert replay.reproduced_exactly, replay.to_payload()


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
@pytest.mark.parametrize("detachment", ["shadow-legion", "blood-legion"])
def test_only_shadow_legion_offers_belakor_the_no_roll_pact(
    phase: BattlePhase,
    detachment: str,
) -> None:
    session, _ = _session(phase, "wipe", detachment=detachment)
    initial = session.lifecycle.to_payload()
    _select(session, phase)
    request = pending_request(session)
    if detachment == "shadow-legion":
        assert request.options[1].label == "Make a Dark Pact"
        _choose(session, request, request.options[1].option_id)
        (resolution,) = _events(session, RESOLVED)
        assert resolution["source_rule_id"] == army_rule.SHADOW_LEGION_SOURCE_RULE_ID
        assert resolution["passed"] is True
        assert resolution["leadership_auto_pass"] is True
        assert resolution["leadership_target"] is None
        assert resolution["leadership_roll"] is None
        assert resolution["mortal_wound_application"] is None
        assert _pact_rolls(session) == []
        assert {option.label for option in pending_request(session).options} == {
            "Dark Pacts: Lethal Hits",
            "Dark Pacts: Sustained Hits 1",
        }
    else:
        assert not any("Dark Pact" in option.label for option in request.options)
        assert _pact_rolls(session) == []
        assert _events(session, RESOLVED) == []
    replay = ReplayRunner(
        ReplayArtifact.capture(
            artifact_id=f"dark-pact-{detachment}-{phase.value}",
            initial_lifecycle_payload=initial,
            final_lifecycle=session.lifecycle,
        )
    ).run()
    assert replay.reproduced_exactly, replay.to_payload()


def test_dark_pact_survivor_without_a_legal_gun_ends_shooting_without_an_attack() -> None:
    session, special = _session(BattlePhase.SHOOTING, "only-gun")
    initial = session.lifecycle.to_payload()
    _select(session, BattlePhase.SHOOTING)
    request = pending_request(session)
    _choose(session, request, request.options[1].option_id)
    request = pending_request(session)
    assert request.decision_type == "select_mortal_wound_model"
    option = next(
        option
        for option in request.options
        if isinstance(option.payload, dict) and option.payload.get("selected_model_id") == special
    )
    _choose(session, request, option.option_id)
    request = pending_request(session)
    assert {option.label for option in request.options} == {
        "Dark Pacts: Lethal Hits",
        "Dark Pacts: Sustained Hits 1",
    }
    _choose(session, request, request.options[0].option_id)
    request = pending_request(session)
    assert request.decision_type == "select_shooting_type"
    _choose(session, request, "normal")
    assert _events(session, "shooting_declaration_accepted") == []
    (ended,) = _events(session, "shooting_without_attacks_completed")
    assert ended["unit_instance_id"] == ACTOR
    replay = ReplayRunner(
        ReplayArtifact.capture(
            artifact_id="dark-pact-no-gun",
            initial_lifecycle_payload=initial,
            final_lifecycle=session.lifecycle,
        )
    ).run()
    assert replay.reproduced_exactly, replay.to_payload()


@pytest.mark.parametrize("case", ["pass", "survive"])
def test_attached_fight_dark_pact_targets_formation_through_attack_and_replay(case: str) -> None:
    session, special = _session(BattlePhase.FIGHT, case, attached=True)
    state = session.lifecycle.state
    assert state is not None
    formation = rules_unit_view_by_id(state=state, unit_instance_id=ACTOR)
    assert set(formation.component_unit_instance_ids) == {ACTOR, LEADER}
    assert formation.unit_instance_id not in {ACTOR, LEADER}
    initial = session.lifecycle.to_payload()
    _select(session, BattlePhase.FIGHT, actor=formation.unit_instance_id)
    commitment = pending_request(session)
    _choose(session, commitment, commitment.options[1].option_id)
    while (request := pending_request(session)).decision_type == "select_mortal_wound_model":
        _choose(session, request, request.options[0].option_id)
    (resolution,) = _events(session, RESOLVED)
    assert resolution["passed"] is (case == "pass")
    assert len(_pact_rolls(session)) == (1 if case == "pass" else 2)
    assert not _events(session, "melee_declaration_accepted")
    benefit = (
        army_rule.FIGHT_LETHAL_HITS_HOOK_ID
        if case == "pass"
        else army_rule.FIGHT_SUSTAINED_HITS_HOOK_ID
    )
    _choose(session, request, benefit)
    effect = army_rule.active_dark_pact_effect_for_unit(
        state, unit_instance_id=formation.unit_instance_id, phase=BattlePhase.FIGHT
    )
    assert effect is not None
    assert effect.target_unit_instance_ids == (formation.unit_instance_id,)
    assert effect.expiration == EffectExpiration.end_phase(
        battle_round=1, phase=BattlePhase.FIGHT, player_id="player-a"
    )
    request = pending_request(session)
    assert request.decision_type == "submit_melee_declaration"
    submit_fixture_request(session, request)
    (declaration,) = _events(session, "melee_declaration_accepted")
    proposal = declaration["proposal"]
    assert isinstance(proposal, dict)
    assert isinstance(proposal["declarations"], list)
    attacker_ids: set[str] = set()
    for row in proposal["declarations"]:
        assert isinstance(row, dict)
        model_id = row["attacker_model_instance_id"]
        assert isinstance(model_id, str)
        attacker_ids.add(model_id)
    assert attacker_ids == {model.model_instance_id for model in formation.alive_models()}
    assert any(model.model_instance_id == special for model in formation.alive_models())
    fight_state = state.fight_phase_state
    assert fight_state is not None
    sequence = fight_state.attack_sequence
    assert sequence is not None
    expected_keyword = WeaponKeyword.LETHAL_HITS if case == "pass" else WeaponKeyword.SUSTAINED_HITS
    assert sequence.attack_pools
    assert all(expected_keyword in pool.weapon_profile.keywords for pool in sequence.attack_pools)
    for _ in range(40):
        if _events(session, "attack_sequence_completed"):
            break
        submit_fixture_request(session, pending_request(session))
    else:
        pytest.fail("The Attached formation never attacked.")
    artifact = ReplayArtifact.capture(
        artifact_id=f"attached-fight-dark-pact-{case}",
        initial_lifecycle_payload=initial,
        final_lifecycle=session.lifecycle,
    )
    replay = ReplayRunner(ReplayArtifact.from_payload(artifact.to_payload())).run()
    assert replay.reproduced_exactly, replay.to_payload()


def _overwatch_fixture(detachment: str) -> LocalGameSession:
    session, _ = _session(BattlePhase.MOVEMENT, "pass", detachment=detachment)
    lifecycle = session.lifecycle
    state = lifecycle.state
    assert state is not None
    state.active_player_id = "player-b"
    _clear_terrain(state)
    record_primary_turn_start_evidence_for_fixture(state, decisions=lifecycle.decision_controller)
    state.gain_command_points(
        player_id="player-a",
        amount=1,
        source_id="pact-reaction:cp",
        source_kind=CommandPointSourceKind.OTHER,
        cap_exempt=True,
    )
    if detachment == PAIN_DETACHMENT:
        state.gain_faction_resource(
            player_id="player-a",
            resource_kind=power_from_pain.PAIN_TOKEN_RESOURCE_KIND,
            amount=1,
            source_id="pain-reaction:token",
        )
    state.movement_phase_state = MovementPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-b",
        move_units_completed=True,
        selected_unit_ids=(TARGET,),
        moved_unit_ids=(TARGET,),
    )
    append_authenticated_normal_move(
        state=state,
        decisions=lifecycle.decision_controller,
        unit_instance_id=TARGET,
        suffix="pact-reaction",
        pose_transform=lambda pose: Pose.at(pose.position.x + 0.1, pose.position.y),
    )
    return session


@pytest.mark.parametrize("phase_scoped", [True, False])
def test_native_overwatch_grant_expires_at_its_own_boundary(phase_scoped: bool) -> None:
    session = _overwatch_fixture("pactbound-zealots" if phase_scoped else PAIN_DETACHMENT)
    initial = session.lifecycle.to_payload()
    stratagem = pending_overwatch(session)
    assert isinstance(stratagem.payload, dict)
    proposal = StratagemTargetProposal.from_payload(
        cast(StratagemTargetProposalPayload, stratagem.payload["proposal_request"])
    ).with_binding(StratagemTargetBinding(StratagemTargetKind.FRIENDLY_UNIT, "player-a", ACTOR))
    status = session.submit_parameterized_payload(
        request_id=stratagem.request_id,
        result_id="pact-reaction:use-overwatch",
        payload=validate_json_value({"proposal": proposal.to_payload()}),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    request = pending_request(session)
    if phase_scoped:
        assert request.options[1].label == "Make a Dark Pact"
        _choose(session, request, request.options[1].option_id)
        request = pending_request(session)
        (resolution,) = _events(session, RESOLVED)
        assert resolution["passed"] is True
    _choose(
        session,
        request,
        army_rule.SHOOTING_SUSTAINED_HITS_HOOK_ID
        if phase_scoped
        else pain.HATRED_ETERNAL_SHOOTING_HOOK_ID,
    )
    state = session.lifecycle.state
    assert state is not None
    assert state.out_of_phase_shooting_state is not None
    source = army_rule.SOURCE_RULE_ID if phase_scoped else power_from_pain.SOURCE_RULE_ID
    source_effects = tuple(e for e in state.persisting_effects if e.source_rule_id == source)
    assert len(source_effects) == (1 if phase_scoped else 2)
    assert state.out_of_phase_shooting_state.grant_effect_ids == (
        () if phase_scoped else tuple(e.effect_id for e in source_effects)
    )
    if phase_scoped:
        assert source_effects[0].expiration == EffectExpiration.end_phase(
            battle_round=1, phase=BattlePhase.MOVEMENT, player_id="player-b"
        )
    request = pending_request(session)
    assert request.decision_type == "submit_shooting_declaration"
    declaration = _proposal_from_request(request=request, target_unit_id=TARGET)
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="pact-reaction:attacks",
        payload=validate_json_value(declaration.to_payload()),
    )
    if phase_scoped:
        (accepted,) = _events(session, "out_of_phase_shooting_declaration_accepted")
        pools = accepted["attack_pools"]
        assert isinstance(pools, list)
        assert pools
        assert all(
            WeaponKeyword.SUSTAINED_HITS
            in RangedAttackPool.from_payload(
                cast(RangedAttackPoolPayload, pool)
            ).weapon_profile.keywords
            for pool in pools
        )
    finish_overwatch(session, status)
    state = session.lifecycle.state
    assert state is not None
    assert state.out_of_phase_shooting_state is None
    assert state.current_battle_phase is BattlePhase.MOVEMENT
    assert tuple(e for e in state.persisting_effects if e.source_rule_id == source) == (
        source_effects if phase_scoped else ()
    )
    (completion,) = _events(session, "out_of_phase_shooting_completed")
    assert completion["removed_grant_effects"] == (
        [] if phase_scoped else [e.to_payload() for e in source_effects]
    )
    assert any("attack_sequence.hit" in str(row["spec"]) for row in _events(session, "dice_rolled"))
    session.advance_until_decision_or_terminal()
    state = session.lifecycle.state
    assert state is not None
    assert state.current_battle_phase is not BattlePhase.MOVEMENT
    assert not any(e.source_rule_id == source for e in state.persisting_effects)
    artifact = ReplayArtifact.capture(
        artifact_id=f"dark-pact-reaction-expiry-{phase_scoped}",
        initial_lifecycle_payload=initial,
        final_lifecycle=session.lifecycle,
    )
    replay = ReplayRunner(ReplayArtifact.from_payload(artifact.to_payload())).run()
    assert replay.reproduced_exactly, replay.to_payload()
