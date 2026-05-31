# 반복 실수 패턴

작업 중 실수가 발생하면 여기에 추가.
사용법: `@docs/MISTAKES.md 참고해서 [작업] 해줘`

---

## 사용 예시

```
@docs/MISTAKES.md 참고해서 결제 API 구현해줘
@docs/MISTAKES.md 참고해서 FastAPI 라우터 작성해줘
```

---

## FastAPI

<!-- 실수 발생 시 여기에 추가 -->
<!-- 예시:
- SQLModel 관계에서 lazy loading으로 N+1 발생
  → selectinload 명시적으로 써야 함
- 포트원 webhook 금액 검증 누락
  → 결제 API는 항상 서버에서 금액 재검증
-->

## Astro / React

<!-- 실수 발생 시 여기에 추가 -->
<!-- 예시:
- React 아일랜드에 client: 지시자 누락 → hydration 안 됨
- Signed URL 만료 시간 너무 짧게 설정 → 뷰어 로딩 중 만료
-->

## 공통

- pnpm workspace에서 `@tailwindcss/vite` peer dep 충돌
  → admin이 vite@8을 쓰면 workspace 전체에서 `@tailwindcss/vite`가 vite@8 바인딩으로 resolve됨
  → Astro 6 (vite@7) 환경에서 `tsconfigPaths` 누락 에러 발생
  → 해결: 각 패키지에 peer 고정 (`frontend`에 `vite@^7` devDep 명시)
  → 근본 해결은 Astro 7 (vite@8) 출시 후 일괄 업그레이드 (DECISIONS.md 참조)

- pnpm workspace 추가 후 lockfile이 구버전 peer 해석을 캐싱할 수 있음
  → `pnpm install --force` 또는 `rm pnpm-lock.yaml && pnpm install`로 강제 재계산
  → `pnpm why --filter <패키지> <dep>` 으로 실제 resolve 경로 확인

- 백엔드 Python 실행 시 `python` 대신 `uv run python` 사용
  → `python` 명령은 PATH에 없음. `uv run python`, `uv run uvicorn`, `uv run pytest` 형태로 실행할 것

- 이미 push된 커밋을 rewrite(`reset --soft`/rebase/amend)하면 로컬과 origin이 갈라진다(divergence)
  → 히스토리 재작성 전 push 여부 확인: `git status -sb`(ahead/behind) 또는 `git rev-parse origin/<branch>`
  → 이미 pushed면 (1) 새 커밋으로 fix-forward가 기본, (2) 굳이 정리하면 `--force-with-lease` 필요함을 먼저 고지
  → 이 repo는 squash-merge라 중간 커밋은 어차피 합쳐지므로 정리 목적 rewrite는 대개 불필요

- 코딩 완료 후 커밋 전 반드시 Opus 검증 단계 거칠 것
  → 순서: 계획(Opus) → 코딩(Sonnet) → 검증(Opus) → 커밋
  → Opus 없이 바로 `git commit`으로 넘어가지 말 것
