import { createRootRoute, Outlet } from '@tanstack/react-router'
import { TanStackRouterDevtools } from '@tanstack/react-router-devtools'

export const Route = createRootRoute({
  component: RootLayout,
})

function RootLayout() {
  return (
    <>
      <Outlet />
      {/* 라우트 디버깅용. 프로덕션 번들에서는 자동 제외됨 */}
      <TanStackRouterDevtools />
    </>
  )
}
