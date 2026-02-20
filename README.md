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
│   Knowledge Graph / Serendipity / Team-Up Engine            │
├─────────────────────────────────────────────────────────────┤
│                Layer 2: Gateway Refinery                     │
│                  (情報の関所)                                │
│   Privacy Sanitizer / Insight Distiller / Sharing Broker    │
├─────────────────────────────────────────────────────────────┤
│                Layer 1: Private Safehouse                    │
│                  (思考の私有地)                              │
│   ThoughtStream (Input UI) / Context Analyzer               │
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

* **ThoughtStream**: チャット形式の入力UI
* **Context Analyzer**: 感情・トピック・インテントの自動解析 `[FAST モデル]`
* ノン・ジャッジメンタル応答（受容的な相槌のみ）

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

* **Knowledge Graph Store**: ベクトル検索、意味的類似検索 `[Embeddings]`
* **Serendipity Matcher**: 入力中のリアルタイム推奨
* **Interest Overlap Detection**: 関心重複検出
* **Team-Up Suggestion Engine（予定）**: 小規模チーム自動提案
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

* **Frontend**: Next.js 14 (App Router), React, TypeScript, Tailwind CSS
* **Backend**: FastAPI, Python 3.11, SQLAlchemy
* **Database**: PostgreSQL (RDB), Qdrant (Vector DB)
* **Queue**: Celery, Redis
* **LLM**: マルチプロバイダー対応（OpenAI / Google Cloud Vertex AI）

---

## LLMアーキテクチャ

PLURAは用途に応じて最適なLLMプロバイダーとモデルを選択できるマルチプロバイダー設計を採用しています。

| 用途 | 使用箇所 | デフォルトモデル | 特徴 |
|------|----------|------------------|------|
| **FAST** | Layer 1 (Context Analyzer) | gpt-5-nano | 低レイテンシ優先、リアルタイム解析 |
| **BALANCED** | Layer 2 (Privacy Sanitizer, Insight Distiller, Sharing Broker) | gpt-5-mini | バランス重視、標準的な処理 |
| **DEEP** | Layer 2 (Structural Analyzer) | gpt-5.2 | 品質優先、深い洞察・構造化 |

プロバイダーは環境変数で柔軟に切り替え可能です（OpenAI ↔ Vertex AI）。

---

## Embeddingアーキテクチャ

ベクトル検索（Knowledge Store）で使用するEmbeddingもマルチプロバイダー対応です。

| プロバイダー | モデル | 次元数 | 特徴 |
|-------------|--------|--------|------|
| **OpenAI** | text-embedding-3-small | 1536 | 推奨、高速 |
| **OpenAI** | text-embedding-3-large | 3072 | 高精度 |
| **Vertex AI** | text-embedding-004 | 768 | Google Cloud統合 |
| **Vertex AI** | text-multilingual-embedding-002 | 768 | 多言語対応 |

---

## 開発環境のセットアップ

### 前提条件

- Docker & Docker Compose
- (オプション) OpenAI API Key

### クイックスタート

```bash
# リポジトリのクローン
git clone https://github.com/dx-junkyard/plura.git
cd plura

# 環境変数の設定
cp .env.example .env
# .env ファイルを編集し、OPENAI_API_KEY を設定

# Docker Compose で起動
docker-compose up -d

# アプリケーションにアクセス
# Frontend: http://localhost:3000
# Backend API: http://localhost:8000
# API Docs: http://localhost:8000/api/v1/docs
```

### LLMプロバイダーの設定

#### OpenAI（デフォルト）

`.env` ファイルに以下を設定：

```bash
OPENAI_API_KEY=your-openai-api-key

# 用途別モデル設定（JSON形式）
LLM_CONFIG_FAST='{"provider": "openai", "model": "gpt-5-nano"}'
LLM_CONFIG_BALANCED='{"provider": "openai", "model": "gpt-5-mini"}'
LLM_CONFIG_DEEP='{"provider": "openai", "model": "gpt-5.2"}'

# Embedding設定（JSON形式）
EMBEDDING_CONFIG='{"provider": "openai", "model": "text-embedding-3-small"}'
```

#### Google Cloud Vertex AI（Gemini）

Vertex AI を使用する場合は、以下の手順で設定してください。

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

# アプリケーション用の認証ファイル(ADC)を作成（再度URL認証が必要な場合があります）
gcloud auth application-default login

# アクセス権付与
sudo chmod -R 755 .gcp
```

**2. 環境変数の設定**

`.env` ファイルに以下を追加：

```bash
# Google Cloud 設定
GOOGLE_CLOUD_PROJECT=your-gcp-project-id

# 例: BALANCED に Gemini を使用
LLM_CONFIG_BALANCED='{"provider": "vertex", "model": "gemini-1.5-flash"}'

# 例: DEEP に Gemini Pro を使用
LLM_CONFIG_DEEP='{"provider": "vertex", "model": "gemini-1.5-pro"}'

# 例: Vertex AI Embedding を使用
EMBEDDING_CONFIG='{"provider": "vertex", "model": "text-embedding-004"}'
```

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

**利用可能なGeminiモデル（LLM）:**
- `gemini-1.5-flash` - 高速、コスト効率重視
- `gemini-1.5-pro` - 高品質、複雑なタスク向け
- `gemini-1.0-pro` - 汎用モデル

**利用可能なVertex AIモデル（Embedding）:**
- `text-embedding-004` - 推奨、768次元
- `text-embedding-005` - 最新、768次元
- `text-multilingual-embedding-002` - 多言語対応、768次元

### ローカル開発（Docker不使用）

#### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
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
| `quality-gate.yml` | `backend/` 変更を含む PR | ルールベース評価（常時）+ LLM 評価（`eval` ラベル付き PR のみ） |

### テストディレクトリ構成

```
backend/tests/
├── conftest.py               # MockLLMProvider、共通フィクスチャ
├── golden_datasets/           # Phase 1: 評価用テストケース (JSON)
│   ├── intent_router.json
│   ├── privacy_sanitizer.json
│   ├── insight_distiller.json
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
└── optimization/              # Phase 3: プロンプト自己最適化 (予定)
```

---

## 開発ロードマップ

* [x] Phase 1: 最高の「独り言ツール」の構築
* [ ] Phase 2: 精製パイプラインの安定化
* [ ] Phase 3: 構造的マッチングの実装
* [ ] Phase 4: Team-Up Suggestion Engine
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
