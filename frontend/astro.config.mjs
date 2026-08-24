// @ts-check
import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import tailwindcss from '@tailwindcss/vite';
import sentry from '@sentry/astro';
import node from '@astrojs/node';

export default defineConfig({
  adapter: node({ mode: 'standalone' }),
  session: false,
  integrations: [react(), sentry()],
  vite: {
    plugins: [tailwindcss()],
  },
});
