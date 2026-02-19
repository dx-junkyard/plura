import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  test: {
    // jsdom でブラウザ環境をシミュレート
    environment: 'jsdom',
    // テスト実行前に MSW サーバーを起動するセットアップファイル
    setupFiles: ['./src/__tests__/setup.ts'],
    // グローバル (describe, it, expect) を自動インポート
    globals: true,
    // カバレッジ設定
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'lcov'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/**/*.d.ts',
        'src/mocks/**',
        'src/__tests__/**',
        'src/app/**', // Next.js App Router はコンポーネントテストで個別に扱う
      ],
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
})
