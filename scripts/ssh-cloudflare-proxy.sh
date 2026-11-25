#!/usr/bin/env bash
set -Eeuo pipefail
[[ $# -eq 1 && $1 =~ ^[A-Za-z0-9.-]+$ ]] || { echo 'Invalid Access hostname' >&2; exit 1; }
: "${TUNNEL_SERVICE_TOKEN_ID:?Cloudflare Access client ID is required}"
: "${TUNNEL_SERVICE_TOKEN_SECRET:?Cloudflare Access client secret is required}"
: "${RUNNER_TEMP:?runner temporary directory is required}"
# Credentials stay in the environment, never in process arguments or stdout.
exec "$RUNNER_TEMP/cloudflared" access ssh --hostname "$1"
