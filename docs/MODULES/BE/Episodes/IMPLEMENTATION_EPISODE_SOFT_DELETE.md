# 회차 soft delete + 공개 내리기 (#85)

| 항목 | 내용 |
|------|------|
| 모듈 | BE / Episodes + Admin / Episodes |
| 관련 이슈 | #85 (공개된 회차를 내리는 수단이 없음) + 사용자 요청 "공개된 에피소드 삭제 기능" |
| 작성 시점 | 2026-07-26, 브랜치 `be/feat/episode-soft-delete` |
| 상태 | 구현 + `pytest` 426 passed(신규 18: soft delete 16 + JWT leeway 회귀 2), ruff check/format 클린, admin `vitest` 71(신규 11)·`eslint`·`build` 클린. **DB 마이그레이션 1**(`c3f0a1d4b25e`, nullable 컬럼 추가). Opus 리뷰 완료(§5) - 확정 1건(minor) 수정 반영 |
| 관련 문서 | DB_SCHEMA §episodes, `IMPLEMENTATION_EPISODE_DRAFT_SEPARATION.md`(#86 발행본 보호), `../../ADMIN/Episodes/IMPLEMENTATION_EPISODE_EDITOR.md` |

문제: 회차를 공개한 뒤 되돌릴 UI가 없었고(에디터 저장 경로는 #86 발행본 보호에 막혀 409), 잘못 올린 회차를 목록에서 치울 방법도 없었다.

---

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `models/work.py` | `Episode.deleted_at`(TIMESTAMPTZ, nullable) + `Work.episode_count` 상관 서브쿼리에 미삭제 조건 |
| `migrations/.../20260726_1130_episodes_soft_delete.py` | nullable 컬럼 1개 (`c3f0a1d4b25e`). UNIQUE는 손대지 않음 |
| `services/episode_service.py` | `soft_delete_episode` 신설, `get_episode`·`list_episodes` 필터, `_duplicate_no_message`(번호 소진 안내) |
| `routers/admin_episodes.py` | `DELETE /admin/works/{work_id}/episodes/{episode_id}` → 204 |
| `services/catalog_service.py` | `public_episode_filters()` 신설(공개+미삭제 단일 출처) - count·상세·존재확인 3곳에서 사용 |
| `services/episode_read_service.py` | 회차 본문 조회에 같은 필터 적용 |
| `lib/scheduler.py` | 예약 공개 잡에 `deleted_at IS NULL` 가드 |
| admin `hooks/useEpisodes.ts` | `useUnpublishEpisode`(is_published:false 단독) + `useDeleteEpisode` |
| admin `components/common/ActionsMenu.tsx` | 목록 "···" 드롭다운 껍데기 추출(작품·회차 공용) |
| admin `components/episodes/EpisodeActionsMenu.tsx` + `EpisodeList.tsx` | 메뉴 연결, 삭제 확인창 |

## 2. 주요 결정

- **soft delete(행 유지)**: 원고·업로드 매니페스트를 남겨 복구 가능성을 유지한다. R2 객체(`image_keys`)는 지우지 않는다.
- **"삭제 ⟹ 비공개" 불변식**: `deleted_at` 스탬프 + `is_published=false` + `published_at=NULL`을 **한 UPDATE**로 건다. 나눠 쓰면 "삭제됐는데 아직 공개"인 창이 생기고, 그 사이 독자 요청 하나가 통과하면 되돌릴 수 없다. `deleted_at IS NULL` 조건부라 동시 삭제는 한쪽만 이긴다(rowcount 0 = 409).
- **회차 번호는 소진된다**: `UNIQUE(work_id, episode_no)`가 `deleted_at`을 보지 않으므로 삭제 행이 번호를 계속 점유한다. 부분 유니크 인덱스로 바꿔 재사용을 허용하는 안은 **기각** - 독자 URL이 `/works/{작품}/{회차번호}`라, 번호를 재사용하면 기존 북마크·공유 링크가 다른 내용을 가리킨다. 대신 ①자동 할당(max+1)이 삭제분을 세도록 두고 ②충돌 시 "삭제된 회차가 사용 중인 번호입니다"로 문구를 갈라 목록에 없는 번호로 409를 받는 혼란을 없앴다.
- **독자 경로에 중복 방어를 건다**: 계획 단계에선 "독자 경로는 전부 `is_published=true`를 보므로 불변식만으로 충분"이었으나, 그러면 불변식이 깨지는 순간 노출 경로 4곳이 동시에 뚫린다. `public_episode_filters()`(공개+미삭제)를 단일 출처로 만들어 명시했다. `is_published = true`를 그대로 포함하므로 partial 인덱스는 계속 탄다.
- **재공개 경로 봉쇄**: `get_episode`가 라우터의 `_episode_or_404` 관문이라, 여기서 걸러야 삭제된 회차의 PUT·이미지 업로드가 전부 404가 된다. 특히 PUT이 막혀야 불변식을 되돌릴 수단이 없어진다. 스케줄러 가드는 중복 방어다(soft delete가 `published_at`을 비우므로 기존 조건만으로도 안 걸리지만, 이 잡이 비공개→공개를 자동으로 뒤집는 유일한 경로라 명시).
- **공개 버킷 썸네일은 지운다**: 회차 썸네일 축소본은 서명 없이 열리는 공개 객체라, 남기면 회차를 내린 뒤에도 URL을 아는 사람에게 계속 서빙된다. 페이지 원본에서 다시 만들 수 있는 파생물이라 지워도 복구성이 줄지 않는다. DB 커밋 **후** 삭제하고, 실패는 경고 로그만 남기고 삼킨다 - 이미 커밋된 삭제를 5xx로 뒤집어 보여주면 관리자가 재시도해 404를 받는다.
- **DELETE는 멱등이 아니다**: 이미 삭제된 회차는 404. "지웠는데 204가 또 온다"보다 "그 회차는 이미 없다"가 관리자에게 정확한 정보다. 되살리는 엔드포인트는 두지 않는다.
- **비공개 전환은 전용 훅**: 에디터 저장(`useUpdateEpisode`)은 `content`를 항상 동봉하는데 공개 회차에 `content`를 보내면 #86 발행본 보호가 409를 낸다. 목록 메뉴는 `is_published:false`만 단독 전송한다.

## 3. 테스트 - 변이 실험으로 판별력 확인

가드를 5개 전부 제거하고 돌려 **9건이 죽는 것**을 확인했다(가드마다 최소 1건 대응). 원복 후 424 그린 재확인.

| 제거한 가드 | 죽은 테스트 |
|---|---|
| `list_episodes` 미삭제 필터 | 1 (삭제 후 목록에서 사라짐) |
| `soft_delete_episode`의 공개 해제 | 1 (불변식 3종 단언) |
| `Work.episode_count` 미삭제 조건 | 1 (총 N화 감소) |
| `public_episode_filters()` 미삭제 조건 | 5 (카탈로그 3 + 본문 404 + 진행도 404) |
| 스케줄러 `deleted_at` 가드 | 1 (삭제된 예약 회차 재공개 안 됨) |

독자 경로 테스트는 **`is_published=true`인 채로 `deleted_at`만 세운 행**으로 만든다. 비공개로 만들면 기존 필터에 먼저 걸려 새 가드가 없어도 통과하는, 판별력 0의 테스트가 된다(#84 교훈).

admin 쪽도 같은 방식으로 확인했다 - "비공개로 전환" 조건 제거 시 1건, 전환 PUT에 `content` 동봉 시 2건(컴포넌트·훅), 리뷰 후 추가한 직렬화 잠금을 행 단위로 되돌리면 1건.

## 4. 이연 / 후속

- **예약 취소 액션 없음**: 예약(미공개 + 미래 `published_at`) 회차의 예약만 푸는 항목은 두지 않았다. 서버가 `is_published:false`에 `published_at`도 함께 비우므로 "내리기"와 겸용하면 의도가 섞인다.
- **복구(undelete) 없음**: DB 직접 조작으로만 가능. 필요해지면 별건.
- **삭제 회차의 R2 원고 정리**: soft delete라 남긴다. 영구 삭제 정책은 미정.
- **테스트 간헐 실패(해결됨 - 2026-07-27)**: 이 브랜치 작업 중 전체 `pytest`가 ~17회 중 3회 임의 테스트 1개가 401로 죽는 현상을 관측했다. 원인은 이 diff가 아니라 **WSL2/NTP 시계 역점프**(~1.9초, PG 로그 타임스탬프 역행으로 실측) - 토큰 발급 직후 시계가 뒤로 가면 JWT `iat`가 미래가 돼 PyJWT가 ImmatureSignatureError로 거부한다. `jwt.decode` 3곳에 `leeway=10초`(`JWT_LEEWAY_SECONDS`)를 추가하고 회귀 테스트 2건(iat 미래 토큰 - 단위 + TOTP stage2 통합)으로 고정했다. M1부터 잠복하던 문제로 #85와 무관, 상세 경위는 MISTAKES "시계는 단조가 아니다" 항목.
- **WorkActionsMenu(작품 목록)도 같은 최신-mutate 추적 문제 보유**: §5의 확정 결함과 동일 패턴이 main 기존 코드에 있다. 이번 diff 밖이라 손대지 않음 - 직렬화 잠금 패턴을 옮겨 심는 것은 별건.

## 5. 커밋 전 리뷰 (2026-07-27, /code-review 워크플로)

Opus 25에이전트(7관점 발견 + 발견당 반박 검증 2인). 발견 18건 중 **17건 기각**(반박 근거로 설계가 맞음을 재확인: 썸네일만 지우고 원고를 남기는 비대칭은 의도, `deleted_at` 방어는 노출 경로 전부에 존재, `is_published`만 보는 쿼리 부재), **확정 1건(minor)**:

- **동시 같은 종류 mutate 시 앞선 요청의 실패 표시 유실**: TanStack Query의 훅 옵저버는 가장 최근 `mutate()` 하나만 추적한다. 삭제가 인플라이트인 상태에서 다른 행의 삭제를 또 발사하면 앞선 요청이 실패해도 `isError`가 화면에 안 뜨고, 행 잠금이 새 행으로 옮겨간다(검증자가 임시 vitest로 실측 재현).
- 수정: **같은 종류 액션의 직렬화** - 어느 행이든 삭제가 진행 중이면 모든 행의 삭제 항목을 잠근다(`deleteLocked`, 비공개 전환도 동일). 종류가 다르면(내리기 vs 삭제) 별개 훅 인스턴스라 간섭이 없어 잠그지 않는다. 회귀 vitest 1건 + 변이 검증(행 단위 잠금으로 되돌리면 red).
