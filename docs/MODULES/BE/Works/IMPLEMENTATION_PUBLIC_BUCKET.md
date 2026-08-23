# 표지/썸네일 공개 버킷 (M2 그룹 D - D1+D2)

| 항목 | 내용 |
|------|------|
| 모듈 | Backend / Works |
| 관련 마일스톤 | [M2](../../../milestones/M2_foundation.md) 그룹 D - D1·D2 |
| 작성 시점 | M2 D1+D2 (2026-07-20) |
| 상태 | 구현 + Opus 계획 검증 → Sonnet 구현 → Opus 코드 리뷰(Critical/Major 0, Minor 3건 반영) + 실서버 스모크(표지·썸네일 공개 URL GET 200). `pytest` 350 passed(신규 14), ruff·`alembic check` 클린. **DB 마이그레이션 0**(`episodes.thumbnail` 컬럼은 기존) |
| 관련 문서 | [IMPLEMENTATION_PUBLIC_CATALOG_API.md](./IMPLEMENTATION_PUBLIC_CATALOG_API.md)(그룹 A - 이 문서가 남긴 "D1/D2 이후 조립" 배선을 완료), [IMPLEMENTATION_R2_IMAGE_SERVICES.md](../Upload/IMPLEMENTATION_R2_IMAGE_SERVICES.md)(M1.5 - `r2_service`/`image_service` 원조 구현, 이번 작업이 확장), M2_foundation.md 결정 2, MISTAKES.md "R2 / boto3" |

작품 표지와 회차 썸네일을 원고 버킷(`dweb`, 비공개)과 분리된 공개 버킷(`dweb-cover`)으로 서빙한다. D1은 표지 업로드 전환 + 공개 URL 조립 단일화, D2는 회차 썸네일의 공개 축소본을 서버가 파생시키는 side-effect다.

---

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `backend/src/config.py` | `r2_public_bucket`(기본 `dweb-cover`) 신설 |
| `backend/src/services/r2_service.py` | `public_url(key, *, version)` 신설(URL 조립 단일 출처, 캐시 버스터 `?v=`) / `upload_bytes`에 `bucket=` 키워드 파라미터 추가(생략 시 원고 버킷 유지) / `download_bytes`·`delete_object` 신설(D2가 원고를 다시 읽고 공개 축소본을 정리하는 유일한 경로) / `episode_thumb_key()` 헬퍼 |
| `backend/src/services/image_service.py` | `convert_to_webp(..., target_width=)` 파라미터화(`THUMB_WIDTH=400` 상수), `_maybe_draft_jpeg`도 연동 |
| `backend/src/services/work_service.py` | `set_cover_image`가 공개 버킷(`r2_public_bucket`)으로 업로드하도록 전환 |
| `backend/src/services/episode_service.py` | `update_episode`에 썸네일 side-effect 훅(변경 감지 → 생성은 검증 후·커밋 전, 삭제는 두 커밋 분기 각각의 성공 후) |
| `backend/src/services/catalog_service.py` | 자체 `_public_url` 삭제 → `r2_service.public_url` 호출로 교체, `_to_episode_summary`에 썸네일→표지 fallback 체인 |
| `backend/src/schemas/work.py` | `WorkRead.cover_url` / `AdminEpisodeRead.thumbnail_url`을 `computed_field`로 추가(스키마가 서비스를 import하는 첫 사례) |
| `backend/src/schemas/catalog.py` | "D2 이전엔 항상 None" docstring을 실제 동작으로 정정 |
| `backend/.env.example` | `R2_PUBLIC_BUCKET` 문서화, `PUBLIC_ASSET_BASE_URL`의 dev(r2.dev)/운영(커스텀 도메인) 구분 명시 |
| `admin/src/components/works/WorkList.tsx` | `cover_url` 있으면 `<img>`, 없으면 기존 placeholder |
| `backend/tests/test_r2_service.py` | 신규 7: 버킷 파라미터화 2 + `public_url` None/캐시버스터/트레일링슬래시 5 |
| `backend/tests/test_admin_episodes.py` | 신규 4: 표지·썸네일 버킷 라우팅, 미변경 시 R2 호출 0, 해제 시 delete_object 버킷 인자 |
| `backend/tests/test_catalog.py` | 신규 3: 썸네일 URL 조립(원고 키 비노출 재확인) + 표지 fallback + 둘 다 없을 때 None |

---

## 2. 주요 결정

### URL 조립은 `r2_service.public_url()` 하나로 단일화
그룹 A(#81)가 `catalog_service._public_url`로 먼저 구현해뒀던 걸 이관했다. 표지(`WorkListItem`/`WorkDetail`)와 썸네일(`EpisodeSummary`), 그리고 admin의 `WorkRead.cover_url`/`AdminEpisodeRead.thumbnail_url`까지 전부 이 한 함수를 거친다 - 조립 지점이 흩어지면 캐시 버스터 같은 규칙을 한 곳에서만 빼먹어도 조용히 깨진다.

### 캐시 버스터(`?v={updated_at}`)가 필요한 이유
표지·썸네일 키는 고정(`works/{id}/cover.webp`, `.../thumb.webp`)이고 재업로드는 덮어쓰기다. presigned 시절엔 URL 자체가 매번 달라 브라우저/CDN 캐시가 자동으로 갱신됐지만, 공개 URL은 고정이라 그 이점이 없어진다 - `version=` 인자로 리소스가 바뀔 때마다(`updated_at`) URL도 바뀌게 한다.

### R2 side-effect 순서: 조건부 DB write 뒤 생성, 커밋 뒤 삭제
`episode_service.update_episode`의 썸네일 훅. 원본 **다운로드·변환**은 검증 뒤 DB write 전에 준비하지만, 공개 고정 키 **업로드**는 content·thumbnail 스냅샷을 포함한 조건부 UPDATE가 행을 잡은 뒤와 commit 사이에만 실행한다(2026-08-21 보강). stale 요청은 rowcount 0에서 rollback·409로 끝나므로 공개 객체를 덮지 않고, upload 실패도 commit 전 rollback돼 DB 대표 이미지가 바뀌지 않는다. **삭제**는 DB commit 성공 후에만 실행한다 - 먼저 지웠다가 commit이 실패하면 DB가 존재하지 않는 객체를 계속 가리키게 된다.

### 썸네일 fallback 체인: 회차 썸네일 → 작품 표지 → null
회차에 썸네일이 없다고 원고 첫 페이지로 대체하면, 유료·미공개 페이지가 공개 URL로 새는 경로가 된다(M2 결정 2). 대신 작품 표지로 대체하고, 표지도 없으면 `null`(FE placeholder). `public_url()`이 키 없음/base 미설정 둘 다 `None`을 반환하므로 이 체인은 호출부에서 별도 분기 없이 자연스럽게 성립한다.

### 변경 감지로 미변경 요청은 R2 왕복 0
`changes.get("thumbnail", episode.thumbnail) != episode.thumbnail`로 판정한다. 클라이언트가 동일한 썸네일 키를 재전송해도(예: 다른 필드만 바꾸는 PUT에 폼이 기존 값을 그대로 동봉) 다운로드·변환·업로드가 전혀 일어나지 않는다.

### dev는 r2.dev, 운영은 커스텀 도메인
`dweb-cover` 커스텀 도메인 DNS가 아직 미연결이라(외부 블로커), Cloudflare의 "Public Development URL"(r2.dev)을 dev 한정으로 켜서 `PUBLIC_ASSET_BASE_URL`에 넣었다. 공식 문서상 r2.dev는 rate-limited & non-production 명시라 운영 전환 시 커스텀 도메인으로 교체가 필수 - env 한 줄만 바꾸면 되고 코드 변경은 없다. `dweb`(원고 버킷)엔 이 공개 개발 URL을 절대 켜면 안 된다(버킷 단위 공개라 원고 전체가 새어나감) - 실측으로 `dweb`은 꺼져 있고 `dweb-cover`만 켜져 있음을 확인했다.

---

## 3. 리뷰

**계획 검증**(Fable): D1/D2 계획을 코드와 대조해 전제 6개 검증. `EpisodeCreate`에 thumbnail이 의도적으로 없음(생성 시점 임의 키 주입 방지) → D2 훅은 update 경로만으로 충분함을 확인, 에피소드 삭제 라우트 자체가 없어 삭제 시 정리 경로 불필요함을 확인.

**코드 리뷰**(Opus, general-purpose + `model:"opus"`): Critical/Major **0건**, 머지 가능 판정.

- **Minor 3건 - 테스트 커버리지 공백, 전부 반영**: 썸네일 업로드의 공개 버킷 라우팅 미단언(기존 `uploaded_keys` 픽스처가 `bucket` 인자를 무시), "미변경 시 R2 호출 0" 미단언, 삭제 시 버킷 인자 미단언. `bucket`/`key`를 함께 기록하는 전용 픽스처(`r2_calls`)를 추가해 3개 테스트로 메꿨다.
- **FYI 2건 - 코드 변경 없이 수용**:
  1. 공개 고정 키 upload 성공 뒤 DB commit 자체가 실패하는 극희소 경로와 commit 뒤 삭제 실패는 완전한 원자성을 보장하지 않는다. 해결에는 versioned key와 outbox가 필요해 현재 범위를 넘으므로, 재시도가 같은 키를 덮어쓰는 자가 치유와 운영 관측으로 수용한다.
  2. D2 배포 이전에 이미 `thumbnail`이 세팅된 회차가 있다면, 재저장 전까지 `thumbnail_url`이 404(FE가 placeholder로 완화). 프로덕션 전 dev 데이터뿐이라 무해 - 배포 전 재저장으로 정리(이관 스크립트 없음, D1의 기존 표지 정리와 동일 패턴).

**커밋 전 LEARN 퀴즈**(fill-in-comments): computed_field를 스키마에 둔 이유, `public_url`이 base 미설정 시 None을 반환하는 이유, 썸네일 업로드를 커밋 전에 하는 이유 3문항 - 전부 정답 확인 후 주석 제거.

---

## 4. main 동기화 사고 (기록)

D1/D2 구현 도중 그룹 C(뷰어 진행도, #90)가 별도 워크트리에서 먼저 머지됐다. 브랜치가 옛 `main`에서 갈라진 채 커밋 0개로 남아있어 `git reset --mixed origin/main` + 파일별 복원으로 base를 옮겼는데, 이 과정에서 `catalog_service.py`(그룹 C가 `public_episode_exists()` 추가)와 `test_catalog.py`(그룹 C가 `tests/factories.py` 공용 팩토리로 리팩터)를 **둘 다 건드린 공유 파일**로 처음엔 놓칠 뻔했다 - "겹치는 파일 없음" 판단을 diff stat만 보고 내렸다가, 실제 88e1f2e↔444c24a 커밋 간 diff로 재확인해서 잡았다. `pytest` 전체 재실행(그룹 C 테스트 포함 350 passed)으로 최종 검증.

## 5. 이연 / 후속

| 항목 | 이동처 |
|------|--------|
| `dweb-cover` 커스텀 도메인 DNS 연결 후 `PUBLIC_ASSET_BASE_URL`을 r2.dev → 커스텀 도메인으로 교체 | 외부 작업(도메인 등록) 완료 시 |
| D2 배포 전 존재하던 회차의 썸네일 재저장(공개 축소본 백필) | 배포 체크리스트 |
| 그룹 B(회차 콘텐츠 API) 완성 후 원고 첫 페이지 fallback 재검토 여부 | B1/B2 착수 시(현재는 금지 유지) |
