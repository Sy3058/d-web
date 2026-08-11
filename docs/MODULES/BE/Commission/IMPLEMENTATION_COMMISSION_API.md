# 커미션 카드·사이트 문구 API (M2 그룹 G PR1)

| 항목 | 내용 |
|------|------|
| 모듈 | Backend / Commission |
| 관련 마일스톤 | [M2](../../../milestones/M2_foundation.md) 그룹 G (2026-07-29 카드 모델 재정의) |
| 작성 시점 | M2 G PR1 (2026-07-29) |
| 상태 | 구현 + 코드 리뷰 반영. PR2 머지 전 리뷰에서 컬렉션 벌크 재정렬과 서버 `sort_order` 배정을 추가(커미션 24 / 전체 backend 466 passed, 변경 범위 ruff 클린). **DB 마이그레이션 1개**(기존 테이블 2: commission_items·site_texts, PR2 추가 migration 없음) |
| 관련 문서 | DB_SCHEMA.md §2 commission_items·site_texts, M2_foundation.md 그룹 G, DECISIONS "랜딩 페이지 구성 + 커미션 단계 분리" |

크레페식 커미션 홍보 카드(제목·가격/기간 자유문자열·샘플 이미지·슬롯 마감)와 작가가 admin에서 편집하는 사이트 문구(랜딩 소개·커미션 유의사항)의 백엔드. **작가는 리포에 접근할 수 없다**는 사실이 세션 중 확인돼 원래 결정 4(마크다운 content collection)를 폐기하고 DB + admin 편집으로 재설계했다(경위·council 리뷰는 M2_foundation 그룹 G 절에 반영 예정 - PR4).

---

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `backend/src/models/commission.py` | `CommissionItem` / `SiteTextKey`(StrEnum) / `SiteText` |
| `backend/migrations/versions/20260728_1728_commission_items_and_site_texts.py` | 테이블 2개 (리비전 `7f25d827c9ab`) |
| `backend/src/schemas/commission.py` | admin Create/Update/Reorder/Read(+`sample_images` key·URL 쌍) / 공개 `PublicCommissionItem`(URL만) / `SiteTextRead`·`SiteTextUpdate` |
| `backend/src/services/commission_service.py` | CRUD·벌크 재정렬·원자 append·삭제분 공개 버킷 정리·ON CONFLICT upsert |
| `backend/src/routers/admin_commission.py` | owner 전용 8개 엔드포인트 |
| `backend/src/routers/commission.py` | 공개 2개 엔드포인트 |
| `backend/src/lib/exceptions.py` | `CommissionConflictError`(409)·`CommissionValidationError`(422) 추가 |
| `backend/src/services/r2_service.py` | `commission_sample_key()` 추가 |
| `backend/tests/test_commission.py` | 24케이스 |

| 엔드포인트 | 인증 | 역할 |
|-----------|------|------|
| `GET/POST /admin/commission-items` | owner | 목록(sort_order순)·생성 |
| `PUT /admin/commission-items` | owner | 카드 전량 ID 순서로 sort_order 원자 재배정 |
| `PUT/DELETE /admin/commission-items/{id}` | owner | 부분수정(매니페스트 축소 포함)·하드 삭제 |
| `POST /admin/commission-items/{id}/images` | owner | 샘플 1장 업로드(변환→공개 버킷→원자 append) |
| `GET/PUT /admin/site-texts/{key}` | owner | 문구 조회(행 없음=빈 기본값)·upsert |
| `GET /commission-items` | 불요 | 공개 카드 목록(마감 포함, URL만) |
| `GET /site-texts/{key}` | 불요 | 공개 문구(무등록 key 422, 미저장 404 no-store) |

---

## 2. 주요 결정

### 샘플 이미지 = 공개 버킷(dweb-cover), 회차 업로드 구조 복제
커미션 예시는 원고가 아니라 **의도적으로 공개하는 미끼 자산**이라 표지·썸네일과 같은 부류다(M2 결정 2 - 버킷은 "공개 정책"으로 정한다). 업로드 흐름은 `admin_episodes.upload_episode_image`와 동일(선검증 → 읽기 트랜잭션 rollback → 변환 → R2 → 조건부 UPDATE 원자 append)하고 대상 버킷만 다르다. 키는 `commission/{item_id}/{uuid4hex}.webp` - 유일 키라 표지(고정 키 덮어쓰기)와 달리 캐시 버스터가 필요 없다. `upload_bytes`가 `bucket or settings.r2_bucket`으로 **원고 버킷에 폴백**하는 구조라, mock의 bucket 인자 단언이 라우팅 회귀의 유일한 탐지 수단이다(테스트 고정, 리뷰 뮤테이션으로 탐지력 실증).

### price_text = 표시 전용 자유 문자열
커미션은 사이트 결제 대상이 아니다(M5도 이메일 접수) - "50,000원~"·"오마카세" 같은 범위·협의 표기가 필요해 숫자 컬럼 대신 VARCHAR(100). 결제가 붙는 시점(로드맵 없음)에 재설계한다.

### 하드 삭제 (works와 다른 선택)
참조하는 자식 테이블·독자 URL이 없어 soft delete가 지킬 것이 없다. 삭제·매니페스트 축소로 빠진 샘플 객체는 **커밋 성공 후** 공개 버킷에서 정리한다(D2 순서 패턴 - 먼저 지우면 DB 실패 시 깨진 참조, 나중이면 실패해도 무해한 미참조 파일). 정리는 베스트 에포트 + 장당 `exc_info` 로깅 - 형제(`episode_service:408`)와 달리 개별 try로 감싸 한 장 실패가 나머지 정리·요청 성공을 막지 않는다(리뷰 Good 항목 - 형제의 약점 보정).

### SiteText 시딩 규약: 행 없음 ≠ 404 (admin 한정)
행은 시딩하지 않는다. admin GET은 행 없음을 `{key, body: "", updated_at: null}`로 응답해 첫 편집 진입이 막히지 않게 하고, PUT이 `ON CONFLICT DO UPDATE` upsert로 생성한다(check-then-insert는 동시 첫 저장 PK 충돌 500). `updated_at`은 `set_`에 명시 - `onupdate=func.now()`는 ON CONFLICT SET절에 발동하지 않는다(C1과 동일 함정, 테스트로 고정). **공개** GET은 미저장 슬롯을 404(no-store)로 - FE가 존을 접는 신호다.

### 공개 응답 계약: 키 문자열 미노출
`PublicCommissionItem`은 `sample_image_urls`(공개 URL 배열)만 싣는다. 공개 버킷이라 보안 목적이 아니라 "독자 응답에 R2 키 부재"(B2 계약)와 표면을 일치시키는 목적. admin 응답은 반대로 `sample_image_keys`(재배열 PUT용)와 `sample_images[]`(key·URL 쌍 - 렌더용)를 함께 싣는다 - **PR2 인계 계약: 재배열·삭제 PUT은 `sample_image_keys` 기준, 렌더는 `sample_images` 기준**(리뷰 FYI).

### 동시성: last-write-wins + append만 원자화
작가 1인이라 일반 메타 수정에는 낙관적 잠금을 두지 않는다. 샘플 append는 조건부 UPDATE로 원자화한다. 카드 순서는 컬렉션 전체의 속성이므로 전량 ID 집합 검사를 낙관적 동시성 검사로 사용하고 한 트랜잭션에서 `1..N`으로 재배정한다. 생성·개별 수정 입력에는 `sort_order`를 노출하지 않고 생성 시 서버가 max+1을 배정한다.

---

## 3. 리뷰 (Opus, 커밋 전)

Critical 0 / Major 2 / Minor 3 / FYI 2. 리뷰어가 **뮤테이션 실험**으로 테스트 판별력을 실측한 것이 특징 - 발견 전부 실패 시나리오 동반.

1. **[Major] 원자 append 계약이 테스트로 미고정** - 빈 카드 1회 업로드만 검증해 `expected_len` 오염(항상 0)·append→덮어쓰기 회귀가 21건 전부 통과(뮤테이션 실측, MISTAKES "시작값=기대값 판별력 0" 해당). → 같은 카드 연속 2회 업로드 + 순서 보존 단언 테스트 추가. **뮤테이션 2종 재주입으로 red 실증 후 원복.**
2. **[Major] LEARN 주석 잔존** - 규약대로 채점 후 커밋 전 삭제(사용자 답변 대기).
3. **[Minor] upsert `updated_at` 갱신 미고정** - `set_`에서 빼도 전부 통과(뮤테이션 실측). → put2 > put1 단언 추가 + red 실증.
4. **[Minor] 정리 실패 로깅에 `exc_info` 누락** - 키만 남기면 "이미 없는 객체(정상)"와 "권한 상실(장애)"이 로그에서 구분 불가. → 추가.
5. **[Minor] 인가 회귀 커버 공백** - PUT/DELETE/images 3개 엔드포인트의 비-owner 경로 미검증(의존성 정리 중 `OwnerDep` 제거 회귀에 무방비). → 403 루프에 더미 UUID 3줄 추가(인가가 404보다 먼저).

리뷰 확인 통과 항목: 인가 경계(admin 7개 전부 OwnerDep + TOTP), 임의 키 주입 차단(생성 스키마 필드 부재 + PUT 부분집합 검증 + 서버 발급 uuid 키), 버킷 라우팅, rollback 후 만료 객체 접근 없음(스냅샷 선행), `eager_defaults` 전제, 마이그레이션 upgrade/check/downgrade 왕복(일회용 DB 실측), 라우트 충돌 0, 형제 일관성(404 no-store·`_NON_NULLABLE` 패턴·정수 상한).

---

## 4. 이연 / 후속

| 항목 | 이동처 |
|------|--------|
| admin 커미션 관리 화면(카드 폼·이미지 업로드·마감 토글·순서) | PR2 (`admin/feat/commission-screens`) |
| 랜딩·`/commission` FE + compose 헬스체크 수정 | PR3 (`fe/feat/m2-landing-commission`) |
| DECISIONS 결정 4 대체·M2_foundation 그룹 G 재작성 | PR4 (PR3 편승) |
| 커미션 신청 폼(아이템 선택→신청)·이메일 접수·admin 접수 관리 | M5 - CommissionItem 위에 얹음 |
| site_texts에 약관·개인정보처리방침 슬롯 추가 | M7 (법무 문서 - 같은 모양) |
