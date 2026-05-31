// @ts-check
import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import tailwindcss from '@tailwindcss/vite';
import sentry from '@sentry/astro';

export default defineConfig({
  integrations: [react(), sentry()],
  vite: {
    plugins: [tailwindcss()],
  },
});