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

<!-- 실수 발생 시 여기에 추가 -->
<!-- 예시:
- .env 변수 타입 검증 없이 사용 → 런타임 에러
- CORS 설정 빠뜨리고 admin 페이지 연동 → 403
-->