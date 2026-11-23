// @ts-check
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import tailwindcss from '@tailwindcss/vite';
import sentry from '@sentry/astro';
import node from '@astrojs/node';

export default defineConfig({
  adapter: node({ mode: 'standalone' }),
  session: false,
  integrations: [react(), sentry(), {
    name: 'dweb-command-cache',
    hooks: {
      'astro:config:setup': ({ command, updateConfig }) => {
        // 타입 검사 임시 서버가 실행 중인 dev 의존성 캐시를 덮어쓰지 않게 분리한다.
        updateConfig({
          vite: {
            cacheDir: fileURLToPath(new URL(`./node_modules/.vite/${command}/`, import.meta.url)),
          },
        });
      },
    },
  }],
  vite: {
    plugins: [tailwindcss()],
    server: {
      strictPort: true,
    },
  },
});
