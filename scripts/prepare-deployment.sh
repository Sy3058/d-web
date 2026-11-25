#!/usr/bin/env bash
set -Eeuo pipefail

: "${DEPLOY_ENVIRONMENT:?deployment environment is required}"
: "${GITHUB_EVENT_NAME:?event is required}"
: "${GITHUB_REF:?ref is required}"
: "${GITHUB_SHA:?SHA is required}"
: "${GITHUB_REPOSITORY:?repository is required}"
: "${GITHUB_OUTPUT:?output file is required}"

case "$DEPLOY_ENVIRONMENT" in
  staging) expected_ref=refs/heads/develop ;;
  production) expected_ref=refs/heads/release ;;
  *) echo 'Unsupported deployment environment' >&2; exit 1 ;;
esac
if [[ ( $GITHUB_EVENT_NAME != push && $GITHUB_EVENT_NAME != workflow_dispatch ) || $GITHUB_REF != "$expected_ref" ]]; then
  echo 'Deployment requires CI on the matching integration branch' >&2
  exit 1
fi
if [[ ! $GITHUB_SHA =~ ^[0-9a-f]{40}$ || ! $GITHUB_REPOSITORY =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; then
  echo 'Invalid deployment identity' >&2
  exit 1
fi

# Only a public hostname is accepted as a browser build value. Never pass API secrets as build args.
python3 - <<'PY'
import ipaddress
import os
import re

host = os.environ.get('API_HOST', '')
label = re.compile(r'(?!-)[a-zA-Z0-9-]{1,63}(?<!-)$')
if len(host) > 253 or not all(label.fullmatch(part) for part in host.split('.')) or '.' not in host:
    raise SystemExit('API_HOST must be a bare public hostname')
if host.lower().endswith(('.localhost', '.local')):
    raise SystemExit('API_HOST must be a bare public hostname')
try:
    if not ipaddress.ip_address(host).is_global:
        raise SystemExit('API_HOST cannot be a private address')
except ValueError:
    pass
PY

{
  printf 'image_prefix=ghcr.io/%s/%s\n' "${GITHUB_REPOSITORY,,}" "$DEPLOY_ENVIRONMENT"
  printf 'deployment_sha=%s\n' "$GITHUB_SHA"
  printf 'api_url=https://%s\n' "$API_HOST"
} >> "$GITHUB_OUTPUT"
