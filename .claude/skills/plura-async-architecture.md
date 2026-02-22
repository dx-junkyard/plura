# 📂 `.claude/skills/plura-async-architecture.md`

## 概要
PLURAの非同期タスク（Celery）およびLLM呼び出しに関するアーキテクチャガイドライン。

## ⚙️ キューの分離原則 (Queue Separation)
重負荷なタスクによってユーザー体験（チャットの即時応答など）が阻害されることを防ぐため、タスクは必ず以下の2つのキューのいずれかに明示的にルーティングすること。

1. `fast_queue` (worker-fast):
   - **対象:** チャットのリアルタイム応答、単発のタグ付け、SerendipityMatcherによる即時マッチング提案など、数十秒以内で完了するタスク。
   - **実装:** `@celery_app.task(queue='fast_queue')`
2. `heavy_queue` (worker-heavy):
   - **対象:** Policy Weaverの抽出処理、過去ログ全体のバックテスト、TTL監視と再評価など、数分以上かかるバッチ的な重負荷LLMタスク。
   - **実装:** `@celery_app.task(queue='heavy_queue')`

## 🛡️ LLMタスク実装のベストプラクティス
- **タイムアウトとリトライ:** `heavy_queue` のLLM呼び出し（Google GenAI / OpenAI）はAPIのRate Limitや長時間の推論待ちが発生しやすいため、適切な `retry_backoff` とエラーハンドリング（`try-except`）を実装すること。
- **ステートレス性の維持:** Celeryワーカー内で状態を持たず、必要なデータはすべて引数で受け取るか、タスク内でDBから取得すること。
