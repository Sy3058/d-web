## 변경 사항

<!-- 무엇을, 왜 변경했는지 -->

## 타입

- [ ] feat (새 기능)
- [ ] fix (버그 수정)
- [ ] chore (설정/인프라)
- [ ] refactor
- [ ] docs

## 🚨 보안 체크 (Critical)

- [ ] 결제 금액 DB에서 계산 (클라이언트 값 무시)
- [ ] 권한 검증 Depends() 누락 없음
- [ ] 미결제 유저에게 Signed URL / r2_key 미노출
- [ ] 환경변수 하드코딩 없음
- [ ] 개인정보 로깅 없음 (이메일, 카드, TOTP 시크릿)
- [ ] CORS 와일드카드(`*`) 없음

## ✅ 구현 체크

- [ ] 레이어 분리 (router → service → model)
- [ ] 트랜잭션 경계 명시 (결제 다중 INSERT)
- [ ] N+1 방지 (selectinload 명시)
- [ ] 에러 코드 구분 (401 / 403 / 400)
- [ ] DB 마이그레이션 포함 (모델 변경 시)
- [ ] `datetime.now(timezone.utc)` 사용 (`datetime.now()` 금지)
- [ ] soft delete 모델(User, Episode, Comment) 조회 시 `deleted_at IS NULL` 누락 없음
- [ ] Signed URL 만료 시간 적절 설정 (뷰어 로딩 중 만료 방지)

## 📝 문서

> 이번 PR에서 작성/수정한 것만 체크하고 옆에 파일을 적는다.

- [ ] IMPLEMENTATION 작성 - 
- [ ] TROUBLESHOOTING 작성 - 
- [ ] CHANGELOG 작성 - 
- [ ] 마일스톤 업데이트 - 
- [ ] 그 외 문서/설정 수정 - 

## 🚫 구현 범위 (feat PR인 경우)

- [ ] 보류 기능 미포함 (멤버십, 소설 뷰어, 포렌식 워터마크, 충전식 코인)

## 검증 체크

- [ ] `ruff check src/` 통과
- [ ] `pytest` 통과 (테스트 있는 경우)
- [ ] `uvicorn src.main:app` 정상 실행
- [ ] 변경된 API 엔드포인트 직접 호출 확인

## 비고

<!-- 리뷰어에게 전달할 추가 정보 -->
