#!/usr/bin/env bash
# ntfy_dati.sh PRIORITY TAGS EVENT BODY
#
# Publishes one UTXOracle event on the ntfy dati topic (gbg-agents decision
# ntfy-topic-per-dominio). Everything here runs on the Dell, so the priority is
# capped at 3. The topic comes from NTFY_TOPIC_DATI (EnvironmentFile .env) and
# reaches curl on stdin, never argv. curl's own diagnostics can quote the URL, so
# they never reach stderr: the log carries only domain, priority, HTTP code and
# curl exit code. Exits 1 on a missing topic or a non-2xx; callers decide whether
# that is fatal. There is no default destination: NTFY_BASE_URL must be an http(s)
# URL, otherwise nothing is published.
set -euo pipefail

priority="$1" tags="$2" event="$3" body="$4"
# Clamp to [1,3]: the Dell never goes above 3; a non-numeric value falls back to 3.
case "${priority}" in "" | *[!0-9]*) priority=3 ;; esac
[ "${priority}" -ge 1 ] || priority=1
[ "${priority}" -le 3 ] || priority=3
title="dati/utxoracle: ${event} su $(hostname -s)"
title="${title//[$'\r\n']/ }"

# A dotenvx-encrypted value (ENC[...] / encrypted:...) is not a topic: never publish to it.
case "${NTFY_TOPIC_DATI:-}" in
    "" | ENC\[* | encrypted:*)
        echo "ntfy: NTFY_TOPIC_DATI not set, dati priority ${priority} not sent" >&2
        exit 1
        ;;
esac

case "${NTFY_BASE_URL:-}" in
    http://?* | https://?*) ;;
    *)
        echo "ntfy: NTFY_BASE_URL not set or not an http(s) URL, dati priority ${priority} not sent" >&2
        exit 1
        ;;
esac

rc=0
code="$(printf 'url = "%s/%s"\n' "${NTFY_BASE_URL%/}" "${NTFY_TOPIC_DATI}" \
    | curl -s --globoff -m 10 -o /dev/null -w '%{http_code}' -K - \
        -H "Priority: ${priority}" -H "Tags: ${tags}" -H "Title: ${title}" \
        --data-binary "$(printf '%s' "${body}" | head -c 4000)" 2>/dev/null)" || rc=$?
[[ "${code}" =~ ^[0-9]{3}$ ]] || code="000"
if [[ "${code}" != 2* ]]; then
    echo "ntfy: publish to dati priority ${priority} failed with HTTP ${code} (curl exit ${rc})" >&2
    exit 1
fi
echo "ntfy: published to dati priority ${priority} (HTTP ${code})" >&2
