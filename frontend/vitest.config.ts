import { defineConfig } from 'vitest/config';

// astro check(타입)와 분리된 순수 로직 테스트. jsdom·React 플러그인 불필요 -
// lib/의 네트워크 없는 함수만 대상으로 한다(admin처럼 컴포넌트 테스트는 범위 밖).
export default defineConfig({
  test: {
    environment: 'node',
  },
});
