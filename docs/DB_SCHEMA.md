# DB Schema - 웹툰 작가 개인 사이트

| 항목 | 내용 |
|------|------|
| 문서 버전 | v1.2 (2026-05-26) |
| DB | PostgreSQL |
| ORM | SQLModel |
| 작성 기준 | PRD v1.0 + 미결 사항 확정 답변 |

---

## 설계 원칙

- 모든 테이블에 `id UUID PRIMARY KEY DEFAULT gen_random_uuid()` 사용
- soft delete는 `deleted_at TIMESTAMPTZ` 로 처리 (NULL = 유효)
- 타임스탬프는 전부 `TIMESTAMPTZ` (UTC 저장, 표시는 KST 변환)
- 원시 SQL 금지, SQLModel ORM 사용
- 금액은 `INTEGER` (원 단위, 소수점 없음)

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
├── is_admin        BOOLEAN DEFAULT FALSE
├── is_email_verified BOOLEAN DEFAULT FALSE
├── email_verified_at TIMESTAMPTZ
├── created_at      TIMESTAMPTZ DEFAULT now()
├── updated_at      TIMESTAMPTZ DEFAULT now()
└── deleted_at      TIMESTAMPTZ           -- soft delete, NULL = 유효
```
> - 탈퇴 시 `deleted_at` 기록, `nickname` → "알 수 없음" 익명화
> - 결제 내역은 user 삭제 후에도 5년 보관 (전자상거래법)

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
├── created_at TIMESTAMPTZ DEFAULT now()
└── revoked_at TIMESTAMPTZ            -- NULL = 유효
```

### email_verifications
```sql
email_verifications
├── id         UUID PRIMARY KEY DEFAULT gen_random_uuid()
├── user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
├── token      VARCHAR(255) NOT NULL
├── expires_at TIMESTAMPTZ NOT NULL   -- 발급 후 1시간
└── used_at    TIMESTAMPTZ            -- NULL = 미사용
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
├── bundle_discount_rate NUMERIC(4,3) DEFAULT 0.1  -- 전편 할인율 (0.1 = 10%)
├── status               VARCHAR(20) DEFAULT 'ongoing'
│                        -- 'ongoing' | 'completed' | 'hiatus'
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
├── episode_no   INTEGER NOT NULL          -- 회차 번호
├── title        VARCHAR(200) NOT NULL
├── thumbnail    TEXT                      -- R2 key
├── price        INTEGER                   -- NULL이면 works.episode_base_price 사용
├── is_free      BOOLEAN DEFAULT FALSE     -- 에피소드별 무료 여부 직접 지정
├── image_keys   JSONB NOT NULL DEFAULT '[]'
│               -- ["r2/ep1/001.webp", "r2/ep1/002.webp", ...]
│               -- 배열 인덱스 = 페이지 순서
├── is_published BOOLEAN DEFAULT FALSE
├── published_at TIMESTAMPTZ               -- 예약 공개 시간
├── created_at   TIMESTAMPTZ DEFAULT now()
├── updated_at   TIMESTAMPTZ DEFAULT now()
└── UNIQUE (work_id, episode_no)
```
> - `price IS NULL` → 런타임에 `works.episode_base_price` 참조
> - `is_free = TRUE` → 비로그인 유저도 `image_keys` 접근 가능
> - `is_free = FALSE` AND 미구매 → 이미지 URL 절대 비공개, Signed URL만 발급

### viewer_progress
```sql
viewer_progress
├── id          UUID PRIMARY KEY DEFAULT gen_random_uuid()
├── user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
├── episode_id  UUID NOT NULL REFERENCES episodes(id) ON DELETE CASCADE
├── page_no     INTEGER NOT NULL DEFAULT 0  -- 마지막으로 본 페이지 번호
├── updated_at  TIMESTAMPTZ DEFAULT now()
└── UNIQUE (user_id, episode_id)
```

---

## 3. 결제 도메인

### purchases
```sql
purchases
├── id              UUID PRIMARY KEY DEFAULT gen_random_uuid()
├── user_id         UUID NOT NULL REFERENCES users(id)
├── episode_id      UUID NOT NULL REFERENCES episodes(id)
├── amount          INTEGER NOT NULL          -- 실제 결제 금액 (원)
├── purchase_type   VARCHAR(20) DEFAULT 'single'
│                   -- 'single' | 'bundle'    ← 낱개 vs 전편 구매 구분
├── bundle_id       UUID                      -- 전편 구매 시 같은 트랜잭션 묶음 식별
│                   -- 낱개 구매는 NULL, 전편 구매는 N개 레코드가 동일 bundle_id 공유
├── pg_provider     VARCHAR(30) NOT NULL      -- 'tosspayments' 등
├── pg_payment_id   VARCHAR(255) NOT NULL     -- PG사 결제 고유 ID
├── paid_at         TIMESTAMPTZ NOT NULL
├── first_viewed_at TIMESTAMPTZ               -- NULL = 미열람 → 환불 가능 판단 기준
├── refunded_at     TIMESTAMPTZ               -- NULL = 환불 안 됨
└── refund_amount   INTEGER                   -- 환불된 금액
```
> - 전편 구매는 에피소드 수만큼 `purchases` 레코드 N개 일괄 생성 (단일 트랜잭션)
> - 전편 구매 레코드들은 동일한 `bundle_id` (UUID)를 공유 → 일괄 환불/통계 처리 가능
> - 환불 가능 조건: `first_viewed_at IS NULL` AND `refunded_at IS NULL`
> - 전편 일괄 환불 시: `WHERE bundle_id = ? AND first_viewed_at IS NULL` 로 대상 추출
> - 중복 구매 방지는 partial unique index로 처리 (인덱스 정리 섹션 참조)
>   → 환불된 레코드(`refunded_at IS NOT NULL`)는 제외되어 재구매 허용

### payment_logs
```sql
payment_logs
├── id            UUID PRIMARY KEY DEFAULT gen_random_uuid()
├── user_id       UUID REFERENCES users(id)
├── episode_id    UUID REFERENCES episodes(id)
├── pg_payment_id VARCHAR(255)
├── status        VARCHAR(20) NOT NULL  -- 'success' | 'fail' | 'cancel'
├── amount        INTEGER
├── failure_reason TEXT
└── created_at    TIMESTAMPTZ DEFAULT now()
```
> - 결제 성공/실패 모두 기록. Sentry 연동은 `status = 'fail'` 시

### donations
```sql
donations
├── id            UUID PRIMARY KEY DEFAULT gen_random_uuid()
├── user_id       UUID NOT NULL REFERENCES users(id)
├── post_id       UUID REFERENCES posts(id)   -- 게시글 후원 (NULL이면 작가 단위)
├── episode_id    UUID REFERENCES episodes(id) -- 에피소드 후원
├── amount        INTEGER NOT NULL             -- 100원 단위, 최소 100원
├── message       TEXT
├── visibility    VARCHAR(20) DEFAULT 'public'
│                 -- 'public' | 'private' | 'author_only'
├── pg_payment_id VARCHAR(255) NOT NULL
├── paid_at       TIMESTAMPTZ NOT NULL
└── CHECK (NOT (post_id IS NOT NULL AND episode_id IS NOT NULL))
         -- post_id, episode_id 둘 다 NOT NULL 금지
         -- 둘 다 NULL이면 작가 단위 후원, 하나만 NOT NULL이면 해당 대상 후원
```

---

## 4. 커뮤니티 도메인

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
> - 작가 댓글은 프론트에서 `is_admin` 확인 후 배지 표시
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

## 5. 알림 도메인

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

## 6. 인덱스 정리

```sql
-- 자주 쓰이는 조회 기준 인덱스
CREATE INDEX idx_episodes_work_id       ON episodes(work_id);
CREATE INDEX idx_episodes_published_at  ON episodes(published_at) WHERE is_published = TRUE;
CREATE INDEX idx_purchases_user_id      ON purchases(user_id);
CREATE INDEX idx_purchases_episode_id   ON purchases(episode_id);
CREATE INDEX idx_purchases_bundle_id    ON purchases(bundle_id) WHERE bundle_id IS NOT NULL;

-- 활성 구매(미환불) 중복 방지. 환불된 레코드는 제외되어 재구매 가능
CREATE UNIQUE INDEX uq_purchases_active
  ON purchases(user_id, episode_id)
  WHERE refunded_at IS NULL;
CREATE INDEX idx_comments_target        ON comments(target_type, target_id);
CREATE INDEX idx_comments_parent_id     ON comments(parent_id);
CREATE INDEX idx_likes_target           ON likes(target_type, target_id);
CREATE INDEX idx_notifications_user_id  ON notifications(user_id, is_read);
CREATE INDEX idx_posts_created_at       ON posts(created_at DESC) WHERE deleted_at IS NULL;

-- 태그 검색
CREATE INDEX idx_tags_name              ON tags(name);

-- soft delete 필터링
CREATE INDEX idx_users_deleted_at       ON users(deleted_at) WHERE deleted_at IS NULL;

-- 리프레시 토큰 회전/재사용 탐지 시 user_id로 세션 전체 revoke (M1 C4)
CREATE INDEX idx_refresh_tokens_user_id ON refresh_tokens(user_id);

-- 공개된 에피소드만 조회 (idx_episodes_work_id와 별개의 partial index)
CREATE INDEX idx_episodes_published     ON episodes(work_id) WHERE is_published = TRUE;
```

---

## 7. 미결 상태로 남긴 항목

| 항목 | 내용 | 결정 시점 |
|------|------|-----------|
| 환불 시간 제한 | 미열람 조건만 확정, 7일 기간 제한은 법무 검토 후 결정 | 런칭 전 |
| 휴면 계정 분리 | 현재 스키마에 반영 안 함, 안정화 후 추가 | 6개월 후 |
| push 토큰 저장 | 웹 푸시 도입 시 `push_tokens` 테이블 별도 추가 필요 | P1 작업 시 |