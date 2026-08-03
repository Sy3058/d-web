# 에피소드 콘텐츠 모델 전환 - 문서형 본문 + 회차 내 유료 경계 (M1.5 F3 재설계 ①)

| 항목 | 내용 |
|------|------|
| 모듈 | Backend / Episodes |
| 관련 마일스톤 | [M1.5](../../../milestones/M1.5_foundation.md) F3 재정의 ① (BE 선행 PR) |
| 작성 시점 | F3 재설계 (2026-07-16) |
| 상태 | 구현 + Opus 코드 리뷰(Critical 0 / Major 1 / Minor 1 - 전부 반영) + `pytest` 294 passed(신규 content_doc 29 포함, 2026-07-16), ruff·`alembic upgrade`/`check` 클린. **DB 마이그레이션 1**(백필 포함) |
| 관련 문서 | DECISIONS "에피소드 콘텐츠 모델"·"원고 presigned GET", DB_SCHEMA episodes, M1.5 F3 배너 |

회차 본문의 진실을 `image_keys` 배열에서 `episodes.content`(TipTap/ProseMirror JSON 문서)로
옮기는 재설계. 에피소드 화면이 포스타입식 게시글 에디터(글+이미지+드래그 유료 경계)로
확정되면서(2026-07-15), M2 뷰어·M3 결제 절단의 전제가 되는 데이터 모델을 먼저 머지한다.

---

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `backend/src/lib/content_doc.py` | **신설** - 문서 검증기. 노드·마크 화이트리스트, paywall 최상위 최대 1개, image 키 ⊆ 매니페스트, 상한(노드 3,000·텍스트 100,000자·깊이 20), 링크 http(s)만. `has_meaningful_content`(공개 요건)·`derive_is_free`(경계 파생)·`EMPTY_DOC` 정규형 |
| `backend/src/models/work.py` | Episode에 `subtitle`(VARCHAR 200 NULL)·`content`(JSONB NOT NULL, EMPTY_DOC 기본) 추가. is_free는 파생 컬럼으로 주석 전환 |
| `backend/src/schemas/work.py` | EpisodeCreate: `episode_no` 생략 허용(자동 할당)·`title` 기본 "무제"·`subtitle` 추가·**is_free 입력 폐지**. EpisodeUpdate: `content`·`subtitle` 추가. AdminEpisodeRead: `content`·`subtitle` 노출 |
| `backend/src/services/episode_service.py` | create: episode_no `max+1` 자동 할당(UNIQUE 409 백스톱)·`is_free=True` 명시(빈 문서=무료 정합). update: content 검증→EMPTY_DOC 정규화→is_free 파생, 공개 요건을 `has_meaningful_content` 기준으로 교체 |
| `backend/src/lib/scheduler.py` | 예약 공개 가드 `jsonb_array_length(image_keys)` → `jsonb_array_length(content->'content')` (글만 있는 회차도 예약 공개 가능) |
| `backend/migrations/versions/20260715_1518_*.py` | 컬럼 추가 + 백필(image_keys → image 노드 나열, 유료 회차는 paywall 선행 = "전체 유료" 보존) + 0장 행 is_free=true 정규화 |
| `backend/src/services/r2_service.py` | `presign_get_urls`(만료 600초) - 관리자 미리보기용 presigned GET, M3에서 앞당김 |
| `backend/src/routers/admin_episodes.py` | `GET .../episodes/{id}/image-urls`(require_owner) - `{key, url}` 쌍 배열 |
| `backend/tests/` | test_content_doc.py **신설 26개**(순수 단위), test_admin_episodes.py 콘텐츠 모델 개정(+PUT content 섹션), test_scheduler.py 가드 기준 변경, test_r2_service.py presign 서명 계약 |

API 형태(D3 구조 A)는 불변 - draft POST / 장당 이미지 POST / PUT / 목록 GET / image-urls GET.
이미지 업로드 파이프라인(변환·R2·원자 append)도 무손상.

---

## 2. 주요 결정 (전문은 DECISIONS "에피소드 콘텐츠 모델")

### 본문 = 스키마 제한 JSON (HTML 미저장)
화이트리스트(`ALLOWED_NODE_TYPES`/`ALLOWED_MARK_TYPES`)가 곧 방어선 - 임의 태그·속성이
존재할 수 없어 XSS가 원천 차단된다. 렌더러(admin TipTap, M2 `generateHTML`)는 같은
화이트리스트 스키마로만 해석해야 한다(확장 시 서버·에디터·뷰어 동시 갱신).
리뷰(M1)로 두 구멍을 봉쇄: **marks는 text 노드 전용**(비-text 노드에 실린 link 마크가
href 스킴 검사를 우회하던 경로), **노드·마크 attrs 화이트리스트**(image=`{key}`,
link=`{href}`, 나머지 불허 - PR② 에디터는 TipTap Link 확장에서 target/rel/class attr
제거 필요, rel/target은 렌더러가 강제 부여).

### is_free = 파생 컬럼 (직접 입력 폐지)
유료 경계(paywall 노드) 위치가 진실이고 is_free는 "경계 뒤 유의미 콘텐츠 없음"의
비정규화 캐시다. 직접 입력을 남기면 경계와 이중 진실 - 불일치 버그 온상. 쓰기 경로가
content 저장 시마다 동기화하고, EpisodeCreate에서 필드 자체를 제거(보내면 무시).

### 빈 문서 정규화(EMPTY_DOC) → 스케줄러 SQL 가드 성립
유의미 내용 없는 문서(빈 paragraph·구분선만)를 그대로 저장하면 `content->'content'`
배열 길이 > 0이라 빈 회차가 예약 공개된다. 쓰기 경로가 EMPTY_DOC으로 접어주므로 잡은
`jsonb_array_length > 0` 한 조건으로 "내용 있음"을 판별한다(파이썬 재검사 불요).

### image_keys = 업로드 매니페스트, 최종 상태 기준 재검증
content의 image 키는 매니페스트의 부분집합(임의 키 주입 = 다른 회차·작품 원고 참조 차단).
**content가 요청에 없어도 image_keys가 바뀌면 재검증** - 키 삭제가 본문 참조를 끊는
조합(매니페스트 정리 요청)을 저장 전에 422로 잡는다. 길이-가드 조건부 UPDATE(D3)는
**content 변경에도 확장**(리뷰 m1): 검증에 쓴 매니페스트 스냅샷이 커밋 전에 바뀌면
(인플라이트 업로드·재배열) 409 - 동시 요청에서 부분집합 불변식이 깨지는 경로 봉쇄.

### 공개 요건 = 본문 유의미 콘텐츠 (이미지 장수 아님)
글만 있는 회차(공지·연재글)도 공개 가능해야 한다. 반대로 매니페스트에 이미지가 있어도
본문에 안 실렸으면 독자에게 아무것도 안 보이므로 공개 불가. 리뷰 ④(빈 draft 공개·공개
회차 전삭제 차단) 시맨틱은 기준만 바꿔 계승.

### 백필: 기존 유료 회차 = paywall 선행
구모델의 is_free=false는 "회차 전체 유료"였으므로 경계를 문서 맨 앞에 둬(미리보기 0)
의미를 보존한다. 0장 행은 is_free=true로 정규화(빈 문서=무료 파생 정합 - 구모델에서도
공개 전 임시값이라 손실 무해).

### episode_no 자동 할당 (캔버스 먼저 흐름)
> ⚠️ **폐기됨(2026-07-30)**: `episode_no`가 사라졌다. 독자 URL 조회키는 랜덤 `public_id`,
> 표시 순서는 별도 `sort_order`(UNIQUE 없음 - 유일 제약이 아래 409의 원인이었다)로
> 갈라졌다. 상세: `../../BE/Works/IMPLEMENTATION_EPISODE_PUBLIC_ID.md`.
> 같은 표의 `title` 기본 "무제"도 폐지됐다(제목 필수).

에디터는 "쓰기 시작 → 발행 모달에서 메타 확정" 순서라 draft 생성 시점에 번호가 없다.
생략 시 서버가 해당 작품 `max+1` - 동시 생성 경합은 SELECT 선검사가 아니라
UNIQUE(work_id, episode_no) 409가 백스톱(C1 태그와 동일 계열).

---

## 3. 후속 (이 PR에 없음)

- **에디터 PR(②)**: TipTap 캔버스·paywall 드래그 노드·발행 모달 (`admin/feat/episode-editor`)
- M2 뷰어: `generateHTML` 서버 렌더, `viewer_progress.page_no` 블록 인덱스 재해석
- M3: 미구매 독자 응답 = 서버가 paywall 이전 노드만 잘라 반환 + presigned GET에 결제 검증
- 매니페스트 미참조 키 정리(미참조 파일 정리 후속 노트와 통합)
- **#75**: content 저장 ↔ image_keys 축소 동시성(부분집합 불변식) - 행 버전 컬럼 후속에 편입
