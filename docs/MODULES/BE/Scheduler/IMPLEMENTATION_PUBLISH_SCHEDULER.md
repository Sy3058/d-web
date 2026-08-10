# 예약 공개 스케줄러 + 만료 토큰 정리 (M1.5 그룹 E - E1, #57)

| 항목 | 내용 |
|------|------|
| 모듈 | Backend / Scheduler |
| 관련 마일스톤 | [M1.5](../../../milestones/M1.5_foundation.md) 그룹 E - E1 (ADM-04) + 이슈 #57 |
| 작성 시점 | M1.5 E1 (2026-07-13) |
| 상태 | 구현 + Opus 계획 리뷰(Critical 1·Major 4 착수 전 반영) + Opus 코드 리뷰(**Critical/Major 0**, Nit 1 수정). `pytest` 243 passed(신규 8), ruff·`alembic check` 클린, uvicorn 부팅 스모크(잡 2개 등록 + cleanup 즉시 발화) 통과. **DB 마이그레이션 0** |
| 관련 문서 | M1.5_foundation.md E1 배너, IMPLEMENTATION_EPISODE_UPLOAD.md(D3 - 공개 시맨틱 인계), MISTAKES.md |

D3까지 쌓인 예약 상태(`published_at`)를 실제로 발화시키는 in-process 스케줄러.
같은 인프라에 M1부터 이관돼 온 만료 토큰 정리 잡(#57)을 얹었다.

### E3 후속: 실제 최초 공개 시각(2026-08-11)

예약 목표 시각은 `published_at`, 독자 표시용 실제 최초 공개 전환 시각은 `first_published_at`으로 분리한다. 폴링 UPDATE는 `coalesce(first_published_at, now())`를 사용해 최초 전환 때만 DB 시각을 기록하고 재공개에서는 유지한다. 빈 본문 때문에 예약 목표를 넘긴 뒤 나중에 공개되는 회차가 과거 날짜로 표시되지 않도록, 예약 목표와 실제 전환 시각을 다르게 둔 회귀 테스트로 고정한다.

---

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `backend/src/lib/scheduler.py` | 신설. 잡 본체 2개(session 주입 순수 함수) + 스케줄러용 래퍼 + `EVENT_JOB_ERROR`→Sentry 리스너 + `create_scheduler()` |
| `backend/src/main.py` | lifespan에서 `start()` / 종료 시 `shutdown(wait=False)` |
| `backend/src/services/episode_service.py` | **D3 하드닝**: false 전환 시 페이로드 무관 `published_at` 강제 NULL(`elif`→`else`) |
| `backend/src/schemas/work.py` | `EpisodeUpdate` docstring을 하드닝된 계약으로 갱신(코드 리뷰 Nit) |
| `backend/tests/test_scheduler.py` | 신설 7개: 공개 전환(과거/미래/0장/예약없음/멱등) + cleanup(만료 삭제·보존, 3테이블) |
| `backend/tests/test_admin_episodes.py` | stale 에코 동봉 비공개 전환 케이스 추가 |

새 의존성: `apscheduler==3.11.3`(설치 직전 WebSearch + 공식 문서 확인).

**잡 1 - 공개 전환 (60초 폴링)**: 원자 UPDATE 1문(멱등), DB `now()` 기준.
`WHERE is_published=false AND published_at IS NOT NULL AND published_at<=now() AND jsonb_array_length(image_keys)>0`

**잡 2 - 만료 토큰 정리 (24시간 + 기동 직후 1회)**: `refresh_tokens`·`trusted_devices`·`email_verifications`에서 `expires_at<=now()` 행 DELETE.

---

## 2. 주요 결정

### in-process 폴링 채택 (지연 큐·lazy 평가 미채택 - 마일스톤 확정)
cron+엔드포인트·Redis 지연 큐는 외부 의존(단일 VPS 단순성 위배), lazy 평가(조회
쿼리에서 `published_at<=now()` 계산)는 공개 "이벤트"가 없어 M6 알림 훅을 걸 곳이
없고 조건이 모든 조회 경로에 전파돼야 한다(하나 빠지면 미공개 노출). 폴링+원자
UPDATE는 멱등이라 재시작·중복 발화에 견고. **단일 워커 전제**(멀티워커 중복
발화는 멱등이라 무해하나 낭비 - advisory lock 후속). 배포 시 `--workers 1` 확인.

### cleanup 삭제 기준 = expires_at 경과만 (이슈 #57 본문과 의도적 차이)
이슈는 "만료 **또는** revoked 삭제"였으나 revoked 행은 refresh 회전 재사용
탐지(M1 C4)의 근거 데이터 - 만료 전에 지우면 탈취 토큰 재사용이 "세션 전체
revoke" 대신 조용한 401로 퇴화한다. 만료되면 revoked 여부와 무관하게 삭제되므로
결국 전부 정리된다. 대상 3테이블은 사용자 승인으로 #57(refresh만)에서 확장.

### 잡 본체 = session 주입 순수 함수 (계획 리뷰 Major)
잡이 `async_session_maker`를 직접 열면 conftest `test_engine`(별도 DB) 격리 밖 -
`test_database_url` 설정 시 dev DB 오염 + 테스트 거짓 통과. 본체는 session
파라미터를 받고(테스트가 주입), 스케줄러에는 자체 세션을 여는 얇은 래퍼만 등록.
세션 컨텍스트 종료는 rollback이므로 본체가 명시 commit.

### D3 하드닝: false 전환 시 published_at 페이로드 무관 강제 NULL (계획 리뷰 Critical)
D3의 `elif "published_at" not in changes` 가지는 페이로드에 published_at이
동봉되면 NULL 초기화를 건너뛰었다 - E1 이전엔 무해했지만, 폴링이 생기는 순간
전필드 PUT 폼의 stale 에코(과거 시각)가 "관리자가 내린 회차를 60초 안에 재공개"
하는 경로가 된다. 잡은 DB 상태 `(false, 과거시각)`만으로 "예약 draft"와 "수동
하차"를 구분할 수 없으므로 방어는 쓰기 경로 몫. 422가 아니라 강제 NULL인 이유:
동봉 값은 대부분 폼의 stale 에코라 자동 치유가 맞다(422면 정상 폼이 계속 깨짐).

### APScheduler 설정 (계획 리뷰 Major·Nit)
- `next_run_time=now`(cleanup): interval 첫 발화는 등록+24h라 잦은 재배포에서
  영영 안 돎 → 기동 직후 1회 보장.
- `misfire_grace_time=None`: 기본 1초는 그만큼 늦은 틱을 스킵(24h 잡이면 하루
  통째) - 멱등 잡이라 "늦어도 무조건 실행"이 안전.
- `EVENT_JOB_ERROR` 리스너: APScheduler는 잡 예외를 삼키고 다음 틱 재시도
  (스케줄러는 안 죽음). 자체 로거로만 남으면 반복 실패를 못 알아채므로
  `sentry_sdk.capture_exception` + structlog error로 승격.
- `timezone=UTC` 명시(tzlocal 추정 회피), `start()`는 lifespan에서(호출 시점의
  실행 중 루프에 바인딩 - import 시점이면 different loop 계열 사고).

---

## 3. 프런트(F그룹) 인계 계약

- **순수 메타 수정 PUT에 `is_published`를 에코하지 말 것**: `is_published=false`가
  실리면 서버가 published_at을 무조건 NULL로 밀어 미래 예약이 조용히 풀린다.
  예약 설정은 `is_published` 없이 `published_at`만 전송(D3 계약 유지).
- **과거 예약이 걸린 0장 draft에 첫 이미지를 올리면 다음 틱에 즉시 공개**된다
  ("메타 먼저" 워크플로의 의도된 결과) - F3/F4 UI에서 안내 고려.

## 4. 리뷰

- **계획 리뷰**(Opus, 착수 전): Critical 1(D3 부활 방어 불완전 - 하드닝으로 반영),
  Major 4(테스트 격리 충돌→주입식 / Sentry 미전달→리스너 / 첫 발화 +24h→now /
  ruff E712→`.is_(False)`) 전부 착수 전 반영.
- **코드 리뷰**(Opus): Critical/Major 0. Nit 1(schemas docstring stale - 수정),
  FYI 3(프런트 계약 §3 명시 / `--workers 1` 배포 확인 / 커버리지 보강 여지).

## 5. 이연 / 후속

| 항목 | 이동처 |
|------|--------|
| 멀티워커 잡 중복 방지(advisory lock 또는 스케줄러 단일 프로세스화) | 멀티워커 전환 시 |
| 폴링용 partial index(`WHERE is_published=false AND published_at IS NOT NULL`) | 폴링 대상 증가 시(마일스톤 명시) |
| 혼재 배치 테스트(due+future+공개+빈 draft 한 UPDATE) / revoked+expired 삭제 직접 검증 | 후속으로 충분(코드 리뷰 판정) |
| 공개 시점 알림 발송(PRD Flow 3 step 10) | M6 (`is_published` 전환 훅) |
| `--workers 1` 배포 설정 고정 확인 | M7 배포 |
