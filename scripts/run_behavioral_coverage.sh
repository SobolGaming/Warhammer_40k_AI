#!/usr/bin/env bash
set -euo pipefail
mkdir -p reports
mapfile -t shard_paths < "$SHARD_MANIFEST"
source_index_deadline="$BEHAVIOR_EXECUTION_DEADLINE"
uv run --no-sync python -B -m scripts.validate_source_history
source_index_pid=""
source_index_args=()
finish_source_index_build() {
  if [[ -n "$source_index_pid" ]]; then
    if wait "$source_index_pid"; then
      source_index_pid=""
    else
      source_index_status=$?
      exit "$source_index_status"
    fi
  fi
}
if [[ "$SELECTED_INDEX_CACHE_HIT" != "true" ]]; then
  completion_dir=$(mktemp -d "$RUNNER_TEMP/source-index-completion.XXXXXX")
  uv run --no-sync python -B -m scripts.ci_source_index \
    data/source_snapshots/wahapedia/10th-edition/2026-06-14/json \
    "$SELECTED_ARMY_SOURCE_INDEX" "$completion_dir/result.json" \
    "$SELECTED_INDEX_INPUT_KEY" &
  source_index_pid=$!
  source_index_args=(-p scripts.ci_source_index
    --ci-source-index-result "$completion_dir/result.json"
    --ci-source-index-target "$SELECTED_ARMY_SOURCE_INDEX"
    --ci-source-index-key "$SELECTED_INDEX_INPUT_KEY"
    --ci-source-index-monotonic
    --ci-source-index-deadline "$source_index_deadline")
fi
isolated_status=0
parallel_timing_dir="$TEST_TIMING_DIR"
isolated_case="tests/factions/chaos_daemons/integration/test_cavalcade_v995_roster.py::test_exact_mirror_deploys_all_78_models_and_replays_to_battle"
isolation_args=(--deselect "$isolated_case")
if grep -Fxq "$isolated_case" "$SHARD_MANIFEST"; then
  # Keep the bounded success fixture separate from concurrent coverage
  # work, including when refreshed costs move it to another shard.
  if TEST_TIMING_DIR="$TEST_TIMING_DIR/isolated-mirror" \
    uv run --no-sync python -m pytest "$isolated_case" \
        "${source_index_args[@]}" \
      -n 1 \
      --dist=worksteal \
      -o faulthandler_timeout=180 \
      -o faulthandler_exit_on_timeout=false \
      --selected-army-source-index="$SELECTED_ARMY_SOURCE_INDEX" \
      --cov=warhammer40k_core \
      --cov-report= \
      --cov-fail-under=0 \
      --durations=100 \
      --durations-min=0.1 \
      --junitxml="reports/behavior-shard-${SHARD_ID}-isolated-mirror.xml"; then
    echo "Isolated mirror test passed."
  else
    isolated_status=$?
  fi
  isolation_args=(--deselect "$isolated_case" --cov-append)
  parallel_timing_dir="$TEST_TIMING_DIR/remainder"
  finish_source_index_build
fi
parallel_status=0
if TEST_TIMING_DIR="$parallel_timing_dir" \
  uv run --no-sync python -m pytest "${shard_paths[@]}" "${isolation_args[@]}" \
  "${source_index_args[@]}" \
  -n auto \
  --dist=worksteal \
  -o faulthandler_timeout=180 \
  -o faulthandler_exit_on_timeout=false \
  --selected-army-source-index="$SELECTED_ARMY_SOURCE_INDEX" \
  --cov=warhammer40k_core \
  --cov-report= \
  --cov-fail-under=0 \
  --durations=100 \
  --durations-min=0.1 \
  --junitxml="reports/behavior-shard-${SHARD_ID}.xml"; then
  echo "Parallel shard cases passed."
else
  parallel_status=$?
fi
finish_source_index_build
if (( isolated_status != 0 || parallel_status != 0 )); then
  exit 1
fi
