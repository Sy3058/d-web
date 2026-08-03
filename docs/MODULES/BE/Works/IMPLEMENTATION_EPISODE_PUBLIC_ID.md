# 회차 번호 폐기: episode_no → public_id + sort_order (M2 회차 식별/URL 결정)

| 항목 | 내용 |
|------|------|
| 모듈 | Backend / Works (+ Frontend Works, Admin Episodes) |
| 관련 마일스톤 | [M2](../../../milestones/M2_foundation.md) "회차 식별/URL 결정" |
| 작성 시점 | 2026-07-29 (구현과 동시), 2026-07-30 코드 리뷰 반영分 추가 |
| 상태 | 구현 완료. 마이그레이션 2건 upgrade/downgrade 왕복 검증 |
| 관련 문서 | [DECISIONS.md](../../../DECISIONS.md) "회차 번호 폐기", [DB_SCHEMA.md](../../../DB_SCHEMA.md) §episodes, [IMPLEMENTATION_WORK_DOMAIN_MODEL.md](./IMPLEMENTATION_WORK_DOMAIN_MODEL.md)(원본 `episode_no` 도입), [IMPLEMENTATION_EPISODE_EDITOR.md](../../ADMIN/Episodes/IMPLEMENTATION_EPISODE_EDITOR.md)(제목 필수) |

DECISIONS의 2026-07-28 결정(`episode_no` 순번 폐기, 독자 URL을 랜덤 공개 ID로)을 구현한 것. 독자 콘텐츠 API(`GET /episodes/{id}/content`)는 이미 UUID 기반이라 이 리팩터는 **읽기 엔드포인트를 바꾸지 않는다** - 회차 번호가 실제로 쓰이던 자리는 ①URL 조회키 ②"N화" 표기 ③이전/다음 네비 셋뿐이었다.

단, 코드 리뷰에서 번호가 **네 번째 역할**을 조용히 맡고 있었다는 게 드러났다: **정렬 기준**과 **회차 식별용 이름**이다. 그래서 `sort_order` 컬럼(작가 지정 표시 순서)과 제목 필수화가 같은 PR에 붙었다 - 2·3절.

---

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `backend/src/models/work.py` | `Episode.episode_no` 제거 → `Episode.public_id`(Integer, UNIQUE) + `Episode.sort_order`(Integer, **UNIQUE 없음**) 추가 |
| `backend/migrations/versions/20260728_1717_episodes_public_id.py` | 백필(파이썬 루프 + `secrets.randbelow` 충돌 재시도) → NOT NULL → UNIQUE → 구 컬럼/제약 drop. downgrade는 `row_number() OVER (PARTITION BY work_id ORDER BY created_at, id)`로 재채번(원값 복원 아님) |
| `backend/migrations/versions/20260730_1120_episodes_sort_order.py` | `sort_order` 추가 + 같은 `row_number()`로 백필(기존 표시 순서 보존) → NOT NULL |
| `backend/src/schemas/work.py`, `backend/src/schemas/catalog.py` | `EpisodeCreate`/`EpisodeUpdate`에서 `episode_no` 제거 + **`title` 기본값 `'무제'` 제거(필수화)**, `AdminEpisodeRead` → `public_id`·`sort_order`, `EpisodeSummary` → `public_id`, `EpisodeReorder` 신설 |
| `backend/src/services/episode_service.py` | `_generate_public_id`(랜덤 발급) 신설, `create_episode`가 IntegrityError 재시도(최대 5회) + `sort_order`를 작품 안 `max+1`로 배정, `update_episode`의 번호 충돌 처리 전체 제거(충돌 소스 자체가 사라짐), `reorder_episodes` 신설, 정렬 2곳(`list_episodes`·`catalog_service`) → `sort_order, created_at, id` |
| `backend/src/routers/admin_episodes.py` | `PUT /admin/works/{work_id}/episodes`(컬렉션 PUT = 재배열) 신설 |
| `frontend/src/pages/works/[id]/[publicId].astro`(구 `[episodeNo].astro`) | 라우트 rename, `public_id` 매칭(정규식 `^[1-9]\d{7}$`), "N화" 표기 제거, 이전/다음 링크·라벨을 `public_id`/제목 기반으로 + 긴 제목 truncate |
| `frontend/src/components/works/EpisodeRow.astro`, `frontend/src/lib/catalog.ts` | 동일 교체 |
| `admin/src/components/episodes/EpisodeList.tsx`, `EpisodeActionsMenu.tsx`, `admin/src/hooks/useEpisodes.ts` | "N화" 열 제거, 삭제 확인창을 soft-delete 일반 경고로 단순화, aria-label을 제목 기반으로, **순서 이동(↑↓) 열 + `useReorderEpisodes` 추가** |
| `admin/src/components/episodes/EpisodeEditor.tsx` | `TITLE_FALLBACK`(`'무제'`) 제거, 이미지 업로드 경로에도 제목 가드 |
| `admin/src/types/api.gen.ts` | `pnpm --filter admin generate:types` 재생성(서버 기동 불요 - `app.openapi()` 직렬화) |
| backend/frontend/admin 테스트 다수 | 아래 4절 |

새 의존성: 없음(`secrets`는 표준 라이브러리).

---

## 2. 구현 결정

### public_id 표현형: zero-pad 없는 INTEGER, 9천만 공간
결정문의 "1억 공간"은 8자리 zero-pad(`00000000`~`99999999`)를 전제하지만, zero-pad를 URL에 그대로 쓰면 `/01234567`과 `/1234567`이 같은 회차를 가리키는 정규화 문제가 생긴다. `INTEGER 10_000_000~99_999_999`(9천만 공간, 선행 0 없음)로 좁혀 그 문제를 구조적으로 없앴다. 1인 작가 규모(회차 수백)에서 충돌 확률은 무시 가능하고, 어차피 UNIQUE가 최종 백스톱이다.

### URL 계층: `/works/{workId}/{publicId}` 유지 (`/e/{publicId}` 단독 라우트 기각)
`public_id`가 전역 유니크라 단독 라우트도 가능했지만, 그러려면 "회차→작품 역조회" 엔드포인트가 새로 필요했다. 현재 구조는 FE가 작품 상세를 한 번 fetch해 회차 조회·이전/다음 네비를 동시에 해결하므로, 계층 유지 = **BE 읽기 API 변경 0건**. 짧은 링크가 필요해지면 나중에 리다이렉트를 얹으면 된다.

### public_id 생성: 앱단 `secrets.randbelow` + IntegrityError 재시도(최대 5회)
DB 함수(`gen_random_uuid()` 스타일) 대신 앱단에서 뽑는 이유는 값의 자릿수·범위가 도메인 규칙(포스타입식 8자리)이라 앱 레이어가 소유하는 게 자연스럽고, UNIQUE 제약이 최종 직렬화 권위를 맡는 패턴이 이미 이 코드베이스의 태그 get-or-create와 같은 계열이기 때문. 라우터(`admin_episodes._work_or_404`)가 `work_id`를 미리 검증하므로 `create_episode` 안의 `IntegrityError`는 항상 `public_id` 충돌만 의미한다 - 그래서 재시도 루프가 단순하다. `rollback()`이 세션의 ORM 인스턴스를 전부 만료시키므로, 재시도마다 **새 `Episode` 인스턴스**를 만든다(만료된 인스턴스 재사용 시 다음 커밋에서 async 밖 lazy load로 `MissingGreenlet`).

### soft delete는 유지 - 단, 근거를 재정의
`episode_no` 시절 soft delete를 유지하는 유일한 이유는 "번호 재사용 방지"였다(독자 URL이 나중에 다른 내용을 가리키면 안 됨). 이 근거가 사라지면서 "그냥 하드 삭제로 바꿔도 되지 않나"라는 질문이 자연스럽게 나왔는데, 검증해 보니 **진짜 이유**가 따로 있었다: M3 `purchases.episode_id`가 `ON DELETE` 절 없이(기본 `RESTRICT`) `episodes(id)`를 참조하도록 이미 설계돼 있다(`DB_SCHEMA.md` §purchases). 즉 구매·환불 기록이 걸린 회차는 M3 구현 이후 하드 삭제 자체가 FK로 막힌다. 결론(유지)은 같았지만, 근거를 검증 없이 "바꾸기 귀찮아서"로 얼버무리지 않고 실제 이유를 찾아 문서화했다.

### "N화" 표기 완전 제거 (FE 목록·뷰어, admin 목록·삭제 확인창·액션 메뉴 aria-label)
결정문 "표기는 불필요(제목만 노출)"에 따라 `public_id`를 독자·관리자 어디에도 숫자로 노출하지 않는다. admin 액션 메뉴의 aria-label은 `${episode.episode_no}화 관리 메뉴` → `${episode.title} 관리 메뉴`로, FE 이전/다음 네비 라벨은 번호 대신 인접 회차 제목으로 바꿨다.

### `sort_order`: 번호가 겸하던 "정렬 기준"을 별도 컬럼으로 (UNIQUE 없음)
`episode_no`는 식별자이면서 동시에 정렬 키였다. `public_id`를 랜덤으로 만들자 정렬 기준이 `created_at`밖에 안 남았는데, 그러면 **프롤로그를 나중에 끼워넣거나 잘못 올린 순서를 되돌릴 방법이 없다**(초안 단계에선 안 보였고 리뷰에서 드러났다). 그래서 작가 지정 표시 순서를 별도 컬럼으로 뒀다.

핵심은 **UNIQUE를 걸지 않은 것**이다. `episode_no`가 동시 생성에서 409를 뱉던 원인이 정확히 유일 제약이었는데, 표시 순서는 동점이어도 `(created_at, id)`가 깨주므로 충돌이라는 개념 자체가 성립하지 않는다. 그 대가로 tie-breaker가 장식이 아니라 **순서를 확정하는 필수 요소**가 되고, 테스트도 동점 케이스를 따로 고정한다.

기본값은 작품 안 `max+1`(soft delete된 회차도 max에 포함 - 되살렸을 때 뒤에 생긴 회차에게 자리를 뺏기지 않게).

### 재배열은 컬렉션 PUT + 전량 전송 (`EpisodeUpdate.sort_order` 기각)
`PUT /admin/works/{work_id}/episodes`에 살아있는 회차 **전량**을 원하는 순서로 보내면 서버가 `1..N`을 재배정한다.

- **회차별 `sort_order` 대입을 안 하는 이유**: 클라이언트가 전역 정합성(중복·구멍)을 책임져야 하고, 재배열 한 번이 N개의 PUT으로 쪼개져 중간 상태가 독자에게 노출된다.
- **부분 목록을 안 받는 이유**: "순서"는 전체 집합에 대한 진술이라 부분 적용이 의미를 갖지 않는다. 집합 불일치(다른 탭에서 회차 추가·삭제)를 409로 돌려주는 게 곧 **낙관적 동시성 검사**라 별도 버전 토큰이 필요 없다.
- **경로가 `/reorder`가 아닌 이유**: 바로 위의 `PUT /{episode_id}`가 UUID 경로 파라미터로 `reorder` 세그먼트까지 삼켜서, 라우트 선언 순서에 따라 조용히 422가 나는 함정이 된다.

admin UI는 드래그앤드롭 라이브러리를 새로 들이지 않고 **↑↓ 버튼**으로 했다(의존성 0, 키보드 접근성 기본). 재배열 중에는 전 버튼을 잠근다 - 인플라이트 응답이 캐시를 덮기 전에 또 누르면 화면에 보이는 낡은 순서를 기준으로 계산해 직전 이동을 되돌리는 요청이 나간다.

### 제목 필수: 서버 기본값 `'무제'` 제거
admin에는 이미 "제목 필수" 결정(`ensureTitle`)이 있었지만, **이미지 업로드가 만드는 지연 draft**(`ensureDraft`)만 예외로 서버 기본값 `'무제'`를 그대로 탔다. 번호가 있던 시절엔 그래도 목록에서 "3화"로 구분됐으니 견딜 만한 예외였는데, 번호를 없애면서 목록·액션 메뉴 aria-label·뷰어 네비의 식별자가 **제목 하나로 줄었다** - `'무제'` 행이 둘 이상이면 작가도 독자도 구분할 수 없다. 그래서 서버 기본값을 제거하고(빈 제목은 422), 이미지 업로드 경로에도 같은 가드를 걸었다.

부수 효과 둘: ①`onDiscardDraft`가 `episode.title !== '무제'`로 매직 스트링을 비교하던 오작동(작가가 진짜로 '무제'라고 지으면 편집 재진입 시 빈 칸이 됨)이 사라졌다. ②`MISTAKES.md`에 기록된 codegen 불일치(Pydantic `default="무제"`는 서버에선 생략 가능인데 생성된 TS는 `title: string` 필수가 돼 `mutateAsync({})`가 TS 에러)도 같이 해소됐다.

### `parsePublicId`를 정규식으로 조임
`Number(raw)` + `isSafeInteger`는 `"1e7"`·`"0x989680"`·`" 10000000 "`·`"+10000000"`·`"10000000.0"`을 전부 통과시켜 **한 회차에 URL이 여러 개** 생겼다(중복 콘텐츠). `isSafeInteger`가 `1e21`은 걸러도 `1e7`(=10000000, 유효 범위)은 못 거른다. `public_id`는 표준형이 하나뿐이므로 `^[1-9]\d{7}$`로 좁혔다.

---

## 3. 마이그레이션 (2건)

### `f3a43b32fcfb` (revises `c3f0a1d4b25e`) - public_id

- **upgrade**: `public_id` nullable 추가 → 전체 행을 파이썬 루프로 순회하며 in-memory set으로 충돌 회피한 랜덤값 백필(이 시점엔 아직 UNIQUE가 없어 파이썬 쪽 dedup이 유일한 방어선) → NOT NULL → `UNIQUE(public_id)` → 구 `UNIQUE(work_id, episode_no)`·`episode_no` 컬럼 drop.
- **downgrade**: `episode_no` nullable 추가 → `row_number() OVER (PARTITION BY work_id ORDER BY created_at, id)`로 작품별 1부터 재채번 → NOT NULL → 구 UNIQUE 복원 → `public_id` 컬럼/제약 drop. **원래 `episode_no` 값을 복원하지 않는다**(폐기 시점에 유실됨) - downgrade는 "유효한 스키마 재구성"이 목적이지 이력 복원이 아니다(soft delete로 소진됐던 결번은 재현 안 됨).
- **실측**: dev DB 9행에 대해 `upgrade head → downgrade -1 → upgrade head` 왕복 실행 - upgrade 후 `public_id` 전량 unique(15438990~93491473 범위), downgrade 후 작품별 1부터 정상 재채번 확인. `alembic check` "No new upgrade operations detected".

### `a7c91d05e3b4` (revises `f3a43b32fcfb`) - sort_order

- **upgrade**: `sort_order` nullable 추가 → `row_number() OVER (PARTITION BY work_id ORDER BY created_at, id)`로 백필 → NOT NULL. 백필 순번이 **직전까지의 정렬과 동일**이라 이 마이그레이션 전후로 독자에게 보이는 순서가 바뀌지 않는다. soft delete된 회차도 같이 채번한다(되살릴 일이 생기면 원래 자리로).
- **downgrade**: 컬럼 drop. 작가가 재배열한 이력은 유실되고 정렬이 `created_at`으로 돌아간다(재배열한 적이 없으면 결과 동일).

---

## 4. 테스트 갱신

- **삭제**(전제 소멸): `test_deleted_episode_no_is_burned`, `test_auto_episode_no_counts_deleted`(#85 소진 UX 테스트), `test_update_duplicate_episode_no_409`(수정 시 번호 지정 자체가 불가능해짐), `test_create_episode_duplicate_no_409_before_any_upload`(클라이언트가 더 이상 충돌을 유발할 입력을 못 보냄).
- **신설**: `test_create_episode_retries_on_public_id_collision`·`test_create_episode_public_id_exhausted_409`(`episode_service._generate_public_id`를 monkeypatch해 충돌→성공, 충돌 소진→409를 결정적으로 재현) - 잃은 커버리지(번호 충돌 처리)를 새 메커니즘 기준으로 대체.
- **재작성**: 정렬 테스트(`test_admin_episodes.py`·`test_catalog.py`) - 타임스탬프를 명시적으로 갈라 주입해 결정적으로 만들었다(같은 트랜잭션 안의 `now()`는 상수라 자연 타이밍에 기대면 플레이키해질 여지가 있다).
  - ⚠️ **첫 판(2026-07-29)의 admin 쪽 정렬 테스트는 판별력이 0이었다**: `first`를 먼저 만들고 `first=1/1`, `second=1/2`를 줘서 생성 순서와 기대 순서가 같아졌고, `ORDER BY`를 통째로 지워도 통과했다. 리뷰에서 잡혀 **생성 순서·`created_at` 순서·`sort_order` 순서를 셋 다 다르게** 깔도록 고쳤다(`created_at`은 `sort_order`와 정반대). 같은 파일의 `test_catalog.py` 쪽은 처음부터 역전돼 있어 대비가 뚜렷했다 - 자매 테스트를 그대로 베끼지 않은 게 원인.
- **신설(정렬 계약)**: `sort_order`가 `created_at`을 이긴다는 테스트와, `sort_order` 동점을 `created_at`이 깬다는 테스트를 BE·카탈로그 양쪽에 각각 뒀다. UNIQUE가 없어 동점이 **정상 상태**라 tie-breaker도 계약의 일부다.
- **신설(재배열)**: 순서 재작성, 부분 목록 409, 중복·타 작품 id 409, 삭제 회차 포함 409(제외 시 200). admin 쪽은 "인접 맞바꾼 전량을 컬렉션 PUT으로 보낸다"와 "양 끝 바깥 방향 버튼 비활성".
- **신설(제목 필수)**: BE `test_create_episode_requires_title`(생략·빈 문자열 모두 422), admin "제목 없이 이미지를 올리려 하면 업로드하지 않고 안내한다".
- **`tests/factories.py`**: `make_episode`에 `_next_public_id()`(10_000_000부터)·`_next_sort_order()` 카운터 추가. `sort_order`는 `or` 대신 sentinel 비교로 받는다 - `sort_order=0`을 명시로 넘기는 테스트가 조용히 덮이면 정렬 테스트가 의도와 다른 값을 검증하게 된다.
- admin 3개 테스트 파일(`EpisodeList.test.tsx`·`useEpisodes.test.tsx`·`EpisodeEditor.test.tsx`)의 fixture를 `public_id`+`sort_order`로 교체, `EpisodeList.test.tsx`의 `openMenu` 헬퍼를 번호 기반에서 제목 기반 셀렉터로 전환.
  - `EpisodeEditor.test.tsx` fixture의 `title: '무제'`도 실제 제목으로 바꿨다. 이걸 놓쳤을 때 **엉뚱한 테스트가 깨졌는데**, 원인은 제목 가드에 걸린 앞선 테스트들이 `mockResolvedValueOnce` 큐를 소비하지 못해 뒤 테스트로 응답이 밀린 것이었다(`vi.clearAllMocks()`는 호출 기록만 지우고 once 큐는 비우지 않는다). 단독 실행하면 통과해서 더 헷갈린다.

---

## 5. 검증

- `uv run alembic upgrade head` → `downgrade -1` → `upgrade head` 왕복 정상, `uv run alembic check` 클린(`No new upgrade operations detected`)
- 백필 실측(dev DB 9행): 작품별로 `sort_order`가 1부터 연속, 각 작품 안에서 `created_at` 순서와 일치(`PARTITION BY work_id` 동작 확인). 왕복 후 값이 **완전히 동일**하게 복구돼 백필이 결정적임을 확인
- `uv run ruff check src/` 클린, `uv run ruff format --check src/ tests/` 클린(70 files), `uv run pytest` **435 passed**
- `pnpm --filter frontend astro check`(0 errors) + `build` + `test`(28 passed)
- `pnpm --filter admin lint` 클린 + `build` + `test`(81 passed)
- `grep -rn "episode_no" backend/src frontend/src admin/src` → 0건(생성물 `api.gen.ts` 포함)

### 이 단계에서 잡힌 버그 (2026-08-03)

`pytest`를 처음 돌렸을 때 `test_reorder_episodes_rewrites_sort_order` 1건만 실패했다 - 응답의 **행 순서는 `[c,a,b]`로 맞는데 `sort_order` 값이 `[3,1,2]`(옛값)**. 원인은 `synchronize_session=False` bulk UPDATE + 세션의 `expire_on_commit=False` 조합이라 커밋 후 재조회해도 identity map이 로드된 옛 속성을 유지한 것(상세는 MISTAKES "SQLAlchemy / AsyncSession"). 커밋 직후 `session.expire()`로 만료시켜 뒤따르는 `list_episodes` SELECT가 값을 덮어쓰게 고쳤다.

어드민 UI가 **배열 순서로 렌더링**하는 탓에 화면상으로는 완전히 정상으로 보이는 버그였다 - 브라우저 확인으로는 절대 못 잡고 API 응답을 값 단위로 단언하는 테스트만이 잡는다.

### 반영하지 않은 리뷰 지적 (근거)

| 지적 | 판단 | 근거 |
|------|------|------|
| 마이그레이션 백필이 락을 잡는 동안 쓰기가 막힌다 | 기각 | 1인 작가 사이트고 대상이 실측 9행이다. Postgres 11+는 nullable 컬럼 추가에 테이블 재작성이 없어 `ADD COLUMN`은 즉시 끝나고, 남는 건 9행 UPDATE다. 배포 창에 쓰기를 시도할 주체가 작가 한 명뿐이라 실질 영향이 없다. **회차가 수천 단위가 되면** 백필을 배치로 쪼갤 것 |
| `(work_id, sort_order, created_at, id)` 커버링 인덱스가 없어 매번 정렬한다 | 기각 | 오히려 **역효과**다. 재배열이 `sort_order`를 전량 UPDATE하므로 그 컬럼에 인덱스를 달면 재배열 때마다 인덱스도 전량 갱신된다. 읽기 쪽 이득은 `idx_episodes_work_id`로 좁힌 뒤 작품당 수십 행을 정렬하는 비용이라 애초에 미미하다. 쓰기를 확실히 비싸게 만들어 읽기를 미미하게 개선하는 교환이라 지금 규모에선 손해 |
| `public_id` 충돌 재시도가 조용하다 | **반영** | `logger.warning("episode_public_id_collision", ...)` 추가. 충돌 확률은 회차 수의 제곱에 비례해 커지므로(생일 문제) 이 로그 빈도가 자릿수를 늘릴 시점을 알려주는 유일한 신호다. `rollback()` 뒤 `episode.public_id`를 읽으면 만료 인스턴스 lazy load(MissingGreenlet)라 지역 변수로 먼저 잡아 로그에 넘긴다 |
| 뷰어 탭 제목에 작품명이 없다 | **반영** | 회차 번호가 사라져 회차 제목만으론 여러 작품 탭이 구분되지 않는다 → `회차 · 작품 · 도군`. 함께 `loadError`(5xx)를 "찾을 수 없어요"에서 분리 - 본문 문구는 이미 구분하는데 제목만 어긋나 있었다 |
