# DB Schema - 웹툰 작가 개인 사이트

| 항목 | 내용 |
|------|------|
| 문서 버전 | v2.3 (2026-09-22, M3 취소 발송·시도별 키 계획 보강, 구현 schema 변경 없음) |
| DB | PostgreSQL |
| ORM | SQLModel |
| 작성 기준 | 현재 SQLModel·Alembic migration 우선, 이후 마일스톤 계획은 별도 표시 |

---

## 설계 원칙

- 주요 엔티티는 UUID PK를 사용. `works_tags`는 복합 PK, `site_texts`는 문자열 자연키이며 새 테이블은 실제 모델·migration을 확인
- 삭제 이력 보존이 필요한 모델은 `deleted_at TIMESTAMPTZ`로 soft delete 처리 (현재 User, Work, Episode). 참조가 없는 운영 설정 모델은 별도 결정 가능
- 타임스탬프는 전부 `TIMESTAMPTZ` (UTC 저장, 표시는 KST 변환)
- 사용자 입력을 포함한 원시 SQL 문자열 조합 금지, SQLModel/SQLAlchemy 표현식과 바인딩 사용
- 금액은 `INTEGER` (원 단위, 소수점 없음)

> **상태 표기**: 1-2절은 별도 `[계획]` 표시가 없으면 현재 구현된 스키마다. 3절 이후에는 아직 migration이 없는 후속 초안이 포함된다. M3 계획의 상세 상태·제약 정본은 `docs/milestones/M3_foundation.md`이며 실제 구현 뒤 모델·migration 기준으로 다시 갱신한다.

---

## 1. 계정/인증 도메인

### users
```sql
users
├── id              UUID PRIMARY KEY DEFAULT gen_random_uuid()
├── email           VARCHAR(255) UNIQUE NOT NULL
├── hashed_password VARCHAR(255)          -- 소셜 전용 가입이면 NULL
├── nickname        VARCHAR(50) NOT NULL
├── profile_image   TEXT                  -- URL
├── role            VARCHAR(16) NOT NULL DEFAULT 'reader'  -- reader | owner | moderator (RBAC)
├── is_email_verified BOOLEAN DEFAULT FALSE
├── email_verified_at TIMESTAMPTZ
├── totp_secret     VARCHAR(255)          -- 2FA TOTP 시크릿(Fernet 암호문), NULL = 미등록
├── totp_confirmed_at TIMESTAMPTZ         -- 첫 코드 검증 시각, NULL = 미확인(비활성)
├── totp_last_step  BIGINT                -- 마지막 성공 검증 time-step (#56 replay 가드)
├── created_at      TIMESTAMPTZ DEFAULT now()
├── updated_at      TIMESTAMPTZ DEFAULT now()
└── deleted_at      TIMESTAMPTZ           -- soft delete, NULL = 유효
```
> - 탈퇴 시 `deleted_at` 기록, `nickname` → "알 수 없음" 익명화
> - 결제 내역은 user 삭제 후에도 5년 보관 (전자상거래법)
> - TOTP 3컬럼(M1.5 B, #56): 검증은 매칭 step 엄격 증가(`totp_last_step` - replay 차단, DECISIONS "2FA"). 시크릿 분실 수동 복구 시 **3컬럼 함께 NULL**(step은 시각 기반이라 새 시크릿에 이월됨)
> - `role`: 권한(RBAC). `reader`(일반)/`owner`(작가-매출·정산·환불·콘텐츠+모더레이션)/`moderator`(게시글 삭제·문의 답변만, M4 owner가 부여). VARCHAR이라 후속 역할 추가는 앱 코드만(DB 마이그레이션 0). authz는 DB `user.role` 기준(JWT 미포함). M1.5는 `owner`만 빌드, B1 마이그레이션에서 `is_admin`→`role` 이관(true→owner). 개발자는 product 역할이 아님(매출 차단은 인프라/자격증명 계층 - M7). 상세 DECISIONS "관리자 권한 분리"

### oauth_accounts
```sql
oauth_accounts
├── id          UUID PRIMARY KEY DEFAULT gen_random_uuid()
├── user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
├── provider    VARCHAR(20) NOT NULL   -- 'google' | 'kakao'
├── provider_id VARCHAR(255) NOT NULL  -- provider 측 고유 ID
├── created_at  TIMESTAMPTZ DEFAULT now()
└── UNIQUE (provider, provider_id)
```
> - 동일 이메일로 구글/카카오 가입 시 별도 계정 유지 (자동 병합 없음)

### refresh_tokens
```sql
refresh_tokens
├── id         UUID PRIMARY KEY DEFAULT gen_random_uuid()
├── user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
├── token_hash VARCHAR(255) NOT NULL  -- HMAC-SHA256(+TOKEN_PEPPER) 해시
├── expires_at TIMESTAMPTZ NOT NULL
├── original_issued_at TIMESTAMPTZ NOT NULL  -- 토큰 체인 최초 발급 시각(회전 시 승계), 절대 수명 cap 기준점 (M1 A)
├── created_at TIMESTAMPTZ DEFAULT now()
└── revoked_at TIMESTAMPTZ            -- NULL = 유효
```

### email_verifications
```sql
email_verifications
├── id         UUID PRIMARY KEY DEFAULT gen_random_uuid()
├── user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
├── token      VARCHAR(255) NOT NULL   -- HMAC-SHA256(+TOKEN_PEPPER) 해시, UNIQUE (원문은 메일 링크에만)
├── expires_at TIMESTAMPTZ NOT NULL   -- 발급 후 1시간
└── used_at    TIMESTAMPTZ            -- NULL = 미사용
```

### trusted_devices
관리자 신뢰 기기 - "이 기기에서 30일간 2단계 인증 생략" (M1.5 B3). TOTP 검증 성공 시
옵트인 발급, `/admin/login` 1단계가 유효 행을 확인하면 TOTP 생략(비번은 여전히 필수).
유효 조건에 `created_at >= users.totp_confirmed_at` 포함 - TOTP 재등록 시 옛 신뢰 자동 실효.
```sql
trusted_devices
├── id         UUID PRIMARY KEY DEFAULT gen_random_uuid()
├── user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
├── token_hash VARCHAR(255) NOT NULL  -- HMAC-SHA256(+TOKEN_PEPPER) 해시, UNIQUE (원문은 쿠키에만)
├── expires_at TIMESTAMPTZ NOT NULL   -- 발급 + 30일, 절대 만료(슬라이딩 갱신 없음)
├── created_at TIMESTAMPTZ DEFAULT now()  -- 앱이 명시 세팅(totp_confirmed_at과 같은 시계로 비교)
└── revoked_at TIMESTAMPTZ            -- NULL = 유효
```

---

## 2. 작품/에피소드 도메인

### works
```sql
works
├── id                   UUID PRIMARY KEY DEFAULT gen_random_uuid()
├── author_id            UUID NOT NULL REFERENCES users(id)  -- 확장 대비 FK
├── title                VARCHAR(200) NOT NULL
├── synopsis             TEXT
├── cover_image          TEXT          -- R2 key
├── episode_base_price   INTEGER DEFAULT 500  -- 에피소드 기본가 (원)
├── status               VARCHAR(20) DEFAULT 'ongoing'
│                        -- 'preparing' | 'ongoing' | 'completed' | 'hiatus'
│                        -- 노출 여부는 is_published 별개 축 (#84 - 상호 강제 없음)
├── is_published         BOOLEAN NOT NULL DEFAULT false
│                        -- 독자 카탈로그 노출 게이트. status와 독립이라 준비중+공개
│                        -- (커밍순 티저)도, 연재중+비공개(긴급 하차)도 정상 조합이다
├── created_at           TIMESTAMPTZ DEFAULT now()
├── updated_at           TIMESTAMPTZ DEFAULT now()
└── deleted_at           TIMESTAMPTZ
```

### works_tags (M:N)
```sql
works_tags
├── work_id UUID NOT NULL REFERENCES works(id) ON DELETE CASCADE
├── tag_id  UUID NOT NULL REFERENCES tags(id) ON DELETE CASCADE
└── PRIMARY KEY (work_id, tag_id)
```

### tags
```sql
tags
├── id         UUID PRIMARY KEY DEFAULT gen_random_uuid()
├── name       VARCHAR(50) UNIQUE NOT NULL  -- '로맨스', '판타지' 등
└── created_at TIMESTAMPTZ DEFAULT now()
```

### episodes
```sql
episodes
├── id           UUID PRIMARY KEY DEFAULT gen_random_uuid()
├── work_id      UUID NOT NULL REFERENCES works(id) ON DELETE CASCADE
├── public_id    INTEGER NOT NULL          -- 독자 URL 조회키(랜덤 8자리, 전역 UNIQUE)
├── sort_order   INTEGER NOT NULL          -- 작품 안에서의 표시 순서(작가 지정, max+1 자동)
│               -- ⚠️ UNIQUE 없음: 동점은 정상이고 (created_at, id)가 깬다. 유일 제약이
│               -- episode_no가 동시 생성에서 409를 뱉던 원인이라 반복하지 않는다.
├── title        VARCHAR(200) NOT NULL     -- 필수. 서버 기본값 '무제' 폐지(2026-07-30)
├── subtitle     VARCHAR(200)              -- 부제목 (포스타입식 에디터, F3 재설계)
├── thumbnail    TEXT                      -- 대표 이미지로 선택한 원고 R2 key
│               -- NULL 또는 image_keys와 발행본 content의 image key 양쪽에 포함
├── price        INTEGER                   -- NULL이면 works.episode_base_price 사용
├── is_free      BOOLEAN DEFAULT FALSE     -- ⚠️ 파생 컬럼: content의 paywall 경계에서
│               -- 서버가 계산(직접 입력 폐지) - 목록·무료구간 SQL용 비정규화
├── content      JSONB NOT NULL DEFAULT '{"type": "doc", "content": []}'
│               -- 본문(발행본) = TipTap/ProseMirror JSON 문서(글+이미지+유료 경계 paywall 노드)
│               -- 표시 순서·구성의 진실. 검증은 lib/content_doc (화이트리스트·상한·키 소유)
│               -- 유의미 내용 없으면 EMPTY_DOC으로 정규화(스케줄러 SQL 가드 성립 조건)
├── draft        JSONB                     -- 편집본 봉투 {"title","subtitle","content"} (#86)
│               -- NULL = 편집본 없음. 공개 회차의 임시저장은 여기에만 쓰고, content(발행본)는
│               -- 발행 액션(is_published 동반 요청)만 덮는다. content 쓰기 시 자동 NULL(소진).
│               -- owner 전용(AdminEpisodeRead) - 독자 DTO 노출 금지(미발행 원고)
├── image_keys   JSONB NOT NULL DEFAULT '[]'
│               -- 업로드 매니페스트: 이 회차에 업로드된 R2 키 전량(50장 가드·미참조 추적)
│               -- content의 image 키는 이 배열의 부분집합이어야 함 (F3 재설계로
│               -- "배열 인덱스 = 페이지 순서" 의미는 content로 이관)
├── is_published BOOLEAN DEFAULT FALSE
├── published_at TIMESTAMPTZ               -- 예약 목표 시각·현재 공개 제어
├── first_published_at TIMESTAMPTZ          -- 실제 최초 공개 전환 시각(재공개 시 불변)
├── created_at   TIMESTAMPTZ DEFAULT now()
├── updated_at   TIMESTAMPTZ DEFAULT now()
├── deleted_at   TIMESTAMPTZ               -- 회차 soft delete (#85)
│               -- 불변식: NOT NULL이면 is_published=false이고 published_at IS NULL
│               -- (soft_delete_episode가 한 UPDATE로 보장). 되살리는 API 없음. 하드
│               -- 삭제를 안 하는 이유: M3 purchases.episode_id가 ON DELETE 절 없이
│               -- (기본 RESTRICT) 참조 - 구매·환불 기록이 걸린 회차는 삭제 자체가 불가.
└── UNIQUE (public_id)
```
> - `price IS NULL` → 런타임에 `works.episode_base_price` 참조
> - 유료 경계 = content 최상위의 `paywall` 노드(최대 1개). 경계 앞 = 무료 미리보기,
>   경계 뒤 = 유료. `is_free` = "경계 뒤 유의미 콘텐츠 없음"(전체 무료)의 파생값.
> - 미구매 독자 응답(M3) = 서버가 경계 이전 노드만 잘라 반환. 유료 구간의 이미지
>   키·Signed URL은 절대 비공개(클라이언트 숨김 처리 금지).
> - **회차 번호 폐기(2026-07-29, DECISIONS "회차 번호 폐기")**: `episode_no`(순번) 개념을
>   없앴다. `public_id`는 서버가 발급하는 무작위 8자리 정수(`10_000_000`~`99_999_999`,
>   `secrets.randbelow` + UNIQUE 재시도)이고 클라이언트가 지정할 수 없다. 독자 URL은
>   `/works/{workId}/{publicId}`.
> - **정렬은 `sort_order` → `created_at` → `id`**. `public_id`가 랜덤이 되면서 순번이
>   정렬 기준 역할을 못 하게 됐고, `created_at`만 남기면 프롤로그를 나중에 끼워넣거나
>   잘못 올린 순서를 되돌릴 수 없어 작가 지정 컬럼을 뒀다. 기본값은 작품 안 `max+1`,
>   재배열은 `PUT /admin/works/{workId}/episodes`(살아있는 회차 전량을 순서대로 전송,
>   집합 불일치는 409). `published_at`으로 정렬하지 않는 이유: 내렸다 재공개하면 맨
>   뒤로 밀린다.
> - **제목 필수(2026-07-30)**: `EpisodeCreate.title`의 서버 기본값 `'무제'`를 제거했다.
>   번호가 사라져 목록·액션 메뉴·뷰어 네비의 식별자가 제목 하나로 줄었기 때문에
>   `'무제'` 행이 둘 이상이면 구분이 불가능하다.

### viewer_progress
```sql
viewer_progress
├── id          UUID PRIMARY KEY DEFAULT gen_random_uuid()
├── user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
├── episode_id  UUID NOT NULL REFERENCES episodes(id) ON DELETE CASCADE
├── page_no     INTEGER NOT NULL DEFAULT 0  -- 마지막으로 본 최상위 블록 인덱스
├── block_offset_bp INTEGER NOT NULL DEFAULT 0  -- 블록 내부 상대 위치(0..10000)
├── updated_at  TIMESTAMPTZ DEFAULT now()
├── UNIQUE (user_id, episode_id)
└── CHECK (block_offset_bp BETWEEN 0 AND 10000)
```

### M3 뷰어 확장 [계획]

```sql
episode_images
├── id          UUID PRIMARY KEY DEFAULT gen_random_uuid()
├── episode_id  UUID NOT NULL REFERENCES episodes(id) ON DELETE CASCADE
├── key         TEXT UNIQUE NOT NULL
├── width       INTEGER NOT NULL CHECK (width > 0)
├── height      INTEGER NOT NULL CHECK (height > 0)
├── byte_size   BIGINT NOT NULL CHECK (byte_size > 0)
├── created_at  TIMESTAMPTZ DEFAULT now()
└── updated_at  TIMESTAMPTZ DEFAULT now()

episodes
└── sales_paused_at TIMESTAMPTZ  -- NULL이면 신규 판매 가능, 기존 구매 열람과 무관

viewer_progress
├── progress_bp INTEGER NOT NULL DEFAULT 0 CHECK (progress_bp BETWEEN 0 AND 10000)
└── completed_at TIMESTAMPTZ
```

> `episode_images`는 `image_keys`의 소유권 매니페스트와 `content`의 표시 구성을 대체하지 않는다. M3 백필은 공개·비공개·draft의 모든 image key를 transaction 밖 R2 I/O로 읽고 재실행 가능한 batch upsert를 수행한다. `sales_paused_at`과 일반 비공개는 신규 intent만 막고 활성 구매 full은 유지한다. route를 없애는 soft delete는 `active|refund_pending|review_required` 구매가 남아 있으면 409로 막는다.

### commission_items (M2 그룹 G)
```sql
commission_items
├── id                UUID PRIMARY KEY DEFAULT gen_random_uuid()
├── title             VARCHAR(200) NOT NULL
├── description       TEXT                       -- 플레인 텍스트(줄바꿈만, 마크업 없음)
├── price_text        VARCHAR(100) NOT NULL      -- 표시 전용 자유 문자열("50,000원~")
│                    -- 숫자 컬럼이 아닌 이유: 커미션은 사이트 결제 대상이 아님(M5도 이메일 접수)
├── duration_text     VARCHAR(100)               -- 작업 기간 표기("5일")
├── sample_image_keys JSONB NOT NULL DEFAULT '[]'
│                    -- 공개 버킷(dweb-cover) 키 매니페스트. episodes.image_keys와 달리
│                    -- **배열 순서 = 표시 순서**(별도 콘텐츠 문서가 없어 순서의 진실이 여기뿐)
├── is_open           BOOLEAN NOT NULL DEFAULT TRUE  -- 크레페식 슬롯 상태(마감 배지)
├── sort_order        INTEGER NOT NULL DEFAULT 0     -- 공개 목록 정렬(오름차순)
├── created_at        TIMESTAMPTZ DEFAULT now()
└── updated_at        TIMESTAMPTZ DEFAULT now()
```
> - 크레페식 커미션 홍보 카드(M2 그룹 G, 2026-07-29 카드 모델 확정). 신청 폼·접수는 M5.
> - **soft delete 없음**(하드 삭제) - 참조하는 자식 테이블·독자 URL이 없다. 삭제 시 샘플
>   이미지는 커밋 성공 후 공개 버킷에서 정리(commission_service).
> - 샘플 키 = `commission/{item_id}/{uuid4hex}.webp` - 유일 키라 캐시 버스터 불요.

### site_texts (M2 그룹 G)
```sql
site_texts
├── key         VARCHAR(50) PRIMARY KEY   -- 자연키: 'landing_intro' | 'commission_notes'
│              -- 앱 enum(SiteTextKey) 검증 - 슬롯 추가는 멤버만 늘리면 됨(마이그레이션 0)
├── body        TEXT NOT NULL DEFAULT ''  -- 플레인 텍스트(작가가 admin에서 편집)
└── updated_at  TIMESTAMPTZ DEFAULT now()
```
> - 작가(owner)가 admin에서 편집하는 사이트 문구(랜딩 소개·커미션 유의사항). 행은
>   시딩하지 않는다 - admin GET이 행 없음을 빈 기본값으로 응답, PUT이 ON CONFLICT upsert.
> - M7 법무 문서(약관·개인정보처리방침)도 같은 모양이라 슬롯 추가로 흡수 가능(후보).

---

## 3. 결제 도메인 [부분 구현 - M3 그룹 C]

> `payment_orders`, `purchases`, `payment_webhook_receipts`, `payment_logs`는 M3 그룹 C의 revision `d0c3a4b5e6f7`에서 구현했다. 주문 생명주기·동기화·권한 서비스와 `refund_requests`·`donations`는 후속 그룹 범위다. PortOne은 실제 자금 상태, `payment_orders`는 로컬 주문·동기화 상태, `purchases`는 열람 권한의 기준이다. 모든 외부 `PAID`는 구매/후원 결과 또는 전액 보상 취소로 종결한다. 구매 commit 뒤 일반 비공개는 기존 full 권한을 유지하고, 비공개·soft delete commit 뒤 늦은 `PAID`는 권한 없이 전액 보상한다. M3는 개발자 소유 테스트 고객사, M7 실결제는 작가 소유의 새 고객사를 사용하며 외부 거래를 이관하지 않는다. 두 환경은 같은 schema를 쓰되 Store·secret·DB를 분리하고 `environment`를 영구 provenance로 보존한다.

### payment_orders
```sql
payment_orders
├── id                     UUID PRIMARY KEY DEFAULT gen_random_uuid()
├── payment_id             VARCHAR(64) UNIQUE NOT NULL  -- 서버 생성 V2 paymentId
├── user_id                UUID NOT NULL REFERENCES users(id)
├── kind                   VARCHAR(24) NOT NULL
│                          CHECK (kind IN ('episode_purchase', 'donation'))
├── episode_id             UUID REFERENCES episodes(id)
├── expected_amount        INTEGER NOT NULL CHECK (expected_amount > 0)
├── provider_total_amount  INTEGER CHECK (provider_total_amount > 0) -- 검증된 PortOne amount.total, 미조회는 NULL
├── currency               VARCHAR(3) NOT NULL DEFAULT 'KRW' CHECK (currency = 'KRW')
├── store_id               VARCHAR(255) NOT NULL
├── requested_channel_key  VARCHAR(255) NOT NULL
├── environment            VARCHAR(8) NOT NULL
│                          CHECK (environment IN ('test', 'live'))
├── order_name             VARCHAR(255) NOT NULL  -- PG 제한에 맞춘 안전 표시명
├── item_title             VARCHAR(200) NOT NULL  -- 구매내역 표시 snapshot
├── checkout_notice_version VARCHAR(32)
├── immediate_supply_consented_at TIMESTAMPTZ
├── donation_message       VARCHAR(500)
├── status                 VARCHAR(24) NOT NULL
│                          -- preparing | ready | expired | paid | cancel_pending
│                          -- | cancelled | review_required
│                          CHECK (status IN ('preparing', 'ready', 'expired', 'paid',
│                                 'cancel_pending', 'cancelled', 'review_required'))
├── provider_status        VARCHAR(40)
├── transaction_id         VARCHAR(255)
├── cancellation_id        VARCHAR(255)
├── pg_provider            VARCHAR(40)
├── payment_method         VARCHAR(40)
├── easy_pay_provider      VARCHAR(40)
├── receipt_url            TEXT
├── cancel_reason          VARCHAR(40)             -- 내부 allowlist code만 허용
├── cancel_idempotency_key VARCHAR(256)
├── cancel_request_snapshot JSONB              -- 개인정보 없는 exact cancel body, immutable
├── cancel_key_issued_at    TIMESTAMPTZ           -- 계획: E, 재생 창의 보수적 시작점
├── cancel_dispatch_token  UUID                  -- 계획: E, 외부 POST 발송 선점
├── cancel_dispatch_started_at TIMESTAMPTZ       -- 계획: E, token과 함께 존재
├── cancelled_amount       INTEGER
├── expires_at             TIMESTAMPTZ NOT NULL
├── next_reconcile_at      TIMESTAMPTZ
├── reconcile_attempts     INTEGER NOT NULL DEFAULT 0
├── last_synced_at         TIMESTAMPTZ
├── needs_action_reason    VARCHAR(80)
├── prepared_at            TIMESTAMPTZ
├── paid_at                TIMESTAMPTZ
├── cancelled_at           TIMESTAMPTZ
├── created_at             TIMESTAMPTZ DEFAULT now()
└── updated_at             TIMESTAMPTZ DEFAULT now()
```
> - 구매 주문은 `episode_id NOT NULL AND donation_message IS NULL`, 후원 주문은 `episode_id`와 message가 각각 nullable인 kind CHECK를 둔다.
> - 구매 주문은 `checkout_notice_version`과 `immediate_supply_consented_at`이 NOT NULL이고 후원 주문은 둘 다 NULL이다. 서버가 현재 고지 버전과 동의 시각을 기록하며 클라이언트의 확인 금액을 현재 서버 가격과 실제 선택 주문의 `expected_amount`에 모두 대조한다. M3 테스트는 `episode-immediate-v1`로 시작하고 문구 변경 시 새 버전을 쓰며 기존 주문 snapshot은 갱신하지 않는다.
> - 같은 사용자·회차·환경의 `preparing|ready` 주문은 하나만 허용한다. ready 재사용은 금액·channel·현재 고지 버전이 호환될 때만 30분 허용하며 만료 전 PortOne을 다시 조회한다. `expired`는 checkout 재사용 종료이지 자금 종결이 아니므로 대사 대상에서 제외하지 않는다.
> - 결제 시도 `FAILED`는 주문 terminal 상태로 두지 않고 `payment_logs`에 남긴다. 늦은 `PAID`는 expired 주문에서도 정상 sync한다.
> - `PARTIAL_CANCELLED`와 알 수 없는 자금 상태는 `review_required`로 격리하고 권한을 닫는다.
> - 외부 응답 뒤 transaction에서 현재 상태를 다시 읽고 허용 from-status CAS만 수행한다. `paid`·`cancelled`·`cancel_pending`은 늦은 `READY|PAID` 응답으로 회귀하지 않는다.
> - `expected_amount`는 서버 주문·구매 provenance로 보존한다. `provider_total_amount`는 서버가 인증된 PortOne 단건 조회의 `amount.total`에서 기록하며, 클라이언트 값이나 할인 등이 반영된 `amount.paid`로 대체하지 않는다. 금액 불일치도 실제 총액을 보존해 권한 없이 전액 보상한다.
> - 취소 사유는 `system_verification|system_unavailable|system_duplicate|customer_refund`만 허용한다. 사유·16~256자 ASCII 멱등 키·request snapshot·E 계획의 key 발급 시각은 모두 NULL이거나 모두 존재하고, `cancel_pending`에서는 반드시 존재한다. 취소 묶음에는 양수 `provider_total_amount`가 필수다. snapshot은 주문의 Store·사유·`provider_total_amount` 기준 전액 `amount`·`currentCancellableAmount`와 사유별 requester로 DB에서 재구성한 5-key JSONB와 정확히 같아야 하므로 추가 키나 개인정보를 넣을 수 없다. reason·snapshot은 한 번 정하면 유지하고, 같은 미확정 시도의 key만 발급 시각 기준 3시간 안에 재생한다. 확정 실패 뒤 사용자 환불의 새 시도는 새 key·발급 시각으로 원자적으로 교체한다. 기존 key가 있는 행의 E migration은 `created_at`을 보수적 시각으로 사용하고 불명확한 건은 자동 POST하지 않는다. `cancelled_amount`는 NULL이거나 `0 < cancelled_amount <= provider_total_amount`여야 하고 후자는 provider 총액도 필수다.
> - E 계획의 `cancel_dispatch_token`·`cancel_dispatch_started_at`은 함께 NULL 또는 존재하고 token이 있으면 order는 `cancel_pending`이어야 한다. 현재 상태·key와, 사용자 환불이면 현재 시도 번호까지 다시 확인한 worker만 token NULL→UUID CAS로 발송권을 얻는다. HTTP 호출이 응답·예외·로컬 timeout으로 끝난 뒤 같은 token·key와 사용자 환불 시도 번호로만 응답 반영과 token 해제를 commit한다. timeout은 외부 실패 확정이 아니다. 발송권이 있는 동안 실패 복원·새 시도·다른 POST를 금지한다. task 취소·프로세스 중단·응답 반영 commit 실패로 token이 남으면 TTL 자동 회수 없이 권한을 잠그고, 발송 프로세스 종료와 외부 자금 상태를 확인한 통제된 복구만 허용한다.
> - environment는 계정 이메일이 아니라 서버 설정과 검증된 PortOne channel에서 정한다. 생성 뒤 바꾸지 않고 개발자 테스트 Store를 작가 실판매 Store로 교체해도 기존 test 행을 live로 갱신하지 않는다.
> - 구매 권한이 참조하는 주문 provenance는 `(id, user_id, kind, episode_id, environment, expected_amount, paid_at)` UNIQUE로 고정한다. `status`는 취소 상태 전이를 허용해야 하므로 이 묶음에 넣지 않는다.

### purchases
```sql
purchases
├── id               UUID PRIMARY KEY DEFAULT gen_random_uuid()
├── payment_order_id UUID UNIQUE NOT NULL
├── user_id          UUID NOT NULL REFERENCES users(id)
├── payment_order_kind VARCHAR(24) NOT NULL DEFAULT 'episode_purchase'
│                    CHECK (payment_order_kind = 'episode_purchase')
├── episode_id       UUID NOT NULL REFERENCES episodes(id)
├── environment      VARCHAR(8) NOT NULL
│                    CHECK (environment IN ('test', 'live'))
├── status           VARCHAR(24) NOT NULL
│                    CHECK (status IN ('active', 'refund_pending', 'refunded', 'review_required'))
├── amount           INTEGER NOT NULL CHECK (amount > 0)
├── paid_at          TIMESTAMPTZ NOT NULL
├── first_viewed_at  TIMESTAMPTZ
├── refunded_at      TIMESTAMPTZ
└── refund_amount    INTEGER
```
> - 결제 완료나 purchase 생성만으로 `first_viewed_at`을 기록하지 않는다. 결제 복귀 뒤 자동 full 요청 또는 사용자의 직접 회차 진입에서 실제 전문을 처음 발급할 때만 기록한다.
> - 전문 첫 발급과 환불 승인은 같은 행의 `status='active' AND first_viewed_at IS NULL` 조건부 UPDATE로 경합한다.
> - `(payment_order_id, user_id, payment_order_kind, episode_id, environment, amount, paid_at)`은 `payment_orders(id, user_id, kind, episode_id, environment, expected_amount, paid_at)`를 가리키는 composite FK다. 사용자·회차·환경·금액·결제 시각이 주문과 다른 권한이나 donation 기반 권한은 DB가 거부하고, 구매 뒤 그 주문 provenance 변경도 막는다.
> - `payment_order_kind`는 향후 상품 유형을 표현하는 `purchase_type`이 아니라 FK를 완성하는 고정 discriminator다. 구매 생성 시 주문이 실제 `paid`인지 확인하는 책임은 상태를 바꾸는 공통 sync transaction에 남긴다.
> - environment는 구매를 생성한 payment_order에서 같은 transaction으로 복사하는 immutable snapshot이다. 전문 권한은 purchase와 order 환경이 모두 현재 `PAYMENT_ENVIRONMENT`와 일치할 때만 성립한다.
> - 활성 구매의 full은 작품·회차의 일반 `is_published=false`보다 우선한다. soft delete는 route를 없애므로 `active|refund_pending|review_required` 구매가 남아 있으면 409로 막는다.
> - `(user_id, episode_id, environment) WHERE status IN ('active','refund_pending','review_required')` partial unique가 같은 환경의 중복 권한과 환불 중 재구매를 막는다. test 구매는 live 구매를 막지 않는다.
> - `purchase_type`, `bundle_id`, 전편 구매는 현재 범위 제외다.

### payment_webhook_receipts
```sql
payment_webhook_receipts
├── id              UUID PRIMARY KEY DEFAULT gen_random_uuid()
├── webhook_id      VARCHAR(255) UNIQUE NOT NULL
├── payment_id      VARCHAR(64)
├── event_type      VARCHAR(40) NOT NULL
├── attempts        INTEGER NOT NULL DEFAULT 0
├── next_attempt_at TIMESTAMPTZ
├── received_at     TIMESTAMPTZ NOT NULL DEFAULT now()
├── processed_at    TIMESTAMPTZ
└── ignored_at      TIMESTAMPTZ
```
> raw webhook 서명 검증 뒤 이 receipt가 commit되기 전에는 2xx를 보내지 않는다. scheduler가 미처리 행을 bounded batch로 sync하고 상태 전이와 `processed_at`을 같은 transaction에 commit한다. 원시 body·헤더는 저장하지 않는다.

### payment_logs
```sql
payment_logs
├── id               UUID PRIMARY KEY DEFAULT gen_random_uuid()
├── payment_order_id UUID NOT NULL REFERENCES payment_orders(id)
├── webhook_receipt_id UUID REFERENCES payment_webhook_receipts(id)
├── source           VARCHAR(20) NOT NULL -- browser | webhook | reconcile | admin
├── event_type       VARCHAR(40) NOT NULL
├── from_status      VARCHAR(24)
├── to_status        VARCHAR(24)
├── provider_status  VARCHAR(40)
├── failure_code     VARCHAR(80)          -- 제한 code만, PII·원시 payload 금지
└── created_at       TIMESTAMPTZ DEFAULT now()
```
> 일반 거절·사용자 취소는 감사 로그만, 불변식 위반·장기 미수렴만 Sentry 대상이다.

### refund_requests [계획 - M3 그룹 G]
```sql
refund_requests
├── id           UUID PRIMARY KEY DEFAULT gen_random_uuid()
├── purchase_id  UUID NOT NULL REFERENCES purchases(id)
├── requested_by UUID NOT NULL REFERENCES users(id)
├── reason       VARCHAR(40) NOT NULL
├── detail       VARCHAR(1000)
├── status       VARCHAR(24) NOT NULL
│                CHECK (status IN ('pending', 'processing', 'approved', 'rejected', 'action_required'))
├── cancel_attempt_no INTEGER NOT NULL DEFAULT 0 CHECK (cancel_attempt_no >= 0)
├── resolved_by  UUID REFERENCES users(id)
├── admin_note   VARCHAR(1000)
├── notification_status VARCHAR(24) NOT NULL DEFAULT 'none'
│                CHECK (notification_status IN ('none', 'pending', 'sent', 'action_required'))
├── notification_attempts INTEGER NOT NULL DEFAULT 0
├── next_notification_at TIMESTAMPTZ
├── notified_at  TIMESTAMPTZ
├── requested_at TIMESTAMPTZ DEFAULT now()
├── resolved_at  TIMESTAMPTZ
└── updated_at   TIMESTAMPTZ DEFAULT now()
```
> - 한 구매의 `pending|processing|action_required` 요청은 하나만 허용한다. 최초 승인 또는 최종 실패 뒤 재선점 때 `cancel_attempt_no`를 증가시키고 `refund_<request UUID hex>_<attempt no>` key를 생성한다. 같은 `processing` 시도의 timeout 재생에는 번호·key·body를 유지하며 168시간이 지나도 기존 권한 잠금을 유지한다. 동일 key 재생은 `cancel_key_issued_at + 3시간` 안에만 허용하고 이후 불명확한 건은 GET 대사·격리한다.
> - token owner가 최종 실패를 받으면 같은 token·시도 번호·key로 현재 cancellation ID와 실패 증거를 기록하고 token만 먼저 해제한다. 별도 짧은 transaction이 현재 cancellation의 `FAILED`·payment `PAID`·token NULL을 다시 확인한 뒤에만 order `paid`·purchase `active`·request `action_required`를 함께 확정한다. `action_required` 재시작은 이 상태와 `now < paid_at + 168 hours`, `first_viewed_at IS NULL`, purchase `active`를 다시 확인해 request `processing`·purchase `refund_pending`·order `cancel_pending`, 시도 번호 증가, 새 key·발급 시각, `cancellation_id=NULL`을 한 transaction에서 CAS한다. exact body는 유지한다. 외부 POST는 별도 발송 token CAS 선점 뒤에만 가능하고 응답 반영은 같은 token·시도 번호·key를 요구한다. 이전 시도 응답은 새 시도를 덮지 못한다.
> - reject는 취소 시도 전 `pending`, 또는 이전 취소의 최종 실패·order `paid`·purchase `active`와 첫 발급/168시간 경과에 따른 자격 상실이 모두 확인된 `action_required`에서만 허용한다. 자격이 남으면 같은 요청을 retry하고 `processing`은 거부하지 않는다. 자격을 잃은 retry는 요청 `rejected`·사유·메일 `pending`을 함께 commit한 뒤 409를 반환하며 취소 호출은 하지 않는다. CAS loser는 상대 시도를 덮지 않고 재조회한다.
> - 실결제 자격 정책은 M7 법무 gate에서 확정한다. 승인·거부 확정은 결과 메일을 `pending`으로 함께 예약하며 발송 실패는 환불 transaction을 되돌리지 않고 scheduler가 재시도한다.

### donations
```sql
donations
├── id               UUID PRIMARY KEY DEFAULT gen_random_uuid()
├── payment_order_id UUID UNIQUE NOT NULL REFERENCES payment_orders(id)
├── user_id          UUID NOT NULL REFERENCES users(id)
├── episode_id       UUID REFERENCES episodes(id) -- NULL이면 작가 후원
├── amount           INTEGER NOT NULL
│                    CHECK (amount IN (1000, 3000, 5000))
├── message          VARCHAR(500)              -- owner 전용
└── paid_at          TIMESTAMPTZ NOT NULL
```
> 게시글 후원, 공개 visibility, 후원 환불 자동화는 M3 범위 제외다.

---

## 4. 커뮤니티 도메인 [계획 - M4]

### posts
```sql
posts
├── id           UUID PRIMARY KEY DEFAULT gen_random_uuid()
├── author_id    UUID NOT NULL REFERENCES users(id)  -- 작가만 작성 가능
├── post_type    VARCHAR(20) NOT NULL
│                -- 'text' | 'poll'
├── content      TEXT
├── images       JSONB DEFAULT '[]'   -- ["r2/posts/xxx.webp", ...]
├── is_published BOOLEAN DEFAULT TRUE
├── created_at   TIMESTAMPTZ DEFAULT now()
├── updated_at   TIMESTAMPTZ DEFAULT now()
└── deleted_at   TIMESTAMPTZ
```
> - 작가 전용 단일 피드. 독자는 읽기 + 댓글만 가능
> - `post_type = 'poll'` 이면 `polls` 테이블과 1:1 연결

### polls
```sql
polls
├── id               UUID PRIMARY KEY DEFAULT gen_random_uuid()
├── post_id          UUID NOT NULL UNIQUE REFERENCES posts(id) ON DELETE CASCADE
├── allow_multiple   BOOLEAN DEFAULT FALSE   -- 복수 선택 허용 여부
├── is_anonymous     BOOLEAN DEFAULT FALSE   -- 익명 투표 여부
├── ends_at          TIMESTAMPTZ             -- NULL = 마감 없음
└── created_at       TIMESTAMPTZ DEFAULT now()
```

### poll_options
```sql
poll_options
├── id       UUID PRIMARY KEY DEFAULT gen_random_uuid()
├── poll_id  UUID NOT NULL REFERENCES polls(id) ON DELETE CASCADE
├── content  VARCHAR(200) NOT NULL
└── order_no INTEGER NOT NULL   -- 표시 순서
```

### poll_votes
```sql
poll_votes
├── id             UUID PRIMARY KEY DEFAULT gen_random_uuid()
├── poll_id        UUID NOT NULL REFERENCES polls(id) ON DELETE CASCADE
├── poll_option_id UUID NOT NULL REFERENCES poll_options(id)
├── user_id        UUID NOT NULL REFERENCES users(id)
├── created_at     TIMESTAMPTZ DEFAULT now()
└── UNIQUE (poll_id, poll_option_id, user_id)  -- 중복 투표 방지
```
> - `is_anonymous = TRUE`면 집계 시 `user_id` 노출 안 함

### comments
```sql
comments
├── id          UUID PRIMARY KEY DEFAULT gen_random_uuid()
├── user_id     UUID NOT NULL REFERENCES users(id)
├── target_type VARCHAR(20) NOT NULL   -- 'episode' | 'post'
├── target_id   UUID NOT NULL          -- episode.id 또는 post.id
├── parent_id   UUID REFERENCES comments(id)  -- NULL = 최상위, 값 있음 = 답글 (1depth)
├── content     TEXT NOT NULL          -- 최대 1,000자
├── created_at  TIMESTAMPTZ DEFAULT now()
├── updated_at  TIMESTAMPTZ DEFAULT now()
└── deleted_at  TIMESTAMPTZ
```
> - 댓글 작성 조건 없음 (가입 직후 바로 가능)
> - 작가 댓글은 프론트에서 `role=owner` 확인 후 배지 표시
> - `parent_id IS NOT NULL`인 댓글의 자식 댓글은 허용하지 않음 (1depth 강제)

### likes
```sql
likes
├── id          UUID PRIMARY KEY DEFAULT gen_random_uuid()
├── user_id     UUID NOT NULL REFERENCES users(id)
├── target_type VARCHAR(20) NOT NULL   -- 'episode' | 'post' | 'comment'
├── target_id   UUID NOT NULL
├── created_at  TIMESTAMPTZ DEFAULT now()
└── UNIQUE (user_id, target_type, target_id)   -- 1유저 1좋아요
```

### reports
```sql
reports
├── id          UUID PRIMARY KEY DEFAULT gen_random_uuid()
├── reporter_id UUID NOT NULL REFERENCES users(id)
├── target_type VARCHAR(20) NOT NULL   -- 'comment' | 'post' | 'user'
├── target_id   UUID NOT NULL
├── reason      VARCHAR(100)
├── status      VARCHAR(20) DEFAULT 'pending'
│               -- 'pending' | 'resolved' | 'dismissed'
├── created_at  TIMESTAMPTZ DEFAULT now()
└── resolved_at TIMESTAMPTZ
```

---

## 5. 알림 도메인 [계획 - M6]

### notification_settings
```sql
notification_settings
├── id                    UUID PRIMARY KEY DEFAULT gen_random_uuid()
├── user_id               UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE
├── new_episode_email     BOOLEAN DEFAULT TRUE
├── new_episode_push      BOOLEAN DEFAULT TRUE
├── new_episode_inapp     BOOLEAN DEFAULT TRUE
├── new_post_email        BOOLEAN DEFAULT FALSE
├── new_post_push         BOOLEAN DEFAULT FALSE
├── new_post_inapp        BOOLEAN DEFAULT TRUE
├── comment_reply_email   BOOLEAN DEFAULT FALSE
├── comment_reply_push    BOOLEAN DEFAULT TRUE
├── comment_reply_inapp   BOOLEAN DEFAULT TRUE
└── updated_at            TIMESTAMPTZ DEFAULT now()
```

### notifications
```sql
notifications
├── id              UUID PRIMARY KEY DEFAULT gen_random_uuid()
├── user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
├── type            VARCHAR(50) NOT NULL   -- 'new_episode' | 'new_post' | 'comment_reply' | ...
│                   -- VARCHAR로 열어둬서 나중에 타입 추가 용이
├── title           VARCHAR(200) NOT NULL
├── body            TEXT
├── link            TEXT                   -- 클릭 시 이동할 URL
├── is_read         BOOLEAN DEFAULT FALSE
├── created_at      TIMESTAMPTZ DEFAULT now()
└── read_at         TIMESTAMPTZ
```

### notification_logs
```sql
notification_logs
├── id              UUID PRIMARY KEY DEFAULT gen_random_uuid()
├── notification_id UUID REFERENCES notifications(id)
├── channel         VARCHAR(20) NOT NULL   -- 'email' | 'push' | 'inapp'
├── status          VARCHAR(20) NOT NULL   -- 'sent' | 'failed'
├── sent_at         TIMESTAMPTZ DEFAULT now()
└── error_message   TEXT
```

---

## 6. 인덱스 정리 (현행 + 후속 계획)

> 1-2절과 M3 그룹 C 결제 테이블의 인덱스는 현재 model·migration과 대조한다. `refund_requests`, `donations`, comments, notifications 등 아직 없는 테이블의 인덱스는 각 `[계획]` 절에 종속된 초안이다.

```sql
-- 자주 쓰이는 조회 기준 인덱스
CREATE INDEX idx_episodes_work_id       ON episodes(work_id);
CREATE INDEX idx_episodes_published     ON episodes(work_id) WHERE is_published = TRUE;
CREATE INDEX idx_episode_images_episode ON episode_images(episode_id);
CREATE INDEX idx_payment_orders_episode_id ON payment_orders(episode_id);
CREATE INDEX idx_payment_orders_reconcile ON payment_orders(environment, status, next_reconcile_at);
CREATE INDEX idx_payment_orders_user_environment_created_at ON payment_orders(user_id, environment, created_at DESC);
CREATE INDEX idx_payment_webhook_receipts_pending
  ON payment_webhook_receipts(next_attempt_at, received_at)
  WHERE processed_at IS NULL AND ignored_at IS NULL;
CREATE INDEX idx_payment_webhook_receipts_payment_id ON payment_webhook_receipts(payment_id);
CREATE INDEX idx_payment_logs_payment_order_id ON payment_logs(payment_order_id);
CREATE INDEX idx_payment_logs_webhook_receipt_id ON payment_logs(webhook_receipt_id);
CREATE UNIQUE INDEX uq_payment_orders_open_episode_intent
  ON payment_orders(user_id, episode_id, environment)
  WHERE kind = 'episode_purchase' AND status IN ('preparing', 'ready');
CREATE INDEX idx_purchases_user_id      ON purchases(user_id);
CREATE INDEX idx_purchases_episode_id   ON purchases(episode_id);

-- 열람 가능·환불 처리·검토 상태는 모두 재구매를 막는다.
CREATE UNIQUE INDEX uq_purchases_entitlement
  ON purchases(user_id, episode_id, environment)
  WHERE status IN ('active', 'refund_pending', 'review_required');
CREATE UNIQUE INDEX uq_refund_requests_open
  ON refund_requests(purchase_id)
  WHERE status IN ('pending', 'processing', 'action_required');
CREATE INDEX idx_refund_requests_notification_pending
  ON refund_requests(next_notification_at)
  WHERE notification_status = 'pending';
CREATE INDEX idx_comments_target        ON comments(target_type, target_id);
CREATE INDEX idx_comments_parent_id     ON comments(parent_id);
CREATE INDEX idx_likes_target           ON likes(target_type, target_id);
CREATE INDEX idx_notifications_user_id  ON notifications(user_id, is_read);
CREATE INDEX idx_posts_created_at       ON posts(created_at DESC) WHERE deleted_at IS NULL;

-- 태그 검색: tags.name UNIQUE(§2)가 만드는 유니크 인덱스가 WHERE name=? 조회를 겸하므로
-- 별도 idx_tags_name은 중복이라 두지 않는다 (M1.5 A1, 2026-07-01). 역방향 tag_id 조회는 M2/M5 시 추가.

-- soft delete 필터링
CREATE INDEX idx_users_deleted_at       ON users(deleted_at) WHERE deleted_at IS NULL;

-- 리프레시 토큰 회전/재사용 탐지 시 user_id로 세션 전체 revoke (M1 C4)
CREATE INDEX idx_refresh_tokens_user_id ON refresh_tokens(user_id);
-- 리프레시 토큰 해시 직접 조회(매 갱신·로그인) + 회전 불변식 방어선 (M1 I1, forward-only 마이그레이션)
CREATE UNIQUE INDEX uq_refresh_tokens_token_hash ON refresh_tokens(token_hash);

-- 이메일 인증 토큰 해시 직접 조회(M1 E2) + 중복 방지(결정적 해시 + 고엔트로피 랜덤)
CREATE UNIQUE INDEX uq_email_verifications_token ON email_verifications(token);
-- 재발송/무효화(M1 E3)의 WHERE user_id=? 조회 (M1 I2, forward-only 마이그레이션)
CREATE INDEX idx_email_verifications_user_id ON email_verifications(user_id);

-- 신뢰 기기 토큰 해시 직접 조회(/admin/login) + 중복 방지 (M1.5 B3)
CREATE UNIQUE INDEX uq_trusted_devices_token_hash ON trusted_devices(token_hash);
-- 승격/재등록 시 user 단위 일괄 revoke 조회 (M1.5 B3)
CREATE INDEX idx_trusted_devices_user_id ON trusted_devices(user_id);

-- 진행도의 FK 자식 조회 (M2 C1, 2026-07-20 코드리뷰 반영). UNIQUE(user_id, episode_id)는
-- 선두 컬럼이 user_id라 episode_id 단독 조회에 쓰이지 못한다. episodes 행 삭제 시
-- ON DELETE CASCADE가 자식을 찾을 때 없으면 순차 스캔.
CREATE INDEX idx_viewer_progress_episode_id ON viewer_progress(episode_id);
```

---

## 7. 미결 상태로 남긴 항목

| 항목 | 내용 | 결정 시점 |
|------|------|-----------|
| 환불 시간 제한 | M3 테스트는 결제 후 168시간 미만·전문 미발급. 실결제 기간·문구는 법무 검토 후 확정 | M7 출시 gate |
| 휴면 계정 분리 | 현재 스키마에 반영 안 함, 안정화 후 추가 | 6개월 후 |
| push 토큰 저장 | 웹 푸시 도입 시 `push_tokens` 테이블 별도 추가 필요 | P1 작업 시 |
