# 랜딩 + 공개 커미션 페이지 (M2 그룹 G PR3)

| 항목 | 내용 |
|------|------|
| 모듈 | Frontend / Commission |
| 관련 마일스톤 | [M2](../../../milestones/M2_foundation.md) 그룹 G |
| 작성 시점 | M2 G PR3 (2026-08-13) |
| 상태 | 구현·정적 게이트 완료, 사용자 브라우저 확인 대기 |
| 관련 문서 | BE `IMPLEMENTATION_COMMISSION_API.md`, ADMIN `IMPLEMENTATION_COMMISSION_SCREENS.md`, DECISIONS "랜딩 페이지 구성 + 커미션 단계 분리" |

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `frontend/src/lib/commission.ts` | 공개 카드·사이트 문구 DTO, fetch 함수, 랜딩·모집 상태 순수 로직 |
| `frontend/src/lib/commission.test.ts` | API 경로·404 판정·작품 0/1/N 분기·모집 상태 테스트 |
| `frontend/src/components/commission/CommissionCard.astro` | 4:3 대표 썸네일 + 이름·가격·설명·모집 상태 소형 카드 |
| `frontend/src/pages/index.astro` | 최근 등록 작품 소형 히어로 + 다른 작품 + 커미션 앞 4개 SSR |
| `frontend/src/pages/commission.astro` | 카드 목록·유의사항·모집 상태 SSR |
| `frontend/src/components/common/Navbar.astro` | 커미션 링크 |
| `frontend/Dockerfile` | nginx 정적 서버에서 Astro Node standalone 런타임으로 전환 |
| `compose.yml`, `Caddyfile` | frontend 4321 프록시와 정적 자산 readiness 검사 |

신규 의존성과 DB·BE·admin 변경은 없다. 더 이상 쓰이지 않는 `frontend/nginx.conf`는 제거했다.

## 2. 데이터와 렌더링 결정

작가는 리포 파일을 직접 편집하지 않으므로 옛 마크다운 content collection 계획을 폐기했다. 두 페이지는 선행 PR의 `GET /commission-items`, `GET /site-texts/{key}`와 공개 작품 API를 SSR에서 병렬 조회한다. 정상 응답은 `public, max-age=60`, 일부 API 실패나 미저장 문구 404가 있으면 페이지 전체를 `no-store`로 둔다. 존은 독립적으로 남겨 보조 API 장애가 페이지 전체 500으로 번지지 않지만, 장애 HTML은 캐시하지 않는다.

공개 작품 목록은 `created_at DESC`이지 대표작이나 실제 공개 최신순 계약이 아니다. 첫 작품을 "최근 등록 작품"으로 표시하고 나머지를 기존 `WorkCard` 그리드로 렌더한다. 히어로 표지는 소개 문구보다 과도하게 커지지 않도록 220px로 제한한다. 랜딩 커미션은 서버가 작가 지정 순서로 준 앞 4개를 소형 그리드로 사용하며 모집 중 카드를 FE에서 앞으로 재정렬하지 않는다.

커미션 카드는 랜딩·목록 모두 동일한 밀도를 쓴다. 작가가 정렬한 샘플 중 첫 이미지를 4:3 대표 썸네일로 보이고, 이름·가격·모집 상태를 우선 노출하며 설명은 2줄로 제한한다. 이동 대상인 신청 폼·상세 페이지가 없는 M2에서는 카드를 링크로 위장하지 않는다.

사이트 문구는 플레인 텍스트 계약이다. Astro 기본 escaping을 유지하고 `whitespace-pre-line`으로 줄바꿈만 보존한다. 샘플은 공개 URL만 소비하며 URL 없음과 브라우저 로드 실패를 각각 placeholder로 처리한다.

## 3. 신청 경로 범위

외부 플랫폼 CTA와 이메일 링크를 만들지 않는다. 우리 사이트 카드와 외부 플랫폼 정보를 이중 관리하지 않고, 잠깐 쓰고 버릴 URL 설정 계약도 추가하지 않는다. M2는 가격·기간·샘플·모집 상태와 "온라인 신청 기능 준비 중" 안내까지 제공한다. M5에서 공개 DTO의 안정 식별자 `CommissionItem.id`와 내부 신청 폼을 연결하고 이메일 접수·admin 접수 관리를 구현한다.

## 4. SSR 컨테이너 전환

기존 Docker 최종 이미지는 nginx가 정적 파일만 서빙해 이미 존재하던 `prerender=false` 경로도 실행할 수 없었다. `@astrojs/node` standalone entry인 `frontend/dist/server/entry.mjs`를 Node 24로 실행하고 `HOST=0.0.0.0`, `PORT=4321`을 지정했다. pnpm workspace symlink가 루트 `.pnpm` 저장소를 가리키므로 root와 frontend의 `node_modules`를 함께 복사한다. 런타임은 `node` 사용자로 실행한다.

compose healthcheck는 API에 의존하는 SSR 홈 대신 `/favicon.svg`를 확인한다. 이 검사는 Node 프로세스와 정적 자산 서빙 readiness만 측정하고 API 장애를 frontend 컨테이너 장애로 오판하지 않는다. Caddy는 `frontend:4321`로 프록시한다.

SSR은 컨테이너 내부 DNS `API_INTERNAL_URL=http://api:8000`, 브라우저는 `PUBLIC_API_URL`을 사용한다. 하나의 공개 주소를 공유하지 않아 compose 안에서 `localhost` 접속이 frontend 자신으로 향하는 회귀를 막는다.

## 5. 검증

- `pnpm --filter frontend test`: 7 files, 65 tests 통과
- `pnpm --filter frontend astro check`: 0 errors, 기존 작품 목록의 실제 사용 import에 대한 hint 1건
- `pnpm --filter frontend build`: 통과, Node server 산출물 생성
- 산출물 검사: server chunk은 `process.env.API_INTERNAL_URL`을 런타임 조회하고 client chunk에는 `API_INTERNAL_URL`이 없음
- 빌드 산출물 직접 기동: `/favicon.svg`, `/`, `/commission`, 기존 `/works` 모두 HTTP 200
- API 미기동 상태에서 세 SSR 경로가 오류 존을 렌더하고 `Cache-Control: no-store`를 반환함을 확인
- `docker compose build frontend`: 현재 WSL 배포판에 Docker CLI 연동이 없어 미실행

브라우저 실기능과 실제 API 성공 데이터의 모바일·데스크톱 레이아웃은 프로젝트 원칙에 따라 사용자가 확인한다.

## 6. M5 인계

- `CommissionItem.id`를 신청 대상과 연결
- `/commission` 내부 신청 폼
- 이메일 발송과 접수 저장
- admin 접수 목록·처리 화면
- 개인정보 수집·보관 정책
