"""FastAPI 앱의 OpenAPI 스키마를 JSON으로 출력 (openapi-typescript 입력, M1.5 F2 선행).

서버를 띄우지 않고 app.openapi()만 호출한다(FastAPI가 라우터 스캔으로 조립한 결과를
그대로 직렬화). admin의 수기 타입 드리프트(admin/CLAUDE.md 참조)를 없애기 위한 codegen
파이프라인의 백엔드측 절반 - 나머지 절반은 scripts/generate-api-types.sh.

실행(backend/ 에서):
    uv run python -m scripts.export_openapi > ../admin/src/types/openapi.schema.json
"""

import json

from src.main import app


def main() -> None:
    print(json.dumps(app.openapi()))


if __name__ == "__main__":
    main()
