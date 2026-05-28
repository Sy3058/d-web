# 기술 스택 & 기획 결정 기록

이 문서는 프로젝트 초기 기획 단계에서 내린 결정들과 그 이유를 기록한다.
스택 선택 이유, 기능 범위, 보류된 것들을 추적하기 위한 문서.

---

## 서비스 개요

1인 웹툰 작가의 개인 판매 플랫폼.
- 작품 열람 + 유료 결제 + 팬 소통 기능을 갖춘 미니 웹툰 플랫폼
- 상업 플랫폼(네이버, 카카오)이 아닌 작가 직영 사이트
- 모바일 웹 위주, 누적 사용자 5천명 규모 목표
- 1인 운영, TypeScript + Python 기반

---

## 프론트엔드 스택 결정

### 결정: Astro (독자용) + Vite React SPA (관리자)

**이유**
- 서비스 성격이 콘텐츠 중심 (작품 목록, 에피소드, 작가 소개)
- SEO와 모바일 초기 로딩이 핵심 — Astro의 정적 HTML 서빙이 최적
- 인터랙티브 기능(결제, 댓글, 후원)은 React 아일랜드로 처리 가능한 수준
- 관리자 페이지는 SEO 불필요 + 동적 화면 중심 → SPA가 적합
- React 경험 활용 가능 (Astro 안에서 React 아일랜드로 그대로 사용)

**탈락한 후보들**
- Next.js: 이 프로젝트엔 과함. 복잡한 앱 기능이 독자용 사이트에 없음
- Vite+React SPA 단독: SEO 약해서 검색 유입 불가
- SvelteKit/React Router v7: 한국 자료/결제 가이드 부족

### Node 버전: 24 LTS

**이유**
- Node 20은 2026-04-30 EOL (이미 만료)
- Node 22 (LTS, 2027-04까지) / Node 24 (Active LTS, 더 긴 지원 + npm 11 + 최신 V8) 중 새 프로젝트는 24 권장
- 26은 2026-10에 LTS 승격 예정이므로 현 시점 선택 X

### 관리자 라우터: TanStack Router

**이유**
- 타입 안전 라우팅 + search params 스키마 검증이 빌트인 → 관리자 페이지의 폼·필터·페이지네이션 처리에 강함
- loader 패턴으로 데이터 페칭과 라우팅 결합 명확
- React Router v7도 후보였으나 search params 타입 처리는 TanStack이 우위

### FE/Admin 공유 코드: pnpm workspace + `packages/shared`

**이유**
- `lib/api.ts` (fetch 래퍼, `credentials: 'include'`), `lib/validation.ts` (Zod 스키마), BE 응답 타입이 양쪽에서 동일하게 필요
- 복붙은 한쪽 수정 누락 사고가 잦음 (특히 Zod 스키마/API 응답 타입)
- 사설 npm 패키지는 1인 프로젝트에 publish 사이클 오버스펙
- pnpm: 디스크·속도 우위, monorepo 표준

**구조**
```
/
├── package.json          # workspace 루트
├── pnpm-workspace.yaml
├── packages/shared/      # api 래퍼, zod 스키마, 공통 타입
├── frontend/             # Astro
└── admin/                # Vite React
```

향후 FastAPI OpenAPI → TS 타입 자동 생성으로 발전 가능.

---

## 백엔드 스택 결정

### 결정: FastAPI + SQLModel + PostgreSQL

**이유**
- FastAPI: Python 기반, 비동기 처리, 자동 API 문서, AI 기능 확장 용이
- SQLModel: FastAPI 제작자가 만든 ORM. 코드 중복 없이 DB 모델을 API 응답 타입으로 재사용
- PostgreSQL: 안정적, FastAPI 궁합 좋음, VPS 안에서 직접 운영

### Python 버전: 3.12

**이유**
- 3.13도 안정화됐지만 일부 C 확장(asyncpg, pydantic-core 등) 휠 배포·호환성이 3.12가 더 안전
- FastAPI/SQLModel/Alembic 전부 3.12에서 가장 검증됨
- 3.13의 free-threaded/JIT 기능은 이 프로젝트에서 필요 없음

### 패키지 매니저: uv

**이유**
- 2026 기준 새 Python 프로젝트의 사실상 디폴트 (poetry 대비 10~100× 빠름)
- 가상환경 + 의존성 + Python 버전 + lockfile을 한 도구로 관리
- Docker 이미지 빌드 시간·이미지 크기 모두 작음
- 이 프로젝트 의존성(FastAPI, SQLModel, asyncpg, pydantic) 모두 휠 잘 배포되어 uv의 약점(C 확장)과 무관

**탈락한 후보**
- poetry: publish 워크플로우만 약간 우위, 그 외 모든 면에서 uv 우위
- pip + venv 수동: lockfile/재현성 약함

---

## 인프라 결정

### VPS: Hetzner 싱가포르

**이유**
- 월 $8~10으로 압도적으로 저렴
- AWS 서울 대비 응답속도 20~40ms 느리지만 Cloudflare CDN으로 이미지/정적 파일은 보완
- API 호출만 싱가포르 거치는 구조라 체감 차이 크지 않음
- 나중에 사용자 늘면 서울로 이전 가능 (Docker라 이전 쉬움)

**탈락한 후보들**
- AWS Lightsail 서울: 서울 리전 장점 있으나 월 $20~25로 2.5배 비쌈
- DigitalOcean 싱가포르: Hetzner와 위치 동일한데 2배 비쌈
- NCP: 가격 대비 이점 없음

### 이미지 스토리지: Cloudflare R2

**이유**
- S3보다 저렴한 egress 비용
- Cloudflare CDN과 세트라 이미지 서빙 속도 자동 최적화
- Signed URL 지원 → 유료 콘텐츠 보호 가능

### 웹서버: Caddy

**이유**
- HTTPS 자동 처리 (Let's Encrypt 연동 자동)
- 설정 파일이 Nginx보다 훨씬 단순
- 1인 개발 초기에 설정 실수 줄이기 위해 선택
- 나중에 Nginx 전환 가능 (Docker 컨테이너만 교체하면 됨)

### 결제: 포트원

**이유**
- 한국 개발자 자료 최다
- SDK 하나로 카드/카카오페이/토스페이 한 번에 연동
- FastAPI 연동 예제 존재

---

## 기능 범위 결정

### 확정 기능

**콘텐츠/뷰어**
- 작품 목록 → 에피소드 목록 → 뷰어 3단계 구조
- 세로 스크롤 웹툰 뷰어
- N화까지 무료, 이후 Signed URL 잠금
- 드래그/복사 차단, 이미지 우클릭 저장 차단
- 작가 소개 페이지

**결제**
- 에피소드 개별 구매 / 전편 구매
- 카드, 카카오페이, 토스페이 (포트원)
- 구매 내역 확인

**계정**
- 회원가입/로그인 + 소셜 (카카오, 구글)
- 구매 목록
- 알림 설정 (새 에피소드 / 새 커뮤니티 게시글 / 댓글 답글)

**소통**
- 하트 + 댓글 + 답글
- 후원 기능
- 커뮤니티 게시판 (근황, Q&A, 투표)

**관리자**
- 에피소드 업로드/관리
- 수익 확인
- 독자 통계
- 업로드 리마인더 알림
- 커미션(리퀘스트) 페이지

### 보류/나중에 추가

| 기능 | 보류 이유 |
|------|----------|
| 멤버십/구독 | 초기 에피소드 개별 구매로 시작, 수요 확인 후 추가 |
| 묶음 할인 | 기본 구조 완성 후 추가 |
| 무통장 입금 | 가상계좌 운영 복잡도, 나중에 추가 |
| 소설 뷰어 | 웹툰 우선, 뷰어 타입 선택 구조만 열어둠 |
| 포렌식 워터마크 | VPS 성능 이슈 + 포스타입도 미적용, 나중에 연구 |
| Grafana | 초기엔 Hetzner 콘솔로 충분, 트래픽 늘면 추가 |
| 관리자 IP 화이트리스트 | 안정화 후 추가 |

### 제외 결정

| 기능 | 제외 이유 |
|------|----------|
| 다크모드 | 불필요하다고 판단 |
| 다운로드 소장 | 불법 유포 위험 |

---

## 콘텐츠 보호 전략 결정

**채택: 드래그/복사 차단 + 이미지 저장 차단 + Signed URL**

**검토했으나 제외한 방식들**

| 방식 | 제외 이유 |
|------|----------|
| Visible 워터마크 | 작품 감상 방해, 포스타입도 미사용 |
| 포렌식 워터마크 | VPS 성능 이슈, JPEG 압축 시 픽셀 파괴 |
| EXIF 메타데이터 | 카카오톡 전송만 해도 자동 삭제됨 |
| 다운로드 파일 제공 | 불법 유포 위험 |

**참고: 포스타입의 현재 방식**
- 드래그/복사 차단, 이미지 저장 차단
- Invisible 워터마크는 연구 단계, 미적용

---

## 보안 결정

### 관리자 로그인: 2FA(TOTP) 적용

**이유**
- 관리자 계정은 결제 데이터, 독자 개인정보, 콘텐츠 업로드 권한을 모두 보유
- 관리자 IP 화이트리스트는 안정화 후로 보류 → 그동안 비번 단독 보호는 위험
- TOTP는 무료(Google Authenticator 등) + 구현 단순 (시크릿 + 6자리 코드 검증)

**구현 방향**
- 흐름: 이메일/비번 검증 → TOTP 코드 검증 → JWT 발급
- 시크릿은 DB에 저장, 클라이언트에 절대 노출 금지
- 백업 코드는 1차 구현에서는 제외 (시크릿 분실 시 DB 직접 조작으로 복구)

**탈락한 후보들**
- SMS 2FA: SIM 스와핑 위험 + 발송 비용
- 이메일 OTP: 메일 계정 탈취되면 무력화
- WebAuthn: 1인 운영 초기엔 과함, TOTP만으로 충분

### 이메일 인증 필수

**이유**
- 환불 처리 시 정상 이메일로 안내해야 함 → 가짜 이메일로 가입하면 환불 통지 불가
- 결제 영수증 발송, 비밀번호 재설정 등 핵심 플로우가 이메일 의존
- 소셜 가입(카카오/구글)은 이미 검증된 이메일이라 별도 인증 생략 가능

**구현 방향**
- 일반 가입: 가입 후 인증 메일 발송, 유효 기간 1시간 토큰
- 미인증 상태에서도 무료분 열람은 가능하되, 결제는 인증 후에만 허용
- `users.is_email_verified` + `email_verifications` 테이블로 관리

### 환경 베이스 URL: config.py에서 조립

**이유**
- OAuth 콜백 URI, CORS 허용 도메인, Signed URL 생성 등 동일한 베이스 URL이 여러 곳에서 필요
- env에 평면적으로 두면 환경(dev/prod) 이동 시 4~5군데 동시 수정 필요 → 누락 사고 잦음

**구현 방향**
- env: `APP_BASE_URL`(독자 사이트), `ADMIN_BASE_URL`(관리자) 두 개만 정의
- `config.py`에서 `KAKAO_REDIRECT_URI`, `GOOGLE_REDIRECT_URI`, `CORS_ORIGINS` 등을 베이스 URL로 조립
- env에 콜백 URI/CORS 직접 박지 않음

---

## 결제 구조 결정

- 에피소드별 개별 구매 (500원 예정)
- 전편 구매 옵션 추가
- 충전식 코인 방식 채택 안 함 (개인 사이트 신뢰도 문제)
- 카카오페이/토스페이 수수료가 카드보다 낮음 (1.5~2% vs 2.5~3.5%)
- 소액 결제 마찰 줄이기 위해 카카오페이/토스페이 우선 노출

### 결제 내역 보관 기간: 5년

**이유**
- 전자상거래법상 대금 결제 및 재화 공급 기록은 5년 보관 의무
- 회원 탈퇴 시에도 `purchases`, `payment_logs`, `donations` 테이블 데이터는 유지
- 탈퇴 유저는 `users.deleted_at` 기록 + `nickname` 익명화로 처리, 결제 레코드는 user_id FK 유지

---

## 커뮤니티 결정

### 댓글 작성 조건: 없음

**이유**
- 1인 운영 + 초기 사용자 규모 → 가입 직후 바로 댓글 가능
- "가입 N일 이후" 같은 제약은 사용자 경험만 해침, 스팸은 신고 기능으로 대응
- 스팸/어뷰징 문제 발생하면 그때 다시 검토

### 댓글에도 좋아요 가능

**이유**
- 게시글/에피소드 좋아요와 동일하게 댓글에도 반응 가능
- `likes.target_type`에 `'episode' | 'post' | 'comment'` 모두 포함

---

## 브랜치 전략 결정

### GitHub Flow + 영역 prefix (area-first)

**흐름**
```
main (항상 배포 가능 상태)
  └── be/feat/auth-jwt
  └── be/fix/payment-webhook
  └── fe/feat/episode-viewer
  └── fe/fix/viewer-scroll
  └── admin/feat/upload-form
  └── common/docs/code-review
  └── common/chore/env-setup
```

**브랜치 패턴**

| 타입 | 패턴 | 예시 |
|------|------|------|
| 기능 | `{영역}/feat/{기능}` | `be/feat/auth-jwt` |
| 버그 | `{영역}/fix/{내용}` | `fe/fix/viewer-scroll` |
| 공통/설정/문서 | `common/{type}/{내용}` | `common/docs/code-review` |
| 긴급 핫픽스 | `{영역}/hotfix/{내용}` | `be/hotfix/payment-duplicate` |

영역: `be` (백엔드), `fe` (프론트), `admin`, `common`

**이유**
- 1인 프로젝트 → GitFlow 오버스펙, GitHub Flow가 적합
- 영역 prefix를 맨 앞에 두고 area-first로 구성
  - `git branch`에서 `be/`, `fe/`, `admin/`, `common/` 별로 자동 그룹화
  - 어느 영역 작업인지 한눈에 확인, 영역별 진행 상황 파악 용이

---

## 모니터링 결정

| 도구 | 역할 |
|------|------|
| UptimeRobot | 사이트 다운 감지 + 알림 (무료) |
| Sentry | 코드 에러 추적, 프론트/백엔드 (무료 플랜) |
| Hetzner 콘솔 | CPU/메모리/디스크 기본 확인 |
| Grafana | 나중에 추가 (Docker로 쉽게 붙일 수 있음) |