#!/usr/bin/env bash
# ntfy_dati.sh PRIORITY TAGS EVENT BODY
#
# Publishes one UTXOracle event on the ntfy dati topic (gbg-agents decision
# ntfy-topic-per-dominio). Everything here runs on the Dell, so the priority is
# capped at 3. The topic comes from NTFY_TOPIC_DATI (EnvironmentFile .env) and
# reaches curl on stdin, never argv. Exits 1 on a missing topic or a non-2xx,
# with the HTTP code on stderr; callers decide whether that is fatal.
set -euo pipefail

priority="$1" tags="$2" event="$3" body="$4"
[ "${priority}" -le 3 ] || priority=3
title="dati/utxoracle: ${event} su $(hostname -s)"
title="${title//[$'\r\n']/ }"

# A dotenvx-encrypted value (ENC[...] / encrypted:...) is not a topic: never publish to it.
case "${NTFY_TOPIC_DATI:-}" in
    "" | ENC\[* | encrypted:*)
        echo "ntfy: NTFY_TOPIC_DATI not set, not sent: ${title}" >&2
        exit 1
        ;;
esac

code="$(printf 'url = "%s/%s"\n' "${NTFY_BASE_URL:-https://ntfy.sh}" "${NTFY_TOPIC_DATI}" \
    | curl -sS -m 10 -o /dev/null -w '%{http_code}' -K - \
        -H "Priority: ${priority}" -H "Tags: ${tags}" -H "Title: ${title}" \
        --data-binary "$(printf '%s' "${body}" | head -c 4000)")" || code="${code:-000}"
if [[ "${code}" != 2* ]]; then
    echo "ntfy: publish to dati failed with HTTP ${code}: ${title}" >&2
    exit 1
fi
echo "ntfy: published to dati priority ${priority}: ${title}" >&2
