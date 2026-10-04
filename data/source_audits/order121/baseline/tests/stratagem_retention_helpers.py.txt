"""Source-backed retained-reaction fixtures for both Core damage Stratagems."""

from dataclasses import replace

from tests.crushing_impact_helpers import complete_charge, crushing_session
from tests.explosives_helpers import explosives_scene
from tests.retained_attack_helpers import for_the_chapter_catalog
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.random_profile_values import resolved_profile_characteristic
from warhammer40k_core.engine.decision_request import DecisionRequest


def offered_stratagem_reaction(
    stratagem: str, *, collateral_depth: int = 0
) -> tuple[LocalGameSession, DecisionRequest]:
    catalog = replace(
        for_the_chapter_catalog(),
        wargear=ArmyCatalog.phase9a_canonical_content_pack().wargear,
    )
    catalog = replace(
        catalog,
        datasheets=tuple(
            replace(
                sheet,
                model_profiles=tuple(
                    replace(
                        profile,
                        characteristics=tuple(
                            replace(resolved_profile_characteristic(value), raw=1, base=1, final=1)
                            if value.characteristic is Characteristic.WOUNDS
                            else replace(
                                resolved_profile_characteristic(value), raw=96, base=96, final=96
                            )
                            if collateral_depth and value.characteristic is Characteristic.TOUGHNESS
                            else value
                            for value in profile.characteristics
                        ),
                    )
                    for profile in sheet.model_profiles
                ),
            )
            for sheet in catalog.datasheets
        ),
    )
    if stratagem == "crushing-impact":
        session = crushing_session(
            catalog=catalog,
            toughness=96,
            wounds=1,
            game_id="order49-retention-0" if collateral_depth == 1 else "order48-crushing-impact",
        )
    else:
        lifecycle, _ = explosives_scene(catalog=catalog, extra_friendly=collateral_depth == 1)
        session = LocalGameSession(lifecycle)
    if collateral_depth:
        from tests.crushing_impact_helpers import record_deadly_demise_for_fixture
        from warhammer40k_core.engine.lifecycle import GameLifecycle
        from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

        assert collateral_depth in (1, 2)
        state = session.lifecycle.state
        assert state is not None
        unit_ids = (
            ("army-alpha:source", "army-alpha:next")
            if stratagem == "crushing-impact"
            else ("army-beta:target", "army-alpha:source")
        )
        for unit_id in unit_ids[:collateral_depth]:
            model = rules_unit_view_by_id(state=state, unit_instance_id=unit_id).alive_models()[0]
            record_deadly_demise_for_fixture(session, model_instance_id=model.model_instance_id)
        # Reload catalog-backed sources alongside the fixture's added Deadly
        # Demise before the facade captures its replay starting checkpoint.
        session = LocalGameSession(GameLifecycle.from_payload(session.lifecycle.to_payload()))
    request = (
        complete_charge(session)
        if stratagem == "crushing-impact"
        else session.advance_until_decision_or_terminal()
    ).decision_request
    assert request is not None
    option = next(
        option
        for option in request.options
        if option.option_id.startswith(f"use-stratagem:{stratagem}:")
    )
    status = session.submit_option(
        request_id=request.request_id,
        option_id=option.option_id,
        result_id="order48:explosives-use",
    )
    for index in range(30):
        request = status.decision_request
        assert request is not None
        if request.decision_type == "select_destruction_reaction":
            if collateral_depth:
                from warhammer40k_core.engine.retained_destruction_state import (
                    destruction_cause_ancestor_ids,
                    retained_destructions,
                )

                state = session.lifecycle.state
                assert state is not None
                retained = next(
                    r
                    for r in retained_destructions(state=state)
                    if r.request_id == request.request_id
                )
                if len(destruction_cause_ancestor_ids(state=state, cause_id=retained.cause_id)) != (
                    collateral_depth
                ):
                    status = session.submit_option(
                        request_id=request.request_id,
                        option_id="decline_destruction_reaction",
                        result_id=f"r48-002:decline-ancestor:{index}",
                    )
                    continue
            return session, request
        assert request.decision_type == "select_mortal_wound_model", request
        status = session.submit_option(
            request_id=request.request_id,
            option_id=request.options[0].option_id,
            result_id=f"r48-001:allocate:{index}",
        )
    raise AssertionError("Stratagem did not offer its source-backed retained reaction.")


def finish_stratagem_reactions(session: LocalGameSession) -> None:
    from tests.phase13b_shooting_declaration_helpers import _proposal_from_request
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.phase import LifecycleStatusKind

    status = session.advance_until_decision_or_terminal()
    for index in range(100):
        if status.status_kind is LifecycleStatusKind.TERMINAL:
            return
        request = status.decision_request
        assert request is not None
        if request.decision_type in {
            "select_charging_unit",
            "select_shooting_unit",
            "select_movement_unit",
        }:
            return
        result_id = f"r48-001:finish:{index}"
        if request.decision_type == "submit_shooting_declaration":
            payload = request.payload
            assert isinstance(payload, dict)
            proposal_request = payload["proposal_request"]
            assert isinstance(proposal_request, dict)
            candidates = proposal_request["target_candidates"]
            assert isinstance(candidates, list)
            target = next(
                candidate
                for candidate in candidates
                if isinstance(candidate, dict) and candidate["is_legal"] is True
            )
            assert isinstance(target, dict)
            target_id = target["target_unit_instance_id"]
            assert isinstance(target_id, str)
            proposal = _proposal_from_request(request=request, target_unit_id=target_id)
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=result_id,
                payload=validate_json_value(proposal.to_payload()),
            )
        elif request.decision_type == "submit_stratagem_target_proposal":
            from warhammer40k_core.engine.stratagems import stratagem_decline_payload

            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=result_id,
                payload=stratagem_decline_payload(),
            )
        else:
            option = next(
                (
                    option
                    for option in request.options
                    if option.option_id
                    in {
                        "decline_stratagem_window",
                        "decline_destruction_reaction",
                    }
                ),
                request.options[0],
            )
            status = session.submit_option(
                request_id=request.request_id,
                option_id=option.option_id,
                result_id=result_id,
            )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status
    raise AssertionError("Retained Stratagem reactions did not finish.")
