import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// vite.config.ts와 분리: 테스트는 tanstackRouter 플러그인(라우트 트리 생성)·tailwind가
// 필요 없고, 그 둘이 테스트 실행마다 routeTree.gen.ts를 다시 쓰는 부작용을 피한다.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
  },
})
