# TROUBLESHOOTING - eslint react-refresh가 TanStack 파일 라우트를 막음

대상: admin (Vite React SPA), B7 골격
관련 구현: `IMPLEMENTATION_VITE_SPA_SCAFFOLD.md` (Caution #2)

## 증상

`npm run lint`(eslint)가 모든 라우트 파일에서 실패:

```
src/routes/index.tsx
  7:10  error  Fast refresh only works when a file only exports components.
               Move your component(s) to a separate file...
               react-refresh/only-export-components
```

- 빌드(`tsc + vite build`)와 런타임은 정상. lint만 error.
- 룰이 error 레벨이라 exit 1 → F1 CI 차단.

## 환경

- `eslint-plugin-react-refresh` (Vite React 스캐폴딩 기본 포함)
- `@tanstack/react-router` 파일 기반 라우팅 (`src/routes/*.tsx`)
- 라우트 파일 구조: `export const Route = createFileRoute(...)({ component: Home })` + 로컬 `function Home`

## 원인

react-refresh 룰은 "파일이 export하는 건 전부 컴포넌트여야 하고, 컴포넌트는 export돼 있어야 한다"를 강제한다 (HMR 상태 보존 전제). 룰 소스는 식별자를 분류한다:

- `nonComponentExports`: export된 비컴포넌트 (예: `Route`)
- `localComponents`: 컴포넌트인데 export 안 됨 (예: `Home`)

판정: 파일에 export가 있고(`hasExports`) → 비컴포넌트 export가 있으면 (A) 그걸 걸고, 없으면 로컬 컴포넌트가 있을 때 (B) 그걸 건다.

라우트 파일은 `Route`(비컴포넌트 export) + `Home`(로컬 컴포넌트)를 둘 다 가져서 구조적으로 이 룰에 걸린다.

## 시도와 실패: `allowExportNames: ['Route']`

직관적 수정은 `Route`를 예외 처리하는 것:

```js
'react-refresh/only-export-components': ['error', { allowExportNames: ['Route'] }]
```

→ **안 통한다.** `allowExportNames`는 분류 단계에서 그 이름만 skip할 뿐이다. `Route`가 `nonComponentExports`에서 빠지면 (A)는 통과하지만, `Home`이 여전히 `localComponents`에 남아 (B)로 걸린다. 에러 위치가 `Route` → `Home`으로 옮겨갈 뿐 사라지지 않는다. (`eslint --print-config`로 옵션 적용은 확인되나 에러는 지속)

## 해결

`src/routes/**`에 한해 룰 off:

```js
// eslint.config.js
{
  files: ['src/routes/**/*.{ts,tsx}'],
  rules: { 'react-refresh/only-export-components': 'off' },
}
```

정당성: 룰이 막으려는 실제 피해(편집 시 풀 리로드 → 상태 소실)는, 라우트 파일 HMR을 `@tanstack/router-plugin`이 따로 처리하므로 발생하지 않는다. 룰은 라우터 플러그인의 HMR 처리를 모르는 AST 휴리스틱이라 false positive를 낸 것. `components/**` 등 일반 컴포넌트엔 룰을 그대로 살려둔다.

## 재발 방지 / 일반화

- 같은 충돌이 React Router/Remix(`loader`/`action`/`meta` export), 상수+컴포넌트 동거 파일에서도 난다.
- 프레임워크가 강제하는 비컴포넌트 export는 `allowExportNames`로 면제하되, 그 파일에 export 안 된 로컬 컴포넌트가 남으면 그것까지 해결해야 한다(export하거나 디렉터리 단위 off).
