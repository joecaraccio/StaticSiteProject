#!/bin/sh
# Start the DuckDB UI on 127.0.0.1:4213, then forward 0.0.0.0:4213 to it.
set -eu

INTERNAL_PORT="${DUCKDB_UI_INTERNAL_PORT:-4212}"
EXTERNAL_PORT="${DUCKDB_UI_EXTERNAL_PORT:-4213}"

export DUCKDB_UI_INTERNAL_PORT="$INTERNAL_PORT"

python /opt/duckdb-ui/serve.py &
ui_pid=$!

# Give the UI a moment to bind before socat starts forwarding to it.
i=0
while [ "$i" -lt 60 ]; do
    if ! kill -0 "$ui_pid" 2>/dev/null; then
        echo "duckdb-ui: the UI process exited during startup" >&2
        wait "$ui_pid" || true
        exit 1
    fi
    # `nc` is not installed; socat itself is the probe.
    if socat -u /dev/null "TCP:127.0.0.1:${INTERNAL_PORT}" 2>/dev/null; then
        break
    fi
    i=$((i + 1))
    sleep 1
done

echo "duckdb-ui: forwarding 0.0.0.0:${EXTERNAL_PORT} -> 127.0.0.1:${INTERNAL_PORT}"
exec socat "TCP-LISTEN:${EXTERNAL_PORT},fork,reuseaddr" "TCP:127.0.0.1:${INTERNAL_PORT}"
