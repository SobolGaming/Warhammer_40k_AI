#!/usr/bin/env bash
set -euo pipefail
uv python install 3.14.5
uv lock
uv sync
uv lock --check
