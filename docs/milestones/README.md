# 마일스톤 로드맵

| 항목 | 내용 |
|------|------|
| 문서 버전 | v1.0 (2026-05-27) |
| 대상 | MVP(P0) 4개월 + P1 8주 + P2 시장 검증 후 |
| 우선순위 정의 | P0 = 런칭 차단 / P1 = 런칭 후 8주 / P2 = 안정화 후 |
| 관련 문서 | [PRD.md](./PRD.md), [DECISIONS.md](./DECISIONS.md), [DB_SCHEMA.md](./DB_SCHEMA.md) |

---

## 의존성 다이어그램

```
M0 (기반)
  ↓
M1 (인증) ──┐
            ↓
        M1.5 (관리자 부트스트랩: 로그인+2FA, 작품/에피소드 업로드 골격)
            ↓
        M2 (콘텐츠/뷰어 - 무료 구간)
            ↓
        M3 (결제 + 유료 잠금)
            ↓
        ├── M4 (커뮤니티) ──┐
        └── M5 (관리자 운영 도구) ──┤
                                  ↓
                                M6 (알림)
                                  ↓
                                M7 (출시 검증 + 베타)
```

> **의존 메모**
> - M2 진입 전 M1.5에서 작품/에피소드 업로드가 최소한 작동해야 시드 데이터로 뷰어를 만들 수 있음
> - M4와 M5는 결제 권한(M3) 확정 후 병렬 진행 가능
> - M6 알림 트리거 중 "새 에피소드"는 M5, "댓글 답글"은 M4 이벤트라서 양쪽 모두 필요
> - **외부 블로커 (마일스톤 외부 일정)**: 도메인 등록, SMTP 발신 도메인 인증(SPF/DKIM), 토스페이먼츠 샌드박스 키 발급, 카카오 비즈앱 사업자 서류(M1.5 이후 카카오 OAuth 진행 시)

---

## M0. 프로젝트 기반 세팅

> **목적**: 인프라 + 개발 환경 + 외부 서비스 키. 이후 모든 마일스톤의 전제 조건.
> **DoD**: 로컬에서 `docker compose up`으로 FastAPI + Postgres가 뜨고, 푸시 시 CI가 lint/test를 돌리며, 스테이징 도메인이 HTTPS로 응답.

### 인프라
- [ ] 서비스 도메인 등록 + DNS A/AAAA 레코드 (Cloudflare)
- [ ] Hetzner VPS 초기화 + SSH 키 + 방화벽 (22/80/443만 개방)
- [ ] Docker Compose 구성 (FastAPI + PostgreSQL + Caddy)
- [ ] Caddy 리버스 프록시 + 자동 HTTPS 동작 확인
- [ ] Cloudflare R2 버킷 생성 + 액세스 키 + 커스텀 도메인 연결
- [ ] PostgreSQL **일 1회 풀 덤프 → R2 30일 보관** 스크립트 + cron 등록 (Q18)

### 백엔드 기반
- [x] FastAPI 프로젝트 구조 잡기 (routers/services/models/lib)
- [x] SQLModel + Alembic + asyncpg 세팅
- [x] Pydantic Settings로 `.env` 로딩 + 베이스 URL에서 OAuth/CORS 조립 (DECISIONS "환경 베이스 URL")
- [x] structlog JSON 로깅
- [x] Sentry 백엔드 연결
- [x] pytest 기본 골격 + DB 픽스처

### 프론트엔드 기반
- [x] Astro 프로젝트 생성 + React 통합 + Tailwind
- [x] Vite React SPA 프로젝트 생성 (관리자) + Tailwind
- [x] Sentry 프론트엔드 연결 (양쪽)
- [x] 공통 API 래핑(lib/api.ts) + Zod 검증 스키마 골격

### 외부 서비스 연결
- [ ] **SMTP 외부 메일 서비스** 가입 + 발신 도메인 SPF/DKIM 인증 (Resend 또는 SendGrid 무료 플랜)
- [ ] **토스페이먼츠 샌드박스** 테스트 키 발급 (Q4 결정 - 출시 결정 시 포트원으로 교체)
- [ ] 구글 OAuth Client ID 발급
- [ ] UptimeRobot 모니터 등록 (5분 간격)

### CI/CD
- [ ] GitHub Actions: lint(ruff/biome) + test + build
- [ ] main 머지 시 스테이징 자동 배포 (docker pull → compose up)
- [ ] PR 템플릿/이슈 템플릿 동작 확인

---

## M1. 인증 (이메일 + 구글)

> **목적**: 가입/로그인/세션 + 이메일 인증. **카카오 OAuth는 M1.5에서 별도 진행** (Q20 결정: 비즈앱 사업자 서류 필요).
> **선행**: M0
> **DoD**: 신규 유저가 이메일 또는 구글로 가입 → 인증 메일 수신 → 로그인 상태로 마이페이지 진입까지 완주.

> **M1 시작 전 준비**: backend models/routers/services/lib 스켈레톤이 git stash에 보관되어 있음.
> 아래 명령으로 확인 후 적용:
> ```bash
> git stash list  # "backend src skeleton (models/routers/services) - M1~M4 필요" 찾기
> git stash pop stash@{N}
> ```

### 백엔드
- [ ] `users` + `oauth_accounts` + `refresh_tokens` + `email_verifications` 모델 + 마이그레이션
- [ ] bcrypt(cost=12) 비밀번호 해싱
- [ ] JWT 발급/검증 (Access 15분 / Refresh 7일)
- [ ] HttpOnly + Secure + SameSite=Lax 쿠키 발급 (refresh는 SameSite=Strict)
- [ ] 회원가입 / 로그인 / 로그아웃 / 토큰 갱신 엔드포인트
- [ ] 구글 OAuth2 콜백 처리 (신규 시 user + oauth_accounts 동시 생성)
- [ ] 이메일 인증 메일 발송 (1시간 토큰) + 검증 엔드포인트
- [ ] **미인증 차단 의존성**: 결제·댓글 API에 `require_verified_email` 데코레이터 (실제 차단은 M3/M4에서 적용)
- [ ] Rate limiting (로그인 5회/분)
- [ ] 동일 이메일 소셜 별도 계정 안내 메시지 (Q6 결정)

### 프론트엔드 (Astro + React 아일랜드)
- [ ] 회원가입 / 로그인 페이지 (이메일 + 구글 버튼)
- [ ] OAuth 콜백 페이지 (SSR)
- [ ] 이메일 인증 안내 페이지 + 재발송 버튼
- [ ] 마이페이지 골격 (구매 목록은 M3, 알림 설정은 M6에서 채움)

> ⚠️ JWT는 HttpOnly 쿠키만 사용. localStorage 저장 절대 금지.
> ⚠️ Astro `SECRET_*` 환경변수는 빌드 타임 HTML에 노출되므로 클라이언트 코드에서 참조 금지.

### M1에서 의도적으로 제외 (후속 마일스톤에서 진행)
- 카카오 OAuth → M1.5 (사업자 등록 후)
- 비밀번호 재설정 (AUTH-05, P1) → P1 사이클
- 회원 탈퇴 (AUTH-07, P1) → P1 사이클
- 알림 설정 UI → M6

---

## M1.5. 관리자 부트스트랩

> **목적**: M2 콘텐츠 마일스톤이 시작되려면 작품/에피소드 데이터를 입력할 수단이 필요. 관리자 로그인(P0)과 업로드 최소 골격을 먼저 깐다.
> **선행**: M1
> **DoD**: 관리자가 2FA로 로그인 → 작품 등록 → 에피소드 이미지 업로드(50장, WebP 변환) → 회차 공개까지 작동.

### 백엔드
- [ ] `is_admin` 플래그 기반 관리자 권한 미들웨어
- [ ] TOTP 시크릿 발급 + 검증 (이메일·비번 → TOTP → JWT 순서, DECISIONS "2FA" 결정)
  - 백업 코드는 1차 구현 제외, 시크릿 분실 시 DB 직접 조작 복구
- [ ] `works` + `tags` + `works_tags` + `episodes` 모델 + 마이그레이션
- [ ] 작품 등록/수정 API (`is_admin` 필수)
- [ ] R2 presigned PUT 발급 API (회차당 최대 50장)
- [ ] **이미지 가로 800px WebP 자동 변환** (Q23 결정 필요 - 동기 vs Arq 워커. 1차는 동기, 응답 1초 초과 시 워커 분리)
- [ ] 에피소드 페이지 순서 저장 (`image_keys` JSONB)
- [ ] 에피소드 공개 예약 (스케줄러: APScheduler 또는 cron + `published_at` 도달 시 `is_published=true`)

### 프론트엔드 (Vite React SPA)
- [ ] 관리자 로그인 화면 (TOTP 입력 단계 포함)
- [ ] 작품 목록 / 등록 / 수정 화면
- [ ] 에피소드 업로드 화면 (드래그앤드롭, 페이지 순서 조정, 임시저장)
- [ ] 에피소드 공개 예약 UI

> ⚠️ TOTP 시크릿은 DB 저장 + 클라이언트 절대 노출 금지.
> ⚠️ 미인증/일반 유저가 관리자 API 호출 시 403, 라우터 단에서 권한 미들웨어 적용 일관성 점검.

---

## M2. 콘텐츠 (무료 구간)

> **목적**: 작품 목록 → 에피소드 목록 → 뷰어 3단계 + 무료 회차 정책.
> **선행**: M1.5 (시드 데이터 입력 가능 상태)
> **DoD**: 비로그인 유저가 작품 목록 → 무료 1~N화 끝까지 스크롤. 4화(유료) 진입 시 잠금 UI(M3 작업 전이라 placeholder)까지 노출.

### 백엔드
- [ ] 작품 목록 API (페이지네이션, 태그 필터)
- [ ] 작품 상세 API (works + tags + episodes 요약, `selectinload` 사용)
- [ ] 에피소드 목록 API (회차 번호·제목·썸네일·무료/유료/구매상태)
- [ ] **무료 에피소드 이미지 URL 반환 API** (`is_free=TRUE`만 통과, 미결제 + 유료는 403)
- [ ] `viewer_progress` 모델 + 진행도 저장 API (페이지 번호 기준, WORK-09)
- [ ] 작가 소개 정적 데이터 API (또는 Astro에서 마크다운 직접 import)

### 프론트엔드 (Astro)
- [ ] 작품 목록 페이지 (SSG, 24시간 ISR 또는 빌드 시 fetch)
- [ ] 작품 상세 페이지 (SSG)
- [ ] 에피소드 목록 페이지 (SSG)
- [ ] **세로 스크롤 웹툰 뷰어** (React 아일랜드 `client:idle`)
  - lazy load, 이전/다음 화 이동
  - 드래그/복사/우클릭/저장 차단 (UX 우선, 완벽 차단 아님)
  - 마지막 페이지 번호 진행도 저장 (debounce)
- [ ] 작가 소개 페이지 (정적)

### M2에서 의도적으로 제외
- 작품 검색 (WORK-11, P2)
- 유료 회차 Signed URL → M3

---

## M3. 결제 + 유료 콘텐츠 잠금

> **목적**: 토스페이먼츠 샌드박스 + 서버 사이드 금액 검증 + Signed URL.
> **선행**: M2
> **DoD**: 미구매 유저가 잠금 UI → 결제 → 서버 검증 통과 → Signed URL로 즉시 열람. 결제 실패는 사용자 안내 + Sentry 알림. 환불은 미열람 회차에 한해 관리자 수동 처리 가능.

### 백엔드
- [ ] `purchases` + `payment_logs` 모델 + 마이그레이션
- [ ] **active 구매 중복 방지 partial unique index** (`refunded_at IS NULL`)
- [ ] **단건 구매 검증 엔드포인트**
  - 클라이언트가 `imp_uid` 전달 → 토스페이먼츠 REST로 금액·상태 재확인
  - 금액은 반드시 **DB에서 계산** (works.episode_base_price + episodes.price 우선)
  - 검증 통과 시 트랜잭션 1개로 `purchases` + `payment_logs(success)` insert
  - 실패 시 `payment_logs(fail)` + Sentry
- [ ] **유료 에피소드 Signed URL 발급 API**
  - 권한 확인: `purchases` 활성 레코드 (`refunded_at IS NULL`) 존재
  - **회차 단위 1개 URL**, **TTL 10분**, 매 요청마다 생성
- [ ] **첫 열람 시 `first_viewed_at` 기록** (환불 가능 판정 기준)
- [ ] 영수증 URL 반환 (토스페이먼츠/포트원 응답 그대로 노출)
- [ ] **환불 API (관리자 전용)**
  - 조건: `first_viewed_at IS NULL` AND `refunded_at IS NULL`
  - 토스페이먼츠 cancel API 호출 → `purchases.refunded_at` + `refund_amount` 기록
  - 트랜잭션으로 묶고, **결제 cancel 실패 시 DB 롤백**
- [ ] 결제 시도 rate limit (10회/분)

### 프론트엔드
- [ ] 유료화 잠금 UI + 구매 버튼 (React 아일랜드 `client:idle`)
- [ ] 토스페이먼츠 결제창 (카카오페이/토스페이 우선, 카드 후순위)
- [ ] 결제 완료 후 뷰어 자동 언락 (Signed URL 받아서 이미지 로드)
- [ ] 결제 실패 모달 + 재시도 UI
- [ ] 구매 내역 페이지 (`/my/purchases`, SSR, 페이지네이션 20건)
- [ ] 영수증 링크

> ⚠️ 결제 금액 검증은 반드시 서버. 클라이언트 검증 금지.
> ⚠️ 미구매 유저에게 유료 이미지 URL 절대 노출 금지.
> ⚠️ 토스페이먼츠 API 호출 결과 확인 **후** DB 저장 (외부 호출과 DB 트랜잭션 묶지 말 것).
> ⚠️ Q1 (환불 약관) / Q7 (만 14세) 법무 검토 결과를 결제 화면 약관 텍스트에 반영해야 출시 가능 → M7과 연계.

### M3에서 의도적으로 제외 (P1 후속)
- 전편 구매 (PAY-07) → P1: `purchases.bundle_id` 활용한 일괄 생성/환불
- 후원 (PAY-09) → M4에서 결제 흐름 재사용

---

## M4. 커뮤니티 + 후원

> **목적**: 하트 + 댓글 + 후원 + 작가 게시판(근황).
> **선행**: M3
> **DoD**: 인증된 유저가 에피소드/게시글에 하트·댓글·답글 작성. 작가 답글은 배지 표시. 후원은 결제 후 메시지 등록. 신고 5회 누적 시 자동 숨김.

### 백엔드
- [ ] `comments` + `likes` + `reports` + `donations` + `posts` + `polls` + `poll_options` + `poll_votes` 모델 + 마이그레이션
- [ ] 댓글 CRUD (1depth 답글 강제, 1,000자 제한)
- [ ] 댓글 작성 가입 **7일 제한** (Q13 결정) + 본인 글 7일 미만 차단 미들웨어
- [ ] 하트 토글 (1유저 1좋아요, `target_type` = 'episode'|'post'|'comment')
- [ ] 신고 API + **5회 누적 시 자동 숨김** (Q14 결정)
- [ ] 댓글 삭제 (본인/작가/관리자, soft delete)
- [ ] 후원 결제 (토스페이먼츠 재사용, `donations` insert)
- [ ] 작가 게시판 - 근황 CRUD (작성은 `is_admin`만)
- [ ] 댓글 작성 rate limit (10회/분)

### 프론트엔드 (Astro + React 아일랜드)
- [ ] 에피소드 하단 댓글 UI (`client:idle`)
- [ ] 하트 버튼 (`client:idle`)
- [ ] 후원 UI + 결제창 (`client:idle`, 1,000/3,000/5,000원 + 메시지)
- [ ] 작가 게시판 - 근황 페이지
- [ ] 신고 모달

### M4에서 의도적으로 제외 (P2)
- Q&A 게시판 (COMM-07)
- 투표 게시판 (COMM-08) - `polls` 테이블만 만들어두고 작성 UI는 P2
- 비로그인 커뮤니티 읽기 허용 여부 (Q15, 출시 전 결정)

---

## M5. 관리자 운영 도구

> **목적**: 수익/통계, 환불 승인, 댓글/신고 관리, 후원 확인, 커미션 페이지.
> **선행**: M3 (수익) + M4 (신고/후원/게시글)
> **DoD**: 작가가 관리자 화면에서 일/주/월 매출 확인, 환불 요청 승인, 신고된 댓글 처리, 후원 메시지 확인, 커미션 페이지 표시까지 가능.

### 백엔드
- [ ] 수익 집계 API (일/주/월, 작품별·회차별·결제수단별)
- [ ] 독자 통계 API (가입자 추이, MAU, 회차별 열람 수, 결제 전환율)
- [ ] 환불 요청 리스트 + 승인/거부 API (M3 환불 API 호출)
- [ ] 신고된 댓글 리스트 + 처리 API
- [ ] 후원 내역 + 메시지 조회 API
- [ ] 커미션 신청 폼 (이메일 발송)
- [ ] 업로드 리마인더 (마지막 업로드 후 N일 경과 시 작가 이메일, **P2**)

### 프론트엔드 (Vite React SPA)
- [ ] 수익 대시보드
- [ ] 독자 통계 화면
- [ ] 환불 처리 화면 (요청 리스트 → 승인/거부)
- [ ] 댓글/신고 관리 화면
- [ ] 후원 내역 화면
- [ ] 커뮤니티 게시글 작성 화면 (근황/투표)
- [ ] 커미션 관리 화면

### 독자용 사이트 (Astro)
- [ ] 커미션 페이지 `/commission` (작가 가격·일정·예시 + 신청 폼)

> 💡 작품/에피소드 관리(ADM-02/03/04)는 **M1.5에서 이미 구현**됨. M5에서는 운영 기능에 집중.

---

## M6. 알림 (in-app + email + push)

> **목적**: 새 에피소드 / 댓글 답글 / 새 게시글 알림. 채널별 on/off.
> **선행**: M5 (새 에피소드 트리거) + M4 (댓글 답글 트리거)
> **DoD**: 알림 동의 유저가 새 에피소드 업로드 시 in-app 알림 즉시 + 이메일 5분 내 수신. 알림 센터에서 읽음 처리. 설정 화면에서 채널별 on/off.

### 백엔드
- [ ] `notification_settings` + `notifications` + `notification_logs` 모델 + 마이그레이션
- [ ] **푸시 채널 결정** (DB 스키마 §7 미결): 웹 푸시 도입 시 `push_tokens` 테이블 추가 또는 P1 보류
- [ ] 알림 발송 서비스 (이벤트 → in-app insert + email send + push send + `notification_logs` 기록)
  - 새 에피소드 업로드 트리거 (M5 `is_published` 변경 시)
  - 댓글 답글 등록 트리거 (M4 comments insert 시)
  - 새 게시글 등록 트리거 (M4 posts insert 시)
- [ ] 알림 목록 API (페이지네이션, 읽음 필터)
- [ ] 읽음 처리 API
- [ ] 알림 설정 조회/수정 API (채널 × 종류 매트릭스)

### 프론트엔드
- [ ] 알림 센터 UI (Navbar 벨 아이콘 → 드롭다운)
- [ ] 알림 설정 화면 (`/my/notifications`, 채널 × 종류 토글)

### M6에서 의도적으로 제외
- 웹 푸시 (브라우저 권한 + push_tokens) - 복잡도 따라 P1으로 분리 가능
- 카카오톡 알림톡 - 비용/심사 이슈, 보류

---

## M7. 출시 검증 + 베타

> **목적**: P0 마일스톤 완료 후 출시 직전 검증. PRD §5.2 "관리자+QA 1개월"이 여기에 해당.
> **선행**: M0~M6 P0 항목 완료
> **DoD**: 보안/부하/법무 모두 통과, 베타 사용자 10~30명 1주일 운영 후 치명 버그 0.

### 보안
- [ ] **보안 리뷰**: 결제·인증·Signed URL 권한·CORS·rate limit 종합 점검 (Opus 4.7로 `/security-review`)
- [ ] OWASP Top 10 자체 체크리스트 (XSS, CSRF, SQLi, IDOR)
- [ ] 비밀번호 reset 토큰, 이메일 인증 토큰, JWT TTL 재검토
- [ ] 환경변수 누출 점검 (Astro `PUBLIC_*` 외 빌드 산출물 grep)

### 부하 테스트
- [ ] **100명 동시 뷰어 열람** 시나리오 (k6 또는 wrk)
- [ ] DB 쿼리 N+1 점검 (selectinload 누락 여부)
- [ ] R2 egress 시뮬레이션 (월 7GB 경보 임계치, Q17)

### 법무 검토
- [ ] **약관 / 개인정보처리방침 / 청약철회 안내** 초안 (Q1, Q24)
  - "결제 후 즉시 이용 가능, 청약철회 불가" 결제 화면 명시 필수
- [ ] **만 14세 이상** 가입 체크박스 + 약관 명시 (Q7)
- [ ] 결제 약관 노출 위치 확인

### 외부 키 교체
- [ ] **토스페이먼츠 샌드박스 → 실 키** 또는 **포트원 가맹점 심사 통과 후 키 교체** (Q4)
- [ ] 사업자 등록증 + 가맹점 신청
- [ ] **카카오 OAuth 비즈앱 전환** (사업자 서류 완료 후 활성화, Q20)
- [ ] SMTP 발신 도메인 정식 검증 (스팸 분류 회피)

### 베타
- [ ] 작가 SNS 팔로워 중 10~30명 초청
- [ ] Sentry 에러 모니터링 + 1일 1회 점검
- [ ] 결제·환불·뷰어 흐름 실 사용자 피드백 수집
- [ ] 치명 버그 수정 + 출시 결정

### 운영 준비
- [ ] 다운 감지 알림 작동 확인 (UptimeRobot → 카카오톡)
- [ ] 백업 복원 리허설 1회 (R2 덤프 → 새 VPS로 복구)
- [ ] CS/환불 대응 SOP 문서

---

## 보류 / 제외 결정

전체 목록은 [DECISIONS.md](./DECISIONS.md) "기능 범위 결정 - 보류/나중에" 및 "제외 결정" 섹션 참조. 마일스톤 진입 시 결정이 필요한 항목은 각 마일스톤의 "의도적으로 제외" 블록에서 별도 표기.
