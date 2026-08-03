# 에피소드 TipTap 에디터 + 발행하기 (M1.5 그룹 F - F3/F4)

| 항목 | 내용 |
|------|------|
| 모듈 | Admin / Episodes |
| 관련 마일스톤 | [M1.5](../../../milestones/M1.5_foundation.md) 그룹 F - F3/F4 (ADM-03 프런트, ADM-04 예약 UI) |
| 작성 시점 | M1.5 F3 PR② (2026-07-16 1차, 2026-07-17 발행 흐름 재설계) + F4 예약·이미지 DnD·제목 필수·기본가 표기 (2026-07-17, `admin/feat/episode-schedule`) |
| 상태 | 구현 + Opus 자체 코드 리뷰. admin `tsc`·`eslint`·`build` 클린, `vitest` 51 passed. **DB 마이그레이션 0**(BE 데이터 모델은 PR① #76에서 선머지, F4도 BE 변경 0) |
| 관련 문서 | BE 콘텐츠 모델(`../../BE/Episodes/IMPLEMENTATION_EPISODE_CONTENT_MODEL.md`), DECISIONS "에피소드 콘텐츠 모델", M1.5_foundation.md F3 |

PR①이 확정한 콘텐츠 문서 모델(`episodes.content` = TipTap JSON, 유료 경계 = `paywall` 노드, is_free 서버 파생)을 소비하는 포스타입식 에디터. **발행 흐름은 사용자 피드백(2026-07-17)으로 재설계**: 회차번호 자동, 유료 경계 상시 표시, "발행하기" 모달(시리즈·대표이미지·조건부 가격·즉시 공개), 작품 미지정 글로벌 진입.

---

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `components/episodes/EpisodeEditor.tsx` | 메인. 상단 시리즈(작품) 선택 + 제목/부제 + 캔버스 + 임시저장/발행하기 |
| `components/episodes/EditorToolbar.tsx` | 굵게·기울임·밑줄·취소선·링크·구분선·이미지 (유료 경계 버튼 없음 - 상시 존재) |
| `components/episodes/PublishModal.tsx` | 발행하기: 시리즈 확인·대표이미지(단일)·가격(유료일 때만)·공개 시점(지금/예약 datetime) |
| `components/episodes/extensions/index.ts` | `buildEditorExtensions(store)` - StarterKit 화이트리스트 정렬 |
| `components/episodes/extensions/link.ts` | `WhitelistLink` - href attr만 직렬화 |
| `components/episodes/extensions/image.ts` + `ImageNodeView.tsx` | 커스텀 image 노드(attr=key) + 노드뷰(store 구독) |
| `components/episodes/extensions/paywall.ts` + `PaywallNodeView.tsx` | 유료 경계 노드(상시 1개, singleton 플러그인) + 분량 요약 노드뷰 |
| `components/episodes/imageUrlStore.ts` / `contentSummary.ts` / `imageUpload.ts` | URL 해석 store / 분량 집계 / 이미지 검증 |
| `components/episodes/EpisodeList.tsx` | 목록 테이블(부제·"이미지 N장"·상태 배지·가격 실금액[기본가 해소]) |
| `hooks/useEpisodes.ts` | `useEpisodeImageUrls` episodeId null 수용, 저장 주석 |
| `lib/validation.ts` | `episodePublishSchema`(판매가 + 공개 예약 mode·publishedAt, `superRefine` 미래 검증) |
| `routes/.../episodes/upload.tsx`·`$episodeId.tsx` | 작품 경로 진입(에디터에 `initialWorkId` 전달) |
| `routes/_auth/episodes/new.tsx` | **글로벌 '새 에피소드'**(작품 미지정 진입) |
| `routes/_auth/index.tsx` | 대시보드에 "새 에피소드" 링크 |
| `types/index.ts` | `ContentDoc` 별칭 + api.gen 재생성 |

새 의존성: **TipTap 5종** `@tiptap/core`·`react`·`pm`·`starter-kit`·`extension-link` (`3.27.4`). singleton 플러그인은 `@tiptap/pm/state`(pm에 포함) 사용, 추가 패키지 없음.

---

## 2. 주요 결정

### 화이트리스트 정렬 = 방어선을 클라에도
StarterKit v3가 포함하는 heading·목록·codeBlock·code 마크를 **확장 자체로 끈다**(서버 `lib/content_doc` 밖). 안 끄면 마크다운 단축키로 저장 시 422 노드가 생긴다. `whitelist.test.ts`가 `getSchema`로 뷰 없이 서버와 1:1 대조.

### Link href-only / 커스텀 image + imageUrlStore
Link는 JSON에 href만 저장(rel/target은 렌더 전용). image 노드는 attr=key 하나, 표시용 presigned URL은 문서에 안 넣고 노드뷰가 주입된 store를 `useSyncExternalStore`로 구독(React context 노드뷰 전파 미보장 회피). 업로드 직후 로컬 blob→refetch로 실 URL 교체.

### 유료 경계 = 상시 1개 (삽입 버튼 없음)
paywall은 **항상 정확히 1개** 존재한다. 로드 시 없으면 `ensurePaywall`이 말미에 넣고(= 기본 전체 무료), 편집 중 삭제되면 확장의 ProseMirror 플러그인(`appendTransaction`)이 말미에 되살린다(0개면 삽입, 2개↑면 첫 개만 남김 - 붙여넣기 방어). 위로 드래그하면 그 뒤가 유료. is_free는 서버가 위치에서 파생. attrs 없음.

### 발행하기 모달 (회차 "설정"이 아니라 "발행")
- **회차번호 입력 제거**: 서버가 `max+1` 자동(1화·2화 순서대로). ⚠️ 2026-07-30에 회차번호 자체가 폐기됐다 - 표시 순서는 `sort_order`(목록 화면의 ↑↓ 버튼)로 옮겨졌고 에디터는 순서를 다루지 않는다.
- **시리즈(작품)**: 발행 대상. 선택은 에디터 상단(이미지가 작품을 필요로 해 상단), 모달은 확인.
- **대표 이미지**: 업로드된 본문 이미지 중 단일 1장(기존 `thumbnail` 필드).
- **판매가**: 유료 분량이 있을 때만 노출(클라가 경계 위치로 판단, 서버가 is_free 최종 파생). 비우면 작품 기본가.
- **발행**: 즉시 공개(`is_published=true`). 유의미 내용 없으면 발행 버튼 비활성(서버도 거부).
- 임시저장(draft)은 유지 - 비공개로 남긴다.

### 작품(시리즈) 미지정 글로벌 진입
`/episodes/new`로 작품을 안 정하고 글쓰기 시작 가능(작품 경로 진입도 유지). 작품은 상단 드롭다운(글로벌 진입일 때만)에서 선택하고, **draft가 생기면 고정**(다른 작품 이동 = work_id 변경이라 별도 BE 작업, 미포함). **이미지·저장·발행은 작품 선택 후에만**(업로드가 `작품/에피소드` 경로 필요) - 미선택 시 버튼 비활성 + 안내.

### is_published 취급 (F3/F4 경계 이동)
발행하기 = 즉시 공개(`is_published=true`)가 **F3로 들어왔다**. 임시저장 등 draft 경로는 is_published를 싣지 않는다(에코 시 published_at NULL로 예약 풀림 - E1 계약).

### 발행본/편집본 분리 (#86, 2026-07-23 개정)
공개 회차의 임시저장은 `content`가 아니라 **`draft` 봉투**(`{title, subtitle, content}`)를 PUT한다 - 발행본·공개 상태 무접촉. 편집 진입은 `draft ?? content`, 배너 + "임시저장본 버리기"(`draft: null`), 발행 버튼은 "수정 반영"(`content` + `is_published: true`, 서버가 draft 소진), PublishModal은 `isLive` 모드에서 공개 시점 토글을 숨긴다. 공개 회차에 `is_published` 없이 `content`를 보내면 서버 409(스케줄러 전환 race까지 WHERE 가드로 봉쇄). 이 절의 상세·BE 불변식: `../../BE/Episodes/IMPLEMENTATION_EPISODE_DRAFT_SEPARATION.md`. 하단 안내 문구는 공개/발행 전 분기로 교체(기존 단일 문구는 발행된 회차에서 거짓이었음 - 이슈 본문).

### 공개 예약 (F4, 2026-07-17)
발행 모달에 **지금 공개 / 예약 공개** 토글 + `datetime-local`을 추가. 예약이면 로컬 datetime을 `new Date(v).toISOString()`(offset 포함 aware ISO)로 변환해 **`published_at`만 PUT**하고 `is_published`는 **키 자체를 싣지 않는다**(false 에코 시 서버가 published_at을 NULL로 밀어 예약이 풀림 - E1 계약). BE(`episode_service`)는 `is_published`가 페이로드에 없으면 published_at 초기화 블록을 건너뛰어 예약이 그대로 저장되고, E1 스케줄러가 시각 도달 시 공개한다. **예약은 미래 시각만 허용**(과거는 서버가 다음 틱에 즉시 공개해 "지금"과 구분 불가 - 클라 `episodePublishSchema.superRefine`으로 차단). 예약 상태는 `EpisodeList`가 `published_at`으로 "예약" 배지 표시(기존, 무변경). **BE 변경 0.** RHF `watch()`는 React Compiler 경고(stale UI)라 `useWatch`로 구독.

### 이미지 드래그앤드롭 (2026-07-17)
에디터 컨테이너 div에 drag/drop 핸들러. **외부 파일 드래그만** 가로챈다(`dataTransfer.types`에 `'Files'` 포함) - 내부 노드 드래그(유료 경계 재배치)는 `'Files'`가 없어 ProseMirror에 위임. 드롭 지점을 `posAtCoords`로 커서 이동(레이아웃/`elementFromPoint` 의존이라 try/catch 방어 - 실패 시 현재 커서), 이후 기존 `onFilesSelected`(검증·업로드·삽입 파이프라인) 재사용. 파일 입력 버튼 경로와 동일한 흐름 - 검증·상한·optimistic blob 그대로. 이미지 업로드는 `works/{id}/episodes/{id}/images` 경로라 **작품 미선택 시 드롭도 막는다**(발행 검증과 별개인 하드 의존 - 업로드가 즉시 일어나고 URL에 work가 필요. 지연 업로드로 우회 가능하나 미채택).

### 목록 가격 표기 (기본가 해소)
`EpisodeList`가 `basePrice`(=`works.episode_base_price`)를 받아 `price=NULL`(기본가를 따르는) 회차를 "기본가" 텍스트 대신 **실제 금액 `N원`**으로 표기한다(관리 화면에서 실제 판매가 확인 편의). 기본가가 아직 로딩 전이면 `기본가`로 폴백. 개별 지정가(`price` 있음)도 `N원`으로, 목록에선 둘을 굳이 구분 표기하지 않는다(사용자 결정). A1 원결정("값을 지어내지 않고 그대로 표기")에서 관리 편의를 위해 현재 기본가를 풀어 보여주는 쪽으로 조정.

### 제목 필수 (조용한 '무제' 대체 폐지)
저장·발행 시 제목이 비면 서버 기본값 '무제'로 조용히 넘기지 않고, `ensureTitle()`이 "제목을 작성해 주세요."를 띄우고 막는다(임시저장·발행 버튼 모두). 입력 placeholder도 "제목"으로 정리(기존 "제목 (비우면 무제)"). ~~단, **이미지 업로드가 만드는 지연 draft**(`ensureDraft`)는 서버 기본값 '무제'를 그대로 두는데, 이건 사용자가 저장하기 전 임시 상태이고 저장 시 실제 제목으로 덮인다(이미지-먼저 워크플로 보존). 편집 재진입 시 제목이 '무제'면 빈 칸으로 취급.~~

**예외 폐지(2026-07-30)**: 이 예외는 "이탈하면 '무제' 회차가 실제로 남는다"는 구멍이었고, 회차 번호 폐기로 제목이 **유일한 식별자**가 되면서 감당할 수 없게 됐다. 지금은 ①서버가 `EpisodeCreate.title` 기본값을 없애 빈 제목을 422로 거부하고 ②이미지 업로드 진입점(`onFilesSelected`)도 제목을 먼저 요구한다("이미지를 넣기 전에 제목을 작성해 주세요."). 편집 재진입의 `'무제' → 빈 칸` 매직 스트링 비교도 제거했다 - 작가가 진짜로 '무제'라고 지은 제목이 빈 칸이 되던 오작동이었다.

---

## 3. 코드 리뷰 (Opus 자체) / CODE_REVIEW_ADMIN 대조
- 이미지 업로드 후 클라 URL 미저장(content엔 서버 key만, presigned/blob은 표시용 메모리). ✅
- 발행은 owner 액션, thumbnail은 image_keys 부분집합(서버 검증), 미결제 유저 노출 없음. ✅
- draft 경로 is_published 미전송·에러 catch+표시·작품 미선택/저장중 버튼 비활성. ✅
- "presigned PUT 3단계" 체크항목은 D3 결정(서버 경유 업로드)과 상충 stale로 미반영.
- (반영) 링크 http(s) 클라 검증, `!editor`/`!workId` 가드, 작품 경로 진입은 드롭다운 대신 작품명 고정(controlled select 경고 제거).
- **F4/DnD(2026-07-17 셀프리뷰)**: 예약 경로가 `is_published` 키를 생략함을 BE와 대조 확인(`if "is_published" in changes` 블록 스킵 → published_at 보존·저장) / `toISOString`(aware ISO)가 `AwareDatetime` 수용 / 내용 없는 예약은 클라 canPublish + E1 발행 시 content 가드로 이중 차단 / DnD는 외부 파일만 가로채고(types 'Files') 좌표 해석 실패 방어. Critical/Major 0.

## 4. 이연 / 후속

| 항목 | 이동처 |
|------|--------|
| 독자용 뷰어 렌더(`generateHTML`) + 결제 잠금 절단 | M2 뷰어 / M3 결제 |
| 기존 회차의 작품 이동(work_id 변경 + 회차번호 재계산) | BE 작업 필요 - 별도 |
| 회차별 태그 / 성인 콘텐츠 표시 | 모델 밖(마이그레이션·정책 필요) - 보류 |
| 다중 대표이미지(0/20·순서변경) | 모델·업로드 파이프라인 밖 - 별도 |
| 미참조 이미지 키 정리(캔버스에서 지운 이미지) | 후속(서버 불변식 content⊆image_keys 유지) |
| 장시간 편집 세션 presigned 만료 갱신 | 필요 실감 시 |
