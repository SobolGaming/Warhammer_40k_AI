from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from warhammer40k_core.adapters.battlefield_projection import (
    BATTLEFIELD_VIEW_SCHEMA_VERSION,
    BattlefieldViewPayload,
    project_battlefield_view,
)
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.missions import MissionPackDefinition
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
    muster_army,
)
from warhammer40k_core.engine.deployment import create_empty_deployment_battlefield_state
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.list_validation import DetachmentSelection, UnitMusterSelection
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    event_companion_2026_06 as event_source,
)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
VIEWER_SCHEMA_VERSION = "event-companion-battlefield-viewer-v2"

_ATTACKER_PLAYER_ID = "viewer-attacker"
_DEFENDER_PLAYER_ID = "viewer-defender"
_ASSET_DIRECTORY = Path(__file__).resolve().parent / "mock_event_layout_ui_assets"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Serve the projection-backed Event Companion 3D battlefield viewer.",
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)

    data = build_data_payload()
    html = html_document(data=data)
    handler = _handler_for(html=html, data=data)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Serving Event Companion battlefield viewer at http://{args.host}:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped Event Companion battlefield viewer.")
    finally:
        server.server_close()
    return 0


def build_data_payload() -> dict[str, object]:
    return _build_data_payload()


def html_document(*, data: dict[str, object] | None = None) -> str:
    return _html_document(data=build_data_payload() if data is None else data)


def viewer_javascript() -> str:
    return _asset_text("viewer.js")


def viewer_stylesheet() -> str:
    return _asset_text("viewer.css")


def _build_data_payload() -> dict[str, object]:
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    matrix = {
        f"{cell.player_force_disposition_id}|{cell.opponent_force_disposition_id}": {
            "primary_mission_id": cell.primary_mission_id,
            "layout_ids": list(cell.battlefield_layout_ids),
        }
        for cell in mission_pack.primary_mission_matrix_cells
    }
    descriptors = {
        descriptor.layout_id: descriptor for descriptor in event_source.layout_descriptor_rows()
    }
    mission_pool_entry_by_layout_id = _mission_pool_entry_by_layout_id(mission_pack)
    runtime_geometry_layout_ids = {
        layout.battlefield_layout_id for layout in mission_pack.battlefield_layouts
    }
    ruleset, catalog, muster_requests, armies = _preview_projection_dependencies()

    layouts: dict[str, object] = {}
    for row in event_source.battlefield_layout_rows():
        layout_id = row.battlefield_layout_id
        descriptor = descriptors.get(layout_id)
        if descriptor is None:
            raise GameLifecycleError("Viewer layout descriptor is missing.")
        mission_pool_entry_id = mission_pool_entry_by_layout_id.get(layout_id)
        if mission_pool_entry_id is None:
            raise GameLifecycleError("Viewer mission-pool entry is missing.")
        mission_setup = MissionSetup.from_mission_pack(
            mission_pack=mission_pack,
            mission_pool_entry_id=mission_pool_entry_id,
            attacker_player_id=_ATTACKER_PLAYER_ID,
            defender_player_id=_DEFENDER_PLAYER_ID,
        )
        battlefield_view = _battlefield_view_payload(
            mission_setup=mission_setup,
            ruleset=ruleset,
            catalog=catalog,
            muster_requests=muster_requests,
            armies=armies,
        )
        mission_payload = mission_setup.to_payload()
        objective_ids = set(battlefield_view["authoritative"]["objectives_by_id"])
        bound_objective_ids = {
            binding["objective_marker_id"] for binding in mission_payload["objective_terrain_areas"]
        }
        if not bound_objective_ids <= objective_ids:
            raise GameLifecycleError(
                "Viewer objective-terrain binding references an unknown objective."
            )
        layouts[layout_id] = {
            "id": layout_id,
            "name": row.name,
            "attacker_edge": descriptor.attacker_edge,
            "defender_edge": descriptor.defender_edge,
            "geometry_status": (
                "runtime_geometry_available"
                if layout_id in runtime_geometry_layout_ids
                else "terrain_geometry_pending"
            ),
            "objective_footprint_status": (
                "source_linked_footprints_available"
                if bound_objective_ids == objective_ids
                else "footprint_binding_pending"
            ),
            "objective_terrain_areas": mission_payload["objective_terrain_areas"],
            "battlefield_view": battlefield_view,
        }
    return {
        "viewer_schema": VIEWER_SCHEMA_VERSION,
        "battlefield_view_schema": BATTLEFIELD_VIEW_SCHEMA_VERSION,
        "force_dispositions": _force_disposition_payloads(),
        "matrix": matrix,
        "layouts": layouts,
    }


def _mission_pool_entry_by_layout_id(mission_pack: MissionPackDefinition) -> dict[str, str]:
    by_layout_id: dict[str, str] = {}
    for entry in mission_pack.mission_pool_entries:
        if len(entry.terrain_layout_ids) != 1:
            raise GameLifecycleError("Viewer mission-pool entry must reference one layout.")
        layout_id = entry.terrain_layout_ids[0]
        if layout_id in by_layout_id:
            raise GameLifecycleError("Viewer layout has duplicate mission-pool entries.")
        by_layout_id[layout_id] = entry.mission_pool_entry_id
    return by_layout_id


def _preview_projection_dependencies() -> tuple[
    RulesetDescriptor,
    ArmyCatalog,
    tuple[ArmyMusterRequest, ...],
    tuple[ArmyDefinition, ...],
]:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    ruleset = RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
        descriptor_version="event-companion-battlefield-viewer-v2"
    )
    muster_requests = (
        _preview_muster_request(
            catalog=catalog,
            player_id=_ATTACKER_PLAYER_ID,
            army_id="viewer-attacker-army",
            unit_selection_id="viewer-attacker-unit",
        ),
        _preview_muster_request(
            catalog=catalog,
            player_id=_DEFENDER_PLAYER_ID,
            army_id="viewer-defender-army",
            unit_selection_id="viewer-defender-unit",
        ),
    )
    armies = tuple(muster_army(catalog=catalog, request=request) for request in muster_requests)
    return ruleset, catalog, muster_requests, armies


def _preview_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_id: str,
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        force_disposition_id="purge-the-foe",
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
        ),
    )


def _battlefield_view_payload(
    *,
    mission_setup: MissionSetup,
    ruleset: RulesetDescriptor,
    catalog: ArmyCatalog,
    muster_requests: tuple[ArmyMusterRequest, ...],
    armies: tuple[ArmyDefinition, ...],
) -> BattlefieldViewPayload:
    state = GameState.from_config(
        GameConfig(
            game_id=f"event-companion-viewer-{mission_setup.battlefield_layout_id}",
            allow_legacy_non_strict_rosters=True,
            ruleset_descriptor=ruleset,
            army_catalog=catalog,
            army_muster_requests=muster_requests,
            player_ids=(_ATTACKER_PLAYER_ID, _DEFENDER_PLAYER_ID),
            turn_order=(_ATTACKER_PLAYER_ID, _DEFENDER_PLAYER_ID),
            fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
            mission_setup=mission_setup,
        )
    )
    for army in armies:
        state.record_army_definition(army)
    state.record_battlefield_state(create_empty_deployment_battlefield_state(state=state))
    projection = project_battlefield_view(
        state=state,
        visible_model_ids=frozenset(),
        pending_request_id=None,
        selected_entity_ids=(),
        legal_option_ids=(),
    )
    if projection is None:
        raise GameLifecycleError("Viewer battlefield projection was not emitted.")
    return projection


def _force_disposition_payloads() -> list[dict[str, object]]:
    return [
        {
            "id": row.force_disposition_id,
            "name": _force_disposition_display_name(row.force_disposition_id),
        }
        for row in event_source.force_disposition_rows()
    ]


def _force_disposition_display_name(force_disposition_id: str) -> str:
    names = {
        "purge-the-foe": "Purge the Foe",
        "take-and-hold": "Take and Hold",
        "disruption": "Disruption",
        "reconnaissance": "Reconnaissance",
        "priority-assets": "Priority Assets",
    }
    return names[force_disposition_id]


def _force_disposition_options_html() -> str:
    lines: list[str] = []
    for row in _force_disposition_payloads():
        disposition_id = escape(str(row["id"]), quote=True)
        name = escape(str(row["name"]), quote=False)
        selected = " selected" if disposition_id == "purge-the-foe" else ""
        lines.append(f'          <option value="{disposition_id}"{selected}>{name}</option>')
    return "\n".join(lines)


def _embedded_data_json(data: dict[str, object]) -> str:
    return (
        json.dumps(data, sort_keys=True, separators=(",", ":"))
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )


def _asset_text(filename: str) -> str:
    return (_ASSET_DIRECTORY / filename).read_text(encoding="utf-8")


def _handler_for(
    *,
    html: str,
    data: dict[str, object],
) -> type[BaseHTTPRequestHandler]:
    encoded_html = html.encode("utf-8")
    encoded_data = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    encoded_css = viewer_stylesheet().encode("utf-8")
    encoded_javascript = viewer_javascript().encode("utf-8")

    class EventLayoutMockHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                self._send_response(
                    body=encoded_html,
                    content_type="text/html; charset=utf-8",
                    status=HTTPStatus.OK,
                )
                return
            if path == "/data.json":
                self._send_response(
                    body=encoded_data,
                    content_type="application/json; charset=utf-8",
                    status=HTTPStatus.OK,
                )
                return
            if path == "/viewer.css":
                self._send_response(
                    body=encoded_css,
                    content_type="text/css; charset=utf-8",
                    status=HTTPStatus.OK,
                )
                return
            if path == "/viewer.js":
                self._send_response(
                    body=encoded_javascript,
                    content_type="text/javascript; charset=utf-8",
                    status=HTTPStatus.OK,
                )
                return
            self._send_response(
                body=b"Not found",
                content_type="text/plain; charset=utf-8",
                status=HTTPStatus.NOT_FOUND,
            )

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _send_response(
            self,
            *,
            body: bytes,
            content_type: str,
            status: HTTPStatus,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return EventLayoutMockHandler


def _html_document(*, data: dict[str, object]) -> str:
    return (
        _asset_text("index.html")
        .replace("<!-- force-disposition-options -->", _force_disposition_options_html())
        .replace("<!-- layout-data-json -->", _embedded_data_json(data))
    )


if __name__ == "__main__":
    raise SystemExit(main())
