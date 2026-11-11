# 구매 내역과 의존성 추가 점검 (2026-11-12)

## 결과와 범위

구매 내역의 서버 간 연결을 실제 TCP HTTP로 확인하고, 일일 의존성 보고서의 주요 후보를 설치 버전·실행 경로와 대조했다. 구매 내역 뷰어 URL의 404는 수정했다. 추가 의존성 업데이트와 기존 서비스 재시작은 하지 않았다. 전체 공지의 악용 가능성을 모두 배제한 보고서가 아니며, 아래에서 배제 근거가 없는 후보는 확인 필요로 유지한다.

## 기능 확인

격리 테스트 DB와 임시 Uvicorn·빌드된 Astro standalone 서버에서 실제 로그인 → 구매 내역 → 반환된 독자 URL → bootstrap → 전문 요청을 실행했다. 수정 전 URL은 404, 실제 reader 경로는 200이었고 서비스와 기대값 수정 후 반환 URL도 200이다. HttpOnly 쿠키, 인증·page 검증·no-store, 소유자 격리, 비공개 구매자 전문 접근, 미구매자 404, SSR 비공개 정보 미노출, 실제 전문 진입 때만 첫 열람 기록을 확인했다.

결제 provider는 합성 PAID snapshot이다. 기존 개발 DB에 transaction ID가 있는 test PAID 주문은 0건이었다. 실제 PortOne 결제·영수증과 브라우저 UI 확인은 완료로 간주하지 않는다. 임시 DB·서버를 정리했다. FE 구매 내역 화면은 별도 미완료 범위다.

링크 수정 후 Backend Ruff format 116 files·Ruff check와 pytest 전체 1,147개가 통과했다(72.10초). FE·Admin 코드와 API schema는 추가 변경이 없어 앞선 전체 gate 결과를 유지한다.

## 주요 보안 후보

| 대상 | 확인한 상태 | 판단과 후속 조치 |
| --- | --- | --- |
| Pillow 12.3.0 | 로컬과 별도 Backend 이미지 모두 OpenJPEG 2.5.4. `image_service.py`는 형식 allowlist 없이 `Image.open` 후 `load`한다. | JPEG2000 디코드 취약 경로가 존재한다. owner 업로드에 제한되지만 파일·픽셀 상한만으로 메모리 손상을 방지하지 못한다. 수정 버전 13.0.0 반영 또는 디코더 진입 전 허용 형식 제한을 검토해야 한다. 악성 파일은 실행하지 않았다. |
| Vite 8.2.2 | 공지의 영향 버전. 설정·스크립트에 `--host`/`server.host` 외부 노출 설정이 없고 확인 당시 프로젝트 dev server도 없다. | 네트워크로 노출한 dev server가 공격 조건이다. 현재 관찰에서 이 조건은 없으며, 예방 업데이트는 같은 계열 수정 버전 8.2.5가 기준이다. 운영 Astro standalone·Admin nginx는 Vite dev server가 아니다. |
| PostgreSQL 16.14 | 실행 중인 `d-web-postgres-1`에서 버전 확인. | CVE-2026-16239 수정 버전 16.15보다 낮다. SQL 실행 권한이 있는 사용자의 cursor 조작이 조건이다. 공개 SQL 접속 경로는 확인되지 않았지만 운영 전 수정 버전 반영이 필요하다. DB 재시작·볼륨 변경은 하지 않았다. |
| Node 24.22.2 | 로컬 검증 버전. 공식 11월 보안 수정 버전은 24.22.3이다. | 업데이트 대상이다. Astro standalone 기본 경로는 `node:http`이고 TLS 파일을 설정하면 `node:https`를 쓴다. HTTP/2·TLS 서버 관련 공지의 조건을 기본 HTTP에서 확인하지 못했다. proxy 자격증명 오류·TLS agent 등 나머지 조건을 배제하지 않는다. Docker의 `node:24-alpine` 태그만으로 기존 이미지의 수정 여부를 판단하지 않는다. |
| Astro 7.2.4 / Sharp | AVIF 최적화 RCE 영향 버전. 원격 image 허용 설정과 직접 `astro:assets` 사용은 없고 이미지 endpoint의 원격 출처 검사도 존재한다. | 공격자가 제공한 AVIF를 Sharp가 처리하는 경로는 확인되지 않았다. 간접 경로까지 없다고 단정하지 않는다. Astro 7.2.8은 해당 문제 수정 버전이며 다른 공지도 함께 고려해야 한다. |
| Astro transition CSS | ClientRouter를 사용하지만 사용자 입력으로 구성하는 transition animation 속성은 소스에서 발견되지 않았다. | ClientRouter 존재만으로 GHSA-mpr7-6m5w-76rw 악용 조건을 충족하지 않는다. 해당 공지는 신뢰하지 않는 duration 등 animation 속성이 필요하다. 수정 버전은 7.3.3이다. |

Python의 PyJWT JWK·비대칭 키, cryptography PKCS7 decrypt, pydantic nested secrets, Mako 사용자 template 경로는 직접 사용하지 않는 것을 확인했다. 현재 JWT는 서버가 고정한 HS256 검증 경로다. 이는 패키지의 다른 공지를 일괄 배제하는 근거가 아니다. Starlette multipart는 실제 업로드에서 사용되므로 패키지 이름만으로 제외하지 않는다. JS의 직간접 parser·serializer·Sentry 경로도 직접 import 검색만으로 안전 판정하지 않았다. 일일 보고서의 나머지 확인 필요 항목은 유지한다.

## 근거

- [Pillow 원문 공지](https://github.com/python-pillow/Pillow/security/advisories/GHSA-78g4-xqwv-q3g8)
- [Vite 원문 공지](https://github.com/vitejs/vite/security/advisories/GHSA-p4f5-76q4-ffq7)
- [PostgreSQL 원문 공지](https://www.postgresql.org/support/security/CVE-2026-16239/)
- [Node 11월 보안 릴리스](https://nodejs.org/en/blog/vulnerability/november-2026-security-releases?trk=public_post_comment-text)
- [Astro AVIF 원문 공지](https://github.com/withastro/astro/security/advisories/GHSA-26w7-cxv4-gfx2)
- [Astro transition 원문 공지](https://github.com/withastro/astro/security/advisories/GHSA-mpr7-6m5w-76rw)

앞서 수정한 certifi·uv·ProseMirror의 설치·빌드·앱별 gate 근거는 [의존성 보안 수정](IMPLEMENTATION_DEPENDENCY_SECURITY_UPDATES.md)에 있다. 전역 일일 보고서의 확인 필요 상태를 이번 부분 조사로 일괄 종료하지 않는다.
