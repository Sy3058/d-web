# 작품 목록 / 등록 / 수정 화면 (M1.5 그룹 F - F2)

| 항목 | 내용 |
|------|------|
| 모듈 | Admin / Works |
| 관련 마일스톤 | [M1.5](../../../milestones/M1.5_foundation.md) 그룹 F - F2 (ADM-02 프런트) |
| 작성 시점 | M1.5 F2 (2026-07-15) |
| 상태 | 구현 + 수동 e2e(등록·수정·삭제·표지 크롭 확인) + Opus 코드 리뷰(/code-review xhigh, **14건 발견 전부 수정**). admin `test` 24 passed, build·lint 클린. 백엔드 `pytest` 244 passed, `alembic check` 클린 |
| 관련 문서 | C1 백엔드 계약(`../../BE/Works/IMPLEMENTATION_WORK_CRUD.md`), DECISIONS "표지 서빙", M1.5_foundation.md F2 |

C1(작품 CRUD API)을 소비하는 관리자 화면. **백엔드도 한 곳 바뀌었다**(§4 - 목록 N+1 제거).

---

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `admin/src/routes/_auth/works/index.tsx` | 신설. 목록(카드형) + 등록 버튼 |
| `admin/src/routes/_auth/works/new.tsx` | 신설. 등록. 생성 실패·재시도 처리(§3) |
| `admin/src/routes/_auth/works/$workId.tsx` | 신설. 수정 |
| `admin/src/components/works/WorkForm.tsx` | 신설. 등록/수정 공용 폼(RHF + Zod) |
| `admin/src/components/works/WorkList.tsx` | 신설. 카드 리스트(표지 placeholder·상태·태그·총 N화) |
| `admin/src/components/works/WorkActionsMenu.tsx` | 신설. `···` 드롭다운(수정/삭제) |
| `admin/src/components/works/TagInput.tsx` | 신설. 자유 텍스트 다중 태그 입력 |
| `admin/src/components/works/CoverCropModal.tsx` | 신설. 파일 선택 → 3:4 크롭(확대/이동) → 완료 |
| `admin/src/lib/cropImage.ts` | 신설. canvas로 crop 영역을 File로 변환(출력 폭 1600px 캡) |
| `admin/src/lib/workStatus.ts` | 신설. 연재 상태 라벨/옵션/enum 값의 **단일 출처** |
| `admin/src/hooks/useWorks.ts` | 신설. 목록·상세·생성·수정·삭제·표지 업로드 |
| `admin/src/lib/validation.ts` | `workSchema`·`TAG_NAME_MAX` 추가 |
| `admin/src/index.css` | `button:not(:disabled) { cursor: pointer }` 전역 규칙 |
| `backend/src/models/work.py` | `Work.episode_count` column_property (§4) |
| `backend/src/schemas/work.py` | `WorkRead.episode_count` |
| `backend/src/services/work_service.py` | `_load_episode_count` + 3개 커밋 경로에 적용 |

새 의존성: `react-easy-crop@6.2.2` (주간 다운로드 193만, 카테고리 1위. 확대/축소+이동 방식이 요구사항과 일치 - `react-image-crop`은 영역을 드래그로 그리는 다른 UX).

---

## 2. 스코프 결정

### "무료 회차 수 토글"은 F3으로
마일스톤 F2 DoD에 있었으나 `is_free`는 **에피소드 단위 필드**라 `WorkCreate/Update` 스키마에 없다. 에피소드 라우트가 없는 F2 시점엔 토글할 대상 자체가 없다(A1 결정도 "F2/F3"으로 양쪽에 열려 있었다).

### 전편 묶음 할인율 미노출 (사용자 결정)
폼에 입력 필드를 두지 않고 **항상 0으로 고정 전송**한다. 스키마·컬럼은 M3 결제가 참조하므로 그대로 둔다.

### 작품 순서 드래그 미도입 (사용자 결정)
DB에 순서를 저장할 컬럼이 없어 마이그레이션 + 재정렬 API가 필요하다. 클라이언트에서만 바꾸면 새로고침 시 되돌아가 오히려 혼란스러워 도입하지 않았다.

### 표지는 placeholder (DECISIONS "표지 서빙")
`cover_image`는 URL이 아니라 R2 키다. 업로드·저장은 정상 동작하나 **표시할 서빙 경로가 없다.** presigned URL로 지금도 띄울 수는 있지만, 표지는 공개 자산이라 **표지 전용 공개 버킷 + 커스텀 도메인**이 정답이고 그건 M2 소관이다. `dweb`(원고 버킷)에 도메인을 붙이면 R2의 공개 설정이 버킷 단위라 **미공개 원고까지 서명 없이 뚫린다** - DECISIONS와 milestones/README M0에 경고를 못 박아 뒀다.

---

## 3. 코드 리뷰 발견(전부 수정)

**Opus /code-review xhigh: 14건 발견 → 14건 수정.** 아래는 재발 위험이 큰 것들.

### 작품 중복 생성 (Critical)
작품 생성(POST)과 표지 업로드(POST cover)는 **별개 요청**이다(백엔드가 work_id를 요구). 표지만 실패하면(R2 미설정 dev에서 흔함) 에러를 띄우고 폼에 머무는데, 사용자가 "등록"을 다시 누르면 **작품이 하나 더 만들어진다**(백엔드에 멱등성 없음). 생성된 id를 `useRef`에 기억해 재시도 경로에서는 create 대신 update를 태운다.

### blob URL 누수 + StrictMode 함정
`URL.createObjectURL`을 세 곳에서 만들면서 revoke가 없어 최대 20MB 원본이 페이지 수명 내내 남았다. 정리를 `useEffect([url])`로 걸면 **StrictMode의 mount→cleanup→mount에서 아직 `<img>`가 쓰는 URL을 revoke해 미리보기가 깨진다** - ref에 담고 빈 deps 정리 + 교체 시점 명시 revoke로 해결(마운트 시점엔 ref가 비어 있어 안전).

### 쿼리 키가 서로 prefix
목록 키가 `['admin','works']`면 상세·에피소드 키의 prefix라, TanStack Query의 **기본 prefix 매칭** 때문에 작품 하나만 고쳐도 마운트된 모든 하위 쿼리가 재요청된다. 키를 세그먼트로 분리했다(`list`/`detail`). `exact: true`로 때울 수도 있었으나 구조가 남으면 다음 사람이 같은 덫을 밟는다.

### 조용한 실패 3종 (admin/CLAUDE.md "API 에러 무시 금지" 위반)
- 삭제 실패 → 아무 안내 없음 (`deleteWork.error`를 아무 데서도 안 읽음)
- 크롭 실패 → `try/finally`에 catch가 없어 "완료"가 먹통 (canvas `toBlob`이 null 반환 시)
- 50자 초과 태그 → `errors.tag_names`를 렌더링하지 않아 제출이 말없이 막힘 (입력에 `maxLength`로 근본 차단 + 안전망 렌더링)

### unhandled promise rejection
react-hook-form의 `handleSubmit`은 onValid에서 난 예외를 **finally 후 재throw**한다(v7 createFormControl). `mutateAsync`를 catch 없이 쓰면 form의 onSubmit이 rejected promise를 반환하고, 아무도 await하지 않아 unhandled rejection → **Sentry에 중복 보고**된다.

### 나머지
NaN 입력 시 zod 영문 기본 메시지 노출(`z.number({ error })`), 상태 라벨 중복 정의(→ `lib/workStatus.ts`), `role="button"` li 안의 버튼 중첩(→ 카드 본문만 `<Link>`, 메뉴는 형제), 크롭 출력 폭 무제한(→ 1600px 캡. 백엔드가 어차피 800px WebP로 변환하므로 큰 JPEG은 순수 낭비).

---

## 4. 백엔드 변경: 목록 N+1 제거 (`episode_count`)

목록의 "총 N화"를 위해 작품마다 `GET /admin/works/{id}/episodes`를 호출하면, 개수 하나 얻자고 **`image_keys`가 통째로 실린 응답**을 작품 수만큼 받는다(50화×50장 작품 10개 = R2 키 수천 개). 올바른 깊이의 수정은 백엔드가 개수를 세는 것이다.

```python
# models/work.py (Episode가 뒤에 정의돼 클래스 본문에서 참조 불가 → 사후 부착)
Work.episode_count = column_property(
    select(func.count(Episode.id))
    .where(Episode.work_id == Work.id)
    .correlate_except(Episode)
    .scalar_subquery()
)
```

**새 컬럼이 아니라 SELECT에 얹히는 상관 서브쿼리라 마이그레이션이 0이다**(`alembic check` "No new upgrade operations"로 확인). `idx_episodes_work_id`를 탄다.

### ⚠️ column_property는 커밋 후 만료된다 (실측)
`column_property`는 컬럼이 아니라 **SQL 표현식**이라 두 가지가 성립하지 않는다.

1. INSERT/UPDATE RETURNING(`eager_defaults`)으로 받아올 수 없다 → 갓 생성한 인스턴스에는 값이 없다
2. flush 후에는 값이 달라졌을 수 있다고 보고 **만료(expire)된다** → 이미 로드했던 인스턴스도 커밋 뒤엔 비어 있다

만료된 채로 응답 직렬화가 읽으면 lazy load가 async 밖에서 터진다(**MissingGreenlet**). 처음엔 생성 경로만 refresh했다가 **수정·표지 업로드 응답이 전부 500으로 깨졌다**(테스트 8개 실패로 검출). 커밋을 수반하는 세 경로 전부에 `_load_episode_count`(해당 속성만 refresh)를 넣어 해결했고, 세 경로를 모두 지나는 테스트를 추가했다.

> 이 프로젝트의 `eager_defaults=True`(C1)는 **서버 계산 컬럼**(`updated_at` 등)을 RETURNING으로 받아오는 정책이지 column_property까지 덮지 않는다. 둘을 헷갈리면 정확히 이 버그가 난다.

---

## 5. 테스트 유효성 검증

쿼리 키 분리가 실제로 회귀를 막는지 확인하려고 **키를 옛 구조(`['admin','works']`)로 되돌려 테스트를 돌렸다.** 예상대로 "무관한 쿼리가 무효화됨"으로 실패했고, 복원 후 통과했다. 통과만 시키는 테스트가 아님을 실측(F1과 같은 절차).

---

## 6. 이연 / 후속

| 항목 | 이동처 |
|------|--------|
| 표지 실제 표시(공개 버킷 + 커스텀 도메인) | M2 (DECISIONS "표지 서빙") |
| 기존 표지 **삭제** API(현재 백엔드는 업로드/덮어쓰기만) | 필요 시 |
| 무료 회차(`is_free`) 토글 | F3 |
| 작품 순서 지정(DB 컬럼 + 재정렬 API) | 필요 시 |
| 삭제 확인이 `window.confirm`(admin/CLAUDE.md 구조표의 `common/Modal.tsx` 미구현) | 공용 모달 도입 시 |
| FE/admin CI job | F2 이후(결정: 2026-07-14) |
