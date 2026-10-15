from typing import TYPE_CHECKING, cast

from tests.shared.category_migration.s25_permission_relevance import (
    SHARED_PERMISSION_SOURCE,
    Characteristic,
    Counter,
    DecisionError,
    GameLifecycleError,
    JsonValue,
    LifecycleStatusKind,
    ModifierIgnoreKind,
    ModifierPermissionAttackContext,
    WeaponDeclarationPayload,
    WeaponSelectionContext,
    WeaponSelectionContextPayload,
    assert_checkpoint,
    declared_activated_relevance_ability,
    json,
    modifier_ignore_permissions_for_subject,
    modifier_ignore_sources_for_gathering,
    native_profile_request,
    proposal_from_request,
    pytest,
    replace,
    submit_fixture_request,
    validate_json_value,
    validate_save_gathering_characteristics,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.catalog_modifier_ignore_sources import (
        ModifierIgnoreSourceTemplate,
    )


def test_save_provider_output_inventory_keeps_unknown_and_validates_known_slots() -> None:
    validate_save_gathering_characteristics(None)
    validate_save_gathering_characteristics((Characteristic.INVULNERABLE_SAVE,))
    validate_save_gathering_characteristics((Characteristic.SAVE, Characteristic.ARMOR_PENETRATION))
    for malformed in (
        (),
        (Characteristic.TOUGHNESS,),
        (Characteristic.INVULNERABLE_SAVE, Characteristic.INVULNERABLE_SAVE),
        [Characteristic.INVULNERABLE_SAVE],
        ("invulnerable_save",),
    ):
        with pytest.raises(GameLifecycleError, match="typed unique slots"):
            validate_save_gathering_characteristics(
                cast(tuple[Characteristic, ...] | None, malformed)
            )


@pytest.mark.parametrize("player", ["player-a", "player-b"])
def test_public_selected_shared_unit_permission_keeps_source_and_attack_subjects(
    player: str,
) -> None:
    session, request = native_profile_request(player=player, mode="shared-unit-permission")
    target = "army-beta:scalar" if player == "player-a" else "army-alpha:scalar"
    proposal = proposal_from_request(request=request, target_unit_id=target).to_payload()
    offered = cast(
        dict[str, JsonValue], cast(dict[str, JsonValue], request.payload)["proposal_request"]
    )
    weapons = cast(list[dict[str, JsonValue]], offered["available_weapons"])
    first = proposal["declarations"][0]
    matching = [
        weapon for weapon in weapons if weapon["weapon_profile_id"] == first["weapon_profile_id"]
    ]
    proposal["declarations"] = [
        {
            **first,
            "attacker_model_instance_id": cast(str, weapon["model_instance_id"]),
            "weapon_instance_id": cast(str, weapon["weapon_instance_id"]),
        }
        for weapon in matching[:2]
    ]
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="s25-shared-unit:declaration",
        payload=validate_json_value(proposal),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    state = session.lifecycle.state
    assert state is not None
    assert state.shooting_phase_state is not None
    sequence = state.shooting_phase_state.attack_sequence
    assert sequence is not None
    group = sequence.current_gathered_group
    assert group is not None
    assert group.pool_indices == (0, 1)
    assert group.total_attacks == 4
    assert len({snapshot.rules_json for snapshot in group.native_snapshots}) == 1
    assert len({snapshot.source_proof_json for snapshot in group.native_snapshots}) == 2
    bundle = session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    source_rows: list[ModifierIgnoreSourceTemplate] = []
    for pool in sequence.attack_pools:
        sources = modifier_ignore_sources_for_gathering(
            state=state,
            ability_index=bundle.runtime_modifier_registry.modifier_permission_index(player),
            unit_instance_id=sequence.attacking_unit_instance_id,
            kind=ModifierIgnoreKind.HIT_ROLL,
            model_instance_id=pool.attacker_model_instance_id,
            weapon_profile_id=pool.weapon_profile_id,
            attack_context=ModifierPermissionAttackContext(
                sequence.attacking_unit_instance_id,
                pool.attacker_model_instance_id,
                pool.target_unit_instance_id,
                "attacker",
                sequence.source_phase,
                pool.weapon_profile,
                None,
                None,
            ),
        )
        assert not sources.catalog_permissions
        assert len(sources.persisted_source_templates) == 1
        row = sources.persisted_source_templates[0]
        subject = cast(dict[str, JsonValue], row.raw_payload["subject"])
        source = cast(dict[str, JsonValue], row.raw_payload["source"])
        persisted = cast(dict[str, JsonValue], row.raw_payload["persisting_effect"])
        assert subject["subject_model_instance_id"] == pool.attacker_model_instance_id
        assert subject["subject_weapon_profile_id"] == pool.weapon_profile_id
        assert source["source_id"] == SHARED_PERMISSION_SOURCE
        assert source["target_kind"] == "this_unit"
        assert source["source_model_instance_id"] != pool.attacker_model_instance_id
        assert source["source_component_unit_instance_id"] == (
            "army-alpha:leader" if player == "player-a" else "army-beta:leader"
        )
        assert persisted["owner_player_id"] == player
        assert persisted == validate_json_value(
            next(
                effect.to_payload()
                for effect in state.persisting_effects
                if effect.effect_id == persisted["effect_id"]
            )
        )
        assert row.comparison_payload["effect_id"] == persisted["effect_id"]
        semantic_subject = cast(dict[str, JsonValue], row.comparison_payload["subject"])
        assert not {
            "subject_model_instance_id",
            "subject_weapon_profile_id",
            "subject_component_unit_instance_id",
        }.intersection(semantic_subject)
        source_rows.append(row)
    assert source_rows[0].comparison_payload == source_rows[1].comparison_payload
    assert source_rows[0].raw_payload != source_rows[1].raw_payload
    for index in range(4):
        physical = sequence.attack_pools[index // 2]
        current = replace(sequence, attack_index=index).current_pool()
        assert current.attacker_model_instance_id == physical.attacker_model_instance_id
        assert current.weapon_selection_context == physical.weapon_selection_context
    pending = session.advance_until_decision_or_terminal().decision_request
    assert pending is not None
    before = session.to_persistence_payload()
    with pytest.raises(DecisionError, match="finite action space"):
        session.submit_option(
            request_id=pending.request_id,
            option_id="s25-shared-invalid",
            result_id="s25-shared-invalid",
        )
    assert session.to_persistence_payload() == before
    assert_checkpoint(session)
    for _ in range(120):
        if any(
            event.event_type == "attack_sequence_completed"
            for event in session.lifecycle.decision_controller.event_log.records
        ):
            break
        pending = session.advance_until_decision_or_terminal().decision_request
        assert pending is not None
        submit_fixture_request(session, pending)
    else:
        raise AssertionError("Native shared unit source did not complete.")
    assert_checkpoint(session)
    events = session.lifecycle.decision_controller.event_log.records
    selected = [
        event.payload for event in events if event.event_type == "catalog_shadow_form_selected"
    ]
    assert len(selected) == 1
    assert (
        cast(dict[str, JsonValue], selected[0])["selected_shadow_form_source_id"]
        == SHARED_PERMISSION_SOURCE
    )
    choices = [
        record.request
        for record in session.lifecycle.decision_controller.records
        if record.request.decision_type == "select_modifier_ignores"
    ]
    assert len(choices) == 4
    physical_subjects = Counter(
        (
            cast(
                str,
                cast(dict[str, JsonValue], cast(dict[str, JsonValue], choice.payload)["subject"])[
                    "model_instance_id"
                ],
            ),
            cast(
                str,
                cast(dict[str, JsonValue], cast(dict[str, JsonValue], choice.payload)["subject"])[
                    "weapon_profile_id"
                ],
            ),
        )
        for choice in choices
    )
    assert physical_subjects == Counter(
        {
            (pool.attacker_model_instance_id, pool.weapon_profile_id): 2
            for pool in sequence.attack_pools
        }
    )
    for choice in choices:
        assert choice.actor_id == player
        payload = cast(dict[str, JsonValue], choice.payload)
        subject = cast(dict[str, JsonValue], payload["subject"])
        assert subject["kind"] == ModifierIgnoreKind.HIT_ROLL.value
        permissions = cast(list[dict[str, JsonValue]], payload["permissions"])
        assert len(permissions) == 1
        context = cast(dict[str, JsonValue], permissions[0]["source_context"])
        assert context["subject_model_instance_id"] == subject["model_instance_id"]
        assert context["subject_weapon_profile_id"] == subject["weapon_profile_id"]
        assert (
            context["source_model_instance_id"]
            == cast(dict[str, JsonValue], source_rows[0].raw_payload["source"])[
                "source_model_instance_id"
            ]
        )
        assert permissions[0]["record_id"] == source_rows[0].comparison_payload["effect_id"]
    stages: dict[str, list[int]] = {"hit": [], "wound": []}
    for index, event in enumerate(events):
        if event.event_type == "dice_rolled" and isinstance(event.payload, dict):
            spec = cast(dict[str, JsonValue], event.payload["spec"])
            for name in stages:
                if spec.get("roll_type") == "attack_sequence." + name:
                    stages[name].append(index)
    assert len(stages["hit"]) == 4
    assert stages["wound"]
    assert max(stages["hit"]) < min(stages["wound"])


__all__: list[str] = []
__all__ += ["WeaponDeclarationPayload", "WeaponSelectionContext", "WeaponSelectionContextPayload"]
__all__ += ["declared_activated_relevance_ability", "json"]
__all__ += ["modifier_ignore_permissions_for_subject"]
