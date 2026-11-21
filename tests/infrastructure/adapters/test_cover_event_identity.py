"""Viewer projection of an attack save with source-backed Cover."""

from typing import cast

import pytest

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.redaction import viewer_event_records, viewer_identity_map
from warhammer40k_core.adapters.viewer_identity import ViewerIdentityError
from warhammer40k_core.engine.event_log import EventLog, JsonValue, canonical_json


def _cover_keys(value: JsonValue) -> list[JsonValue]:
    assert isinstance(value, dict)
    step = value["payload"]
    assert isinstance(step, dict)
    selected = step["option"]
    all_options = step["save_options"]
    assert isinstance(selected, dict)
    assert isinstance(all_options, list)
    options = [selected, *all_options]
    cover_results = [cast(dict[str, JsonValue], option)["cover_result"] for option in options]
    assert all(isinstance(cover, dict) and cover["has_benefit"] is True for cover in cover_results)
    return [cast(dict[str, JsonValue], cover)["los_cache_key"] for cover in cover_results]


def test_save_cover_cache_key_projects_embedded_request_reference() -> None:
    raw_key = "attack-sequence:decision-request-000003:section04:pool-001:attack-001:stealth-cover"
    geometry_key = "a" * 64
    selected = {"cover_result": {"los_cache_key": raw_key, "has_benefit": True}}
    other = {"cover_result": {"los_cache_key": geometry_key, "has_benefit": True}}
    log = EventLog()
    event = log.append(
        "attack_sequence_step",
        {"step": "save", "payload": {"option": selected, "save_options": [selected, other]}},
    )
    event_before = canonical_json(event.payload)
    aliases: set[str] = set()
    for player in ("player-a", "player-b"):
        viewer = ViewerContext.for_player(player)
        (projected,) = viewer_event_records(event_log=log, viewer=viewer)
        alias, repeated_alias, geometry = _cover_keys(projected["payload"])
        assert isinstance(alias, str)
        assert alias.startswith("view-derived-")
        assert alias == repeated_alias
        assert geometry == geometry_key
        aliases.add(alias)
        identities = viewer_identity_map(event_log=log, viewer=viewer)
        assert identities.resolve(alias, key="los_cache_key") == raw_key
        assert raw_key not in canonical_json(projected["payload"])
        with pytest.raises(ViewerIdentityError, match="unissued viewer identity"):
            identities.resolve(raw_key, key="los_cache_key")
    assert len(aliases) == 2
    assert canonical_json(event.payload) == event_before
    assert _cover_keys(event.payload) == [raw_key, raw_key, geometry_key]
