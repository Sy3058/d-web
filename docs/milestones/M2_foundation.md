# M2. 콘텐츠 (무료 구간) - 세부

| 항목 | 내용 |
|------|------|
| 문서 버전 | v0.5 (2026-07-18, M1.5 완전 종료·그룹 D 계획 구체화: 에디터 #78·예약 UI #79 머지 반영, 썸네일 = 원고 키 방식 확정(D2 = BE-only 공개 축소본 파생), D1/D2에 #81 후속 조사 반영(공개 URL 조립 단일화·캐시 버스터·공개 카탈로그 배선·download_bytes), R2 토큰 스코프 리스크 추가) · v0.4 (2026-07-18, 그룹 A 완료 반영: `works.is_published` 신설 확정 + B1/B2에 `public_work_filters()` 사용 지시 추가 - admin 패턴 복사 시 is_published 누락 함정 리뷰 발견) · v0.3 (2026-07-16, M1.5 F3 재설계 #76 반영: 콘텐츠 문서(회차 내 유료 경계) 모델 기준 전면 개정 - 무료 서빙 = content 절단 앞당김, 뷰어 = 문서 렌더러, 진행도 = 블록 인덱스, presign 실물 계약 반영) · v0.2 (2026-07-15, 리뷰 반영: 공개 서빙 게이트에 작품 soft-delete join 명시 + TTL config 키 관계 정리) · v0.1 (2026-07-15, 초안) |
| 상위 마일스톤 | [M2](./README.md#m2-콘텐츠-무료-구간) |
| 예상 기간 | 약 2~3주 (표지 공개 버킷 커스텀 도메인 외부 왕복 포함) |
| 완료 기준 | 비로그인 유저가 작품 목록 → 무료 구간(전체 무료 회차 + 부분 유료 회차의 경계 이전 미리보기) 열람, 유료 경계 도달 시 잠금 UI(M3 전이라 placeholder) 노출 (그룹 H 체크리스트) |
| 선행 마일스톤 | [M1.5](./M1.5_foundation.md) - 관리자 부트스트랩. **완전 종료**(2026-07-17, G 검증 28/28 + `v0.1.5` 태깅 - 에디터 #78·예약 UI #79 포함 전부 main 머지) |
| 다음 마일스톤 | [M4](./README.md#m4-커뮤니티-후원은-m3로-이동) - 커뮤니티 (결제 무관, M2 뒤 바로) |

> **목적**: 작품 목록 → 작품 상세 → 에피소드 목록 → 뷰어의 독자 열람 경로를 완성한다. 결제는 없다(M3). 회차 본문은 **콘텐츠 문서(TipTap JSON, `episodes.content`) + 회차 내 유료 경계(paywall 노드)** 모델(#76, DECISIONS "에피소드 콘텐츠 모델")이며, M2는 **경계 이전(무료 구간)만 서버가 잘라 서빙**하고 경계 지점에 잠금 placeholder를 노출한다. 범위는 PRD **WORK-01~09**(목록/상세/회차목록/뷰어/진행도) + 작가 소개. 경계 뒤(유료 구간) 반환·결제 검증은 **M3**, 커뮤니티(댓글·하트)는 **M4**, 작품 검색은 **P2**.

---

## 의존성 다이어그램

```
[D] 표지/썸네일 공개 버킷 (dweb-cover 전환 + config)  ──(외부 블로커: 커스텀 도메인 DNS)
      ↓ (공개 URL 조립)
[A] 공개 카탈로그 조회 API (works 목록 · 상세)
      ├───────────────────────────┐
      ↓                           ↓
[B] 회차 목록 + 무료 구간 콘텐츠 API   [C] 뷰어 진행도 (viewer_progress)
    (content 절단 · presigned 치환)
    ↑ #76 머지분 재사용: presign_get_urls · lib/content_doc
      └─────────────┬─────────────┘
                    ↓
[E] 목록/상세/회차목록 페이지 (Astro SSR, prerender=false)
                    ↓
[F] 뷰어 - 콘텐츠 문서 렌더러 (React 아일랜드) ──uses──> [B], [C]
                    ↓
[G] 작가 소개 페이지 (Astro 정적)
                    ↓
[H] M2 완료 검증 (e2e DoD)
```

- D(버킷/config)는 A/B의 표지·썸네일 URL 조립 전제. 단 **외부(커스텀 도메인 DNS)만 블로커**이고, API/FE는 config 값으로 코딩 가능(도메인 미연결 구간은 placeholder).
- A(카탈로그)는 E(목록/상세 페이지)의 선행. B(무료 구간 콘텐츠)는 F(뷰어)의 선행. C(진행도)는 F가 소비.
- B는 **#76(main 머지 완료)의 `r2_service.presign_get_urls`·`lib/content_doc`을 재사용**한다(중복 구현 금지 - 결정 1). M2 신규는 독자용 절단·치환 층과 공개 엔드포인트뿐.
- BE(A~D)와 FE(E~G)는 API 계약 확정 후 병렬 가능(백엔드 미완성분은 mock 선행).

> **외부 블로커**: **표지 전용 공개 버킷 `dweb-cover` 커스텀 도메인 연결**(DNS). 버킷 자체는 생성 완료(2026-07-15 사용자 확인). 도메인 미연결이어도 A/B/D는 진행 가능(표지·썸네일 *실제 표시*만 지연).
> **선행 리스크(해소, 2026-07-17)**: M2 e2e 시드 데이터(본문+경계)는 관리자 에디터로 입력한다 - 에디터(#78)·예약 UI(#79)가 main 머지 완료(M1.5 종료)라 의존 없음.

---

## 설계 결정 (2026-07-15 확정 · 2026-07-16 #76 반영 개정)

M2 착수 전 확정. presigned·표지·콘텐츠 모델은 기존 결정(DECISIONS "표지 서빙"·"원고 presigned GET"·"에피소드 콘텐츠 모델")의 연장선이라 **재정의가 아니라 참조**한다.

### 결정 1: 무료 구간 서빙 = 서버 절단(paywall 이전) + presigned URL 치환 (2026-07-16 개정)
- 흐름: `GET /episodes/{id}/content`(공개·작품 미삭제 회차, **인증 불요**)가 `episodes.content`를 **paywall 노드에서 절단해 경계 이전 노드만** 반환(`is_free=true`면 전문 - 경계 없음/경계 뒤 무의미와 동치, 파생 규칙은 `lib/content_doc.derive_is_free`). 문서 내 image 노드의 `key` attr은 **presigned URL로 치환**해 내보낸다(키 문자열은 비관리자 노출 금지 - admin `{key,url}` 쌍 방식은 독자용 부적합). 유료 구간 존재 여부(`has_paid_part` 등 잠금 표시용 메타) 동봉.
- **절단의 M2 앞당김**: DECISIONS "에피소드 콘텐츠 모델"은 "미구매 독자 절단 반환"을 M3로 적었으나, **부분 무료를 M2에서 보이게 하려면 절단이 M2 소관**(2026-07-16 사용자 확정). M2는 전원이 미구매라 **구매 검사 없이 절단만** 구현하고, M3가 구매 검증 통과 시 경계 뒤 포함 전문 반환을 얹는다. 클라 숨김 금지 원칙(서버 절단) 그대로.
- presigned 실물 재사용: **`r2_service.presign_get_urls(keys)`**(#76, 만료 600초 상수 `PRESIGN_GET_EXPIRES`). DECISIONS 규칙 "presigned URL은 서버·클라 어디서도 캐시 금지, 매 요청 발급" 준수 → **SSR HTML에 presigned를 박지 않는다**(Caddy/브라우저 캐시에 실려 다른 유저에게 재사용되는 경로 차단). 콘텐츠는 no-store API 응답으로 아일랜드가 fetch. TTL은 600초 유지(장기화는 캐시 금지·짧은 만료 규칙과 긴장 + 새면 오래 유효), 긴 체류로 만료된 이미지는 onerror → content 재요청(1차 단순).
- 탈락: 회차 단위 `is_free` 게이트 + 유료 통째 403(v0.2안 - 부분 미리보기가 M3까지 잠겨 새 모델 표현력 낭비), TTL 3600 장기화(v0.2안 - 위 규칙 긴장), 공개 버킷에 원고(버킷 단위 공개 유출 - 표지 서빙 결정), 백엔드 프록시 스트리밍(VPS 대역폭 낭비).

### 결정 2: 표지·썸네일 서빙 = 공개 버킷 `dweb-cover` (2026-07-15 확정) + 썸네일도 공개 축소본
- 표지·썸네일은 원고가 아니라 **의도적으로 공개하는 미끼 자산**이라 원고(`dweb`)와 다른 부류다. 버킷은 "어느 페이지에 뜨느냐"가 아니라 **"공개 정책"으로 정한다** → 표지·썸네일 = `dweb-cover`(공개, 고정 URL, 브라우저/CDN 캐시 O, egress 무료), 원고 = `dweb`(presigned, 만료 O).
- **표지**: 업로드 대상을 `dweb`→`dweb-cover`로 전환(현재 `works/{id}/cover.webp`를 `dweb`에 올림 - M1.5 D3). 공개 URL = `{public_asset_base_url}/{cover_key}`.
- **썸네일**: BE의 썸네일 = "이 회차 `image_keys` 중 하나"(= `dweb`의 원고 키, 정리로 제거되면 자동 NULL - #76·#78로 확정). 그대로 공개 페이지에 쓰면 presigned로만 서빙 가능해 캐시가 깨지고 **유료 회차 원고 1장이 노출**된다. → **썸네일 확정 시 서버가 그 페이지를 축소한 공개 축소본을 `dweb-cover/works/{work_id}/episodes/{episode_id}/thumb.webp`(결정적 키)에 side-effect로 생성**한다. `episodes.thumbnail` 컬럼은 **선택 페이지 키 의미를 유지**(공개 키를 저장하지 않음 - 부분집합 검증·자동 NULL 규칙이 그대로 살아남아 스키마·마이그레이션·검증 재작성 0). 공개 URL은 `thumbnail IS NOT NULL`일 때 결정적 키로 조립. 유료 회차 썸네일도 공개 OK(구매 유도용 미끼). 탈락: 컬럼에 공개 키 직접 저장(검증·자동 NULL 재작성 + 페이지 삭제와 썸네일 수명의 연결 단절), `thumbnail_source` 컬럼 추가(마이그레이션 비용 대비 이득 없음).
- **에디터(#78 머지)는 원고 키 방식을 유지한 채 종료** - 공개 축소본 파생은 **M2 D2가 BE-only로 구현**(2026-07-18 확정). PublishModal이 이미 `thumbnail: <페이지 키>`를 보내므로 admin 변경 0.
- "한 페이지에 두 버킷 혼재?" → 문제없음. `<img>`는 요청마다 독립이고 표시용 이미지는 CORS 대상이 아니다. 실제로도 목록/상세/회차목록은 `dweb-cover`만, 뷰어는 `dweb` presigned만이라 혼재 거의 없음.

### 결정 3: 프론트 렌더링 = 콘텐츠 페이지 페이지별 SSR(`prerender=false`) + 짧은 `Cache-Control`
- 목록/상세/회차목록은 **SSR**(요청 시 백엔드 fetch)로 항상 최신 + `Cache-Control: max-age=60`급으로 Caddy/브라우저 캐시 활용. 작가 소개만 정적(prerender).
- 이유: 자체 호스팅 **Node standalone 어댑터엔 네이티브 ISR이 없고**, 스케줄러(M1.5 E1)가 에피소드를 자동 공개하므로 신선도가 중요. 순수 SSG는 공개 전환을 재빌드 없이 반영 못 함. 기존 auth/마이페이지가 이미 페이지별 `prerender=false` SSR이라 정합.
- ⚠️ 뷰어 본문은 예외: presigned가 실리므로 **SSR 렌더·캐시 금지**(결정 1). 뷰어 페이지 셸(회차 메타·네비)만 SSR, 본문은 아일랜드 fetch.
- 탈락: 순수 SSG(빌드 시 fetch - 공개 전환 미반영), 재빌드 훅(자체 호스팅에서 복잡).

### 결정 4: 작가 소개 = Astro 마크다운(content collection), 백엔드 API 없음
- 정적 작가 작성 콘텐츠라 API·관리 UI가 과함(YAGNI). DECISIONS가 "API 또는 Astro 마크다운 import"로 열어둔 항목 → **마크다운**. 편집은 리포 파일 수정(1인 작가).
- 탈락: 백엔드 정적 데이터 API(관리 화면·엔드포인트 추가 비용 대비 이득 없음).

### 결정 5: 페이지네이션 = offset/limit + total
- 단일 작가·소규모 카탈로그라 keyset 불필요. `lib/pagination.py` 신설(offset/limit + total count), 태그 필터는 쿼리 파라미터. 회차 목록은 한 작품 기준이라 페이지네이션 없이 전체 반환(무한 스크롤/더보기는 FE 판단, 필요 시 후속).

---

## 그룹 A. 공개 카탈로그 조회 API (WORK-01, 02)

> 관리자 CRUD(M1.5 C1)와 **별개 공개 라우터**. table 모델 직접 노출 금지 → 공개 전용 DTO(**`content`·`image_keys`·`price` 내부값·미공개 회차 미포함** - 본문은 그룹 B의 절단 API로만). `selectinload`로 N+1 방지. `deleted_at IS NULL` + 회차는 `is_published` 필터 필수.

### A1. 공개 작품 목록 API ✅ (2026-07-18 완료 - PR `be/feat/m2-catalog-api`)
- 선행: D(공개 URL 조립), 없음(모델은 M1.5 A1 기존)
- 산출물: `routers/works.py`(공개, main.py 등록), `schemas/catalog.py`(공개 DTO), `lib/pagination.py`, `services/catalog_service.py`(또는 `work_service` 공개 조회 함수)
- `GET /works?page=&size=&tag=` - soft-delete 제외, 최신순, 태그 필터. 응답 = `{items: [WorkListItem], total, page, size}`. `WorkListItem` = id·title·표지 공개 URL·status·태그·`episode_count`(공개분).
- DoD: pytest 통합 - 비로그인 목록·페이지네이션·태그 필터, 응답에 `deleted_at` 작품 미포함, 표지 URL이 `public_asset_base_url` 기반 공개 URL.
- 결정: `episode_count`는 **공개(`is_published`) 회차만** 세도록 조정(M1.5 column_property는 전체 카운트라 공개용은 별도 계산 or 필터).
- **구현에서 확정(2026-07-17)**: 목록 노출 기준 = "공개 회차 ≥ 1"이 아니라 **작품 단위 `works.is_published` 플래그 신설**(사용자 결정 - 0회차 커밍순도 노출, 준비 중 숨김은 플래그로. 기존 행 backfill=true, 신규 기본 비공개). **admin 폼 토글·목록 배지·`generate:types` 재생성은 2026-07-18 완료**(codegen required 함정이 예고대로 발현 - `workSchema`에 필드 추가로 해소. 상세 `docs/MODULES/ADMIN/Works/IMPLEMENTATION_WORK_CRUD_SCREENS.md` §7). 상세: `docs/MODULES/BE/Works/IMPLEMENTATION_PUBLIC_CATALOG_API.md`.

### A2. 공개 작품 상세 API ✅ (2026-07-18 완료 - A1과 같은 PR)
- 선행: A1
- 산출물: `GET /works/{id}` - works + tags + **공개 회차 요약 목록**(`selectinload`). 응답 = `WorkDetail`(작품 메타 + `episodes: [EpisodeSummary]`).
- `EpisodeSummary` = id·`episode_no`·title·`subtitle`(#76 신설)·썸네일 공개 URL·`is_free`(전체 무료 - 경계 파생 컬럼)·`is_locked`(유료 구간 존재 = `!is_free`)·`is_purchased`(M2=항상 false). **`content`·`image_keys`·`price` 내부값 미포함**.
- DoD: pytest - 상세 응답에 미공개 회차·`content`·`image_keys` 미포함, 무료/잠금 플래그 정확, soft-delete 작품은 404.

---

## 그룹 B. 회차 목록 + 무료 구간 콘텐츠 API (WORK-03, 04) ⚠️ 보안 그룹

> ⚠️ **유료 구간·미공개 원고 유출 방어선**. 계획·코드 Opus xhigh 검증 생략 금지. 절단·presign은 **#76 머지분(`lib/content_doc`·`presign_get_urls`) 재사용**(결정 1), M2는 독자용 절단·치환 층과 공개 엔드포인트만 얹는다.

### B1. 공개 회차 목록 API
- 선행: A2
- 산출물: `routers/episodes.py`(공개), `services/episode_read_service.py`
- `GET /works/{id}/episodes` - 공개(`is_published`) 회차만, `episode_no` 순. **부모 작품 Work join은 `catalog_service.public_work_filters()`**(공개 `is_published` + 미삭제 - A 구현에서 신설된 단일 출처. `deleted_at`만 걸면 숨긴 작품의 회차가 샌다). 항목 = A2의 `EpisodeSummary`와 동일 스키마.
- DoD: pytest - 미공개 회차 제외, 순서 정확, 부분 유료 회차는 `is_locked=true`, soft-delete 작품의 회차는 404.

### B2. 무료 구간 콘텐츠 API (절단 + presigned 치환)
- 선행: B1, #76(`presign_get_urls`·`content_doc` - main 머지 완료)
- 산출물: `GET /episodes/{id}/content`, `services/episode_read_service.py`에 절단 함수(paywall 최상위 노드에서 문서 분할 - `lib/content_doc` 스키마 전제) + image `key`→presigned URL 치환 함수
- 동작: 회차가 **작품 공개 노출 가능(Work join `public_work_filters()` = `is_published` + 미삭제) AND 회차 공개**이면 content의 **경계 이전 노드만**(`is_free=true`면 전문) image 키를 presigned URL로 치환해 반환 + `has_paid_part` 메타. 미공개·작품 비공개/soft-delete·없음 → **404**. 응답 헤더 **`Cache-Control: no-store`**(presigned 캐시 금지 - DECISIONS).
- DoD: pytest(전부 mock) - (a) 전체 무료 회차 = 전문 + 문서 내 노드 순서 보존, (b) 부분 유료 회차 = 경계 이전만 + `has_paid_part=true` + **경계 뒤 노드·텍스트가 응답에 부재**, (c) 응답 JSON 어디에도 **원본 R2 키 문자열 부재**(치환 검증), (d) 미공개 404, (e) soft-delete 작품의 회차 404, (f) no-store 헤더. **비로그인 통과**(인증 불요).
- 결정: 로그인 불요(무료 구간은 공개 열람). `viewer_progress` 저장(그룹 C)만 로그인 필요. 절단 위치 = 문서 **최상위** paywall 노드(스키마가 최상위 최대 1개 보장 - `content_doc`). presigned 발급은 절단 **후** 남은 image 노드만(유료 구간 키에 서명하지 않음).
- ⚠️ 함정: 절단 전 문서를 직렬화 경로에 흘리지 말 것 - **경계 뒤 노드(글 포함)와 image `key` attr이 유료 자산**이다. 유료 구간 유출은 이미지만이 아니라 텍스트도 해당(글 유료 연재 가능 - 콘텐츠 모델 결정).
- ⚠️ 함정: **작품 soft-delete는 에피소드를 남긴다**(`work_service.soft_delete_work` - 하드 삭제 금지 A1 결정). episode 행만 검사하면 내려간 작품이 계속 열람된다. ⚠️ **admin 패턴(`episode_service.get_episode`)을 그대로 복사하지 말 것**(2026-07-18 리뷰 발견) - admin은 비공개 작품도 봐야 해서 `deleted_at`만 검사하므로, 독자 경로가 이를 복사하면 **숨긴 작품(`works.is_published=false`)의 공개 회차가 회차 ID 직접 접근으로 샌다**. 독자용 Work join은 `catalog_service.public_work_filters()`를 쓸 것.

---

## 그룹 C. 뷰어 진행도 (WORK-09)

### C1. `viewer_progress` 모델 + 진행도 저장/조회 API
- 선행: M1.5 A1(episodes), M1(users)
- 산출물: `models/viewer.py`(`ViewerProgress`), Alembic 마이그레이션 1개, `routers/progress.py`, `services/progress_service.py`
- `PUT /episodes/{id}/progress` - body `{page_no}`, **인증 필수**. `INSERT ... ON CONFLICT (user_id, episode_id) DO UPDATE`(upsert, `page_no`·`updated_at` 갱신). 선택적 `GET /episodes/{id}/progress`(재진입 복원용).
- DoD: `alembic upgrade head` → `viewer_progress` 테이블 + `UNIQUE(user_id, episode_id)`. pytest - 로그인 upsert(중복 시 갱신, 신규 시 insert), 비로그인 401, 존재하지 않는 episode 404/무시.
- 결정: `page_no`는 콘텐츠 모델 전환(#76)에 따라 **"문서 최상위 블록 인덱스"로 재해석**(DECISIONS "에피소드 콘텐츠 모델" 여파 - 컬럼·스키마 변경 없음, 의미만). debounce는 FE 책임(그룹 F). 저장 실패는 조용히 무시(열람 차단 아님 - 부가 기능). 회차 존재 검증은 B와 같은 공개 조회(Work join 포함) 재사용 - soft-delete 작품 회차엔 저장하지 않음.

---

## 그룹 D. 표지/썸네일 공개 버킷 (dweb-cover) - INFRA + BE

> 결정 2 적용. 외부 블로커: `dweb-cover` 커스텀 도메인 DNS(버킷은 생성됨).

### D1. 공개 버킷 config + 표지 업로드 전환
- 선행: 없음(admin 표지 업로드는 M1.5 C1/D3 기존). **#81 선반영분 주의**: config `public_asset_base_url`·`.env.example`·URL 조립(`catalog_service._public_url`)·카탈로그 응답의 표지 공개 URL은 이미 main에 있다 - D1 신규는 `r2_public_bucket`과 업로드 전환·admin 표시뿐.
- 산출물: config `r2_public_bucket`(기본 `dweb-cover`) + `.env.example` 주석(API 토큰이 `dweb`·`dweb-cover` 두 버킷을 커버해야 함), `r2_service` 업로드 대상 버킷 파라미터화(`upload_bytes(key, data, *, bucket=...)`, 기본 `dweb`) + **공개 URL 조립 헬퍼를 r2_service로 단일화**(`catalog_service._public_url`을 이관·재사용 - 조립 지점 이원화 금지), `work_service.set_cover_image` 대상 = 공개 버킷, admin `WorkRead.cover_url`(base 미설정 시 None) + `WorkList` 표지 표시(placeholder 대체)
- **캐시 버스터**: 공개 키는 고정(`works/{id}/cover.webp`) + 재업로드는 덮어쓰기라, 공개 URL 전환 후 표지를 교체해도 브라우저/CDN이 옛 표지를 계속 보여준다(presigned 시절엔 URL이 매번 달라 없던 문제). 조립 헬퍼가 `?v={updated_at}`을 부여 - 단일 헬퍼라 admin·공개 카탈로그 양쪽에 자동 적용.
- DoD: 표지 업로드 → `dweb-cover`에 객체 생성(mock의 Bucket 인자 검증) + 버킷 인자 생략 시 `dweb` 유지(회귀 없음), `cover_url` = `{base}/{key}?v=...` 형태·base 미설정이면 None, (도메인 연결 후) 공개 URL GET 200 스모크. 기존 `dweb`의 표지는 관리자 화면 재업로드로 정리(출시 전 dev 데이터뿐 - 이관 스크립트 안 만듦).
- 결정: 표지·썸네일만 공개 버킷 지정. 원고 업로드(D3)는 변경 없음(`dweb` 그대로).
- ⚠️ 조율: admin 작품 공개 토글 PR(`is_published` 폼 + `generate:types` 재생성)이 `WorkList.tsx`·`api.gen.ts`를 먼저 건드린다 - **그 PR 머지 후 main에서 분기**할 것.

### D2. 에피소드 썸네일 공개 축소본 생성 (BE-only, 2026-07-18 확정)
- 선행: D1. **admin 변경 0** - PublishModal이 이미 `thumbnail: <페이지 키>`를 보내고, 컬럼 의미(선택 페이지 키)를 유지하므로(결정 2 개정) 스키마·마이그레이션·검증 재작성도 0.
- 산출물: `r2_service.download_bytes(key, *, bucket=...)` 신설(현재 put/presign만 있어 서버가 원고를 읽을 경로가 없다 - draft 재진입 시 브라우저엔 원본이 없어 서버 파생이 유일한 길) + `episode_thumb_key()` 헬퍼, `image_service.convert_to_webp(..., target_width=)` 폭 파라미터화 + `THUMB_WIDTH=400`(함수 내부의 `TARGET_WIDTH*2` 배율 로직도 동반 수정), `episode_service` 썸네일 확정 시(**선택이 변경된 경우에만** - 미변경 요청은 R2 왕복 없음) 원고 다운로드 → 축소 → 공개 버킷 업로드, 썸네일 자동 NULL·해제 시 공개 축소본 `delete_object`(원고 파생물이 공개 버킷에 미참조 파일(orphan)로 남지 않게), admin 에피소드 응답 `thumbnail_url`, **공개 카탈로그 배선**: `catalog_service._to_episode_summary`의 `thumbnail_url=None` 하드코딩을 공개 URL 조립으로 교체(`thumbnail IS NOT NULL`일 때 결정적 키 - `schemas/catalog.py` docstring의 "D2 이전" 단서 해제)
- DoD: 썸네일 선택 → `dweb-cover`에 `.../thumb.webp` 생성(mock의 Bucket 인자 검증) + 미변경 요청은 재생성 없음. admin·공개(`GET /works/{id}`) 응답의 `thumbnail_url`이 공개 URL이고 **응답 어디에도 원고 키 문자열 부재**(공개는 `test_catalog`의 기존 부재-단언 패턴 재사용). 선택 페이지가 정리로 제거되면 기존대로 `thumbnail=NULL` + `thumbnail_url=None` + 공개 축소본 삭제. `target_width=400` 축소 폭 검증 + 기본 호출 800 유지. 마이그레이션 없음(`alembic check`).
- 결정: 공개 조회의 썸네일 fallback은 **작품 표지 또는 null**(FE placeholder) - 첫 페이지 fallback은 원고 키를 공개 URL로 내보내는 유출 경로라 금지. #81이 공개 경로를 "항상 null"로 이미 못박아 둠 - D2는 그 값을 채우기만 한다.

---

## 그룹 E. 작품 목록/상세/회차목록 페이지 (Astro, FE)

> 결정 3 적용: 페이지별 `prerender=false` SSR + `Cache-Control`. 부분 유료 회차는 잠금 배지 + 미리보기 진입 가능.

### E1. 작품 목록 페이지
- 선행: A1, D1
- 산출물: `frontend/src/pages/works/index.astro`(SSR), `lib/api.ts` 카탈로그 fetch, 카드 그리드(표지 공개 URL·제목·태그)
- DoD: `pnpm build` 통과, 목록 렌더 + 페이지네이션/태그 필터 동작, 미공개 작품 미노출.

### E2. 작품 상세 + 회차목록 페이지
- 선행: A2, B1
- 산출물: `pages/works/[id].astro`(SSR) - 작품 메타 + 회차 리스트(번호·제목·부제목·썸네일·무료/잠금 배지). 잠금 회차(`is_locked`)도 **뷰어 진입은 가능**(경계 이전 미리보기가 있으므로) - 배지로 유료 구간 존재만 표시.
- DoD: 목록→상세 네비게이션, 무료/잠금 배지 정확, 미공개 회차 미노출.

---

## 그룹 F. 뷰어 - 콘텐츠 문서 렌더러 (WORK-05~08, FE React 아일랜드)

> #76 콘텐츠 모델 기준 재정의: "이미지 세로 스크롤"이 아니라 **문서(글+이미지) 렌더러**. 콘텐츠 보호(DECISIONS): 드래그/복사/우클릭/저장 차단(UX 우선, 완벽 차단 아님).

### F1. 뷰어 아일랜드
- 선행: B2, C1
- 산출물: `pages/works/[id]/[episodeNo].astro`(SSR 셸 - 회차 메타·이전/다음 네비만) + `components/viewer/Viewer.tsx`(아일랜드 - 본문)
- 동작: 아일랜드가 B2 `GET /episodes/{id}/content`를 fetch(no-store) → **`@tiptap/core generateHTML`로 렌더**(React 불요 - DECISIONS 채택 근거. 서버 `lib/content_doc` 화이트리스트와 **동일 스키마**로만 해석, link는 렌더러가 `rel="noopener noreferrer" target="_blank"` 강제 부여 - #76 IMPLEMENTATION 인계). 세로 스크롤 + 이미지 lazy load, `has_paid_part=true`면 본문 말미(경계 지점)에 **잠금 placeholder**(M3 구매 버튼 자리). 이전/다음 화 이동, 진행도 = 뷰포트 기준 최상위 블록 인덱스 debounce 저장(→ C1 PUT), 드래그/복사/우클릭/저장 차단.
- presigned 만료(600초) 대응: 이미지 `onerror` → content 재요청(1차 단순 - 재요청 시 새 URL 세트).
- DoD: 전체 무료 회차 끝까지 스크롤(글+이미지 혼합 렌더·lazy load), 부분 유료 회차 = 미리보기 렌더 + 경계 잠금 노출, 진행도 저장(재진입 시 해당 블록 복원), 우클릭/드래그 차단, **본문 HTML이 SSR 응답에 부재**(아일랜드 fetch 확인).
- ⚠️ 함정(MISTAKES/study 참조): React StrictMode 이펙트 중복(이벤트 리스너 정리), `useEffect`에서 직접 mutate 금지. `generateHTML` 결과 주입은 화이트리스트 스키마 덕에 XSS 면적이 없으나(**서버가 검증한 노드만 존재**), 렌더러 확장 시 서버·에디터·뷰어 **3곳 동시 갱신** 규칙(#76) 준수.

---

## 그룹 G. 작가 소개 페이지 (FE Astro, 정적)

### G1. 작가 소개
- 선행: 없음
- 산출물: `pages/about.astro`(정적, prerender) + 마크다운 content collection(`src/content/`)
- DoD: 정적 빌드 렌더 확인. 백엔드 API 없음(결정 4).

---

## 그룹 H. M2 완료 검증 (DoD)

- [ ] 비로그인 유저: 작품 목록 → 상세 → 전체 무료 회차 뷰어 끝까지(글+이미지 렌더)
- [ ] 부분 유료 회차: 경계 이전 미리보기 열람 + 경계 지점 잠금 UI placeholder(구매는 M3)
- [ ] 무료 구간 콘텐츠가 **절단 + presigned 치환**으로 서빙: 응답에 경계 뒤 노드·원본 R2 키 부재, no-store
- [ ] 표지·썸네일이 `dweb-cover` 공개 URL로 표시, 원고는 `dweb` presigned
- [ ] 로그인 유저: 진행도(블록 인덱스) 저장 → 재진입 시 복원
- [ ] 목록 페이지네이션·태그 필터 동작, 미공개 작품/회차 미노출
- [ ] 작가 소개 페이지 렌더
- [ ] `uv run pytest` 통과, `alembic check` 클린, `pnpm build`/`lint` 그린, CI 그린
- [ ] 보안 그룹(B 절단·치환) Opus 리뷰 통과 - 유료 구간(글·이미지)·미공개·원본 키 유출 경로 점검

---

## M2에서 의도적으로 제외 (후속 마일스톤)

| 항목 | 이동처 | 근거 |
|------|--------|------|
| 유료 구간(경계 뒤) 반환·구매·결제 검증 | M3 | 결제 마일스톤. M2는 절단(경계 이전)까지 - M3가 B2에 구매 검증 + 전문 반환을 얹음 |
| 댓글·하트·신고 (커뮤니티) | M4 | 결제 무관, M2 뒤 바로 |
| 작품 검색 (WORK-11) | P2 | |
| 전용 소설 뷰어(뷰어 설정·이어보기 UX) | 보류 | 글 작성은 콘텐츠 모델에 내장(#76)됐으나 전용 뷰어는 여전히 보류(DECISIONS 여파 항목) |
| 알림(새 에피소드 등) | M6 | 트리거는 M1.5 공개 전환, 발송은 M6 |
| presigned 만료 재요청 고도화 | 후속 | 1차는 onerror → content 재요청. 부분 재발급 등은 실측 후 |
| 태그별 작품 목록 역방향 인덱스(`works_tags.tag_id`) | 필요 시 | 태그 필터 성능 실측 후(M1.5 A1에서 보류) |

---

## 외부 의존 / 일정 리스크

| 항목 | 리스크 | 완화 |
|------|--------|------|
| `dweb-cover` 커스텀 도메인 DNS | 미연결 시 표지·썸네일 실제 표시 지연 | 버킷은 생성됨. API/FE는 config로 진행, 도메인 연결까지 placeholder |
| R2 API 토큰 버킷 스코프 | 토큰이 `dweb` 한정이면 `dweb-cover` put이 **실서버에서만** AccessDenied(테스트는 전부 mock이라 그린) | D1 실서버 스모크 전 Cloudflare 대시보드에서 스코프 확인, 필요 시 두 버킷 포함 토큰 재발급(`.env`는 워크트리 간 심링크 공유 - 한 곳만 수정) |
| presigned 만료(600초 고정) | 긴 체류 시 하단 이미지 fetch 실패 | onerror → content 재요청(F1). TTL 장기화는 캐시 금지 규칙과 긴장이라 미채택 |
| 렌더러 스키마 드리프트 | 서버·에디터·뷰어 화이트리스트 불일치 시 렌더 누락/거부 | 확장 시 3곳 동시 갱신 규칙(#76 IMPLEMENTATION) - M2 뷰어도 같은 스키마 상수 참조 |

---

## 메모

- **순서**: 계획(Opus) → 코딩(Sonnet) → 검증(Opus, `@docs/reviews/GUIDE_REVIEW.md` + `CODE_REVIEW_BE.md`/`CODE_REVIEW_FE.md`) → 커밋. **B(절단·치환)는 보안 로직이라 Opus xhigh 검증 생략 금지**(유료 구간·미공개 원고 유출 방어선).
- 백엔드 실행은 항상 `uv run` 접두사, cwd 명시(`cd .../backend && uv run ...`).
- 새 패키지 설치 직전 WebSearch로 최신 안정 버전 확인(GUIDE_WORKFLOW 검색 규칙). FE 신규 의존성 = `@tiptap/core`(+`@tiptap/starter-kit` 등 렌더 스키마 - 에디터(#78) 머지분과 버전 통일: admin package.json 3.27.4), BE 신규 0(절단·presign·검증 전부 #76 재사용).
- **확정된 결정**(M2 착수 시 DECISIONS.md 반영 - 대부분 기존 결정 참조):
  - 무료 구간 서빙 = 서버 절단(paywall 이전) + presigned 치환, **절단은 M3→M2 앞당김**(2026-07-16). M3는 구매 검증 + 전문 반환만 얹음
  - presigned = #76 `presign_get_urls`(600초) 재사용, SSR HTML에 미포함(no-store API로 아일랜드 fetch), 캐시 금지 규칙 준수
  - 표지·썸네일 = 공개 버킷 `dweb-cover`, 썸네일도 공개 축소본(원고 키 노출 금지) - **D2 BE-only 파생으로 확정**(2026-07-18, 에디터 #78은 원고 키 방식 유지로 종료·`episodes.thumbnail` 컬럼 의미 불변)
  - 뷰어 = `@tiptap/core generateHTML` 문서 렌더러(서버 화이트리스트와 동일 스키마), `viewer_progress.page_no` = 블록 인덱스 재해석
  - 콘텐츠 페이지 = 페이지별 SSR(`prerender=false`) + 짧은 `Cache-Control`(뷰어 본문 제외), 작가 소개만 정적(마크다운)
  - 페이지네이션 = offset/limit + total
- 커밋은 영역 prefix `[BE]`/`[FE]`/`[INFRA]`, 한 커밋 하나의 논리 변경. 분할 예시: `[INFRA/BE] D`(버킷/config) → `[BE] A`(카탈로그) → `[BE] B`(절단·치환, Opus 리뷰 필수) → `[BE] C`(진행도) → `[FE] E/F/G`.
- 진행은 ledger 파일(`task_harness.local`)에 [A] 입력판 + 단계 체크리스트로 추적(GUIDE_TASK_HARNESS). 그룹 착수 시 생성.
