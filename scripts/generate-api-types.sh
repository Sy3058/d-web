#!/usr/bin/env bash
# 백엔드 OpenAPI 스키마 -> admin TypeScript 타입 codegen (M1.5 F2 선행).
#
# backend/src/schemas·models가 진실의 원본이다. admin/src/types/api.gen.ts는
# 여기서 생성되므로 손으로 고치지 말 것 - 스키마가 바뀌면 이 스크립트를 다시 돌린다.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCHEMA_JSON="$ROOT/admin/src/types/openapi.schema.json"

cd "$ROOT/backend"
uv run python -m scripts.export_openapi > "$SCHEMA_JSON"

cd "$ROOT/admin"
pnpm exec openapi-typescript "$SCHEMA_JSON" -o src/types/api.gen.ts

rm "$SCHEMA_JSON"
echo "admin/src/types/api.gen.ts 갱신 완료"
