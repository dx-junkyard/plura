# PLURA 開発ガイド

## 「localhost で接続が拒否されました」(ERR_CONNECTION_REFUSED) が出たとき

**原因**: コンテナが起動していないため、どのサービスもリッスンしていません。

**対処**:

1. 初回は **イメージのビルド** に数分かかります。以下を実行し、ビルドが完了するまで待ってください。
   ```bash
   docker compose up -d
   ```
2. 起動後、**Frontend** は http://localhost:3000 、**Backend** は http://localhost:8000 でアクセスできます。
3. エラーが出る場合は **ログを確認** してください（下記「ログの確認」参照）。

※ nginx / ngrok はローカルでは使わない設定にしてあるため、`docker compose up -d` でフロント・バックエンド・DB だけが起動します。

**ポート競合する場合**: ホストで 6379 や 6333 が既に使われていると起動に失敗します。その場合は `docker-compose.yml` で Redis を `6380:6379`、Qdrant を `6335:6333` に変更してあります（コンテナ間は従来どおり 6379 / 6333 で通信）。

**会話ラリー（自然な返答）について**: AI の自然な返答は **BALANCED** モデル（`LLM_CONFIG_BALANCED`）で生成しています。`.env` で **`OPENAI_API_KEY` を設定しないと** LLM が呼べず、「記録しました。」などの短い相槌だけになります。自然な返答を出すには `.env` に `OPENAI_API_KEY=sk-...` を設定し、バックエンドを再起動してください。ログに `conversation_reply not generated` や `ConversationAgent: ...` が出る場合は API キー未設定または呼び出しエラーです。

**会話の構造（スレッド・状況ルーター）**: 会話は **スレッド**（`raw_logs.thread_id`）でまとまります。タイムラインでログを選んで「続き」で送ると、同じスレッド内の履歴だけを参照します。発話は **Situation Router**（`app/services/layer1/situation_router.py`）でコード分類（続き希望・同じ話題・話題切り替え等）され、その結果が会話エージェントに渡されます。DB に `thread_id` を追加するため、初回は **マイグレーション** を実行してください: `cd backend && alembic upgrade head`（venv 有効時）。

---

## クイックスタート

### 1. 環境変数

```bash
cp .env.example .env
# .env を編集し、OPENAI_API_KEY を設定（LLM・音声認識・Embedding に使用）
```

すでにリポジトリに `.env` がある場合は、`OPENAI_API_KEY` だけ設定すれば Docker で動かせます。

### 2. Docker Compose で起動

```bash
docker compose up -d
```

**初回はビルドに数分かかります。** 完了後は以下でアクセスできます。

- **Frontend**: http://localhost:3000  
- **Backend API**: http://localhost:8000  
- **API Docs**: http://localhost:8000/api/v1/docs  

### 3. ローカルでバックエンドのみ（Docker なし）

DB・Redis・Qdrant は Docker で起動し、アプリだけローカルで動かす例:

```bash
# インフラのみ起動
docker compose up -d postgres redis qdrant

# .env の接続先を localhost に変更
# DATABASE_URL=postgresql+asyncpg://mindyard:mindyard@localhost:5432/mindyard
# REDIS_URL=redis://localhost:6379/0
# CELERY_BROKER_URL=redis://localhost:6379/1
# CELERY_RESULT_BACKEND=redis://localhost:6379/2
# QDRANT_HOST=localhost

cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

別ターミナルで Celery Worker（精製所・構造分析の非同期処理）:

```bash
cd backend && source venv/bin/activate
celery -A app.workers.celery_app worker --loglevel=info -Q layer1,layer2,celery
```

---


## 🏗️ システムアーキテクチャ（3-Layer Architecture）

PLURAのバックエンドは、「自分だけのノートからみんなの知恵袋へ」というビジョンを実現するため、データと処理の公開度・抽象度に応じた3つのレイヤーに厳密に分割されています。

### 1. Layer 1: 思考の私有地 (Private & Conversational)
* **役割:** ユーザーがAIを壁打ち相手（Second Brain）として活用し、個人的な思考や迷いを安全に記録する層。
* **主な処理 (`app/services/layer1/`):**
    * ユーザーの意図判定（IntentRouter）、各種Nodeによる対話エージェント。
* **制約:** このレイヤーのデータ（Raw Logs）は原則として他者には公開されません。

### 2. Layer 2: 情報の関所 (Gateway & Distillation)
* **役割:** Layer 1の私的なログから「組織にとって価値のあるインサイト」を抽出し、プライバシーを保護した上で共有可能な形に変換する層。
* **主な処理 (`app/services/layer2/`):**
    * Celery タスク `process_log_for_insight` による非同期パイプライン:  
      **Privacy Sanitizer** → **Insight Distiller** → **Sharing Broker** → **InsightCard** 作成
    * 共有価値が高いと `PENDING_APPROVAL`、そうでなければ `DRAFT` となります。

### 3. Layer 3: 組織のタペストリー化 (Public & Organizational)
* **役割:** 抽出された個人の知恵を組み合わせ、組織全体の動的なアクションやルールへと昇華させる層。
* **主な処理 (`app/services/layer3/`):**
    * **Knowledge Store** (Qdrant): 共有知のベクトル保存。
    * **Serendipity Matcher**: リアルタイムな動的チーム（Flash Team）の推奨。
    * **Policy Weaver (新規追加)**: チーム解散時のログから現場の「ジレンマと決断」を抽出し、次のチームが再利用可能なルール（Governance as Code）として制度化する。


---

## ⚙️ 非同期処理とタスクキュー設計 (Celery)

PLURAでは、LLMを活用した重い推論タスクが頻発します。ユーザーのリアルタイムなチャット体験（Layer 1）を損なわないため、Celeryのタスクは**処理の重さに応じて2つのキューに厳密に分離**されています。

* **`fast_queue` (高速処理用):**
    * **用途:** 数秒〜十数秒で完了するタスク（チャットのリアルタイム応答、単発ログのメタデータ付与、即時マッチング提案など）。
    * **実装例:** `@celery_app.task(queue='fast_queue')`
* **`heavy_queue` (重負荷・バッチ処理用):**
    * **用途:** 数分以上の時間がかかる、バックグラウンドでの大規模なLLM推論タスク。
    * **該当タスク:** **Policy Weaver**による過去ログの読み込みとジレンマ抽出、バックテストシミュレーション、Deep Researchなど。
    * **実装例:** `@celery_app.task(queue='heavy_queue')`


---

## 🧠 Policy Weaver 実装におけるコア・フィロソフィー

Layer 3の中核機能である `Policy Weaver` を開発する際は、以下の「PLURA独自のガバナンス思想」を必ず遵守してください。

1.  **Heuristic First (二段階制度化):**
    いきなりシステムを強制的にブロックする Strict Policy を作らない。まずはAI Agentのシステムプロンプトとして機能する `Prompt as Code`（強制力: `Suggest` または `Warn`）として実装する。
2.  **TTL Driven (ワクチンのような新陳代謝):**
    「永遠に続くルール」は組織の硬直化を招く。すべてのPolicyには必ず `ttl_expires_at` (例: 30日後) を設け、定期的に再評価する。
3.  **Override as Fuel (逸脱を歓迎する):**
    ユーザーがルールを無視（Override）することはエラーではなく、「ルールの限界を教えてくれる貴重なフィードバック」である。Override理由を収集し、自動で境界条件をアップデートするループを回すこと。

---

## 開発の進め方（ロードマップ）

- [x] **Phase 1**: 最高の「独り言ツール」の構築  
- [ ] **Phase 2**: 「精製所」の稼働  
  - ログ作成時に `process_log_for_insight` をキューするように済済み。  
  - 残タスク例: 共有提案 UI の強化、承認フロー、Knowledge Store への投入トリガー。
- [ ] **Phase 3**: 「偶然の結合」の実現（セレンディピティマッチングの強化）

---

## ルール（CLAUDE.md より）

- **Privacy First**: Layer 2 の **Privacy Sanitizer** をバイパスするコードを入れない。
- **型の同期**: バックエンドの Pydantic を変えたら、フロントの TypeScript 型をすぐ更新する。
- **テスト**: 生ログがどう構造化されるかは `note-structurer` スキルで検証を推奨。

---

## ログの確認（エラー調査時）

| 目的 | コマンド |
|------|----------|
| 全サービスの直近ログ | `docker compose logs --tail=200` |
| バックエンドのログ（リアルタイム） | `docker compose logs -f backend` |
| フロントエンドのログ | `docker compose logs -f frontend` |
| Celery Worker のログ | `docker compose logs -f celery-worker` |
| コンテナの状態確認 | `docker compose ps -a` |

起動に失敗している場合は `docker compose ps -a` で STATUS を確認し、`Exited` や `Restarting` のサービスについて `docker compose logs <サービス名>` で原因を確認してください。

---

## よく使うコマンド

| 目的 | コマンド |
|------|----------|
| 全コンテナ起動 | `docker compose up -d` |
| 起動せずビルドのみ | `docker compose build` |
| ログ確認 | `docker compose logs -f backend` または `celery-worker` |
| DB マイグレーション | `cd backend && alembic upgrade head` |
| フロントのみ開発 | `cd frontend && npm run dev` |
