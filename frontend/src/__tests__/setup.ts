/**
 * Vitest グローバルセットアップ
 *
 * 全テストスイートで MSW サーバーを起動し、
 * API モックが有効な状態でテストを実行できるようにする。
 */
import '@testing-library/jest-dom'
import { afterAll, afterEach, beforeAll } from 'vitest'
import { server } from '../mocks/node'

// テストスイート開始時に MSW サーバーを起動
// onUnhandledRequest: 'error' → 未定義のリクエストはエラーにして見落としを防ぐ
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))

// 各テスト後にハンドラーをリセット（テスト固有の上書きをクリア）
afterEach(() => server.resetHandlers())

// テストスイート終了時にサーバーを停止
afterAll(() => server.close())
