from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from warhammer40k_core.core.deployment_zones import DeploymentZoneShape
from warhammer40k_core.core.missions import BattlefieldLayoutDefinition
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_06_mission_pack,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chapter_approved_2026_27 as chapter_approved,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    event_companion_2026_06 as event_source,
)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Serve a mock Warhammer Event Companion battlefield layout UI.",
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)

    data = _build_data_payload()
    html = _html_document()
    handler = _handler_for(html=html, data=data)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Serving Event Companion layout mock UI at http://{args.host}:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped Event Companion layout mock UI.")
    finally:
        server.server_close()
    return 0


def _build_data_payload() -> dict[str, object]:
    mission_pack = warhammer_event_companion_2026_06_mission_pack()
    force_dispositions = [
        {
            "id": force.force_disposition_id,
            "name": force.name,
        }
        for force in mission_pack.force_dispositions
    ]
    matrix = {
        f"{cell.player_force_disposition_id}|{cell.opponent_force_disposition_id}": {
            "primary_mission_id": cell.primary_mission_id,
            "layout_ids": list(cell.battlefield_layout_ids),
        }
        for cell in mission_pack.primary_mission_matrix_cells
    }
    extracted_layouts = {
        layout.battlefield_layout_id: layout for layout in mission_pack.battlefield_layouts
    }
    descriptors = {
        descriptor.layout_id: descriptor for descriptor in event_source.layout_descriptor_rows()
    }
    layouts = {
        row.battlefield_layout_id: _layout_payload(
            row,
            descriptor=descriptors[row.battlefield_layout_id],
            extracted_layout=extracted_layouts.get(row.battlefield_layout_id),
        )
        for row in event_source.battlefield_layout_rows()
    }
    return {
        "battlefield": {"width_inches": 44.0, "depth_inches": 60.0},
        "force_dispositions": force_dispositions,
        "matrix": matrix,
        "layouts": layouts,
    }


def _layout_payload(
    row: chapter_approved.SourceBattlefieldLayoutRow,
    *,
    descriptor: event_source.WarhammerEventLayoutDescriptor,
    extracted_layout: BattlefieldLayoutDefinition | None,
) -> dict[str, object]:
    return {
        "id": row.battlefield_layout_id,
        "name": row.name,
        "attacker_edge": descriptor.attacker_edge,
        "defender_edge": descriptor.defender_edge,
        "deployment_zones": [
            {
                "id": zone.deployment_zone_id,
                "player_id": zone.player_role,
                "shape": _shape_payload(zone.shape),
            }
            for zone in row.deployment_zones
        ],
        "terrain_areas": _terrain_area_payloads(extracted_layout),
        "terrain_features": [_terrain_feature_payload(feature) for feature in row.terrain_features],
    }


def _terrain_area_payloads(
    layout: BattlefieldLayoutDefinition | None,
) -> list[dict[str, object]]:
    if layout is None:
        return []
    return [
        {
            "id": area.terrain_area_id,
            "footprint_template_id": area.footprint_template_id,
            "classification": area.classification.value,
            "center_x_inches": area.center_x_inches,
            "center_y_inches": area.center_y_inches,
            "rotation_degrees": area.rotation_degrees,
            "local_transform": area.local_transform.value,
            "polygon": [
                {"x": point.x_inches, "y": point.y_inches} for point in area.footprint_polygon
            ],
        }
        for area in layout.terrain_areas
    ]


def _shape_payload(shape: DeploymentZoneShape) -> dict[str, object]:
    return {
        "polygons": [
            [{"x": point.x, "y": point.y} for point in polygon.vertices]
            for polygon in shape.polygons
        ],
        "cutouts": [cutout.to_payload() for cutout in shape.cutouts],
    }


def _terrain_feature_payload(
    feature: chapter_approved.SourceBattlefieldTerrainFeatureRow,
) -> dict[str, object]:
    return {
        "id": feature.feature_id,
        "kind": feature.feature_kind,
        "center_x_inches": feature.footprint_center_x_inches,
        "center_y_inches": feature.footprint_center_y_inches,
        "width_inches": feature.footprint_width_inches,
        "depth_inches": feature.footprint_depth_inches,
    }


def _handler_for(
    *,
    html: str,
    data: dict[str, object],
) -> type[BaseHTTPRequestHandler]:
    encoded_html = html.encode("utf-8")
    encoded_data = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")

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


def _html_document() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Event Companion Layout Mock</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #1f2933;
      --muted: #5c6670;
      --line: #d6dbe1;
      --panel: #f4f6f8;
      --attacker: #b35433;
      --defender: #2878a9;
      --dense: #6f7f5f;
      --light: #b7a36a;
      --feature: #7d7394;
      --objective: #323b43;
    }
    * {
      box-sizing: border-box;
    }
    body {
      margin: 0;
      min-height: 100vh;
      background: #ffffff;
      color: var(--ink);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
        "Segoe UI", sans-serif;
      font-size: 14px;
      line-height: 1.4;
    }
    main {
      display: grid;
      grid-template-columns: minmax(280px, 340px) minmax(360px, 1fr);
      gap: 20px;
      min-height: 100vh;
      padding: 18px;
    }
    aside {
      border-right: 1px solid var(--line);
      padding-right: 18px;
    }
    h1 {
      margin: 0 0 18px;
      font-size: 20px;
      font-weight: 700;
      letter-spacing: 0;
    }
    label {
      display: grid;
      gap: 6px;
      margin-bottom: 14px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0;
    }
    select {
      width: 100%;
      min-height: 36px;
      border: 1px solid #b8c0c8;
      border-radius: 6px;
      background: #fff;
      color: var(--ink);
      font: inherit;
      padding: 6px 8px;
    }
    dl {
      display: grid;
      grid-template-columns: auto 1fr;
      gap: 8px 14px;
      margin: 18px 0 0;
      padding: 12px 0 0;
      border-top: 1px solid var(--line);
    }
    dt {
      color: var(--muted);
      font-weight: 700;
    }
    dd {
      margin: 0;
      min-width: 0;
      overflow-wrap: anywhere;
    }
    .legend {
      display: grid;
      gap: 8px;
      margin-top: 18px;
      padding-top: 12px;
      border-top: 1px solid var(--line);
      color: var(--muted);
    }
    .legend-row {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .swatch {
      width: 16px;
      height: 16px;
      border: 1px solid rgba(0, 0, 0, 0.25);
      border-radius: 3px;
    }
    .swatch.attacker {
      background: color-mix(in srgb, var(--attacker) 28%, transparent);
    }
    .swatch.defender {
      background: color-mix(in srgb, var(--defender) 28%, transparent);
    }
    .swatch.dense {
      background: color-mix(in srgb, var(--dense) 55%, transparent);
    }
    .swatch.light {
      background: color-mix(in srgb, var(--light) 58%, transparent);
    }
    .stage {
      display: grid;
      grid-template-rows: auto minmax(0, 1fr);
      gap: 12px;
      min-width: 0;
    }
    .title-line {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
      min-width: 0;
    }
    .title-line h2 {
      margin: 0;
      min-width: 0;
      font-size: 18px;
      font-weight: 700;
      letter-spacing: 0;
      overflow-wrap: anywhere;
    }
    .size-note {
      color: var(--muted);
      white-space: nowrap;
    }
    .board-wrap {
      min-height: 0;
      overflow: auto;
      border: 1px solid var(--line);
      background: var(--panel);
      padding: 12px;
    }
    svg {
      display: block;
      width: min(100%, 720px);
      height: auto;
      aspect-ratio: 44 / 60;
      margin: 0 auto;
      background: #fff;
      border: 1px solid #9aa3ad;
    }
    .grid-line {
      stroke: #e4e8ec;
      stroke-width: 0.035;
      vector-effect: non-scaling-stroke;
    }
    .grid-line.major {
      stroke: #c8d0d8;
      stroke-width: 0.06;
    }
    .deployment-attacker {
      fill: color-mix(in srgb, var(--attacker) 28%, transparent);
      stroke: var(--attacker);
    }
    .deployment-defender {
      fill: color-mix(in srgb, var(--defender) 28%, transparent);
      stroke: var(--defender);
    }
    .terrain-dense {
      fill: color-mix(in srgb, var(--dense) 55%, transparent);
      stroke: var(--dense);
    }
    .terrain-light {
      fill: color-mix(in srgb, var(--light) 58%, transparent);
      stroke: #8a763e;
    }
    .terrain-feature {
      fill: color-mix(in srgb, var(--feature) 26%, transparent);
      stroke: var(--feature);
    }
    .objective {
      fill: #fff;
      stroke: var(--objective);
      stroke-width: 0.1;
    }
    .label {
      fill: var(--ink);
      font-size: 1.1px;
      font-weight: 700;
      text-anchor: middle;
      dominant-baseline: middle;
      paint-order: stroke;
      stroke: #fff;
      stroke-width: 0.25;
      stroke-linejoin: round;
    }
    path,
    polygon,
    rect {
      stroke-width: 0.12;
      vector-effect: non-scaling-stroke;
    }
    @media (max-width: 820px) {
      main {
        grid-template-columns: 1fr;
      }
      aside {
        border-right: 0;
        border-bottom: 1px solid var(--line);
        padding: 0 0 16px;
      }
      .title-line {
        align-items: flex-start;
        flex-direction: column;
      }
    }
  </style>
</head>
<body>
  <main>
    <aside>
      <h1>Event Companion Layout Mock</h1>
      <label>
        Force Disposition 1
        <select id="force-one"></select>
      </label>
      <label>
        Force Disposition 2
        <select id="force-two"></select>
      </label>
      <label>
        Layout
        <select id="layout-variant">
          <option value="0">A</option>
          <option value="1">B</option>
          <option value="2">C</option>
        </select>
      </label>
      <dl>
        <dt>Layout</dt><dd id="layout-id"></dd>
        <dt>Attacker</dt><dd id="attacker-edge"></dd>
        <dt>Defender</dt><dd id="defender-edge"></dd>
        <dt>Terrain</dt><dd id="terrain-count"></dd>
      </dl>
      <div class="legend" aria-label="Legend">
        <div class="legend-row"><span class="swatch attacker"></span>Attacker deployment</div>
        <div class="legend-row"><span class="swatch defender"></span>Defender deployment</div>
        <div class="legend-row"><span class="swatch dense"></span>Dense terrain area</div>
        <div class="legend-row"><span class="swatch light"></span>Light terrain area</div>
      </div>
    </aside>
    <section class="stage">
      <div class="title-line">
        <h2 id="layout-name"></h2>
        <span class="size-note">44&quot; x 60&quot;</span>
      </div>
      <div class="board-wrap">
        <svg id="board" viewBox="0 0 44 60" role="img" aria-label="Battlefield layout"></svg>
      </div>
    </section>
  </main>
  <script>
    const state = {
      data: null,
      forceOne: document.querySelector("#force-one"),
      forceTwo: document.querySelector("#force-two"),
      layoutVariant: document.querySelector("#layout-variant"),
      board: document.querySelector("#board"),
      layoutName: document.querySelector("#layout-name"),
      layoutId: document.querySelector("#layout-id"),
      attackerEdge: document.querySelector("#attacker-edge"),
      defenderEdge: document.querySelector("#defender-edge"),
      terrainCount: document.querySelector("#terrain-count"),
      lastSelectionKey: null,
    };
    const SVG_NS = "http://www.w3.org/2000/svg";
    const WIDTH = 44;
    const DEPTH = 60;

    fetch("/data.json")
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Data request failed: ${response.status}`);
        }
        return response.json();
      })
      .then((data) => {
        state.data = data;
        populateForceDispositions(data.force_dispositions);
        renderSelection();
      });

    state.forceOne.addEventListener("change", renderSelection);
    state.forceTwo.addEventListener("change", renderSelection);
    state.layoutVariant.addEventListener("change", renderSelection);
    window.setInterval(renderSelection, 250);

    function populateForceDispositions(forceDispositions) {
      for (const select of [state.forceOne, state.forceTwo]) {
        select.replaceChildren();
        for (const force of forceDispositions) {
          const option = document.createElement("option");
          option.value = force.id;
          option.textContent = force.name;
          select.append(option);
        }
      }
      state.forceOne.value = "take-and-hold";
      state.forceTwo.value = "take-and-hold";
    }

    function renderSelection() {
      if (!state.data) {
        return;
      }
      const selectionKey = [
        state.forceOne.value,
        state.forceTwo.value,
        state.layoutVariant.value,
      ].join("|");
      if (state.lastSelectionKey === selectionKey) {
        return;
      }
      state.lastSelectionKey = selectionKey;
      render();
    }

    function render() {
      const key = `${state.forceOne.value}|${state.forceTwo.value}`;
      const cell = state.data.matrix[key];
      const layoutIndex = Number(state.layoutVariant.value);
      const layout = state.data.layouts[cell.layout_ids[layoutIndex]];
      state.layoutName.textContent = layout.name;
      state.layoutId.textContent = layout.id;
      state.attackerEdge.textContent = layout.attacker_edge;
      state.defenderEdge.textContent = layout.defender_edge;
      state.terrainCount.textContent = [
        `${layout.terrain_areas.length} areas`,
        `${layout.terrain_features.length} features`,
      ].join(", ");
      renderBoard(layout);
    }

    function renderBoard(layout) {
      state.board.replaceChildren();
      renderGrid();
      for (const zone of layout.deployment_zones) {
        const path = svgElement("path", {
          d: shapePath(zone.shape),
          "fill-rule": "evenodd",
          class: zone.player_id === "attacker" ? "deployment-attacker" : "deployment-defender",
        });
        path.append(svgElement("title", {}, `${zone.player_id}: ${zone.id}`));
        state.board.append(path);
      }
      for (const feature of layout.terrain_features) {
        const rect = svgElement("rect", {
          x: feature.center_x_inches - feature.width_inches / 2,
          y: DEPTH - feature.center_y_inches - feature.depth_inches / 2,
          width: feature.width_inches,
          height: feature.depth_inches,
          class: "terrain-feature",
        });
        rect.append(svgElement("title", {}, `${feature.kind}: ${feature.id}`));
        state.board.append(rect);
      }
      for (const area of layout.terrain_areas) {
        const polygon = svgElement("polygon", {
          points: area.polygon.map(pointToSvg).join(" "),
          class: area.classification === "dense" ? "terrain-dense" : "terrain-light",
        });
        polygon.append(svgElement("title", {}, `${area.classification}: ${area.id}`));
        state.board.append(polygon);
      }
    }

    function renderGrid() {
      for (let x = 0; x <= WIDTH; x += 1) {
        state.board.append(svgElement("line", {
          x1: x,
          y1: 0,
          x2: x,
          y2: DEPTH,
          class: x % 6 === 0 ? "grid-line major" : "grid-line",
        }));
      }
      for (let y = 0; y <= DEPTH; y += 1) {
        const svgY = DEPTH - y;
        state.board.append(svgElement("line", {
          x1: 0,
          y1: svgY,
          x2: WIDTH,
          y2: svgY,
          class: y % 6 === 0 ? "grid-line major" : "grid-line",
        }));
      }
    }

    function shapePath(shape) {
      const parts = [];
      for (const polygon of shape.polygons) {
        parts.push(polygonPath(polygon));
      }
      for (const cutout of shape.cutouts) {
        if (cutout.kind === "circle") {
          parts.push(circlePath(cutout));
        } else {
          parts.push(polygonPath(cutout.vertices));
        }
      }
      return parts.join(" ");
    }

    function polygonPath(points) {
      return `M ${points.map(pointToSvg).join(" L ")} Z`;
    }

    function circlePath(cutout) {
      const cx = cutout.center_x;
      const cy = DEPTH - cutout.center_y;
      const r = cutout.radius;
      return [
        `M ${cx + r} ${cy}`,
        `A ${r} ${r} 0 1 0 ${cx - r} ${cy}`,
        `A ${r} ${r} 0 1 0 ${cx + r} ${cy}`,
        "Z",
      ].join(" ");
    }

    function pointToSvg(point) {
      return `${point.x},${DEPTH - point.y}`;
    }

    function svgElement(tagName, attributes = {}, text = null) {
      const element = document.createElementNS(SVG_NS, tagName);
      for (const [name, value] of Object.entries(attributes)) {
        element.setAttribute(name, String(value));
      }
      if (text !== null) {
        element.textContent = text;
      }
      return element;
    }
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
