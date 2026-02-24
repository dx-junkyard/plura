# PLURA

**「自分だけのノートから、みんなの集合知へ。」**
そして、
**「集合知から、小さなチームへ。」**

PLURAは、個人が自分のために行う「記録（Log）」を、
安全に構造化し、
意味的に接続し、
自然なチーム形成へと導くナレッジ共創プラットフォームです。

単なる共有ではなく、
**"動ける接続"を生み出すこと**を目的としています。

---

## PLURAが解決する課題

人は毎日、価値ある思考をしている。

しかし──

* 思考は消える
* 記録は孤立する
* 共有しても動かない
* 誰と組めばいいかわからない

PLURAはこの最後の問題、
**「接続の不在」**を解決します。

---

## アーキテクチャ

### 3層構造（The 3-Layer Architecture）

```
┌─────────────────────────────────────────────────────────────┐
│                Layer 3: Public Plaza                         │
│                  (共創の広場)                                │
│   Knowledge Store / Serendipity Matcher / Policy Weaver      │
├─────────────────────────────────────────────────────────────┤
│                Layer 2: Gateway Refinery                     │
│                  (情報の関所)                                │
│   Privacy Sanitizer / Insight Distiller / Sharing Broker    │
├─────────────────────────────────────────────────────────────┤
│                Layer 1: Private Safehouse                    │
│                  (思考の私有地)                              │
│   ConversationGraph (LangGraph) / Private RAG / IntentRouter │
└─────────────────────────────────────────────────────────────┘
```

---

## 思考からチームまでの流れ

1. 個人ログを記録する（Layer 1）
2. 情報が安全に精製される（Layer 2）
3. 類似構造の思考が検出される（Layer 3）
4. 共通課題が抽出される
5. 「小さな実験チーム」が提案される

PLURAは
**偶然の一致を、意図的な連携へ変える。**

---

## 主要機能

### Layer 1: Private Safehouse（思考の私有地）

* **ThoughtStream**: チャット形式の入力UI（タイムライン・スレッド管理）
* **ConversationGraph**: LangGraph ベースの仮説駆動型ルーティング
* **IntentRouter**: 発話意図を分類（Semantic Router 統合） `[FAST モデル]`
* **SituationRouter**: 発話コンテキスト分類（続き / 話題切り替え 等）
* **ContextAnalyzer**: 感情・トピック・インテントの自動解析 `[FAST モデル]`
* **PrivateRAG**: アップロードした PDF / ドキュメントからの類似検索
* **会話ノード（9種）**: empathy / chat / brainstorm / deep\_dive / deep\_research / knowledge / research\_proposal / summarize（Map-Reduce）/ state

> ここでは評価も比較も起きない。

---

### Layer 2: Gateway Refinery（情報の関所）

* **Privacy Sanitizer**: PII除去、固有名詞の一般化 `[BALANCED モデル]`
* **Insight Distiller**: 構造化（Context / Problem / Solution） `[BALANCED モデル]`
* **Structural Analyzer**: パターン分析、仮説更新 `[DEEP モデル]`
* **Sharing Broker**: 共有価値スコアリング、承認フロー `[BALANCED モデル]`

> ここで「共有できる知」に変換される。

---

### Layer 3: Public Plaza（共創の広場）

* **Knowledge Store**: ベクトル検索、意味的類似検索 `[Embeddings]`
* **Serendipity Matcher**: 入力中のリアルタイム推奨・関心重複検出
* **Policy Weaver**: チームログから暗黙知のガバナンスルールを抽出・定着 `[DEEP モデル]`
* **Team-Up Suggestion Engine（実装中）**: 小規模チーム自動提案
* **Project Seed Generator（予定）**: 共通課題から企画を自動生成

> 共有はゴールではない。
> 接続と実験がゴール。

---

## チームアップ思想

PLURAはSNSではありません。

フォロワーも、いいねも、炎上もありません。

あるのは：

* 構造的類似
* 課題の重なり
* 行動可能性

PLURAは
**"相性の良い思考"を接続するシステムです。**

---

## 技術スタック

* **Frontend**: Next.js 14 (App Router), React, TypeScript, Tailwind CSS, Zustand, TanStack Query
* **Backend**: FastAPI, Python 3.11, SQLAlchemy, LangGraph
* **Database**: PostgreSQL (RDB), Qdrant (Vector DB)
* **Object Storage**: MinIO（PDF・ドキュメント保存）
* **Queue**: Celery, Redis
* **Audio**: OpenAI Whisper（音声認識）
* **LLM**: マルチプロバイダー対応（Google Cloud Vertex AI / OpenAI）

---

## LLMアーキテクチャ

PLURAは用途に応じて最適なLLMプロバイダーとモデルを選択できるマルチプロバイダー設計を採用しています。

| 用途 | 使用箇所 | デフォルトモデル | 特徴 |
|------|----------|------------------|------|
| **FAST** | Layer 1 (IntentRouter, ContextAnalyzer) | gemini-2.5-pro (Vertex AI) | 低レイテンシ優先、リアルタイム解析 |
| **BALANCED** | Layer 2 (Privacy Sanitizer, Insight Distiller, Sharing Broker) | gemini-2.5-flash (Vertex AI) | バランス重視、標準的な処理 |
| **DEEP** | Layer 2 (Structural Analyzer), Layer 3 (Policy Weaver) | 設定で切り替え可 | 品質優先、深い洞察・構造化 |

プロバイダーは環境変数で柔軟に切り替え可能です（Vertex AI ↔ OpenAI）。

---

## Embeddingアーキテクチャ

ベクトル検索（Knowledge Store / Private RAG）で使用するEmbeddingもマルチプロバイダー対応です。

| プロバイダー | モデル | 次元数 | 特徴 |
|-------------|--------|--------|------|
| **Vertex AI** | text-embedding-004 | 768 | デフォルト推奨、Google Cloud統合 |
| **Vertex AI** | text-embedding-005 | 768 | 最新版 |
| **Vertex AI** | text-multilingual-embedding-002 | 768 | 多言語対応 |
| **OpenAI** | text-embedding-3-small | 1536 | 高速 |
| **OpenAI** | text-embedding-3-large | 3072 | 高精度 |

---

## 開発環境のセットアップ

### 前提条件

- Docker & Docker Compose
- Google Cloud アカウント（デフォルト：Vertex AI 使用）、または OpenAI API Key

### クイックスタート

```bash
# リポジトリのクローン
git clone https://github.com/dx-junkyard/plura.git
cd plura

# 環境変数の設定
cp .env.example .env
# .env ファイルを編集（LLMプロバイダー設定を参照）

# Docker Compose で起動
docker compose up -d

# アプリケーションにアクセス
# Frontend: http://localhost:3000
# Backend API: http://localhost:8000
# API Docs: http://localhost:8000/api/v1/docs
```

### LLMプロバイダーの設定

#### Google Cloud Vertex AI（デフォルト）

**1. Google Cloud プロジェクトの準備**

```bash
# 認証情報を保存するフォルダを作成
mkdir -p .gcp

# CPUの種類に依存して、A, Bのどちらかを実行
# A. 作業用コンテナを起動（対話モード）
docker run -it --rm \
  -v "$(pwd)/.gcp:/root/.config/gcloud" \
  google/cloud-sdk:alpine \
  /bin/bash

# B. 作業用コンテナを起動（対話モード）: MacのM1/M2/M3以降
docker run -it --rm \
  --platform linux/arm64 \
  -v "$(pwd)/.gcp:/root/.config/gcloud" \
  google/cloud-sdk:alpine \
  /bin/bash

# 認証
gcloud auth login
gcloud auth application-default login

# プロジェクトの設定
gcloud config set project YOUR_PROJECT_ID

# Vertex AI API の有効化
gcloud services enable aiplatform.googleapis.com

# アプリケーション用の認証ファイル(ADC)を作成
gcloud auth application-default login

# アクセス権付与
sudo chmod -R 755 .gcp
```

**2. 環境変数の設定**

`.env` ファイルに以下を追加：

```bash
# Google Cloud 設定
GOOGLE_CLOUD_PROJECT=your-gcp-project-id

# デフォルト設定（省略可）
LLM_CONFIG_FAST='{"provider": "vertex", "model": "gemini-2.5-pro"}'
LLM_CONFIG_BALANCED='{"provider": "vertex", "model": "gemini-2.5-flash"}'

# Embedding設定（デフォルト: Vertex AI）
EMBEDDING_CONFIG='{"provider": "vertex", "model": "text-embedding-004"}'
```

**利用可能なGeminiモデル（LLM）:**
- `gemini-2.5-pro` - 高性能、推論重視
- `gemini-2.5-flash` - 高速、コスト効率重視
- `gemini-1.5-pro` - 高品質、複雑なタスク向け
- `gemini-1.5-flash` - 汎用モデル

**3. サービスアカウント認証（本番環境向け）**

```bash
# サービスアカウントの作成
gcloud iam service-accounts create plura-llm \
    --display-name="PLURA LLM Service Account"

# 必要な権限の付与
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="serviceAccount:plura-llm@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/aiplatform.user"

# キーファイルの生成
gcloud iam service-accounts keys create ./credentials.json \
    --iam-account=plura-llm@YOUR_PROJECT_ID.iam.gserviceaccount.com

# 環境変数でキーファイルを指定
export GOOGLE_APPLICATION_CREDENTIALS="./credentials.json"
```

#### OpenAI（代替）

`.env` ファイルに以下を設定：

```bash
OPENAI_API_KEY=your-openai-api-key

# 用途別モデル設定（JSON形式）
LLM_CONFIG_FAST='{"provider": "openai", "model": "gpt-4o-mini"}'
LLM_CONFIG_BALANCED='{"provider": "openai", "model": "gpt-4o-mini"}'
LLM_CONFIG_DEEP='{"provider": "openai", "model": "gpt-4o"}'

# Embedding設定
EMBEDDING_CONFIG='{"provider": "openai", "model": "text-embedding-3-small"}'
```

### ローカル開発（Docker不使用）

#### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Celery Worker（Layer 2 非同期処理）：

```bash
cd backend && source venv/bin/activate
celery -A app.workers.celery_app worker --loglevel=info -Q layer1,layer2,celery
```

#### Frontend

```bash
cd frontend
npm install
npm run dev
```

## API ドキュメント

起動後、以下のURLでAPIドキュメントにアクセスできます：

- Swagger UI: http://localhost:8000/api/v1/docs
- ReDoc: http://localhost:8000/api/v1/redoc

---

## テスト & 品質評価

PLURAは3段階の品質保証パイプラインを採用しています。

### Phase 1: ユニットテスト（Golden Dataset + Mock）

各コンポーネントに対して Golden Dataset（テストケース集）を整備し、LLM をモックした状態でロジックの正しさを検証します。

```bash
cd backend

# 全テスト実行
pytest tests/ -v

# レイヤー別実行
pytest tests/layer1/ -v   # IntentRouter
pytest tests/layer2/ -v   # PrivacySanitizer
pytest tests/layer3/ -v   # SerendipityMatcher
```

### Phase 2: LLM-as-a-Judge 自動評価

LLM を「裁判官」として、コンポーネント出力の定性的品質を 1-10 点で自動採点します。

| Evaluator | 対象 | 評価軸 |
|-----------|------|--------|
| `IntentEvaluator` | IntentRouter | intent_accuracy / confidence_calibration / probe_appropriateness |
| `PrivacyEvaluator` | PrivacySanitizer | pii_removal / context_preservation / naturalness |
| `InsightEvaluator` | InsightDistiller | structure_quality / suitability_judgment / abstraction_quality |
| `SerendipityEvaluator` | SerendipityMatcher | team_formation / role_complementarity / synergy_quality |

```bash
cd backend

# ルールベース評価（LLM不要、全PR で実行可能）
python -m tests.evaluators.run_evaluation --all

# 特定コンポーネントのみ
python -m tests.evaluators.run_evaluation --component privacy_sanitizer

# LLM Judge を使用した評価（API キーが必要）
python -m tests.evaluators.run_evaluation --component privacy_sanitizer --use-llm

# CI 用（pass_rate < 70% で非ゼロ終了コード）
python -m tests.evaluators.run_evaluation --all --ci
```

評価レポートは `backend/tests/eval_reports/` に JSON 形式で出力されます。
スコアが閾値を下回った失敗ケースは `backend/tests/optimization/failure_cases.json` に自動蓄積され、Phase 3（プロンプト自己最適化）のデータソースとなります。

### CI/CD 品質ゲート

GitHub Actions で以下の2段階チェックが走ります。

| ワークフロー | トリガー | 内容 |
|-------------|---------|------|
| `test.yml` | 全 push / PR | ユニットテスト + カバレッジ |
| `quality-gate.yml` | `backend/` 変更を含む push / PR | ルールベース評価（常時・LLM 不要） |
| `quality-gate.yml` | 手動実行（`workflow_dispatch`）+ `use_llm=true` | LLM-as-a-Judge 評価（APIコストが発生） |

### 品質評価（LLM-as-a-Judge）運用ルール

#### 目的と概要

LLM-as-a-Judge は、各コンポーネントの出力品質を LLM（Gemini / GPT等）が「裁判官」として 1〜10 点で自動採点するフレームワークです。ルールベースでは計測しにくい「自然さ」「文脈保持率」「抽象化の適切さ」といった定性的な品質を定量化できます。

#### 通常の Push / PR では LLM 評価を実行しない

LLM API の呼び出しはトークンコストが発生するため、**通常の push や Pull Request では LLM 評価を実行しません。**
`quality-gate.yml` の自動トリガーでは、常に **ルールベース評価**（`--use-llm` なし）のみが実行されます。

#### LLM 評価を実行するタイミング

以下のような場面で、手動でLLM評価を実行することを推奨します。

- `main` または `development` ブランチへのマージ前（品質最終確認）
- Layer 2（Privacy Sanitizer / Insight Distiller）のプロンプトを大幅に変更したとき
- Golden Dataset を更新・追加したとき
- 定期的な品質ベースライン確認（例: 週次）

#### GitHub リポジトリへの Secrets 登録

CI で LLM 評価を実行するには、GitHub リポジトリに API キーを Secrets として登録する必要があります。

**登録手順:**

1. GitHub リポジトリの **Settings** タブを開く
2. 左サイドバーの **Secrets and variables** → **Actions** を選択
3. **New repository secret** ボタンをクリック
4. 以下のシークレットを登録する

| Secret 名 | 値 | 必須 |
|-----------|-----|------|
| `GOOGLE_CLOUD_PROJECT` | GCP プロジェクト ID | Vertex AI を使う場合は必須 |
| `OPENAI_API_KEY` | OpenAI の API キー（`sk-...` 形式） | OpenAI を使う場合は必須 |

> **注意:** Secrets に登録した値はワークフローのログには表示されません。誤って公開しないよう、`.env` ファイルや直接コードへの記載は避けてください。
>
> Vertex AI（Gemini）を使用する場合は、サービスアカウントキーを別途 Secret（例: `GCP_SA_KEY`）として登録し、ワークフロー内で認証するよう追加設定が必要です。詳細は「LLMプロバイダーの設定」セクションを参照してください。

#### CIでの手動実行手順（GitHub Actions）

1. GitHub リポジトリの **Actions** タブを開く
2. 左サイドバーから **Quality Gate (LLM-as-a-Judge)** を選択
3. 右上の **Run workflow** ボタンをクリック
4. ブランチを選択し、**`use_llm`** のチェックボックスを **オン** にする
5. **Run workflow** を実行

> `use_llm` をオフのまま実行した場合はルールベース評価のみが走ります（コストゼロ）。

#### ローカルでの実行コマンド

```bash
cd backend

# ルールベース評価のみ（LLM 不要・コストゼロ）
python -m tests.evaluators.run_evaluation --all

# LLM Judge を使用した本格評価（APIキーが必要）
python -m tests.evaluators.run_evaluation --all --use-llm

# 特定コンポーネントのみ LLM 評価
python -m tests.evaluators.run_evaluation --component privacy_sanitizer --use-llm

# CI モード（pass_rate < 70% で非ゼロ終了コード）
python -m tests.evaluators.run_evaluation --all --use-llm --ci
```

> **注意:** `--use-llm` を指定する場合は、環境変数（`GOOGLE_CLOUD_PROJECT` または `OPENAI_API_KEY`）が正しく設定されている必要があります。

### テストディレクトリ構成

```
backend/tests/
├── conftest.py               # MockLLMProvider、共通フィクスチャ
├── golden_datasets/           # Phase 1: 評価用テストケース (JSON)
│   ├── intent_router.json
│   ├── context_analyzer.json
│   ├── privacy_sanitizer.json
│   ├── insight_distiller.json
│   ├── sharing_broker.json
│   └── serendipity_matcher.json
├── layer1/                    # Phase 1: IntentRouter 単体テスト
├── layer2/                    # Phase 1: PrivacySanitizer 単体テスト
├── layer3/                    # Phase 1: SerendipityMatcher 単体テスト
├── evaluators/                # Phase 2: LLM-as-a-Judge
│   ├── base_evaluator.py      #   評価基盤クラス
│   ├── intent_evaluator.py    #   Layer 1 評価器
│   ├── privacy_evaluator.py   #   Layer 2 評価器 (Privacy)
│   ├── insight_evaluator.py   #   Layer 2 評価器 (Insight)
│   ├── serendipity_evaluator.py # Layer 3 評価器
│   ├── run_evaluation.py      #   CLI エントリポイント
│   └── test_evaluators.py     #   Evaluator 自体のテスト
├── eval_reports/              # 評価レポート出力先 (JSON)
└── optimization/              # Phase 3: プロンプト自己最適化 (実装中)
```

---

## 開発ロードマップ

* [x] Phase 1: 最高の「独り言ツール」の構築（LangGraph 会話グラフ・Private RAG・PDF学習）
* [x] Phase 2: 精製パイプラインの実装（Privacy Sanitizer / Insight Distiller / Structural Analyzer / Sharing Broker）
* [~] Phase 3: 構造的マッチングの実装（Knowledge Store・Serendipity Matcher・Policy Weaver 実装中）
* [ ] Phase 4: Team-Up Suggestion Engine（小規模チーム自動提案の完成）
* [ ] Phase 5: 小規模プロジェクト自動生成

### 品質保証ロードマップ

* [x] Phase 1: Golden Dataset + ユニットテスト（6コンポーネント分）
* [x] Phase 2: LLM-as-a-Judge 自動評価フレームワーク
* [ ] Phase 3: プロンプト自己最適化（failure_cases → prompt_optimizer → A/B テスト）

開発の進め方・ローカル起動の詳細は **[DEVELOPMENT.md](DEVELOPMENT.md)** を参照してください。

---

## PLURAが目指す世界

* 思考は埋もれない
* 失敗は再利用される
* 偶然は設計できる
* チームは自然発生する

PLURAは
**集合知の保存装置ではない。**

**集合行動の発火装置である。**

---

## ライセンス

MIT License
