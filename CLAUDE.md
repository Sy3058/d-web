# 웹툰 작가 개인 사이트

1인 작가의 웹툰 판매/열람 플랫폼. 독자용 사이트 + 관리자 페이지 분리 운영.

## 프로젝트 구조

```
/
├── frontend/          # Astro 독자용 사이트 → frontend/CLAUDE.md 참조
├── admin/             # Vite + React 관리자 페이지
├── backend/           # FastAPI 서버 → backend/CLAUDE.md 참조
└── docs/
    ├── DECISIONS.md   # 기술 스택 선택 이유, 기능 결정 기록
    └── MISTAKES.md    # 반복 실수 패턴 (필요할 때 @docs/MISTAKES.md로 호출)
```

## 스택 한눈에

| 영역 | 기술 |
|------|------|
| 독자 프론트 | Astro + TypeScript |
| 관리자 | Vite + React SPA + TypeScript |
| 백엔드 | FastAPI + SQLModel + PostgreSQL |
| 인증 | JWT (HttpOnly 쿠키) + OAuth2 (카카오, 구글) |
| 결제 | 포트원 (카드, 카카오페이, 토스페이) |
| 스토리지 | Cloudflare R2 + Signed URL |
| 인프라 | Hetzner 싱가포르, Docker, GitHub Actions, Caddy |

## 모델 & Effort 가이드

작업 시작 전 아래 기준으로 모델을 판단하고, 전환이 필요하면 나에게 알려줄 것.
전환 방법: Claude Code에서 `/model` 또는 `--model` 플래그 사용.
Opus로 전환한 뒤에는 국면에 맞는 스킬을 먼저 호출할 것: 계획·설계 `/fable-plan`, 코딩·디버깅 `/fable-exec`, 리뷰 `/fable-review` (Fable 작업 규율 주입).

| 작업 유형 | 모델 | Effort | 전환 알림 문구 |
|-----------|------|--------|---------------|
| **계획 & 설계** | | | |
| 아키텍처/DB 스키마 설계 | Opus | xhigh | "⚠️ Opus + xhigh로 계획을 세우세요 (`/model opus`)" |
| 간단한 구조 계획 (폴더, 파일 목록) | Sonnet | 기본값 | (전환 불필요) |
| **코딩** | | | |
| 일반 코딩, 버그 수정, 리팩토링 | Sonnet | 기본값 | (전환 불필요) |
| 결제 플로우, 보안 로직 구현 | Opus | xhigh | "⚠️ Opus + xhigh로 전환하세요 (`/model opus`)" |
| 원인 불명 버그 디버깅 | Opus | xhigh | "⚠️ Opus + xhigh로 전환하세요 (`/model opus`)" |
| **검증 & 리뷰** | | | |
| 코드 리뷰, 설계/보안 검증 | Opus | high | "⚠️ Opus로 리뷰하세요 (`/model opus`)" |
| 파일 읽기, 포맷팅, 커밋 메시지 | Haiku 4.5 | low | "💡 Haiku로 전환하면 빠르고 저렴합니다 (`/model haiku`)" |

**Effort 레벨 기준 (Opus 사용 시)**
- `xhigh`: 코딩, 아키텍처, 보안 - Claude Code 기본값, 대부분 이걸로
- `high`: 비용 절약이 필요한 긴 세션
- `low/medium`: 단순 분류, 추출, 포맷팅

## 절대 하면 안 되는 것들

- 결제 검증을 클라이언트에서만 처리 (blur/hide로 숨기기 금지)
- 미결제 유저에게 이미지 URL 내려주기 금지
- JWT를 localStorage에 저장 금지
- 환경변수를 코드에 하드코딩 금지
- CORS 와일드카드(`*`) 사용 금지
- 원시 SQL 문자열 직접 조합 금지

## 지금 구현 금지 (나중에)

멤버십/구독, 묶음 할인, 무통장 입금, 소설 뷰어, 포렌식 워터마크, Grafana, 관리자 IP 화이트리스트

## 상세 규칙 참조

- 워크플로우 (브랜치/커밋/PR/블로그/세션종료/검색): @docs/guides/GUIDE_WORKFLOW.md

아래 문서는 **자동 로드되지 않는다** (토큰 절감을 위해 @-참조 제거, 2026-07-08).
해당 시점이 오면 **Read로 먼저 읽고** 작업할 것:

| 문서 | 읽는 시점 |
|------|----------|
| `frontend/CLAUDE.md` | frontend/ 작업 시작 시 |
| `backend/CLAUDE.md` | backend/ 작업 시작 시 |
| `docs/DECISIONS.md` | 계획·설계 착수, 기존 결정 확인·변경 시 (스택 선택 이유, 2FA·신뢰 기기, OAuth BFF, 비번 해싱, RBAC, 결제 순서 등 결정 전문) |
| `docs/guides/GUIDE_TASK_HARNESS.md` | goal 입력판·ledger(`task_harness.local`) 작업 착수 시 |
| `docs/guides/GUIDE_COMMIT.md` | 커밋 메시지 작성 시 |
| `docs/reviews/GUIDE_REVIEW.md` | 코드 리뷰·검증 시 |
| `docs/MISTAKES.md` | 구현·마이그레이션·테스트·CI 착수 시 해당 영역 섹션 확인 |
| `docs/guides/GUIDE_STUDY.md` | study/ 작성·학습 퀴즈 시 |