# 커미션 관리 화면 + 사이트 문구 편집 (M2 그룹 G PR2)

| 항목 | 내용 |
|------|------|
| 모듈 | Admin / Commission |
| 관련 마일스톤 | [M2](../../../milestones/M2_foundation.md) 그룹 G |
| 작성 시점 | M2 G PR2 (2026-08-05) |
| 상태 | 구현 + 코드 리뷰 반영. 독립 작가 프로필 화면·이미지 업로드 포함. 최종 `pnpm --filter admin test` 109 passed, lint·build 클린 |
| 관련 문서 | `../../BE/Commission/IMPLEMENTATION_COMMISSION_API.md`(PR1 - 인계 계약 원문), M2_foundation.md 그룹 G |

PR1(#107)이 만든 커미션 카드·사이트 문구 API를 소비하는 admin 화면. 최초 구현은 PR1 API만 소비했으나, 머지 전 리뷰에서 개별 PUT 두 건으로는 순서 변경의 원자성을 보장할 수 없음을 확인해 컬렉션 벌크 재정렬 API와 서버 순서 배정을 같은 PR에 보강했다.

---

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `admin/src/routes/_auth/commission/index.tsx` | 신설. 카드 목록 |
| `admin/src/routes/_auth/commission/new.tsx` | 신설. 카드 등록 + 샘플 이미지 로컬 스테이징(등록 제출 시 함께 업로드) |
| `admin/src/routes/_auth/commission/$itemId.tsx` | 신설. 카드 수정 + 샘플 이미지 관리 |
| `admin/src/routes/_auth/site-texts.tsx` | 사이트 문구 2슬롯 편집 |
| `admin/src/routes/_auth/artist-profile.tsx` | 독립 작가 프로필 수정 화면 |
| `admin/src/routes/_auth/index.tsx` | 대시보드에 "커미션 관리"·"사이트 문구 편집" 링크 추가 |
| `admin/src/components/commission/CommissionForm.tsx` | 신설. 등록/수정 공용 폼(RHF + Zod) |
| `admin/src/components/commission/CommissionList.tsx` | 신설. 목록(마감 토글·순서 ▲▼·편집/삭제) |
| `admin/src/components/commission/CommissionActionsMenu.tsx` | 신설. `···` 드롭다운(수정/삭제) |
| `admin/src/components/commission/SampleImageManager.tsx` | 신설. 샘플 이미지 업로드·재배열·삭제(카드 편집 화면 전용, 실제 네트워크 업로드) |
| `admin/src/components/commission/SampleImageStaging.tsx` | 신설. 샘플 이미지 로컬 선택·미리보기·재배열·삭제(카드 등록 화면 전용, 네트워크 없음) |
| `admin/src/components/commission/SiteTextEditor.tsx` | 신설. 문구 슬롯 1개 편집(로딩 게이트 + 폼) |
| `admin/src/components/commission/ArtistProfileEditor.tsx` | 소개용 작가명·프로필 이미지 업로드·Twitter·Postype 폼 |
| `admin/src/components/common/ImageCropModal.tsx` | 작품 표지·프로필 공용 선택·확대·크롭 모달 |
| `admin/src/hooks/useCommissionItems.ts` | 신설. 목록·생성·수정·삭제·샘플 업로드 |
| `admin/src/hooks/useSiteTexts.ts` | 신설. 문구 조회·upsert |
| `admin/src/hooks/useArtistProfile.ts` | 작가 프로필 조회·일괄 upsert |
| `admin/src/lib/validation.ts` | `commissionItemSchema` + 상수(TITLE_MAX·`MAX_SAMPLES_PER_ITEM` 등) 추가 |
| `admin/src/types/index.ts` | `CommissionItem`·`SiteText` 등 별칭 추가 |
| `admin/src/types/api.gen.ts` | `generate:types` 재생성(#107 커미션 + #108 회차 스키마 모두 반영) |

신규 의존성 0.

---

## 2. 주요 결정

### 카드 순서 = 컬렉션 PUT + 전량 ID
목록 ▲▼ 버튼은 화면에서 인접 두 항목을 맞바꾼 뒤 카드 전량 ID를 `PUT /admin/commission-items`에 한 번 보낸다. 서버는 요청 집합이 현재 카드 전량과 정확히 같은지 검사하고 한 트랜잭션에서 `sort_order=1..N`으로 정규화한다. 다른 탭의 추가·삭제로 집합이 어긋나면 409 후 목록을 다시 읽는다.

개별 Create/Update 입력에는 `sort_order`를 노출하지 않는다. 새 카드는 서버가 현재 최댓값+1로 배정하므로 `/commission/new` 직접 진입이나 목록 로딩 실패가 순서를 0으로 오염시키지 않는다. 두 개별 PUT과 클라이언트 rollback은 중간 실패를 완전히 막지 못해 기각했다.

### 로컬 샘플 미리보기 URL은 commit 이후 생성
`SampleImageStaging`의 파일별 하위 컴포넌트가 effect에서 object URL을 만들고 cleanup에서 같은 URL을 revoke한다. render 중 `useMemo`에서 URL을 만들면 StrictMode의 반복 계산이나 폐기된 concurrent render가 cleanup에 도달하지 않아 blob이 누수될 수 있다. StrictMode 재마운트·파일 교체·unmount에서 생성 URL 전량이 회수되는 테스트로 고정했다.

### PR1 인계 계약 준수: 재배열·삭제는 `sample_image_keys`, 렌더는 `sample_images`
`SampleImageManager`는 항상 `item.sample_image_keys`(문자열 배열)를 로컬에서 재구성해 PUT하고, 화면 렌더(썸네일 URL)는 `item.sample_images`(key·URL 쌍, `computed_field`)를 쓴다. 두 배열은 서버가 같은 순서로 보장한다(스키마가 `sample_image_keys`를 그대로 순회해 `sample_images`를 만든다). `CommissionItemUpdate.sample_image_keys`는 기존 키의 부분집합만 허용(신규 주입 금지)하므로, 재배열·삭제 모두 "현재 키 배열의 순서를 바꾸거나 원소를 뺀 배열"만 보낸다.

### 샘플 업로드는 순차 처리(병렬 아님)
서버의 append가 `expected_len` 기반 조건부 UPDATE(PR1 - 원자 append)라, 같은 카드에 여러 장을 동시에 POST하면 각 요청이 서로 다른 스냅샷의 `expected_len`을 들고 경쟁해 뒤에 도착한 요청이 409로 튕기거나(최악의 경우 타이밍에 따라) 유실될 수 있다. `for...of` + `await`로 한 장씩 끝난 뒤 다음 장을 올린다.

### is_open 토글은 `Controller` 양방향 바인딩
`register`+`setValueAs`는 입력(문자열→boolean) 방향만 처리해 수정 폼이 서버의 `is_open=false`를 반영하지 못하는 함정이 있다(WorkForm의 `is_published`에서 이미 겪은 문제 - MISTAKES 폼 섹션). `CommissionForm`도 같은 `Controller` 패턴을 그대로 재사용했고, "`defaultValues.is_open=false`를 무조작 제출" 테스트로 고정했다.

### description·duration_text는 null 변환 없이 빈 문자열 그대로 전송
두 필드 모두 서버에서 nullable(`str | None`)이지만 `min_length`가 없어 빈 문자열도 유효하다. `WorkForm.synopsis`가 이미 같은 이유로 null 변환을 생략하는 선례라 그대로 따랐다(계획 단계에서는 `setValueAs`로 null 변환을 검토했으나, 기존 코드 선례를 확인한 뒤 YAGNI로 단순화).

### 샘플 이미지는 등록 화면에서도 선택 가능(WorkForm 표지 패턴 재사용, 2026-08-05 사용자 요청)
초안에서는 카드 생성 후에만 샘플을 올릴 수 있었다(`SampleImageManager`가 실제 `item.id`를 요구). 사용자가 "등록 버튼 누르기 전에 이미지도 선택할 수 있어야 한다"고 요청해, `WorkForm`의 표지 이미지 패턴(파일을 로컬 `File[]`로만 들고 있다가 생성 성공 직후 업로드)을 그대로 재사용했다. `SampleImageStaging`이 로컬 스테이징(네트워크 없음)을 담당하고, `new.tsx`가 카드 생성 성공 → 스테이징 파일 순차 업로드까지 한 번의 "등록" 제출로 묶는다.

카드 생성과 샘플 업로드는 여전히 별개 요청(백엔드가 `item_id`를 요구)이라, `WorkForm`처럼 `createdItemIdRef`로 재시도 시 중복 생성을 막는다. 업로드 중 하나라도 실패하면(카드 자체는 이미 생성된 상태) **자동으로 편집 화면에 넘어가지 않고 그 자리에 머문다** - 이미 올라간 장은 스테이징에서 빼 재제출이 중복 업로드하지 않게 하고, 사용자가 "등록"을 다시 누르면 `createdItemIdRef`가 설정돼 있어 카드는 만들지 않고 나머지 샘플만 재시도한다. 전부 성공해야 편집 화면(`$itemId`)으로 이동한다.

### SiteText 편집은 RHF 미사용, `useEffect` 없이 데이터 로드 후에만 하위 컴포넌트 마운트
필드가 textarea 하나뿐이라 폼 라이브러리를 얹을 이유가 없다. 처음에는 `useEffect(() => setBody(data.body), [data])`로 서버 값을 로컬 상태에 복사했으나, 새 eslint 규칙(`react-hooks/set-state-in-effect` - React Compiler 대비 룰)이 "effect 안에서 setState 동기 호출"을 에러로 잡았다. `works/$workId/index.tsx`의 `{work && <WorkForm .../>}` 패턴과 동일하게, 데이터가 로드된 뒤에만 마운트되는 `SiteTextForm` 하위 컴포넌트로 분리해 `useState(data.body)` 초기값이 마운트 시점에 한 번만 seed되도록 했다 - effect 자체가 불필요해진다.

작가 프로필은 사이트 문구 화면과 분리한 `/artist-profile`에서 편집한다. 이름·외부 채널은 RHF + Zod를 사용하고 빈 URL 입력은 제출 경계에서 `null`로 바꾸며 클라이언트와 서버 모두 host가 있는 HTTP(S)만 허용한다. 이미지는 URL 입력이 아니라 공용 `ImageCropModal`에서 1:1 원형 가이드로 위치·확대를 조정한 뒤 multipart로 업로드하고, 서버가 WebP·공개 URL로 변환한 응답을 전용 query key에 반영한다. 같은 모달을 작품 표지는 3:4 사각형 설정으로 사용해 파일 선택·blob 정리·canvas 실패 처리를 한 곳에서 유지한다. 작가명은 랜딩의 작가 소개 스트립에만 반영하며 전역 브랜드명 `도군`은 바꾸지 않는다.

---

## 3. 리뷰 (Opus, 커밋 전)

Critical 0 / Major 2 / Minor 6 / FYI 3. 지적마다 실패 시나리오를 붙이고, 판별력 주장은 **변이 실험**으로 실측했다.

1. **[Major] 순서 스왑의 첫 PUT 실패가 화면에 안 뜬다** - 두 `mutate()`가 같은 `useMutation`을 공유해 observer가 뒤 요청으로 교체된다(query-core `mutationObserver.mutate` 소스 확인). 앞 실패 + 뒤 성공 = 두 카드 `sort_order` 동률인데 배너 없음 → 작가는 "왜 순서가 안 바뀌지" 하며 반복 클릭. → 순차 `await` + `try/catch`로 교체(§2 갱신). 실패 주입 테스트 추가, **이중 `mutate()` 재주입으로 red 실증 후 원복**.
2. **[Major] 학습용 질문 주석 2건 잔존**(`CommissionList.tsx`, `SampleImageManager.tsx`) - 검토 완료 후 모두 삭제했고, 설명이 필요한 부분만 일반 주석으로 전환했다.
3. **[Minor] 폼 회귀 테스트의 판별력 0** - "`defaultValues.is_open=false` 무조작 제출"은 시작값=기대값이라, `select`의 `value` 바인딩을 빼 "폼 상태는 false인데 화면은 접수 중"이 되는 회귀에도 green이었다(변이 실측). → 마운트 직후 렌더된 select 값 단언 추가, 같은 변이로 red 실증.
4. **[Minor] 순차 업로드 중단 시 진행 상황 미고지** - 5장 중 3번째가 실패하면 4·5번째가 조용히 누락된다. → 에러 문구에 `N장 중 M장 업로드됨, 나머지는 중단` 추가.
5. **[Minor] 에러 배너가 낡은 에러를 표시** - `deleteItem.error ?? updateItem.error`는 삭제가 먼저 실패해 에러가 남은 뒤 수정이 실패하면 삭제 문구를 보여준다. → `isError`를 각각 보고 고르도록 수정.
6. **[Minor] 샘플 삭제의 방어 조건이 역방향** - `if (sample && !confirm(...)) return`은 `sample`이 없을 때 확인창을 건너뛰고 삭제 PUT까지 진행하는 모양. → 범위 검사와 확인창을 분리.
7. **[Minor] 경계 테스트가 한쪽만 단언** - "10장이면 비활성"·"첫 카드 위로 비활성"만 봐서 "전부 비활성" 구현도 통과. → 9장 활성·반대쪽 버튼 활성 단언 추가.
8. **[Minor, 미반영] 목록 미로드 상태의 신규 카드 `sort_order`** - `/commission/new` 직접 진입이나 목록 fetch 실패 시 `sort_order=0`으로 생성돼 새 카드가 맨 앞에 꽂힌다(알림 없음). ▲▼로 복구 가능하고, 제출 차단·대체값 중 무엇을 택할지는 제품 판단이라 후속으로 남긴다.

### 2026-08-11 재리뷰

Critical 0 / Major 3. ① 개별 PUT 두 건의 두 번째 실패가 중복 순서를 남김, ② render 중 object URL 생성이 StrictMode에서 누수될 수 있음, ③ 목록 미로드 생성이 `sort_order=0`을 보냄. 각각 컬렉션 벌크 재정렬, effect lifecycle, 서버 max+1 배정으로 해소했다. 기존 8번 이연 항목도 함께 완료됐다.

리뷰 확인 통과 항목: PR1 인계 계약(재배열·삭제는 `sample_image_keys`, 렌더는 `sample_images`) 준수 - 테스트로 명시 고정. `_NON_NULLABLE`에 null을 보내는 경로 없음(빈 문자열·불리언·배열만, 빈 배열은 서버가 부분집합으로 허용). 10장 상한을 클라가 사전 반영(버튼 비활성 + 초과분 slice + 안내)해 서버 409에 의존하지 않음. 신규 라우트 3개 전부 `_auth` 하위(`routeTree.gen.ts` 확인)라 가드 적용. D3 계약 준수(멀티파트를 백엔드로, R2 직접 업로드 없음)·`credentials: 'include'`(shared `rawRequest` 고정). 캐시 키 prefix 분리와 그 자체를 검증하는 테스트. `$itemId`의 `getQueryData` 폴백은 타입 프로브로 `CommissionItem` 추론 확인.

**병렬 업로드 위험 실측**: 서버가 `expected_len`을 자체 read로 잡고(`admin_commission.py:100`) **R2 업로드를 조건부 UPDATE보다 먼저** 수행하므로, 같은 카드에 동시 2건이면 뒤 요청이 409로 튕기면서 이미 올라간 객체가 공개 버킷에 미참조 파일(orphan)로 남는다 - 순차 처리 결정이 옳다(§2).

**SiteText 리팩터링 안전성 확인**: 서버가 `body`를 정규화하지 않고(`SiteTextUpdate.body`는 `max_length`만) 그대로 저장·반환하므로, 저장 후 로컬 `useState`와 서버 값이 어긋나지 않는다. 다만 나중에 서버가 trim 등 정규화를 넣으면 textarea만 원본을 붙들게 되므로, 그때는 재-seed 장치(`key`로 remount 등)가 필요하다.

---

## 4. 이연 / 후속

| 항목 | 이동처 |
|------|--------|
| 독자용 랜딩(`/`)·`/commission` FE | PR3 (`fe/feat/m2-landing-commission`) |
| DECISIONS·M2_foundation 그룹 G 재작성 | PR4 (PR3 편승) |
| 카드·회차 목록 드래그 재정렬(현재 둘 다 ▲▼ 버튼) | 필요 시 - 조사 결과(2026-08-05) 아래 참조 |
| 신청 폼(아이템 선택→신청)·이메일 접수·admin 접수 관리 | M5 |

### 드래그앤드롭 재정렬 조사 메모 (2026-08-05, 사용자 문의)

사용자가 "회차 목록처럼 커미션도 드래그로 재정렬하면 안 되냐"고 물어 확인한 결과: **회차 목록도 실제로는 드래그가 아니라 ↑↓ 버튼**이었다(`IMPLEMENTATION_EPISODE_PUBLIC_ID.md` §"재배열은 컬렉션 PUT + 전량 전송" - 드래그앤드롭 라이브러리를 새로 들이지 않고 의존성 0 + 키보드 접근성 기본을 택한 명시적 결정, #108).

두 목록의 재정렬 API 계약이 다르다는 점이 드래그 도입 난이도를 가른다:
- **회차**: `EpisodeReorder`(전체 순서 배열 1건 PUT) - 드롭 결과(전체 새 순서)를 그대로 실어 보내면 되므로 드래그와 계약이 자연스럽게 맞는다.
- **커미션**: 머지 전 재리뷰에서 회차와 같은 컬렉션 PUT + 전량 ID 계약을 추가했다. 드롭 결과를 그대로 보낼 수 있는 서버 전제는 갖춰졌다.

**결론**: 벌크 API 전제는 완료됐지만 드래그 UI는 이 PR에 도입하지 않는다. 필요하면 별도 PR에서 두 목록이 공유하는 드래그 컴포넌트를 검토한다. 그 전까지는 회차·커미션 모두 버튼 방식을 유지한다.
