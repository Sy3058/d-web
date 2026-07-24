# 발행본/편집본 분리 - episodes.draft (#86)

| 항목 | 내용 |
|------|------|
| 모듈 | BE / Episodes + Admin / Episodes |
| 관련 이슈 | #86 ("임시저장"이 발행된 회차에선 즉시 라이브 반영) |
| 작성 시점 | 2026-07-23, 브랜치 `be/feat/episode-draft-separation` |
| 상태 | 구현 + `pytest` 407 passed(신규 draft 10 포함), ruff·`alembic upgrade`/`check` 클린, admin `vitest` 60·`eslint`·`build` 클린. **DB 마이그레이션 1**(`b97cd9397338`, nullable 컬럼 추가). Opus 리뷰 통과(2026-07-25, Critical/Major 0 - 독자 유출 경로·불변식·race 가드·테스트 전수 확인, FYI 1건 반영) |
| 관련 문서 | DECISIONS "에피소드 콘텐츠 모델" 발행본/편집본 분리 절(결정 전문), DB_SCHEMA §episodes, `../../ADMIN/Episodes/IMPLEMENTATION_EPISODE_EDITOR.md` |

문제: `EpisodeEditor.onSaveDraft`가 공개 회차에서도 `content`를 그대로 PUT해 **미완성 원고가 즉시 독자에게 반영**됐고, 에디터 안내 문구("임시저장은 비공개로 남고...")는 신규 draft에서만 참이었다. "임시저장 = `is_published=false`" 등식이 원인 - 임시저장은 공개 여부와 무관한 개념이어야 한다.

---

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `models/work.py` | `Episode.draft` (JSONB, nullable) - 편집본 봉투 `{"title","subtitle","content"}`, NULL = 없음 |
| `migrations/.../20260723_0946_episodes_draft.py` | nullable 컬럼 1개 추가 (`b97cd9397338`) |
| `schemas/work.py` | `EpisodeDraft`(봉투 스키마) + `EpisodeUpdate.draft`(content와 상호배타 422, 명시적 null = 버리기) + `AdminEpisodeRead.draft` |
| `services/episode_service.py` | `update_episode` 불변식 4종 (아래 §2) |
| admin `EpisodeEditor.tsx` | 공개 회차 임시저장 -> draft 봉투 PUT, draft 우선 로드(`draft ?? content`), 배너 + 버리기, 발행 버튼 "수정 반영", 문구 분기 |
| admin `PublishModal.tsx` | `isLive` 모드 - 공개 시점(지금/예약) 토글 숨김, "수정 반영" 라벨 |
| admin `EpisodeList.tsx` | 임시저장본 배지 (`draft != null`) |
| admin `types/index.ts` | `EpisodeDraft` 별칭 + `api.gen.ts` 재생성 |

## 2. 주요 결정 (전문은 DECISIONS)

- **봉투에 메타 포함**: draft가 본문만 담으면 공개 회차의 제목·부제 수정이 여전히 임시저장 즉시 라이브 반영되는 반쪽 분리다.
- **서버 불변식** (`update_episode`):
  1. `draft`·`content` 동시 전송 = 422 (임시저장과 발행은 다른 액션)
  2. **공개 회차의 `content`는 `is_published` 동반 요청만 덮는다** - 위반 409. 클라 분기만으로는 "예약 회차를 편집하다 자정 넘겨 임시저장 -> 스케줄러가 이미 공개 전환" race에서 사고가 재발하므로, 조건부 UPDATE `WHERE is_published = false` 가드로 원자 봉쇄(같은 rowcount 패턴 - refresh 회전·TOTP 전진과 동계열)
  3. `content` 쓰기는 `draft`를 항상 NULL로 소진 - 발행 = 승격. 별도 promote 엔드포인트를 두지 않는 이유: 에디터가 항상 최신 문서를 들고 있어 "stale draft 승격" 혼동이 원천 차단된다
  4. draft 검증 = 발행본과 동일(`validate_content` 화이트리스트·상한·image_keys 부분집합). 매니페스트 축소가 저장된 draft의 참조 키를 지우면 422 - 검증 안 된 문서가 DB에 사는 상태를 만들지 않는다
- **`AdminEpisodeRead.draft`는 `EpisodeDraft` 정타입**: `dict`로 두면 openapi codegen이 `{[key: string]: unknown}`으로 뽑아 admin에서 `draft.title` 접근이 tsc 에러(실측). 쓰기 경로가 같은 스키마로 검증하므로 저장된 봉투는 항상 이 형태다.
- **독자 응답 무접촉**: 공개 DTO(catalog·viewer)는 변경 0. `test_catalog`·`test_episode_content`의 부재-단언("draft 필드·편집본 텍스트가 응답에 없음")으로 회귀 고정.
- **신규 회차는 기존 흐름 유지**: 비공개 회차의 `content` 직접 편집은 그 자체가 draft(독자 무접촉). "아직 발행 안 함"과 "임시저장"은 문구만 분리.
- **기존 테스트 1건 계약 갱신**: `test_published_episode_cannot_clear_content` - 공개 회차 본문 전삭제가 이제 두 단계로 막힌다(발행 액션 없으면 409, 있으면 기존 422).

## 3. 이연 / 후속

| 항목 | 비고 |
|------|------|
| 비공개 내리기 UI | #85 (BE는 기존 지원) |
| 버전 이력(스냅샷 여러 개) | 티스토리식 - 1인 작가에 과함, 수요 생기면 |
| 자동저장(주기적 draft 저장) | 후속 - draft 인프라 위에 얹기만 하면 됨 |
| #75 버전 컬럼 | content·draft·image_keys 경합의 일반 해법 - 기존 길이-가드 수준 유지 |
