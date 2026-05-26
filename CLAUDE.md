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

| 작업 유형 | 모델 | Effort | 전환 알림 문구 |
|-----------|------|--------|---------------|
| **계획 & 설계** | | | |
| 아키텍처/DB 스키마 설계 | Opus 4.7 | xhigh | "⚠️ Opus 4.7 + xhigh로 계획을 세우세요 (`/model opus`)" |
| 간단한 구조 계획 (폴더, 파일 목록) | Sonnet 4.6 | 기본값 | (전환 불필요) |
| **코딩** | | | |
| 일반 코딩, 버그 수정, 리팩토링 | Sonnet 4.6 | 기본값 | (전환 불필요) |
| 결제 플로우, 보안 로직 구현 | Opus 4.7 | xhigh | "⚠️ Opus 4.7 + xhigh로 전환하세요 (`/model opus`)" |
| 원인 불명 버그 디버깅 | Opus 4.7 | xhigh | "⚠️ Opus 4.7 + xhigh로 전환하세요 (`/model opus`)" |
| **검증 & 리뷰** | | | |
| 코드 리뷰, 설계/보안 검증 | Opus 4.7 | high | "⚠️ Opus 4.7로 리뷰하세요 (`/model opus`)" |
| 파일 읽기, 포맷팅, 커밋 메시지 | Haiku 4.5 | low | "💡 Haiku로 전환하면 빠르고 저렴합니다 (`/model haiku`)" |

**Effort 레벨 기준 (Opus 사용 시)**
- `xhigh`: 코딩, 아키텍처, 보안 — Claude Code 기본값, 대부분 이걸로
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

- 프론트엔드: @frontend/CLAUDE.md
- 백엔드: @backend/CLAUDE.md
- 기획 결정: @docs/DECISIONS.md
- 반복 실수: @docs/MISTAKES.md (필요할 때만 호출)

## 세션 종료 규칙

세션이 끝나거나 작업이 완료되면 자동으로 아래를 수행할 것:
1. 이번 세션에서 실수하거나 막혔던 것 확인
2. 심각도에 따라 분류:
   - 치명적 → 루트 CLAUDE.md "절대 하면 안 되는 것들"에 추가
   - 영역별 반복 → backend/ 또는 frontend/CLAUDE.md에 추가
   - 가끔 참고 → docs/MISTAKES.md에 추가
3. 변경사항 없으면 생략

## 검색 규칙

아래 작업 시 반드시 WebSearch로 최신 버전 확인 후 진행할 것:
- 패키지/라이브러리 설치
- 버전 명시가 필요한 모든 작업
- nvm, pip, apt 등으로 뭔가 설치할 때

## 브랜치 작업 규칙

브랜치 관련 작업 전 반드시 아래 순서를 지킬 것:
1. **현재 브랜치 확인**: 새 브랜치 생성/체크아웃/커밋 전 항상 `git branch --show-current` 또는 `git status`로 현재 위치 확인
2. **사용자 의도 확인**: 사용자가 이미 브랜치를 만들어 뒀거나, 다른 브랜치에서 작업 중일 수 있음 — 임의로 `git checkout -b` 실행하지 말 것
3. **새 브랜치가 필요해 보이면 제안만**: "이런 브랜치 이름이 적절해 보이는데 만들까?" 식으로 물어볼 것

## 커밋 작업 규칙

커밋(및 태그/푸시) 실행 전 반드시 아래 순서를 지킬 것:
1. **변경사항 검토 요청 필수**: `git diff` / `git status`로 변경사항을 요약해 보여주고 사용자 확인을 받은 뒤 커밋
2. **커밋 메시지 사전 공유**: 메시지 초안을 먼저 텍스트로 보여주고 OK 받은 후 실행
3. **사용자가 "커밋해도 돼"라고 직접 말하기 전까지는 자동 커밋 금지**
4. **태그/푸시는 별도 확인**: 커밋 승인을 받았어도 `git tag`, `git push`는 다시 한 번 확인받고 실행
5. **`Co-Authored-By: Claude`, `🤖 Generated with Claude Code` 등 AI 생성 문구 절대 금지** (`@docs/GUIDE_COMMIT.md` 참조)
6. **커밋 메시지 형식**: `[PREFIX] type: 제목` (PREFIX는 `[BE]`/`[FE]`/`[ADMIN]`/`[INFRA]`/`[COMMON]`, 상세는 `@docs/GUIDE_COMMIT.md`)