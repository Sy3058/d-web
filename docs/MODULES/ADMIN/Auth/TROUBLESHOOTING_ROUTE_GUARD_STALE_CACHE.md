# TROUBLESHOOTING - 세션 만료 리다이렉트가 캐시된 유저 정보를 안 지움

대상: admin (Vite React SPA), 라우트 가드 `src/routes/_auth.tsx`
관련 구현: `IMPLEMENTATION_ADMIN_LOGIN_2FA.md`, `hooks/useAuth.ts` (`useLogout`의 `queryClient.clear()`)
발생/수정: 2026-07-23 (이슈 #91)

## 증상

세션이 서버 쪽에서 무효화된 뒤(access/refresh 만료, 재사용 탐지 revoke, 강제 로그아웃 등) admin에서 라우트를 이동하면 `_auth` 가드가 `/auth/me`를 재검증하다 401을 받고 `/login`으로 리다이렉트한다. **그런데 `useMe()`(`ME_QUERY_KEY`) 캐시는 그대로 남는다.**

- `useMe`를 구독하는 화면(Dashboard, EpisodeEditor)이 이전 로그인 유저 정보를 계속 들고 있다.
- 다른 계정으로 재로그인하면 로그인 직후 잠깐 **직전 계정 데이터가 비칠 수 있다**(캐시 교체 전 프레임).

> 주의(정직한 범위): 이슈 #91 본문은 "로그인 화면 Navbar에 이전 닉네임이 남는다"고 적었지만, **현재 admin에는 Navbar가 없고**(`__root.tsx`는 `Outlet`만) `/login`에는 `useMe` 구독 컴포넌트가 없다. 따라서 그 화면 그대로의 증상은 지금은 재현되지 않는다. 그러나 아래 **근본 원인(리다이렉트 시 캐시 미정리)은 실재**하며, `/login`에 유저 정보를 표시하는 UI가 생기는 순간 즉시 잔상 버그가 되고, 지금도 계정 간 캐시 누수 경로로 남아 있어 방어적으로 닫는다.

## 원인

`_auth.tsx`의 가드는 401(및 role 불일치) 시 `redirect({ to: '/login' })`만 던지고 캐시를 건드리지 않았다.

```ts
} catch {
  throw redirect({ to: '/login' });   // 캐시 정리 없음
}
```

반면 `useLogout()`은 정확히 이 문제 때문에 `onSuccess`에서 `queryClient.clear()`를 호출한다. **자동 401 리다이렉트 경로에만 같은 처리가 빠져 있던 일관성 결함**이다.

- `fetchQuery`가 401로 던져도 TanStack Query는 그 쿼리의 **마지막 성공 `data`를 캐시에 유지**한다(에러 상태와 data가 공존). 그래서 `useMe` 관측자는 이전 유저를 계속 본다.
- `setQueryData(key, undefined)`로는 못 지운다: TanStack이 `undefined`를 "업데이트 안 함"으로 보고 bail-out하는 no-op이다(query-core `queryClient.js`: `if (data === void 0) return void 0`). 그래서 `useLogout`도, 이 수정도 **`clear()`**를 쓴다.

## 해결

로그인 화면으로 돌려보내는 모든 경로에서 캐시를 비우도록 헬퍼로 묶었다. 401 경로뿐 아니라 `role !== 'owner'` 경로도 동일 결함이라 함께 닫았다(둘 다 `/login`으로 튕기는 동일 행위).

```ts
const bounceToLogin = () => {
  context.queryClient.clear();
  return redirect({ to: '/login' });
};
// ...
catch { throw bounceToLogin(); }
// ...
if (user.role !== 'owner') { throw bounceToLogin(); }
```

`removeQueries({ queryKey: ME_QUERY_KEY })`(me만 제거)가 아니라 `clear()`(전체 비움)를 택한 이유: `/auth/me` 401은 세션 전체가 무효라는 뜻이라 works/episodes 등 다른 인증 캐시도 함께 폐기해야 하고, 그래야 다른 계정 재로그인 시 직전 계정 데이터가 새지 않는다. `useLogout`과 동일한 시맨틱("인증 영역을 떠난다 → 캐시를 비운다")으로 통일된다.

## 재발 방지 / 일반화

- **인증 영역에서 `/login`으로 튕기는 모든 경로는 캐시를 비운다.** 리다이렉트만 하고 캐시를 남기면 stale 신원 데이터가 다음 세션으로 샌다.
- **캐시 제거는 `clear()` 또는 `removeQueries`로.** `setQueryData(key, undefined)`는 no-op이라 안 지워진다.
- 회귀 테스트: `_auth.test.tsx`에 "401/reader 리다이렉트 시 `getQueryData(ME_QUERY_KEY)`가 `undefined`" 케이스 고정.
- 후속: 가드가 일시 오류(500/네트워크)를 세션 만료와 동일하게 로그아웃 취급하는 문제는 별개로 **#97**에 분리(진짜 401만 로그아웃, 나머지는 재시도 UI).
