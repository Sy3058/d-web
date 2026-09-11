# 필수 준수 사항

## 한국어로 설명

## 커밋 메시지
GUIDE_COMMIT.md 참조

커밋 메시지 형식: `[PREFIX] type: 제목`
- PREFIX: `[BE]`, `[FE]`, `[ADMIN]`, `[INFRA]`, `[COMMON]`

## 구현 문서 필수 템플릿 규칙

의미 있는 기능 구현은 구현 문서 작성 대상인지 확인합니다. 사소한 수정은 생략할 수 있습니다.

기존 모듈 문서의 해당 절을 우선 갱신하고, 매 작업마다 새 문서를 만들지 않는다. 아래 항목은 필요한 내용을 빠뜨리지 않기 위한 참고 구조이며 짧은 변경에 빈 섹션을 강제하지 않는다.

경로 형식:
- 백엔드: `docs/MODULES/BE/{Domain}/IMPLEMENTATION_{기능명}.md`
- 프론트엔드: `docs/MODULES/FE/{기능명}/IMPLEMENTATION_{기능명}.md`
- 관리자: `docs/MODULES/ADMIN/{기능명}/IMPLEMENTATION_{기능명}.md`
- 공통/인프라: 기존 `docs/MODULES/COMMON/`, `docs/MODULES/INFRA/` 구조를 따른다.

예시: `docs/MODULES/BE/Episodes/IMPLEMENTATION_EPISODE_CONTENT_MODEL.md`

📌 필수 작성 항목 (Required)

### Background / Context
- 해결하려는 문제의 맥락
- 왜 이 구현이 필요해졌는지

### Decision
- 최종적으로 선택한 구현 방식
- 배제한 대안이 있다면 간단한 요약

📎 권장 작성 항목 (Recommended)

### Why
- 대안 비교, 현재 선택이 적절한 이유

### Caution
- 보안, 성능, 영향 받는 도메인
- 변경 시 깨질 수 있는 전제

### Test Plan
- 검증 방법, 핵심 테스트 케이스

## MODULES 구조

    docs/MODULES/
    ├── BE/       # FastAPI 도메인 구현
    ├── FE/       # Astro 독자 사이트
    ├── ADMIN/    # Vite React 관리자 SPA
    ├── COMMON/   # shared package·공통 계약
    └── INFRA/    # Docker·배포 기반

문서 종류:
- `IMPLEMENTATION_*.md`: 구현 내용 및 의사결정 기록
- `TROUBLESHOOTING_*.md`: 트러블슈팅 기록
- 출시 전 변경 이력은 신규 CHANGELOG 대신 `docs/DECISIONS.md`, 마일스톤 문서와 태그에 반영
