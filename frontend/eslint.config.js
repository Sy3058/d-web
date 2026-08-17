import js from '@eslint/js'
import globals from 'globals'
import astro from 'eslint-plugin-astro'
import reactHooks from 'eslint-plugin-react-hooks'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist', '.astro', 'coverage']),
  {
    // Astro preset이 아래에서 최종 parser를 astro-eslint-parser로 덮고,
    // parserOptions.parser로 TypeScript parser를 사용한다. 여기서는 frontmatter에도
    // 일반 JS/TS와 React Hooks 규칙이 적용되도록 .astro를 함께 포함한다.
    files: ['**/*.{astro,js,jsx,mjs,ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
    ],
    languageOptions: {
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
  },
  ...astro.configs.recommended,
  {
    files: ['**/*.astro'],
    languageOptions: {
      parserOptions: {
        parser: tseslint.parser,
      },
    },
  },
  {
    files: ['src/env.d.ts'],
    rules: {
      // Astro가 생성하는 타입 선언을 연결하는 공식 triple-slash 엔트리다.
      '@typescript-eslint/triple-slash-reference': 'off',
    },
  },
])
