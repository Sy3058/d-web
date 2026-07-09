# R2 업로드 + 이미지 변환 서비스 (M1.5 그룹 D - D1+D2)

| 항목 | 내용 |
|------|------|
| 모듈 | Backend / Upload |
| 관련 마일스톤 | [M1.5](../../../milestones/M1.5_foundation.md) 그룹 D - D1·D2 (ADM-03 서비스 계층) |
| 작성 시점 | M1.5 D1+D2 (2026-07-10) |
| 상태 | 구현 + 강 모델 리뷰(/code-review high, 파인더 8앵글 + verifier 6) 발견 11건 수정 완료. `pytest` 199 passed(신규 29), ruff·`alembic check` 클린. R2 실버킷 스모크(put/get/delete) 통과 |
| 관련 문서 | M1.5_foundation.md 결정 1·2 / D1·D2, MISTAKES.md "Pillow / 이미지"·"R2 / boto3" |

에피소드 업로드(D3)의 하부 서비스 2개. 엔드포인트는 없고(D3 후속 PR), 순수 서비스 계층만. HTTP·DB를 모른다.

---

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `backend/src/services/r2_service.py` | boto3 S3 호환 클라이언트(lru_cache 싱글턴 + `is_configured()`), `upload_bytes`(to_thread), 키 스킴 헬퍼(`episode_page_key` 0~999 가드 / `cover_key`), endpoint 경로 오설정 가드 |
| `backend/src/services/image_service.py` | `convert_to_webp`: 3단 검증(20MB → 실디코드 → 80MP) + 애니메이션 거부 + JPEG draft 축소 디코드 + EXIF transpose·메타데이터 제거 + 16비트 스케일링 + 모드 정규화 + 800px LANCZOS + WebP 16383px 변 한계 검증 |
| `backend/src/lib/exceptions.py` | `ImageValidationError` 추가(도메인 예외 계약 합류 - router가 4xx 매핑) |
| `backend/src/main.py` | production에서 R2 미설정 시 부팅 경고(`r2_not_configured_in_production`) |
| `backend/src/config.py` | `r2_secret_access_key` → `SecretStr`, `r2_bucket` 기본값 실버킷명 `dweb` |
| `backend/tests/test_r2_service.py` | 9개(전부 mock - hermetic): 키 스킴·범위 가드, put_object 계약, 미설정·경로 오설정 거부 |
| `backend/tests/test_image_service.py` | 20개: 변환 규격 10 + 거부 6 + 리뷰 회귀(16비트·팔레트 평균화·draft 2종) + 상수 계약 |

새 의존성: `boto3>=1.43.44`, `pillow>=12.3.0` (설치 직전 WebSearch 확인). DB 마이그레이션: 없음(`alembic check` 클린).

---

## 2. 주요 결정

### 업로드 = 백엔드 경유(결정 1), 변환 = 요청 내 동기 + to_thread(결정 2)
마일스톤 확정 그대로. presigned PUT은 서버가 바이트를 못 봐 변환·규격을 강제할 수 없어 미채택. Pillow는 CPU 바운드라 to_thread는 루프 비블로킹일 뿐 가속이 아님 - 50장 합산 시간은 진행바(F3)로 커버, 초과 시 Arq 분리.

### 키 스킴 = episode_id(UUID) 기준
`works/{work_id}/episodes/{episode_id}/{page:03d}.webp`, 표지 `works/{work_id}/cover.webp`. episode_no는 회차 재정렬 시 바뀌는 값이고 R2엔 rename이 없어(복사+삭제) 불변 UUID에 묶는다. page는 0~999 가드(3자리 zero-pad 계약 보호).

### R2 미설정 = lazy-fail + production 부팅 경고
자격증명 기본값 빈 값 - CI/무자격 로컬 부팅 허용, 사용 시점에 `R2NotConfiguredError`(운영자 귀책 5xx - `ImageValidationError` 4xx와 구분해 서비스 모듈에 유지). 침묵 배포 방지는 main.py lifespan의 기존 resend 경고 선례에 `is_configured()` 검사로 합류.

### endpoint 경로 가드 (리뷰 Critical급)
대시보드 '버킷 Settings > S3 API' 주소는 끝에 `/버킷명`이 붙어 있다. 그대로 넣으면 boto3가 버킷을 한 번 더 덧붙여(`PUT /dweb/dweb/works/...`) R2가 첫 세그먼트를 버킷으로 해석 - **에러 없이 성공하면서 모든 키가 `dweb/` 접두사로 어긋나게 저장**되는 조용한 오염(리뷰 실측 재현). `_get_client`에서 `urlparse(endpoint).path`가 비어있지 않으면 거부.

### 변환 파이프라인 순서 (순서가 곧 정확성)
```
바이트 상한(20MB) → open → 애니메이션 거부(is_animated) → 픽셀 상한(80MP, 헤더만)
→ JPEG draft(조건부) → load(실디코드) → EXIF transpose → 16비트 스케일링
→ 모드 정규화(P/LA/PA→RGBA, 그 외→RGB) → 800px LANCZOS(업스케일 없음)
→ 16383px 세로 한계 → WebP q80 저장(메타데이터 미전달=제거)
```
- **모드 정규화는 리사이즈 앞**: Pillow는 P(팔레트) 모드 resize에서 LANCZOS를 조용히 NEAREST로 강제한다(픽셀값이 색이 아니라 팔레트 인덱스라 보간 산술이 무의미). 뒤에 두면 팔레트 원고가 계단 현상으로 뭉개진다(리뷰 실측: 체커보드 평균 127 vs 위상 선택 255).
- **16비트(I/I;16*) 선형 스케일**: `convert("RGB")` 직행은 0~65535를 255로 클리핑해 스캔 원고가 백지가 된다(리뷰 실측). `point(v*255/65535)` 후 L로.
- **애니메이션 명시 거부**: 변환은 첫 프레임만 남겨 조용한 콘텐츠 손실(리뷰 실측) - 에러로 안내.
- **JPEG draft**: DCT 도메인 축소 디코드로 장당 실측 2.78배(350ms→126ms). 2배 여유(1600px) 요청은 마지막 LANCZOS가 항상 실제로 일어나게 하는 품질 관행(thumbnail의 reducing_gap=2와 동일). EXIF 회전(5~8)은 transpose 후 축이 바뀌므로 유효 가로를 회전 후 기준으로 계산(안 하면 회전 원고 폭이 800 미만으로 어긋남 - 리뷰 검증).
- **폭탄 방어 2겹**: 자체 80MP(헤더 검사, 디코드 전) + Pillow 자체 가드(~179MP, open 시) - 후자도 같은 "해상도 초과" 메시지로 매핑해 안내 일관.
- **WebP 16383px 변 한계**: 스펙(14bit) 자체 제약. 800px 축소 후에도 세로가 넘는 초장축 원고는 인코딩 불가라 분할 업로드 안내.

### 업스케일 금지 (구현 결정)
원본 폭 ≤800이면 그대로 - 없는 정보를 만들어내지 못해 화질은 그대로인데 용량만 커진다.

### 루프 블로킹 0
클라이언트 획득(`_get_client()`, 콜드 실측 62.7ms)도 put_object와 함께 `_put_object_sync`로 묶어 to_thread 안에서. async 경로에 동기 블로킹 0.

---

## 3. 리뷰 (강 모델, /code-review high)

파인더 8앵글 + verifier 6(전부 실측/소스 검증). **CONFIRMED 10 + PLAUSIBLE 1 전부 수정**:
endpoint 경로 오염 / 애니메이션 손실 / 16비트 클리핑 / P-모드 NEAREST / 루프 블로킹 / production 경고 부재 / JPEG draft 미사용 / 예외 위치 / 폭탄 메시지 비일관 / 픽스처 죽은 코드 / page 범위 가드.
**REFUTED 2**: 불투명 P→RGBA 용량 낭비(libwebp가 전불투명 알파 플레인을 인코딩 시 드롭 - 실측 delta 0.0%), `except ImageValidationError: raise` 중복 지적(무해한 방어, 유지).

## 4. 이연 / 후속

| 항목 | 이동처 |
|------|--------|
| 장수(≤50) 검증 - `MAX_IMAGES_PER_EPISODE` 상수만 노출 | D3 엔드포인트 (D2 DoD의 계획된 이연) |
| multipart 요청 전체 크기 상한 (50×20MB=1GB 메모리) | D3 (리뷰 out-of-scope 노트) |
| 중간 실패 시 R2 고아 객체 정리 | D3 노트 (마일스톤 명시, 차단 아님) |
| Signed URL(GET) 발급 | M3 |
| Arq 워커 분리 | 실측 escalation(결정 2) |
| 배포용 R2 토큰 IP 고정 분리 발급 | 배포 마일스톤 |
