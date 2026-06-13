#!/usr/bin/env bash
set -euo pipefail

BRK_URL="${BRK_URL:-http://127.0.0.1:7070}"
CONTAINER="${BRK_CONTAINER:-brk}"
INTERVAL_SECONDS="${1:-60}"

json_field() {
  local key="$1"
  sed -n "s/.*\"${key}\":\\([0-9]*\\).*/\\1/p"
}

health() {
  curl -fsS --max-time 5 "${BRK_URL}/health"
}

latest_index_log() {
  docker logs --tail 300 "${CONTAINER}" 2>&1 \
    | sed -E 's/\x1b\[[0-9;]*m//g' \
    | rg 'Indexing block' \
    | tail -1
}

latest_index_height() {
  latest_index_log | sed -n 's/.*Indexing block \([0-9][0-9]*\).*/\1/p'
}

panic_count_recent() {
  docker logs --since 30m "${CONTAINER}" 2>&1 \
    | sed -E 's/\x1b\[[0-9;]*m//g' \
    | grep -E -c 'panicked|Data inconsistency detected|called `Option::unwrap' || true
}

restart_count() {
  docker inspect --format '{{.RestartCount}}' "${CONTAINER}"
}

sample_one="$(health)"
indexed_one="$(printf '%s' "${sample_one}" | json_field indexed_height)"
tip_one="$(printf '%s' "${sample_one}" | json_field tip_height)"
behind_one="$(printf '%s' "${sample_one}" | json_field blocks_behind)"
log_height_one="$(latest_index_height)"
restart_one="$(restart_count)"

sleep "${INTERVAL_SECONDS}"

sample_two="$(health)"
indexed_two="$(printf '%s' "${sample_two}" | json_field indexed_height)"
tip_two="$(printf '%s' "${sample_two}" | json_field tip_height)"
behind_two="$(printf '%s' "${sample_two}" | json_field blocks_behind)"
log_height_two="$(latest_index_height)"
restart_two="$(restart_count)"

delta=$((indexed_two - indexed_one))
log_delta=0
if [[ -n "${log_height_one}" && -n "${log_height_two}" ]]; then
  log_delta=$((log_height_two - log_height_one))
fi

rate_delta="${delta}"
if (( log_delta > delta )); then
  rate_delta="${log_delta}"
fi

rate_per_minute=$((rate_delta * 60 / INTERVAL_SECONDS))
remaining_minutes=0
if (( rate_per_minute > 0 )); then
  remaining_minutes=$((behind_two / rate_per_minute))
fi

printf 'BRK sync monitor\n'
printf 'URL: %s\n' "${BRK_URL}"
printf 'Container: %s\n' "${CONTAINER}"
printf 'Interval: %ss\n' "${INTERVAL_SECONDS}"
printf '\n'
printf 'indexed_height: %s -> %s (delta %+d)\n' "${indexed_one}" "${indexed_two}" "${delta}"
if [[ -n "${log_height_one}" && -n "${log_height_two}" ]]; then
  printf 'log_height:     %s -> %s (delta %+d)\n' "${log_height_one}" "${log_height_two}" "${log_delta}"
fi
printf 'tip_height:     %s -> %s\n' "${tip_one}" "${tip_two}"
printf 'blocks_behind:  %s -> %s\n' "${behind_one}" "${behind_two}"
printf 'rate:           ~%d blocks/min\n' "${rate_per_minute}"
if (( remaining_minutes > 0 )); then
  printf 'rough ETA:       ~%d h %d min at this sampled rate\n' "$((remaining_minutes / 60))" "$((remaining_minutes % 60))"
else
  printf 'rough ETA:       unavailable; sampled rate is zero\n'
fi
printf 'restart_count:  %s -> %s\n' "${restart_one}" "${restart_two}"
printf 'panic markers in last 30m: %s\n' "$(panic_count_recent)"
printf 'latest index log: %s\n' "$(latest_index_log)"
