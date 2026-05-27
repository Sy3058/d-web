# 필수 준수 사항

## 한국어로 설명

## 커밋 메시지
GUIDE_COMMIT.md 참조

커밋 메시지 형식: `[PREFIX] type: 제목`
- PREFIX: `[BE]`, `[FE]`, `[ADMIN]`, `[INFRA]`, `[COMMON]`

## 구현 문서 필수 템플릿 규칙

코드 구현 시 구현한 기능에 대해 문서를 작성해야 합니다.

경로 형식:
- 백엔드: `docs/MODULES/BE/{Domain}/IMPLEMENTATION_{기능명}.md`
- 프론트엔드: `docs/MODULES/FE/{기능명}/IMPLEMENTATION_{기능명}.md`

예시: `docs/MODULES/BE/Episode/IMPLEMENTATION_EPISODE_VIEWER.md`

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
    ├── BE/
    │   ├── Auth/
    │   ├── Episode/
    │   ├── Payment/
    │   ├── Community/
    │   └── Admin/
    └── FE/
        ├── Viewer/
        ├── Payment/
        └── Community/

문서 종류:
- `IMPLEMENTATION_*.md`: 구현 내용 및 의사결정 기록
- `TROUBLESHOOTING_*.md`: 트러블슈팅 기록
- `CHANGELOG_*.md`: 변경 이력