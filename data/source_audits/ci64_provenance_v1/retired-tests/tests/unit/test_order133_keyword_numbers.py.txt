"""Core number identities through real catalog-loaded unit and model consumers."""

from __future__ import annotations

import json

import pytest
from tests.core_clause_evidence_helpers import assert_persistence_viewers_replay
from tests.order122_helpers import submit_quiet_choice
from tests.order133_helpers import (
    SOURCE_ID,
    advance_to_number_keyword_selection,
    number_keyword_session,
)
from tests.support.ability_presence_fixtures import compiled_ability_rule

from warhammer40k_core.adapters.access_control import (
    ROLE_POLICY_BY_ROLE,
    PrincipalRole,
    ViewerContext,
)
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.modifiers import RollModifierOperation, resolve_roll_modifiers
from warhammer40k_core.engine.catalog_model_scope import scoped_roll_model_ids_for_effect
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.rule_target_resolution import unit_has_required_keywords
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import (
    ChargeRollModifierContext,
    RuntimeModifierRegistry,
)
from warhammer40k_core.rules.rule_ir import parameter_payload
from warhammer40k_core.rules.rule_keyword_sequences import keyword_sequence_tokens
from warhammer40k_core.rules.rule_token_normalization import keyword_any_tokens, keyword_list_tokens


@pytest.mark.parametrize(
    ("singular", "plural", "canonical"),
    [
        ("CHARACTER", "CHARACTERS", "CHARACTER"),
        ("VEHICLE", "VEHICLES", "VEHICLE"),
        ("MONSTER", "MONSTERS", "MONSTER"),
        ("PSYKER", "PSYKERS", "PSYKER"),
        ("GRENADE", "GRENADES", "GRENADES"),
        ("IMMORTAL", "IMMORTALS", "IMMORTALS"),
        ("DEATHMARK", "DEATHMARKS", "DEATHMARKS"),
        ("GUARDIAN", "GUARDIANS", "GUARDIANS"),
    ],
)
def test_source_number_spellings_preserve_declared_runtime_token(
    singular: str,
    plural: str,
    canonical: str,
) -> None:
    for spelling in (singular, plural):
        assert keyword_sequence_tokens(spelling, source_keyword_sequence_parts=(canonical,)) == (
            canonical,
        )
        assert keyword_any_tokens(spelling) == (canonical,)
        assert keyword_list_tokens(spelling) == (canonical,)
        assert unit_has_required_keywords(
            unit_keywords=(canonical,),
            faction_keywords=(),
            required_keywords=(spelling,),
        )


def test_plural_adjacent_sequence_consumes_literal_alias_before_next_keyword() -> None:
    assert keyword_sequence_tokens(
        "PSYKERS CHARACTERS", source_keyword_sequence_parts=("PSYKER", "CHARACTER")
    ) == ("PSYKER", "CHARACTER")
    rule = compiled_ability_rule('Select one friendly CHARACTERS unit within 6" of this model.')
    assert not rule.diagnostics
    assert rule.clauses[0].target is not None
    assert parameter_payload(rule.clauses[0].target.parameters)["required_keyword"] == "CHARACTER"
    assert rule.clauses[0].target.source_span.text == "Select one friendly CHARACTERS unit"


@pytest.mark.parametrize("token", ["CHAOS", "LYCHGUARD", "INFANTRY", "UNKNOWN", "CUSTOMS"])
def test_unknown_and_invariant_tokens_are_not_stemmed(token: str) -> None:
    assert keyword_sequence_tokens(token, source_keyword_sequence_parts=(token,)) == (token,)
    assert not unit_has_required_keywords(
        unit_keywords=(token,), faction_keywords=(), required_keywords=(token + "S",)
    )


def assert_role_views(session: LocalGameSession) -> None:
    restored = LocalGameSession.from_persistence_payload(
        json.loads(json.dumps(session.to_persistence_payload()))
    )
    for role in PrincipalRole:
        for player in (
            ("player-a", "player-b")
            if role in {PrincipalRole.PLAYER, PrincipalRole.COACH}
            else (None,)
        ):
            viewer = ViewerContext(
                principal_id="order133:" + role.value,
                role=role,
                viewer_player_id=player,
                policy=ROLE_POLICY_BY_ROLE[role],
            )
            assert session.view_for_context(viewer=viewer) == restored.view_for_context(
                viewer=viewer
            )
            assert session.events_since_for_context(EventStreamCursor(), viewer=viewer) == (
                restored.events_since_for_context(EventStreamCursor(), viewer=viewer)
            )


@pytest.mark.parametrize("keyword", ["CHARACTER", "CHARACTERS"])
@pytest.mark.parametrize("attached", [True, False])
def test_catalog_loaded_selection_survives_full_lifecycle_continuations(
    keyword: str, attached: bool
) -> None:
    session = number_keyword_session(keyword=keyword, attached=attached)
    request = advance_to_number_keyword_selection(session)
    assert request.actor_id == "player-a"
    assert isinstance(request.payload, dict)
    assert request.payload["source_rule_id"] == SOURCE_ID
    assert request.payload["active_player_id"] == "player-b"
    assert request.payload["source_model_instance_id"] == "army-alpha:transport:core-transport:001"
    assert len(request.options) == 1
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    forked = session.fork()
    assert_persistence_viewers_replay(restored)
    assert_role_views(restored)
    with pytest.raises(DecisionError, match="finite action space"):
        restored.submit_option(
            request_id=request.request_id, option_id="decline", result_id="order133-invalid"
        )
    assert restored.to_persistence_payload() == checkpoint
    state = restored.lifecycle.state
    assert state is not None
    target = rules_unit_view_by_id(state=state, unit_instance_id="army-alpha:leader")
    assert "CHARACTER" in target.keywords
    character_ids = tuple(
        m.model_instance_id for m in target.own_models if "CHARACTER" in m.keywords
    )
    assert character_ids == ("army-alpha:leader:core-character-leader:001",)
    assert (
        scoped_roll_model_ids_for_effect(
            source_rules_unit=target,
            current_roll_model_instance_ids=tuple(m.model_instance_id for m in target.own_models),
            effect_parameters={"required_model_keyword": keyword},
        )
        == character_ids
    )
    restored.submit_option(
        request_id=request.request_id,
        option_id=request.options[0].option_id,
        result_id="order133-select",
    )
    assert forked.to_persistence_payload() == checkpoint
    effects = [effect for effect in state.persisting_effects if effect.source_rule_id == SOURCE_ID]
    assert len(effects) == 1
    assert effects[0].target_unit_instance_ids == (target.unit_instance_id,)
    context = ChargeRollModifierContext(
        state=state,
        unit_instance_id=target.unit_instance_id,
        current_roll_modifiers=(),
    )
    modifiers = RuntimeModifierRegistry.empty().charge_roll_modifiers(context)
    assert len(modifiers) == 1
    assert modifiers[0].operand == 1
    assert modifiers[0].operation is RollModifierOperation.ADD
    assert resolve_roll_modifiers(6, modifiers).final == 7
    assert modifiers[0].source_id is not None
    assert SOURCE_ID in modifiers[0].source_id
    assert_persistence_viewers_replay(restored)
    assert_role_views(restored)
    for index in range(180):
        status = restored.advance_until_decision_or_terminal()
        if state.battle_round == 2:
            break
        assert status.decision_request is not None
        submit_quiet_choice(restored, status.decision_request, result_id=f"order133-after-{index}")
    else:
        raise AssertionError("Full native turn continuation did not finish.")
    assert not [effect for effect in state.persisting_effects if effect.source_rule_id == SOURCE_ID]
    assert RuntimeModifierRegistry.empty().charge_roll_modifiers(context) == ()
    assert_persistence_viewers_replay(restored)
    assert_role_views(restored)
