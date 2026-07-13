# TROUBLESHOOTING - TOTP 등록 QR이 "생성 중"에서 영구 정지

대상: admin (Vite React SPA), M1.5 F1
관련 구현: `IMPLEMENTATION_ADMIN_LOGIN_2FA.md` (결정: "TOTP setup은 mutation이 아니라 query")
발생: 2026-07-14, 수동 e2e 첫 시도

## 증상

관리자 로그인 1단계(이메일/비번)를 통과해 2FA 등록 화면으로 넘어가면 **"QR 코드를 생성하는 중..."에서 멈춘 채 아무 일도 일어나지 않는다.**

- 콘솔에 에러 없음. 예외도, 경고도 없다.
- 처음 확인했을 때 Network 탭에서 `/admin/2fa/setup` 요청이 눈에 띄지 않았다(→ "요청이 아예 안 나간다"는 오해를 유발. 실제로는 나가고 있었다).
- 백엔드 로그도 조용함(사용자 터미널 stdout이라 Claude가 직접 못 봄).

## 환경

- `@tanstack/react-query@5.101.2`, React 19 `<StrictMode>` (Vite dev)
- 문제의 코드: 마운트 시 QR을 받아오려고 **`useEffect`에서 mutation을 발화**하고, StrictMode의 이중 실행을 `useRef` 가드로 막는 구조

```tsx
const setup = useAdminTotpSetup();          // useMutation
const requestedRef = useRef(false);

useEffect(() => {
  if (requestedRef.current) return;         // StrictMode 이중 실행 방지
  requestedRef.current = true;
  setup.mutate();
}, []);

if (setup.isPending || setup.isIdle) return <p>QR 코드를 생성하는 중...</p>;
```

## 진단 경로 (프런트를 의심하기 전에 백엔드부터 잘라냄)

1. **백엔드 격리**: setup pending 쿠키를 직접 만들어 `curl`로 `/admin/2fa/setup` 호출
   → **13ms만에 200 + `otpauth_uri` 정상 반환.** 백엔드·DB·Fernet은 무죄.
2. **브라우저 raw fetch**: 멈춘 화면 그대로 콘솔에서 `fetch(..., {credentials:'include'})`
   → **200 정상.** 네트워크 경로·쿠키·CORS 전부 무죄 → 문제는 앱 코드 안쪽.
   - ⚠️ 이 단계에서 한 번 **오진**: 처음에 `127.0.0.1:8000`으로 테스트해 401을 받고 "쿠키가 없다"고 판단할 뻔했다. **쿠키는 호스트 단위로 격리되고 포트는 무시**되므로, 앱이 `localhost`로 로그인했다면 `127.0.0.1`로 보낸 요청엔 그 쿠키가 실리지 않는다. 앱이 쓰는 호스트와 **똑같은 호스트**로 재현해야 한다.
3. **networkMode 가설 기각**: `setup.isPaused`·`navigator.onLine`을 찍음 → `false`/`true`.
   오프라인 판정으로 mutation이 일시정지된 게 아니다.
4. **mutationFn 내부 로그**(결정타): `start` / `resolved` / `threw` 3지점에 `console.log`
   ```
   [DEBUG] mutationFn start
   [DEBUG] mutationFn resolved {otpauth_uri: 'otpauth://...'}
   ```
   → **요청은 나갔고 성공까지 했다.** 그런데 그 뒤 렌더 로그의 `setup.status`는 계속 `pending`.
   즉 "요청이 실패/정지"가 아니라 **성공 알림이 컴포넌트에 도달하지 않는 것**이 진짜 증상.

## 원인

React StrictMode(개발 모드)는 마운트 시 effect를 `mount → cleanup → mount`로 연달아 실행한다. 이 과정에서 **mutation observer가 구독 해제되며 진행 중인 mutation과의 연결이 끊어져, 이후 성공 알림이 컴포넌트에 전달되지 않는다.**

- 공식 이슈: [TanStack/query#8512](https://github.com/TanStack/query/issues/8512) ("Running a mutation in a useEffect hook on mount causes mutation to remain stuck in pending"), [#5341](https://github.com/TanStack/query/issues/5341)
- 결과: HTTP 요청은 200으로 성공하는데 UI는 `pending`에 영구히 갇힌다. 에러가 없으니 콘솔도 조용하다.

### 아이러니: 중복 방지 ref 가드가 멈춤을 *고정*시켰다

가드 없이 두면 StrictMode의 두 번째 `mutate()` 호출이 **우연히** observer를 다시 붙여 상태를 풀어준다(그래서 "가끔 되는" 것처럼 보이는 보고가 많다). 우리가 넣은 `useRef` 가드는 중복 요청을 막으면서 **그 우연한 복구 경로까지 막아** 100% 재현되는 영구 멈춤으로 만들었다.

즉 이 버그는 "중복 방지를 안 해서" 생긴 게 아니라, **애초에 effect에서 mutation을 발화한 설계 자체**가 문제였다. 가드는 증상을 악화시킨 부수 효과일 뿐이다.

## 해결

"마운트 시 표시할 데이터를 가져온다"는 시맨틱은 mutation이 아니라 **query**다. POST 메서드라는 이유만으로 mutation을 고를 이유가 없다.

```tsx
export function useAdminTotpSetup() {
  return useQuery({
    queryKey: ['admin', '2fa', 'setup'],
    queryFn: () => api.post<TotpSetupResponse>('/admin/2fa/setup', undefined),
    retry: false,
    staleTime: Infinity,   // 포커스 복귀 때 시크릿이 재발급되지 않도록
  });
}
```

`useQuery`는 StrictMode의 재구독을 정상 처리하고 중복 요청도 자체 dedupe한다 → **effect도, ref 가드도 통째로 삭제**됐다. 컴포넌트는 `setup.isPending` / `setup.isError` / `setup.data`만 읽는다.

부수 효과: 등록 완료 후 `removeQueries`로 이 캐시를 지운다(QR URI에 TOTP 시크릿 원문이 들어 있어 필요 이상으로 메모리에 두지 않는다).

## 재발 방지 / 일반화

- **`useEffect` 안에서 `mutate()`를 호출하지 말 것.** 마운트 시점에 자동으로 실행돼야 하는 요청은 (HTTP 메서드와 무관하게) `useQuery`가 맞다. mutation은 "사용자 행동에 대한 응답"으로만 발화한다.
- **"pending에서 안 넘어간다"를 봤을 때의 진단 순서**: ① 백엔드를 curl로 잘라내고 ② 콘솔 raw fetch로 네트워크를 잘라낸 뒤 ③ mutationFn 안에 start/resolved 로그를 심는다. `resolved`가 찍히는데 렌더 status가 안 바뀌면 **요청 문제가 아니라 알림 유실**이고, 그 순간 이 함정을 의심한다.
- **쿠키 재현 테스트는 앱과 같은 호스트로.** `localhost`와 `127.0.0.1`은 쿠키 저장소가 별개다(포트는 무시, 호스트는 구분).
- MISTAKES.md "TanStack Query (v5)" 절에 요약 등재.
