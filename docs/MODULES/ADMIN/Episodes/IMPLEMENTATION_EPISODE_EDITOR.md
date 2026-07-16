# 에피소드 TipTap 에디터 + 발행하기 (M1.5 그룹 F - F3)

| 항목 | 내용 |
|------|------|
| 모듈 | Admin / Episodes |
| 관련 마일스톤 | [M1.5](../../../milestones/M1.5_foundation.md) 그룹 F - F3 (ADM-03 프런트) |
| 작성 시점 | M1.5 F3 PR② (2026-07-16 1차, 2026-07-17 발행 흐름 재설계) |
| 상태 | 구현 + Opus 자체 코드 리뷰. admin `tsc`·`eslint`·`build` 클린, `vitest` 45 passed. **DB 마이그레이션 0**(BE 데이터 모델은 PR① #76에서 선머지) |
| 관련 문서 | BE 콘텐츠 모델(`../../BE/Episodes/IMPLEMENTATION_EPISODE_CONTENT_MODEL.md`), DECISIONS "에피소드 콘텐츠 모델", M1.5_foundation.md F3 |

PR①이 확정한 콘텐츠 문서 모델(`episodes.content` = TipTap JSON, 유료 경계 = `paywall` 노드, is_free 서버 파생)을 소비하는 포스타입식 에디터. **발행 흐름은 사용자 피드백(2026-07-17)으로 재설계**: 회차번호 자동, 유료 경계 상시 표시, "발행하기" 모달(시리즈·대표이미지·조건부 가격·즉시 공개), 작품 미지정 글로벌 진입.

---

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `components/episodes/EpisodeEditor.tsx` | 메인. 상단 시리즈(작품) 선택 + 제목/부제 + 캔버스 + 임시저장/발행하기 |
| `components/episodes/EditorToolbar.tsx` | 굵게·기울임·밑줄·취소선·링크·구분선·이미지 (유료 경계 버튼 없음 - 상시 존재) |
| `components/episodes/PublishModal.tsx` | 발행하기: 시리즈 확인·대표이미지(단일)·가격(유료일 때만)·즉시 공개 |
| `components/episodes/extensions/index.ts` | `buildEditorExtensions(store)` - StarterKit 화이트리스트 정렬 |
| `components/episodes/extensions/link.ts` | `WhitelistLink` - href attr만 직렬화 |
| `components/episodes/extensions/image.ts` + `ImageNodeView.tsx` | 커스텀 image 노드(attr=key) + 노드뷰(store 구독) |
| `components/episodes/extensions/paywall.ts` + `PaywallNodeView.tsx` | 유료 경계 노드(상시 1개, singleton 플러그인) + 분량 요약 노드뷰 |
| `components/episodes/imageUrlStore.ts` / `contentSummary.ts` / `imageUpload.ts` | URL 해석 store / 분량 집계 / 이미지 검증 |
| `components/episodes/EpisodeList.tsx` | 목록 테이블(부제 노출, "이미지 N장") |
| `hooks/useEpisodes.ts` | `useEpisodeImageUrls` episodeId null 수용, 저장 주석 |
| `lib/validation.ts` | `episodePublishSchema`(판매가만) |
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
- **회차번호 입력 제거**: 서버가 `max+1` 자동(1화·2화 순서대로).
- **시리즈(작품)**: 발행 대상. 선택은 에디터 상단(이미지가 작품을 필요로 해 상단), 모달은 확인.
- **대표 이미지**: 업로드된 본문 이미지 중 단일 1장(기존 `thumbnail` 필드).
- **판매가**: 유료 분량이 있을 때만 노출(클라가 경계 위치로 판단, 서버가 is_free 최종 파생). 비우면 작품 기본가.
- **발행**: 즉시 공개(`is_published=true`). 유의미 내용 없으면 발행 버튼 비활성(서버도 거부).
- 임시저장(draft)은 유지 - 비공개로 남긴다.

### 작품(시리즈) 미지정 글로벌 진입
`/episodes/new`로 작품을 안 정하고 글쓰기 시작 가능(작품 경로 진입도 유지). 작품은 상단 드롭다운(글로벌 진입일 때만)에서 선택하고, **draft가 생기면 고정**(다른 작품 이동 = work_id 변경이라 별도 BE 작업, 미포함). **이미지·저장·발행은 작품 선택 후에만**(업로드가 `작품/에피소드` 경로 필요) - 미선택 시 버튼 비활성 + 안내.

### is_published 취급 (F3/F4 경계 이동)
발행하기 = 즉시 공개(`is_published=true`)가 **F3로 들어왔다**. 예약 공개(즉시/예약 토글·datetime)만 F4로 남는다. 임시저장 등 draft 경로는 is_published를 싣지 않는다(에코 시 published_at NULL로 예약 풀림 - E1 계약).

---

## 3. 코드 리뷰 (Opus 자체) / CODE_REVIEW_ADMIN 대조
- 이미지 업로드 후 클라 URL 미저장(content엔 서버 key만, presigned/blob은 표시용 메모리). ✅
- 발행은 owner 액션, thumbnail은 image_keys 부분집합(서버 검증), 미결제 유저 노출 없음. ✅
- draft 경로 is_published 미전송·에러 catch+표시·작품 미선택/저장중 버튼 비활성. ✅
- "presigned PUT 3단계" 체크항목은 D3 결정(서버 경유 업로드)과 상충 stale로 미반영.
- (반영) 링크 http(s) 클라 검증, `!editor`/`!workId` 가드, 작품 경로 진입은 드롭다운 대신 작품명 고정(controlled select 경고 제거).

## 4. 이연 / 후속

| 항목 | 이동처 |
|------|--------|
| 공개 **예약** UI(즉시/예약 토글·datetime) | **F4** (즉시 공개는 F3로 이동) |
| 독자용 뷰어 렌더(`generateHTML`) + 결제 잠금 절단 | M2 뷰어 / M3 결제 |
| 기존 회차의 작품 이동(work_id 변경 + 회차번호 재계산) | BE 작업 필요 - 별도 |
| 회차별 태그 / 성인 콘텐츠 표시 | 모델 밖(마이그레이션·정책 필요) - 보류 |
| 다중 대표이미지(0/20·순서변경) | 모델·업로드 파이프라인 밖 - 별도 |
| 미참조 이미지 키 정리(캔버스에서 지운 이미지) | 후속(서버 불변식 content⊆image_keys 유지) |
| 장시간 편집 세션 presigned 만료 갱신 | 필요 실감 시 |
