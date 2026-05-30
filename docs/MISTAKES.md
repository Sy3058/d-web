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

- 백엔드 Python 실행 시 `python` 대신 `uv run python` 사용
  → `python` 명령은 PATH에 없음. `uv run python`, `uv run uvicorn`, `uv run pytest` 형태로 실행할 것

- 이미 push된 커밋을 rewrite(`reset --soft`/rebase/amend)하면 로컬과 origin이 갈라진다(divergence)
  → 히스토리 재작성 전 push 여부 확인: `git status -sb`(ahead/behind) 또는 `git rev-parse origin/<branch>`
  → 이미 pushed면 (1) 새 커밋으로 fix-forward가 기본, (2) 굳이 정리하면 `--force-with-lease` 필요함을 먼저 고지
  → 이 repo는 squash-merge라 중간 커밋은 어차피 합쳐지므로 정리 목적 rewrite는 대개 불필요

<!-- 실수 발생 시 여기에 추가 -->
<!-- 예시:
- .env 변수 타입 검증 없이 사용 → 런타임 에러
- CORS 설정 빠뜨리고 admin 페이지 연동 → 403
-->