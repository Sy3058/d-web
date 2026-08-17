# 회차 목록 + 무료 구간 콘텐츠 API (M2 그룹 B)

| 항목 | 내용 |
|------|------|
| 모듈 | Backend / Viewer |
| 관련 마일스톤 | [M2](../../../milestones/M2_foundation.md) 그룹 B - B1, B2 |
| 작성 시점 | M2 B (2026-07-21) |
| 상태 | Opus 계획 → 구현(보안 그룹) → 인라인 리뷰 → `/code-review` xhigh 2회(1차 10건 중 7건, 2차 8건 중 4건 반영) → **실서버 스모크 통과**(presigned 실물 200 image/webp, §4). `pytest` 391 passed(신규 41), ruff·`alembic check` 클린. **마이그레이션 없음** |
| 관련 문서 | M2_foundation.md 그룹 B·결정 1, IMPLEMENTATION_EPISODE_CONTENT_MODEL.md(#76), IMPLEMENTATION_VIEWER_PROGRESS.md(C1), study `derived-column-not-security-gate` |

독자에게 회차 본문을 내보내는 유일한 경로. 유료 경계(paywall) 이전만 잘라서, 이미지 키를 presigned URL로 치환해 반환한다. 결제는 없다(M3) - M2는 전원이 미구매라 구매 검사 없이 절단만 한다.

---

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `backend/src/lib/content_doc.py` | `split_at_paywall()` 추가(절단 - 순수 함수) |
| `backend/src/services/episode_read_service.py` | 신규. 공개 회차 조회 + presign 치환 + 조립 |
| `backend/src/schemas/viewer.py` | `EpisodeContent` 추가 |
| `backend/src/routers/episodes.py` | 신규. `GET /episodes/{id}/content`(공개) |
| `backend/src/services/catalog_service.py` | `list_public_episodes()` 추가(B1) |
| `backend/src/routers/works.py` | `GET /works/{id}/episodes` 추가(B1) |
| `backend/src/main.py` | `episodes.router` 등록 |
| `backend/tests/test_episode_content.py` | 신규 17케이스 |
| `backend/tests/test_content_doc.py` | `split_at_paywall` 13케이스 추가 |
| `backend/tests/test_catalog.py` | B1 7케이스 추가 |

| 엔드포인트 | 인증 | 역할 |
|-----------|------|------|
| `GET /works/{id}/episodes` | 불요 | 공개 회차 목록(`EpisodeSummary[]`). 작품 비노출이면 404 |
| `GET /episodes/{id}/content` | 불요 | 무료 구간 본문 + `has_paid_part`. 비노출이면 404. 성공·404 모두 `no-store` |

---

## 2. 주요 결정

### 절단은 `lib/content_doc`, 치환·조회는 `episode_read_service`

절단은 paywall 의미론이라 `derive_is_free`와 같은 모듈에 뒀다. 두 함수가 경계를 다르게 읽으면 "무료 배지인데 잠금이 뜨는" 회차가 생기므로, 같은 파일에 두고 **일치를 감시하는 파라미터라이즈 테스트**(`test_split_has_paid_part_agrees_with_derive_is_free`, 문서 8종)를 걸었다.

### `episodes.is_free`로 분기하지 않는다 (보안 결정)

계획 단계에서 "is_free=true면 절단을 건너뛰고 전문 반환"이 자연스러워 보였으나 채택하지 않았다. `is_free`는 `content`에서 파생된 비정규화 컬럼(목록 SQL·배지용)이고 진실은 문서다. 절단은 유료 본문의 유일한 방어선인데 판단 근거를 캐시에 위임하면, 컬럼이 어긋나는 순간(쓰기 경로 버그·과거 데이터·수동 UPDATE) 유료 글·이미지가 통째로 나가고 그 키에 서명까지 발급된다. 분기를 없애면 같은 불일치의 피해가 **목록 배지 오표시**로 줄어든다. 개념: study `derived-column-not-security-gate`.

부수 효과로 `is_free=true`인데 paywall이 있는 문서(경계 뒤가 빈 노드)에서도 경계 노드가 응답에 실리지 않는다.

### 순서 고정: 절단 → presign

`_substitute_image_urls`는 넘겨받은 문서 **전체**를 훑으므로, 치환이 먼저면 유료 구간 키에도 서명이 발급된다. 그 뒤에 잘라내면 **최종 응답은 멀쩡해 보여서 응답 검사로는 잡히지 않는다.** `presign_get_urls` mock의 호출 인자를 직접 보는 `test_paid_section_keys_are_never_signed`가 유일한 탐지 수단이라, 코드 주석에 그 테스트 이름을 명시했다.

### image attrs는 교체(치환)이지 추가가 아니다 - 응답 스키마가 저장 스키마와 갈라진다

저장은 `attrs={"key": R2키}`, 응답은 `attrs={"src": presigned URL}`. key를 남긴 채 src를 더하면 원본 키가 응답에 실린다. 저장 스키마는 "무엇을 받아들일까"(입력 검증·XSS 방어선), 응답 스키마는 "무엇을 보여줄까"의 계약이라 원래 다르다.

⚠️ **#76의 "서버·에디터·뷰어 3곳 동일 스키마" 규칙에서 image attrs 하나만 의도적 예외다.** 노드·마크 화이트리스트는 동일하다. **그룹 F 뷰어 렌더러는 `src` 기준으로 구현할 것.**

### 저장 검증과 공개 투영을 이중화한다 (#115, 2026-08-17)

M2 전체 보안 검증에서 무료 노드의 임의 최상위 필드에 유료 R2 키를 넣으면 공개 응답에 남는 경로가 발견됐다. 저장 검증은 attrs 내부 키만 제한하고 doc·node·mark 객체 자체의 키 집합은 제한하지 않았으며, 읽기 서비스가 `dict(node)`로 원본 노드를 복사한 것이 결합 원인이었다. 정상 API 쓰기만 가정하면 과거 데이터, 마이그레이션, 수동 DB 편집으로 생긴 오염값을 공개 경계에서 막지 못한다.

방어는 두 층으로 분리했다.

1. `content_doc.validate_content`는 doc·node 타입·mark 타입별 최상위 허용 필드를 검사한다. `content`, `attrs`, `marks`는 truthy 여부가 아니라 필드 존재 기준으로 검사해 `content=[]`, `attrs={}`, `marks=None` 같은 falsy 우회도 닫는다.
2. `episode_read_service`는 저장 dict를 복사하지 않는다. 절단된 무료 문서를 허용 필드만 담은 안전한 내부 트리로 먼저 투영하고, 그 트리의 image key만 수집해 presign한 뒤, 공개 응답을 `attrs={"src": ...}` 형태로 다시 새 객체로 조립한다.

처리 순서는 **절단 → 안전한 내부 투영 → key 수집 → presign → 공개 투영**이다. 따라서 leaf node의 불법 `content`나 알 수 없는 노드 아래에 숨긴 image key는 presign 호출 인자에도 들어가지 않는다. 허용 객체의 임의 필드는 버리고 정상 의미는 유지하며, 알 수 없는 노드·잘못된 mark·key 없는 image는 최소 단위로 폐기한다. 완전히 잘못된 문서 루트는 500 대신 빈 문서와 `has_paid_part=true`로 닫는다. 읽기 투영에도 저장 검증과 같은 깊이·노드·텍스트 상한을 적용하고, 유의미 콘텐츠 판정은 반복형 순회로 바꿔 깊게 오염된 JSON이 `RecursionError`를 만들지 않게 했다. 문자열이 아닌 node·mark type도 membership 검사 전에 폐기해 `TypeError` 500을 막는다.

오염값은 로그에 복사하지 않는다. 구조화 경고에는 `episode_id`와 폐기·정리 개수만 기록한다. 기존 `episode_content_image_dropped` 계약은 유지하고, 그 밖의 오염 정리는 `episode_content_invalid_part_sanitized`로 관측한다.

회귀 테스트는 응답 문자열뿐 아니라 `presign_get_urls` 호출 인자까지 검사한다. 최종 JSON이 정상이어도 유료 키에 이미 서명을 발급했다면 보안 실패이기 때문이다.

### 조회는 `public_work_filters()` 강제

작품을 숨기거나(`is_published=false`) soft delete해도 **회차 행은 남는다.** `Episode.is_published`만 검사하면 회차 ID 직접 접근으로 내려간 작품이 계속 읽힌다. admin `episode_service.get_episode`가 `deleted_at`만 보는 건 관리자가 비공개 작품도 봐야 해서고, 그 패턴을 독자 경로로 복사하면 안 된다(C1과 동일한 함정).

### 치환은 재조립, 제자리 수정 금지

`episode.content`는 세션이 들고 있는 ORM 인스턴스의 JSONB이고 `split_at_paywall`은 노드 dict를 슬라이스로 공유한다. 제자리에서 고치면 이후 flush 시 **만료되는 presigned URL이 원고 키 자리에 영구 저장**될 수 있다. 현재 읽기 경로엔 commit이 없지만 "이 경로는 쓰기를 안 한다"에 기대지 않는다.

### B1은 `get_work_detail()` 재사용 (2026-07-20 사용자 확정)

`GET /works/{id}`(A2)가 이미 같은 `EpisodeSummary` 배열을 embed하고 있어 B1은 정보상 중복이다. 삭제도 검토했으나 존치하되 **같은 서비스 함수를 호출하는 4줄**로 구현했다 - 별도 쿼리를 두면 공개 필터를 타는 경로가 둘로 갈라진다. 작품 메타(tags·synopsis)를 같이 읽는 낭비가 있으나 단일 작품 조회라 무시할 수준이고, `test_episodes_match_detail_payload`가 두 응답의 동일성을 감시한다.

---

## 3. 리뷰

### Minor 1 - 404에 `Cache-Control` 부재 (수정 완료)

`HTTPException`이 발생하면 라우터 함수의 `Response` 객체가 아니라 예외 핸들러가 만든 새 응답이 나가므로, 성공 경로에 붙인 `no-store`가 404에 적용되지 않았다(실측: 404 헤더에 `cache-control` 없음).

404는 명세상 **기본 캐시 가능 상태 코드**(RFC 9111)라 명시적 헤더가 없으면 heuristic 캐싱 대상이다. 실패 시나리오: 예약 공개된 회차 링크를 독자가 공개 전에 열어 404를 받고 브라우저가 캐시 → 스케줄러가 공개해도 캐시된 404를 계속 본다. `HTTPException(headers={"Cache-Control": "no-store"})`로 수정하고 `test_404_is_not_cached`를 추가했다.

### `/code-review` xhigh 2차 - 10건 중 7건 반영

인라인 리뷰가 놓친 것들을 10앵글 스윕이 잡았다. 가장 뼈아픈 건 **자기모순**이다: episodes.py의 404 캐시 결함을 고쳐놓고 **같은 diff에서 새로 추가한 `GET /works/{id}/episodes`에는 적용하지 않았다.** "기존 공유 코드라 범위 밖"이라 판단했으나 B1은 이번에 만든 신규 공개 엔드포인트라 그 논리가 성립하지 않는다. `works.py`의 `_NOT_FOUND`에 `no-store`를 실어 A1/A2/B1 세 엔드포인트에 함께 적용하고 회귀 테스트를 추가했다.

| 반영 | 내용 |
|------|------|
| ✅ | `works.py` 404에 `no-store`(위 자기모순) |
| ✅ | `backend/CLAUDE.md` "Signed URL - 구매 확인 후에만 생성"이 새 코드와 정면 충돌 → M2 결정 1(무료 구간 = 서버 절단 후 발급, 인증 불요) 반영해 갱신 |
| ✅ | 문서 빌더(`_doc`/`_para`/`_img`/`_PAYWALL`)가 두 테스트 파일에 복붙 → `tests/factories.py`로 통합(이 모듈이 만들어진 이유와 같은 사고를 반복했다) |
| ✅ | key attr 잔존 검사가 특정 인덱스 하나뿐 → 문서를 재귀로 훑어 **모든** image 노드의 attrs가 `{"src"}`임을 단언 |
| ✅ | image 노드에 key가 없으면 `KeyError`로 500 → **노드째 폐기**(공개 읽기 경로가 데이터 상태로 죽지 않게. 원본 키 잔존·빈 src는 배제) |
| ✅ | `_fetch_public_episode`가 안 쓰는 `image_keys` JSONB까지 로딩 → `defer()`(catalog_service의 `defer(Work.episode_count)`와 같은 처리) |
| ✅ | `presign_spy == [[]]`가 "빈 키여도 호출한다"는 구현 세부를 고정 → "서명된 키가 하나도 없음"으로 의도 중심 단언 |
| 미반영 | B1의 `get_work_detail` 재사용 낭비(문서화된 트레이드오프), `_no_store` 헬퍼 중복(각 1줄), `doc.get("content") or []` 2회 평가 |

### `/code-review` xhigh 3차 - 8건 중 4건 반영

**1차에서 지적받은 것과 같은 실수가 반복됐다.** 1차 최상위 발견이 "episodes.py는 고치고 works.py는 빠뜨림"이었는데, 그 수정 과정에서 `backend/CLAUDE.md`만 고치고 **루트 `CLAUDE.md`의 같은 규칙("미결제 유저에게 이미지 URL 내려주기 금지", 매 세션 자동 로드되는 "절대 하면 안 되는 것들" 섹션)을 또 빠뜨렸다.** 같은 종류의 수정을 할 때 형제 위치를 훑는 절차가 없다는 뜻이라, MISTAKES에 남길 후보다.

또한 1차 수정 두 개가 각각 새 문제를 만들었다.

| 반영 | 내용 |
|------|------|
| ✅ | 루트 `CLAUDE.md` "미결제 유저에게 이미지 URL 내려주기 금지" → "**유료 구간** 이미지"로 한정(위 반복 실수) |
| ✅ | 1차 수정(KeyError → 노드 폐기)이 **관측성을 대가로 지불**했다: 이미지가 조용히 사라져도 서버가 알 수 없었다 → 폐기 개수를 누산해 `episode_id`와 함께 structlog 경고. 정상 문서에선 안 찍히는 것까지 테스트 |
| ✅ | 1차 수정(`defer(Episode.image_keys)`)이 **MissingGreenlet 잠재 위험**을 들였다(지연 컬럼을 나중에 누가 읽으면 async 밖 lazy load) → `select(Episode.id, Episode.content)`로 필요한 두 컬럼만 조회. 지연 속성 자체가 없어진다 |
| ✅ | `test_404_is_not_cached` docstring이 "목록·상세·회차목록 셋"이라고 적었으나 **목록(`GET /works`)엔 404 경로가 없다**(빈 배열 200) - 사실 정정 |
| 미반영 | 문서 빌더의 `factories.py` 배치(순수 단위 테스트가 DB 계층에 결합), `PAYWALL` 공유 가변 dict, defer 회귀 테스트 부재, 폐기 노드 자식의 헛된 서명 |

### 계획 DoD 문구 정정 - "응답에 원본 R2 키 부재"는 성립 불가

M2 계획 B2의 DoD (c)는 "응답 JSON 어디에도 원본 R2 키 문자열 부재"였으나, **실제 presigned URL은 구조상 키를 경로에 포함한다**(`{endpoint}/{bucket}/{key}?X-Amz-...`). 이미지를 내보내는 한 문자 그대로는 만족할 수 없다.

지켜야 할 성질로 정정했다: **(a) 유료 구간 키는 응답에 전무, (b) 무료 구간 키도 맨 키로는 안 나감(image attrs == `{"src"}`).** 무료 구간 키가 자기 서명 URL 경로에 나타나는 건 무해하다 - 키만으로는 서명 없이 아무것도 못 받고, 페이지 파일명이 `uuid4().hex`라 키 하나로 다른 페이지를 유추할 수도 없다(`r2_service.episode_page_key`).

테스트의 가짜 presign URL에 **일부러 키를 넣어둔 덕에** 발견됐다. 키를 뺀 fake를 썼으면 이 불일치가 영영 드러나지 않았다.

---

## 4. 실서버 스모크 (2026-07-21)

pytest는 presign을 전량 mock하므로, presigned 발급→실 이미지 수신을 실서버 + 실 R2로 별도 검증했다. 무료 이미지 1장 + 유료 이미지 1장(경계 앞/뒤)인 공개 회차로 `GET /episodes/{id}/content` 실측:

| 검증 | 결과 |
|------|------|
| 응답 코드·헤더 | 200, `Cache-Control: no-store` |
| 절단 | 무료 이미지 노드 1개만, 유료 이미지·paragraph·paywall 전부 잘림, `has_paid_part=true` |
| image attrs | `{"src"}`만 (원본 `key` 미노출) |
| 유료 키 유출 | 경계 뒤 키가 응답에 부재 |
| **presigned 실물** | 응답 `src`를 실제 GET → **200 `image/webp` 53,558 bytes, 실 WebP 800×10682** |

서명 경로 자체의 정상성도 확인됐다: 없는 키를 서명해 GET하면 R2가 **403(SignatureDoesNotMatch)이 아니라 404(NoSuchKey)**를 준다 - 서명은 통과했고 객체만 없다는 뜻.

⚠️ **dev `dweb` 버킷 드리프트 발견**: 옛 시드 회차(ep4/ep5 등)의 `image_keys`가 가리키는 원고가 R2에 없다(버킷에 원고 0개 - D1 표지 이관 때 정리된 것으로 추정). 새로 업로드한 회차만 실물이 있다. **F 개발 시 이미지 테스트는 새 회차로** 할 것(옛 회차는 404). admin draft 재진입 미리보기·D2 썸네일 재생성도 옛 회차에선 깨질 수 있다(미검증 추정 - 같은 presign/download 경로).

**F1에 남는 것**: 회차당 총 전송 바이트·장수 실측(다수 이미지, M2 결정 6 재검토 조건 - 5MB 크게 초과 시 서명 쿠키를 M3로).

---

## 5. 이연 / 후속

| 항목 | 이동처 | 근거 |
|------|--------|------|
| 유료 구간 반환 + 구매 검증 | M3 | B2에 구매 통과 시 전문 반환을 얹는다 |
| `routers/works.py`·`progress.py`의 404 캐시 헤더 | 후속 | 같은 패턴이나 works는 A1/A2 공유 기존 코드, progress는 인증 응답이라 공유 캐시 대상 아님. 이번 diff 범위 밖 |
| presigned 만료 재발급 고도화 | 후속 | 뷰어가 즉시 전량 요청해 정상 경로에선 안 탄다(결정 6) |
| B1 존치 재검토 | 필요 시 | A2와 정보상 중복. 그룹 E/F 구현 후 실제 소비자가 없으면 삭제 검토 |
