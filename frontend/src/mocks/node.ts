/**
 * MSW Node.js / テスト環境設定
 *
 * Vitest / Jest などのテスト環境でAPIリクエストをインターセプトします。
 * ブラウザではなく Node.js の http モジュールをインターセプトする点が browser.ts と異なります。
 *
 * 使用方法 (vitest の setup ファイルに追加):
 * ```ts
 * import { server } from '../mocks/node'
 *
 * beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
 * afterEach(() => server.resetHandlers())   // テスト固有のハンドラーをリセット
 * afterAll(() => server.close())
 * ```
 *
 * テスト内でハンドラーを上書きする例 (エラーレスポンスのテスト):
 * ```ts
 * import { http, HttpResponse } from 'msw'
 * import { server } from '../mocks/node'
 *
 * it('APIエラー時にエラーメッセージを表示する', async () => {
 *   server.use(
 *     http.get('/api/v1/logs/', () => {
 *       return HttpResponse.json({ detail: 'Internal Server Error' }, { status: 500 })
 *     })
 *   )
 *   // テストコード...
 * })
 * ```
 */
import { setupServer } from 'msw/node'
import { handlers } from './handlers'

export const server = setupServer(...handlers)
