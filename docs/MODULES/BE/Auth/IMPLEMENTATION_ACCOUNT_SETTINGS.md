# U3 계정 프로필·비밀번호 편집 API

## 범위와 인계

본인 계정의 닉네임·프로필 이미지·비밀번호를 변경하는 BE 전달 단위다. User의 기존 nickname/profile_image/hashed_password 필드를 사용하며 DB 컬럼·migration을 추가하지 않는다. UserRead.has_password는 저장 필드가 아닌 파생 읽기 값으로, 소셜 전용 계정의 비밀번호 편집 가능 여부만 본인 계정 화면에 알린다. 해시와 TOTP 시크릿은 응답하지 않으며 이 DTO를 공개 댓글 프로필에 재사용하지 않는다.

BE main 반영 뒤 최신 main 기반 별도 FE 브랜치에서 마이페이지 편집 화면을 연결한다. 현재 BE 완료를 계정 편집 UI 완료로 표시하지 않는다. 댓글·비밀번호 재설정·소셜 계정 연결·결제·소장본 정책은 이 작업에 포함하지 않는다.

## HTTP 계약

| 경로 | 입력·출력 | 제한과 오류 |
| --- | --- | --- |
| PATCH /auth/me | nickname → UserRead | 공백 제거 후 1~50자, 제어 문자/추가 필드 거부, IP당 10회/분 |
| POST /auth/me/profile-image | multipart file → UserRead | JPEG/PNG/정적 WebP, 최대 5MB·1600만 픽셀, IP당 5회/분 |
| POST /auth/me/password | current_password/new_password/confirm_password → MessageResponse | 현재 비밀번호 검증, 가입과 같은 정책/HIBP, IP당 5회/분 |

모든 경로는 get_current_user로 본인만 식별한다. 대상 user_id나 외부 profile_image URL을 입력으로 받지 않는다. 계정 경로의 정상·인증·요청 검증·rate limit 응답은 no-store다. 요청 검증 오류에서 input/ctx를 제거해 비밀번호와 전체 요청 body가 응답에 반사되지 않게 한다. GET /auth/me에도 no-store를 명시한다.

닉네임 변경은 표시 전용 login_hint만 URL 인코딩해 갱신하며 access/refresh 쿠키를 다시 발급하거나 본문으로 반환하지 않는다. Cookie Secure·SameSite·Path·수명은 기존 공통 설정을 사용한다. 로그인·refresh·OAuth의 기존 세 쿠키 발급은 같은 공용 helper를 계속 사용한다.

현재 비밀번호 불일치는 400으로 구분해 공용 API wrapper의 401 자동 refresh/재전송을 유발하지 않는다. 소셜 전용 계정은 409, 동일한 새 비밀번호·정책/HIBP/확인 불일치는 422다. 소셜 계정에 로컬 비밀번호를 새로 설정하는 기능을 우회 추가하지 않는다.

브라우저 PATCH preflight를 위해 기존 CORS origin allowlist를 유지하면서 PATCH 메서드만 추가했다. 인증 쿠키를 쓰는 임의 origin을 허용하지 않는다.

## 비밀번호·세션·동시성

- 새 비밀번호 정책과 HIBP, bcrypt는 기존 함수와 공유한다. HIBP 장애 처리도 기존 fail-open 계약을 유지한다.
- 새 해시 계산·외부 HIBP는 사용자 잠금 밖에서 수행하고, 현재 비밀번호는 잠근 최신 User 행으로 검증한다.
- 해시 갱신과 모든 refresh·trusted device 폐기를 한 트랜잭션으로 처리한다. 실패 시 변경을 되돌리며 성공 후 access/refresh/login_hint/admin pending/trusted device 쿠키를 실제 설정과 같은 범위로 삭제한다.
- 로그인·refresh·owner 세션 발급은 User → refresh/trusted 행 잠금 순서로 직렬화한다. 로그인은 잠금 대기 중 바뀐 비밀번호를 다시 확인한다. User는 populate_existing으로 다시 읽어 오래된 identity-map 값을 쓰지 않는다.
- refresh는 최초 조회 당시 살아 있던 토큰과 기존 stale 재사용을 구분한다. 정상 회전 경쟁 패자는 기존 RefreshRotationConflictError의 401/no Set-Cookie를 유지해 승자의 쿠키를 지우지 않는다.
- owner pending 토큰은 목적·사용자·기존 비밀번호 해시를 TOKEN_PEPPER HMAC으로 결합한다. 원문 해시는 JWT에 넣지 않는다. 소비 시 잠긴 최신 계정과 비교하므로 변경 전 1차 인증을 변경 후 재사용할 수 없다. 기존 태그 없는 pending은 재로그인을 요구한다.

기존 stateless access 계약을 유지한다. 변경 전 발급된 다른 access는 기본 15분과 leeway 10초까지 유효할 수 있으므로 모든 기기에서 즉시 접근을 차단한다고 설명하지 않는다. 해당 refresh는 폐기되어 추가 세션 연장은 실패한다. auth_version 컬럼이나 별도 access denylist를 새로 도입하지 않았다.

## 아바타 검증·저장 수명

새 아바타 경로는 기존 원고 변환 경로와 분리한다. 형식을 Image.open의 JPEG/PNG/WEBP allowlist로 제한하고 JPEG draft를 호출하지 않는다. 크기·해상도·애니메이션 검사를 거친 뒤 EXIF 방향을 적용하고 중앙 정사각형 256px WebP로 바꾼다. EXIF 등 메타데이터는 출력에 넣지 않는다. 동기 변환은 worker thread에서 수행한다.

서버가 생성한 avatars/{user_id}/{uuidhex}.webp만 공개 버킷에 저장하며 파일명과 MIME을 저장 키의 근거로 쓰지 않는다. 공개 base URL과 R2 설정을 쓰기 전에 확인한다. 기존 외부 OAuth 이미지나 다른 사용자/작품 자산은 삭제하지 않는다.

외부 업로드 뒤 사용자 행을 잠가 실제 직전 URL을 읽고 교체한다. 성공한 DB commit 뒤에만, 설정된 공개 origin/base path·본인 namespace·UUID 파일명이 정확히 맞는 이전 객체를 정리한다. 동시 업로드와 닉네임 갱신은 최신 행을 기준으로 한다.

업로드/commit 전 실패는 신규 고유 키만 정리한다. COMMIT 결과가 불확실하면 이미 참조 중일 수 있는 신규 객체를 삭제하지 않고 보존한다. rollback이었다면 미참조 객체가 남을 수 있으며, 데이터 손실보다 이를 허용한다. 정리 실패는 성공한 DB 상태를 되돌리지 않고 파일명/공개 URL은 로그에 남기지 않는다.

이 제한 경로는 기존 owner 원고 변환의 Pillow/OpenJPEG·JPEG draft 취약점을 해결한 것으로 간주하지 않는다. 기존 경로 업데이트는 별도 보안 작업이다. 실제 R2 호출·브라우저 이미지 선택/저장 조작은 자동 검증에서 수행하지 않는다.

## 검증과 리뷰

- 비밀번호 정책·확인·소셜 전용 거부, 잘못된 현재 비밀번호/HIBP 거부 시 무변경, 해시/토큰/신뢰 기기 rollback, 변경과 로그인·refresh·trusted/pending/TOTP의 양방향 경쟁을 검증한다.
- 실제 HTTP에서 쿠키 범위별 삭제·재로그인, 개인정보/비밀번호 오류 미반사, no-store, 소유자 격리와 IP 제한을 확인한다.
- 실제 JPEG/PNG/WebP 변환·EXIF·메타데이터 제거, JPEG2000/GIF/애니메이션/5MB/해상도 거부·no-draft, 외부/다른 namespace 보호, 동시 업로드와 commit 응답 유실을 검증한다.
- 독립 fable-review에서 PATCH CORS 누락을 발견했다. 허용 origin의 preflight 400을 먼저 재현하고 PATCH 허용 및 불허 origin 400 회귀로 보완했다. 추가 인증·저장 무결성 차단 발견은 없었다.
- Admin 생성 타입은 실제 OpenAPI에서 재생성하고 has_password 소비 fixture를 동기화했다. API 타입을 손으로 편집하지 않았다.

2026-11-16 최종 검증: Backend Ruff format(125개 파일)·Ruff check·pytest 1,228개(87.79초), Admin lint·119개 테스트·build를 통과했다. 기존 CORS 정책 테스트도 PATCH 허용 목록과 TRACE 거부 계약에 맞춰 갱신했다. 테스트는 합성 설정·PID별 임시 PostgreSQL DB와 가짜 외부 I/O를 사용하며 기존 개발 DB 데이터를 변경하지 않는다. 실제 외부 결제·메일·R2 호출은 하지 않는다. 모델에는 읽기 전용 property만 추가해 migration은 필요하지 않다.

## 근거

- [인증 결정](../../../DECISIONS.md)
- [Cookie 구현](IMPLEMENTATION_COOKIE.md)
- [refresh 회전 경쟁](IMPLEMENTATION_REFRESH_ROTATION_RACE.md)
- [OWASP Authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#change-password-feature)
- [Pillow draft 공지](https://github.com/python-pillow/Pillow/security/advisories/GHSA-8g5g-8vmr-9782)
- [Pillow OpenJPEG 공지](https://github.com/python-pillow/Pillow/security/advisories/GHSA-78g4-xqwv-q3g8)
