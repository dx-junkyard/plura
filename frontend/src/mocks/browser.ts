/**
 * MSW ブラウザー設定
 *
 * 開発環境でAPIリクエストをインターセプトし、モックレスポンスを返します。
 * Service Worker として動作するため、実際のネットワークリクエストを透過的にインターセプト。
 *
 * セットアップ手順:
 * 1. Service Worker ファイルを生成:
 *    $ npx msw init public/ --save
 *
 * 2. アプリのエントリポイント (app/layout.tsx or _app.tsx) でモックを起動:
 *    ```ts
 *    async function enableMocking() {
 *      if (process.env.NODE_ENV !== 'development') return
 *      const { worker } = await import('../mocks/browser')
 *      await worker.start({ onUnhandledRequest: 'bypass' })
 *    }
 *    enableMocking()
 *    ```
 */
import { setupWorker } from 'msw/browser'
import { handlers } from './handlers'

export const worker = setupWorker(...handlers)
