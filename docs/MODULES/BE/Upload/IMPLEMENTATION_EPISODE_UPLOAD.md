# 에피소드 업로드/수정 + 표지 업로드 (M1.5 그룹 D - D3)

| 항목 | 내용 |
|------|------|
| 모듈 | Backend / Upload |
| 관련 마일스톤 | [M1.5](../../../milestones/M1.5_foundation.md) 그룹 D - D3 (ADM-03 엔드포인트 계층) |
| 작성 시점 | M1.5 D3 (2026-07-11) |
| 상태 | 구현 + /council 5렌즈 계획 검증(착수 전) + 강 모델 코드 리뷰(파인더 8앵글) 발견 10건 전부 수정. `pytest` 235 passed(신규 36), ruff·`alembic check` 클린, uvicorn 부팅 스모크 통과. **DB 마이그레이션 0** |
| 관련 문서 | M1.5_foundation.md D3 배너·결정 1·2, IMPLEMENTATION_R2_IMAGE_SERVICES.md(D1+D2), MISTAKES.md |

D1(R2)·D2(변환) 서비스를 묶는 관리자 에피소드 엔드포인트. C1에서 이연된 표지 단건 업로드 포함.

---

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `backend/src/routers/admin_episodes.py` | 4 엔드포인트(아래 표), 전부 `require_owner` |
| `backend/src/routers/admin_works.py` | `POST /admin/works/{id}/cover` 추가(표지 단건: 변환→`cover.webp` 덮어쓰기→`cover_image` 갱신) |
| `backend/src/services/episode_service.py` | draft 생성(UNIQUE→409) / 원자 append(조건부 UPDATE) / 부분수정·재배열·썸네일·공개 시맨틱 |
| `backend/src/services/work_service.py` | `set_cover_image` 추가 |
| `backend/src/services/r2_service.py` | `episode_page_key` 파일명 순번→**uuid** 전환(리뷰 - 키 스킴 변경) |
| `backend/src/lib/uploads.py` | 공용 업로드 배관(바운디드 read + R2 503 상수) - 라우터 간 사설 cross-import 제거 |
| `backend/src/lib/exceptions.py` | `EpisodeConflictError`(409)·`EpisodeValidationError`(422) |
| `backend/src/schemas/work.py` | `EpisodeCreate`(thumbnail 제거·published_at 추가)/`EpisodeUpdate`/`AdminEpisodeRead` 개명 |
| `backend/tests/` | test_admin_episodes.py 34개 + test_r2_service 키 계약 갱신 (전체 235) |

| 엔드포인트 | 형식 | 역할 |
|-----------|------|------|
| `POST /admin/works/{id}/episodes` | JSON | draft 생성. episode_no 중복은 이미지 업로드 전 즉시 409 |
| `POST .../episodes/{id}/images` | multipart 단건 | 1장 변환→R2→원자 append. 메모리·재시도·미참조 파일(orphan) 전부 1장 단위 |
| `PUT .../episodes/{id}` | JSON | 메타 부분수정 + 재배열/삭제(부분집합) + 썸네일 선택 + 공개(즉시/예약) |
| `GET .../episodes` | - | 목록만(`AdminEpisodeRead`, image_keys 포함 - 상세 GET 불요) |

새 의존성: `python-multipart>=0.0.32`(설치 직전 WebSearch 확인).

---

## 2. 주요 결정

### 구조 A = 장당 업로드 + JSON 메타 분리 (단일 multipart 일괄안 폐기)
착수 전 /council(5렌즈 + 합성)이 원안의 블로커를 적발: (a) PUT의 부분수정 검증(`model_fields_set`)이 Form 인코딩에서 불성립 (b) episode_id 선행 딜레마(flush 장기 트랜잭션 vs 앱측 uuid는 409가 50장 업로드 후 발각) (c) Starlette은 핸들러 전에 바디 전체를 스풀해 "장수 선검증"이 크기 방어가 안 됨 (d) 원본 50장 동시 보유 메모리 피크. 합성 에이전트의 "5명 전원이 놓친 것"이 구조 A - **장당 요청으로 쪼개면 네 문제가 패치가 아니라 구조적으로 소멸**한다. 결정 1(백엔드 경유 변환)과 양립(presigned 아님). 트레이드오프: 요청 50번(1인 admin이라 무의미), F3가 순차 전송 반복문 보유, 마일스톤 D3 산출물 문구 수정.

### 페이지 키 파일명 = uuid (순번 `{page:03d}` 폐기 - D1 키 스킴 변경)
순서의 진실은 `image_keys` 배열이라 파일명은 순수 식별자인데, 순번은 앱이 stale 스냅샷으로 다음 번호를 계산해 **동시 업로드 두 건이 같은 키에 PUT → 승자가 참조하는 객체를 패자가 에러 없이 덮어씀**(S3 PUT 시맨틱, 리뷰 CONFIRMED). uuid는 조정 없이 충돌 불가 + 순번 방식의 0~999 상한(bare ValueError 500)도 소멸 + M3 CDN 캐시의 키 재사용 고민도 해소.

### 원자 append = 길이-가드 조건부 UPDATE (db-atomic-claim)
`UPDATE ... SET image_keys = image_keys || key WHERE id=? AND jsonb_array_length=기대값 AND < 50` - 경합(stale 스냅샷)과 51장 race를 한 문장으로 차단, rowcount 0 → 409. **PUT 재배열도 같은 길이-가드**로 실행(리뷰: 무보호 last-write-wins면 200을 받은 인플라이트 업로드 결과를 stale 배열이 조용히 삭제). 메타만 바꾸는 PUT은 ORM 경로(lost update는 단일 owner 수용). R2 업로드가 DB보다 먼저 - 실패 시 미참조 파일 최대 1개(깨진 참조보다 쌈), 정리는 후속 노트.

### 공개 시맨틱 (리뷰 - E1·M2 계약)
true 전환 시 `published_at`이 요청에 없고 NULL·미래면 now 스탬프(공개 회차는 항상 유효한 공개 시각 - M2 정렬·partial index 계약). false 전환 시 미지정이면 NULL 초기화 - 안 지우면 E1 폴링(`is_published=false AND published_at<=now` → 공개)이 다음 틱에 되살린다. 공개 결과 상태는 최소 1페이지(빈 draft 공개·공개 회차 전체 삭제 422). 예약 draft는 허용 → **E1 인계: 공개 전환 UPDATE에 `jsonb_array_length > 0` 추가**.

### 썸네일 = 업로드된 페이지 중 직접 선택 (2026-07-10 사용자 확정)
웹툰 관행상 표지 일러스트는 중간의 특정 페이지라 "첫 페이지 자동"은 틀린 기본값. PUT `thumbnail`로 저장(컬럼 기존 - 마이그레이션 0), 검증은 **최종** image_keys 기준(재배열과 같은 요청 정합), 재배열로 선택 페이지가 제거되면 자동 NULL(조회측 첫 페이지 fallback). EpisodeCreate엔 thumbnail 없음 - draft엔 검증할 키가 없어 임의 키 주입 통로가 됨.

### 그 외 (리뷰 반영)
- `AdminEpisodeRead` 명명: image_keys(R2 키) 노출은 관리자 전용 - M2 독자 라우터가 `EpisodeRead`를 무심코 재사용해 키가 새는 경로를 이름 계층에서 차단.
- `get_episode`가 Work join + `deleted_at` 필터: soft-delete된 작품의 에피소드에 업로드·공개되던 비대칭 봉쇄.
- `published_at` = Pydantic `AwareDatetime`: naive 시각 422(KST 로컬 시각이 UTC로 오해석돼 9시간 밀리는 조용한 오동작 차단).
- validate-then-mutate: 검증 실패 raise 경로에 세션 dirty 변이 잔류 금지.
- 업로드 핸들러가 변환·R2 전에 `session.rollback()`으로 읽기 트랜잭션 종료 - 외부 I/O(재시도 시 분 단위) 동안 asyncpg 커넥션 idle-in-transaction 점유 방지(표지는 저빈도라 미적용).
- `lib/uploads.py`: 바운디드 read(`MAX+1` - 자체 검사 없이 image_service가 단일 출처로 거부), R2 503 상수 공유.

---

## 3. 리뷰 (강 모델, /code-review high)

파인더 8앵글 → 후보 검증(검증자 4 완료 + 5는 세션 한도 중단 → 컨텍스트 내 코드로 자체 판정, PLAUSIBLE 강등 표기). **발견 10건 전부 수정**: 동시 append 키 충돌 / PUT 재배열 유실 / 공개 시맨틱 구멍 / 빈 회차 공개 / soft-delete 스코프 / naive datetime / 순번 키 999 상한 500 / 변이-후-검증 / idle-in-transaction / 공유 배관 사설 cross-import. 교훈: **리뷰 에이전트는 `model: opus`로**(Fable 상속이 토큰 과다로 세션 한도 유발 - 메모리 기록).

## 4. 이연 / 후속

| 항목 | 이동처 |
|------|--------|
| E1 공개 전환 UPDATE에 `jsonb_array_length > 0` | E1 (마일스톤 인계 명시) |
| 미참조 파일(orphan) 정리(append 실패 1장·재배열 삭제분) | 후속 노트(스토리지 저가, 차단 아님) |
| 페이지 단위 R2 delete_bytes | 삭제는 미참조 파일 허용으로 대체 - 필요 실감 시 |
| 관리자 GET 에피소드 상세 | 목록의 image_keys로 충분 - F3 계약이 요구할 때 |
| Caddy request body 캡 | 배포 노트(단건 구조라 앱 레벨 20MB로 충분) |
| owner/owner_client 테스트 픽스처 conftest 승격 | 세 번째 admin 테스트 파일 생길 때(E1) |
| Signed URL(GET)·미결제 잠금 | M3 |
