#!/usr/bin/env bash
# Continuous mirror loop. Calls mirror_live_questdb_to_host once per minute,
# logs to /tmp/mirror_live_loop.log. Designed for setsid background launch
# until the systemd timer can be installed by the operator.
set -u
cd "$(dirname "${BASH_SOURCE[0]}")/../.." || exit 1
export PORT_GUARD_OFF=1
while true; do
    uv run python -m scripts.bootstrap.mirror_live_questdb_to_host \
        --batch-limit 20000 2>&1 | tail -1
    sleep 60
done
